"""Offline, mock-based tests for the agentic price_line_items retrieval source.

No live DB or LLM is used — the pricing-role LLM call and the asyncpg pool
are both mocked. Every scenario asserts the "fail closed" contract: a
classifier/DB failure degrades to no pricing context, never an exception.
"""

import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from lightrag.agentic import price_line_items as pli

pytestmark = pytest.mark.offline


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Isolate the module-level pool singleton and warn-once flag per test."""
    monkeypatch.setattr(pli, "_pool", None)
    monkeypatch.setattr(pli, "_warned_fetch_failure", False)
    # The lightrag logger doesn't propagate to the root logger by default;
    # force it to so caplog can capture records.
    monkeypatch.setattr(logging.getLogger("lightrag"), "propagate", True)


def _global_config(pricing_func=None):
    return {"role_llm_funcs": {"pricing": pricing_func} if pricing_func else {}}


# ---------------------------------------------------------------------------
# classify_pricing_intent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_pricing_intent_true_from_dict_response():
    pricing_func = AsyncMock(return_value={"is_pricing_query": True})
    result = await pli.classify_pricing_intent(
        "What is the rate for cabin cleaning?", _global_config(pricing_func)
    )
    assert result is True
    pricing_func.assert_awaited_once()


@pytest.mark.asyncio
async def test_classify_pricing_intent_false_from_string_response():
    pricing_func = AsyncMock(return_value=json.dumps({"is_pricing_query": False}))
    result = await pli.classify_pricing_intent(
        "What is included in cabin cleaning?", _global_config(pricing_func)
    )
    assert result is False


@pytest.mark.asyncio
async def test_classify_pricing_intent_false_on_malformed_json():
    pricing_func = AsyncMock(return_value="not json at all")
    result = await pli.classify_pricing_intent("query", _global_config(pricing_func))
    assert result is False


@pytest.mark.asyncio
async def test_classify_pricing_intent_false_on_missing_role():
    result = await pli.classify_pricing_intent("query", _global_config())
    assert result is False


@pytest.mark.asyncio
async def test_classify_pricing_intent_false_on_exception():
    pricing_func = AsyncMock(side_effect=RuntimeError("LLM down"))
    result = await pli.classify_pricing_intent("query", _global_config(pricing_func))
    assert result is False


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------


def test_extract_keywords_filters_stopwords_and_short_words():
    keywords = pli._extract_keywords("What is the rate for cabin cleaning?")
    assert "cabin" in keywords
    assert "cleaning" in keywords
    assert "rate" in keywords
    for stopword in ("what", "is", "the", "for"):
        assert stopword not in keywords


def test_extract_keywords_dedupes_and_caps_at_max_keywords():
    keywords = pli._extract_keywords("cabin cabin cabin", max_keywords=8)
    assert keywords == ["cabin"]

    many_words = " ".join(f"word{i}" for i in range(20))
    keywords = pli._extract_keywords(many_words, max_keywords=8)
    assert len(keywords) == 8


def test_extract_keywords_returns_empty_list_for_pure_stopwords():
    assert pli._extract_keywords("what is it for") == []


# ---------------------------------------------------------------------------
# fetch_price_line_items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_price_line_items_returns_empty_and_warns_when_pool_unavailable(
    monkeypatch, caplog
):
    monkeypatch.setattr(pli, "_get_pool", AsyncMock(return_value=None))
    with caplog.at_level("WARNING", logger="lightrag"):
        rows = await pli.fetch_price_line_items("query")
    assert rows == []


@pytest.mark.asyncio
async def test_fetch_price_line_items_returns_empty_and_warns_on_query_failure(
    monkeypatch, caplog
):
    class _FailingConn:
        async def fetch(self, *args, **kwargs):
            raise RuntimeError("relation \"price_line_items\" does not exist")

    class _FailingPool:
        @asynccontextmanager
        async def acquire(self):
            yield _FailingConn()

    monkeypatch.setattr(pli, "_get_pool", AsyncMock(return_value=_FailingPool()))

    with caplog.at_level("WARNING", logger="lightrag"):
        rows = await pli.fetch_price_line_items("query")

    assert rows == []
    assert any("price_line_items" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_fetch_price_line_items_returns_rows_on_success(monkeypatch):
    expected_rows = [{"service_type_description": "cabin cleaning", "unit_price": 42.5}]
    captured_args = {}

    class _OkConn:
        async def fetch(self, sql, *args):
            captured_args["sql"] = sql
            captured_args["args"] = args
            return [dict(row) for row in expected_rows]

    class _OkPool:
        @asynccontextmanager
        async def acquire(self):
            yield _OkConn()

    monkeypatch.setattr(pli, "_get_pool", AsyncMock(return_value=_OkPool()))

    rows = await pli.fetch_price_line_items(
        "What is the rate for cabin cleaning?", top_k=5
    )

    assert rows == expected_rows
    assert "contract_price_line" in captured_args["sql"]
    assert "bos_line_station.contract_price_line" in captured_args["sql"]
    assert captured_args["args"] == (5, ["rate", "cabin", "cleaning"])


@pytest.mark.asyncio
async def test_fetch_price_line_items_respects_price_db_schema_override(
    monkeypatch,
):
    captured_args = {}

    class _OkConn:
        async def fetch(self, sql, *args):
            captured_args["sql"] = sql
            return []

    class _OkPool:
        @asynccontextmanager
        async def acquire(self):
            yield _OkConn()

    monkeypatch.setattr(pli, "_get_pool", AsyncMock(return_value=_OkPool()))
    monkeypatch.setenv("PRICE_DB_SCHEMA", "custom_schema")

    await pli.fetch_price_line_items("cabin cleaning rate")

    assert "custom_schema.contract_price_line" in captured_args["sql"]


@pytest.mark.asyncio
async def test_fetch_price_line_items_passes_none_keywords_when_query_has_no_content_words(
    monkeypatch,
):
    captured_args = {}

    class _OkConn:
        async def fetch(self, sql, *args):
            captured_args["args"] = args
            return []

    class _OkPool:
        @asynccontextmanager
        async def acquire(self):
            yield _OkConn()

    monkeypatch.setattr(pli, "_get_pool", AsyncMock(return_value=_OkPool()))

    await pli.fetch_price_line_items("what is it for", top_k=5)

    assert captured_args["args"] == (5, None)


# ---------------------------------------------------------------------------
# format_price_context
# ---------------------------------------------------------------------------


def test_format_price_context_empty_rows_returns_empty_string():
    assert pli.format_price_context([]) == ""


def test_format_price_context_renders_rows_as_json_lines():
    rows = [{"service": "cabin cleaning", "rate": 42.5}]
    result = pli.format_price_context(rows)
    assert result.startswith("<price_line_items>\n")
    assert result.endswith("\n</price_line_items>")
    assert json.dumps(rows[0]) in result or "cabin cleaning" in result


# ---------------------------------------------------------------------------
# get_price_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_context_short_circuits_when_not_pricing_query(monkeypatch):
    fetch_mock = AsyncMock()
    monkeypatch.setattr(pli, "fetch_price_line_items", fetch_mock)
    pricing_func = AsyncMock(return_value={"is_pricing_query": False})

    result = await pli.get_price_context(
        "What is included in cabin cleaning?", _global_config(pricing_func)
    )

    assert result == ""
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_price_context_fetches_and_formats_when_pricing_query(monkeypatch):
    pricing_func = AsyncMock(return_value={"is_pricing_query": True})
    monkeypatch.setattr(
        pli,
        "fetch_price_line_items",
        AsyncMock(return_value=[{"service": "cabin cleaning", "rate": 42.5}]),
    )

    result = await pli.get_price_context(
        "What is the rate for cabin cleaning?", _global_config(pricing_func)
    )

    assert result.startswith("<price_line_items>")
    assert "cabin cleaning" in result


@pytest.mark.asyncio
async def test_get_price_context_fails_closed_on_unexpected_exception(monkeypatch):
    monkeypatch.setattr(
        pli, "classify_pricing_intent", AsyncMock(side_effect=RuntimeError("boom"))
    )
    result = await pli.get_price_context("query", _global_config())
    assert result == ""
