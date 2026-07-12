"""Agentic pricing retrieval: `contract_price_line` PostgreSQL lookup.

Real schema (confirmed against a live dev instance):

    <schema>.contract_price_line(
        id, contract_id, service_type_id, service_variant_id,
        aircraft_group_id, price_effective_date, price_end_date,
        unit_price, currency, raw_service_description, raw_aircraft_type,
        active
    )
    <schema>.contract(
        id, contract_number, contract_title, contract_type, vendor_id,
        station_code, effective_start_date, effective_end_date, active,
        raw_json
    )
    <schema>.service_type(id, code, description)
    <schema>.service_variant(id, service_type_id, code, description)
    <schema>.aircraft_group(id, code, display_name, body_category)

`<schema>` defaults to ``bos_line_station`` and is configurable via
`PRICE_DB_SCHEMA` for other environments/deployments. `fetch_price_line_items`
joins the lookup tables and matches free-text keywords extracted from `query`
against the description/raw-text columns (see `_extract_keywords`), keeping
only currently-active/effective rows and the most recent matches first.

Each LightRAG workspace in this fork is provisioned for exactly one contract,
and its workspace name follows the convention
``<station_code>_<service_line>_<contract_number>`` (e.g.
``sea_cabin_cleaning_cw54832``). `_parse_workspace_filters` recovers the
three identifiers from `global_config["workspace"]` by splitting on "_": the
first token is the station code, the last token is the contract number
(not always numeric — e.g. ``fra_ground_handling_cw``,
``yyz_deicing_unk``), and everything in between is the service line
(matches `service_type.code`, e.g. "cabin_cleaning"). `fetch_price_line_items`
uses these as a hard pre-filter (joined via `contract`/`service_type`)
before ranking by keyword match, so a query only ever surfaces price lines
from its own contract/service line — never another station's or another
line-of-business's pricing. When the workspace name doesn't follow the
convention (fewer than two tokens, or empty), all three come back `None`
and the filter is skipped (falls back to the prior unscoped, keyword-only
behavior) rather than failing the query.

This module intentionally does NOT touch `lightrag.kg.postgres_impl`'s
`ClientManager` — that manager owns LightRAG's own storage tables and has
side effects (`initdb()` / `check_tables()`) specific to those tables. The
pricing tables live in a separate, independent database, so this module owns
its own minimal `asyncpg` pool.

Connection details (host/database/user/password) are never hardcoded here —
they are supplied via the `PRICE_DB_*` environment variables (see
env.example) and must be kept out of version control.

Every public function here fails closed: any exception (classifier LLM
failure, DB/table not provisioned, malformed response, etc.) results in the
feature no-op'ing (``False`` / ``[]`` / ``""``), never raising into the
caller's query path.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import json_repair

from lightrag.prompt import PROMPTS
from lightrag.utils import get_env_value, logger

PRICE_DB_DEFAULT_SCHEMA = "bos_line_station"

# Common short/filler words excluded from keyword-based ILIKE matching so a
# single stopword (e.g. "the", "for") doesn't wildcard-match every row.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "for", "to", "in", "on", "at", "by", "with", "and", "or", "but",
    "what", "which", "who", "whom", "how", "when", "where", "why",
    "do", "does", "did", "can", "could", "would", "should", "will",
    "this", "that", "these", "those", "it", "its", "as", "if", "than",
}

_pool: Any = None
_pool_lock = asyncio.Lock()
_warned_fetch_failure = False


def _parse_workspace_filters(
    workspace: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Recover (station_code, service_line_code, contract_number) from `workspace`.

    Convention: ``<station>_<service_line...>_<contract_number>``. The first
    token is the station code, the last token is the contract number (not
    always numeric — e.g. "cw", "unk"), and everything in between (joined
    back with "_") is the service line code (matches `service_type.code`,
    e.g. "cabin_cleaning").

    Returns `(None, None, None)` when `workspace` is empty or has fewer than
    two "_"-separated tokens — callers should treat that as "not parseable"
    and skip the contract-scoped filter rather than fail the query.
    """
    if not workspace:
        return None, None, None

    tokens = workspace.split("_")
    if len(tokens) < 2:
        return None, None, None

    station_code = tokens[0]
    contract_number = tokens[-1]
    service_line_code = "_".join(tokens[1:-1]) or None
    return station_code, service_line_code, contract_number


def _extract_keywords(query: str, max_keywords: int = 8) -> list[str]:
    """Extract de-duplicated, lowercased content words from `query`.

    Used to build a lightweight ILIKE-based match against the pricing
    tables' free-text columns. Returns [] if `query` has no content words
    (e.g. pure stopwords) — callers should treat that as "no filter".
    """
    words = re.findall(r"[A-Za-z0-9]+", query.lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for word in words:
        if len(word) > 2 and word not in _STOPWORDS and word not in seen:
            seen.add(word)
            keywords.append(word)
        if len(keywords) >= max_keywords:
            break
    return keywords


async def _get_pool() -> Any:
    """Lazily build (and cache) the dedicated asyncpg pool for the price DB.

    Independent of `lightrag.kg.postgres_impl.ClientManager` — separate
    database, separate connection params, no `initdb()`/`check_tables()`.
    Returns None if `asyncpg` is not installed or the pool cannot be built,
    so callers can fail closed without crashing the query path.
    """
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        try:
            import asyncpg
        except ImportError:
            logger.warning(
                "[price_line_items] asyncpg is not installed; pricing lookups disabled"
            )
            return None

        host = get_env_value("PRICE_DB_HOST", None, str, special_none=True)
        database = get_env_value("PRICE_DB_DATABASE", None, str, special_none=True)
        if not host or not database:
            logger.warning(
                "[price_line_items] PRICE_DB_HOST/PRICE_DB_DATABASE not configured; "
                "pricing lookups disabled"
            )
            return None

        try:
            _pool = await asyncpg.create_pool(
                host=host,
                port=get_env_value("PRICE_DB_PORT", 5432, int),
                user=get_env_value("PRICE_DB_USER", None, str, special_none=True),
                password=get_env_value(
                    "PRICE_DB_PASSWORD", None, str, special_none=True
                ),
                database=database,
                max_size=get_env_value("PRICE_DB_MAX_CONNECTIONS", 10, int),
            )
        except Exception as e:
            logger.warning(f"[price_line_items] Failed to create connection pool: {e}")
            _pool = None
            return None

    return _pool


async def classify_pricing_intent(query: str, global_config: dict) -> bool:
    """Return True when `query` is asking about rates/prices/costs/fees.

    Uses the ``pricing`` role LLM func. Fails closed to False on any
    exception (LLM failure, malformed JSON, missing role func, etc.) so a
    classifier problem never blocks normal retrieval.
    """
    try:
        role_llm_funcs = global_config.get("role_llm_funcs") or {}
        pricing_func = role_llm_funcs.get("pricing")
        if pricing_func is None:
            return False

        prompt = PROMPTS["pricing_intent_classify"].format(query=query)
        result = await pricing_func(prompt, response_format={"type": "json_object"})

        if isinstance(result, dict):
            payload = result
        elif isinstance(result, str):
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                payload = json_repair.loads(result)
        else:
            return False

        if not isinstance(payload, dict):
            return False

        return bool(payload.get("is_pricing_query", False))
    except Exception as e:
        logger.warning(f"[price_line_items] Pricing intent classification failed: {e}")
        return False


async def fetch_price_line_items(
    query: str, top_k: int = 5, workspace: str | None = None
) -> list[dict]:
    """Fetch candidate contract price-line rows matching `query`.

    Joins `contract_price_line` with `service_type`, `service_variant`,
    `aircraft_group`, and `contract`; keeps only active, currently-effective
    rows. When `workspace` parses into (station_code, service_line,
    contract_number) (see `_parse_workspace_filters`), those are applied as
    a hard pre-filter via the `contract`/`service_type` join — so a query
    only ever surfaces price lines from its own contract/service line, never
    another station's or line-of-business's pricing. When `workspace` is
    None/unparseable, no such filter is applied (unscoped, matching prior
    behavior).

    Within whatever scope results from that pre-filter, rows are further
    ranked by keywords extracted from `query` against the description/raw-
    text columns. If no content keywords are found in `query`, no text
    filter is applied (falls back to most-recent active rows within scope).
    Rows are ranked by number of matching keywords first (so e.g. a query
    naming both an aircraft type and a service variant surfaces the row
    matching both, ahead of unrelated rows that only match one generic
    keyword), then by effective date (most recent first).

    Returns [] on any error (unprovisioned table/DB, connection failure,
    etc.) so a missing/incomplete price DB never breaks a query.
    """
    global _warned_fetch_failure

    try:
        pool = await _get_pool()
        if pool is None:
            return []

        schema = get_env_value("PRICE_DB_SCHEMA", PRICE_DB_DEFAULT_SCHEMA, str)
        keywords = _extract_keywords(query) or None
        station_code, service_line_code, contract_number = _parse_workspace_filters(
            workspace
        )

        sql = f"""
            SELECT
                cpl.id,
                cpl.contract_id,
                c.contract_number,
                c.station_code AS contract_station_code,
                st.code AS service_type_code,
                st.description AS service_type_description,
                sv.code AS service_variant_code,
                sv.description AS service_variant_description,
                ag.code AS aircraft_group_code,
                ag.display_name AS aircraft_group_display_name,
                ag.body_category AS aircraft_body_category,
                cpl.price_effective_date,
                cpl.price_end_date,
                cpl.unit_price,
                cpl.currency,
                cpl.raw_service_description,
                cpl.raw_aircraft_type
            FROM {schema}.contract_price_line cpl
            LEFT JOIN {schema}.service_type st ON st.id = cpl.service_type_id
            LEFT JOIN {schema}.service_variant sv ON sv.id = cpl.service_variant_id
            LEFT JOIN {schema}.aircraft_group ag ON ag.id = cpl.aircraft_group_id
            LEFT JOIN {schema}.contract c ON c.id = cpl.contract_id
            WHERE cpl.active = true
              AND cpl.price_effective_date <= now()
              AND (cpl.price_end_date IS NULL OR cpl.price_end_date >= now())
              AND ($3::text IS NULL OR c.station_code ILIKE $3)
              AND ($4::text IS NULL OR c.contract_number ILIKE $4)
              AND ($5::text IS NULL OR st.code ILIKE $5)
              AND (
                    $2::text[] IS NULL
                    OR EXISTS (
                        SELECT 1 FROM unnest($2::text[]) AS kw
                        WHERE cpl.raw_service_description ILIKE '%' || kw || '%'
                           OR st.description ILIKE '%' || kw || '%'
                           OR sv.description ILIKE '%' || kw || '%'
                           OR cpl.raw_aircraft_type ILIKE '%' || kw || '%'
                           OR ag.display_name ILIKE '%' || kw || '%'
                    )
              )
            ORDER BY (
                CASE WHEN $2::text[] IS NULL THEN 0 ELSE (
                    SELECT count(*) FROM unnest($2::text[]) AS kw
                    WHERE cpl.raw_service_description ILIKE '%' || kw || '%'
                       OR st.description ILIKE '%' || kw || '%'
                       OR sv.description ILIKE '%' || kw || '%'
                       OR cpl.raw_aircraft_type ILIKE '%' || kw || '%'
                       OR ag.display_name ILIKE '%' || kw || '%'
                )
                END
            ) DESC, cpl.price_effective_date DESC
            LIMIT $1
        """  # noqa: S608 - schema/table names from constant/env config, not user input

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                sql, top_k, keywords, station_code, contract_number, service_line_code
            )
        return [dict(row) for row in rows]
    except Exception as e:
        if not _warned_fetch_failure:
            logger.warning(
                f"[price_line_items] Fetch failed (table/DB may not be provisioned "
                f"yet, or schema mismatch): {e}"
            )
            _warned_fetch_failure = True
        return []


def format_price_context(rows: list[dict]) -> str:
    """Render `rows` as a `<price_line_items>` JSON-lines block.

    Returns "" when `rows` is empty (nothing to inject).
    """
    if not rows:
        return ""

    lines = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    return f"<price_line_items>\n{lines}\n</price_line_items>"


async def get_price_context(query: str, global_config: dict) -> str:
    """Orchestrate classify -> fetch -> format for a single query.

    Returns "" early (fetch/format never called) when `query` is not a
    pricing question. Wrapped in a top-level try/except so this feature can
    never break the main query path.
    """
    try:
        is_pricing_query = await classify_pricing_intent(query, global_config)
        if not is_pricing_query:
            return ""

        rows = await fetch_price_line_items(query, workspace=global_config.get("workspace"))
        return format_price_context(rows)
    except Exception as e:
        logger.warning(f"[price_line_items] get_price_context failed: {e}")
        return ""
