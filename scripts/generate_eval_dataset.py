#!/usr/bin/env python3
"""Generate evaluation datasets for LightRAG workspaces.

For each workspace, reads all processed documents ordered by sequence_index
(latest first = PRIMARY), calls the configured LLM to generate 10-15 Q&A
pairs, and writes the result to evaluation/{workspace}/dataset.json.

Usage:
    # Single workspace
    python scripts/generate_eval_dataset.py --workspace ams_ground_handling_cw76193

    # All workspaces
    python scripts/generate_eval_dataset.py --all

    # Custom options
    python scripts/generate_eval_dataset.py --all --count 12 --reference-date 2026-04-07

See docs/EVALUATION_GUIDE.md § "Generating Evaluation Datasets" for full documentation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = PROJECT_ROOT / "inputs"
DATA_DIR = PROJECT_ROOT / "data"

# Max chars of combined document text sent to the LLM.
# Documents are included latest-first; earlier docs are truncated first when
# this limit is reached.
DEFAULT_MAX_CHARS = 120_000

# ---------------------------------------------------------------------------
# Config & LLM client (mirrors lightrag/functions.py)
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """Load .env into os.environ and validate required keys."""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)

    required = ["LLM_BINDING_HOST", "LLM_BINDING_API_KEY", "LLM_MODEL"]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    if missing:
        logger.error(
            "Missing required environment variables: %s\n"
            "Ensure your .env file is configured (see docs/EVALUATION_GUIDE.md).",
            ", ".join(missing),
        )
        sys.exit(1)


def _make_extra_body() -> dict:
    return {"extra_body": {"trace_data": {"session_id": str(uuid4())}}}


async def _call_llm(prompt: str, system_prompt: str) -> str:
    """Call the LLM using the same auth/transport pattern as lightrag/functions.py."""
    # Import here so env vars are loaded first
    from lightrag.llm.openai import openai_complete_if_cache
    from lightrag.tools.kong_api_client.kong_client import KongClient

    kong_client = KongClient(
        region_name="us-east-1",
        user_secret_manager_name="bos-line-stations-proxy-service-api-key",
    )
    http_client = httpx.AsyncClient(http2=True, verify=False)

    return await openai_complete_if_cache(
        os.getenv("LLM_MODEL"),
        prompt,
        system_prompt=system_prompt,
        api_key=os.getenv("LLM_BINDING_API_KEY"),
        base_url=os.getenv("LLM_BINDING_HOST"),
        extra_headers={"Authorization": f"Bearer {kong_client.generate_token()}"},
        extra_body=_make_extra_body(),
        openai_client_configs={"http_client": http_client},
    )


# ---------------------------------------------------------------------------
# Document loading
# ---------------------------------------------------------------------------


def _load_doc_status(workspace: str) -> list[dict]:
    """Return processed docs for *workspace* sorted by sequence_index descending."""
    status_path = DATA_DIR / workspace / "kv_store_doc_status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"Doc status file not found: {status_path}")

    with status_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    docs = []
    for doc_id, entry in raw.items():
        if doc_id.startswith("__"):
            continue
        if entry.get("status") != "processed":
            continue
        seq = entry.get("metadata", {}).get("sequence_index")
        if seq is None:
            continue
        file_path = entry.get("file_path", "")
        docs.append(
            {
                "doc_id": doc_id,
                "sequence_index": seq,
                "file_path": file_path,
                "content_summary": entry.get("content_summary", ""),
            }
        )

    # Latest first (highest sequence_index = most recent amendment)
    docs.sort(key=lambda d: d["sequence_index"], reverse=True)
    return docs


def _read_doc_content(file_path: str, workspace: str) -> str:
    """Read markdown content for a document.

    file_path may be project-relative.  When the stored path doesn't exist
    (e.g. the directory name was truncated when the graph was built), fall
    back to looking for the same filename inside inputs/{workspace}/.
    """
    p = Path(file_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p

    if not p.exists():
        # Fallback: same filename under the workspace's own inputs directory
        fallback = INPUTS_DIR / workspace / p.name
        if fallback.exists():
            p = fallback
        else:
            logger.warning("Document file not found, skipping: %s", p)
            return ""

    return p.read_text(encoding="utf-8")


def _build_combined_context(docs: list[dict], workspace: str, max_chars: int) -> str:
    """
    Concatenate document texts latest-first.

    The first document is labelled PRIMARY; subsequent ones are labelled
    FALLBACK.  If combined content would exceed *max_chars*, earlier
    (lower sequence_index) documents are dropped first with a warning.
    """
    sections: list[str] = []
    total = 0
    primary_used = False

    for doc in docs:
        content = _read_doc_content(doc["file_path"], workspace)
        if not content:
            continue

        label = (
            f"PRIMARY (sequence {doc['sequence_index']})"
            if not primary_used
            else f"FALLBACK (sequence {doc['sequence_index']})"
        )
        primary_used = True
        header = (
            f"\n{'=' * 70}\n"
            f"--- Document [{label}]: {Path(doc['file_path']).name} ---\n"
            f"{'=' * 70}\n"
        )
        block = header + content

        if total + len(block) > max_chars:
            logger.warning(
                "Combined document content would exceed %d chars. "
                "Stopping at sequence_index %d. "
                "Increase --max-chars to include earlier documents.",
                max_chars,
                doc["sequence_index"],
            )
            break

        sections.append(block)
        total += len(block)

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# LLM question generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are generating evaluation test cases for a Retrieval-Augmented Generation \
(RAG) chatbot used by airline line station managers.

You will receive the text of one or more service-contract documents for an \
airline ground-handling or cabin-cleaning workspace.  When multiple documents \
are provided:
- The document labelled PRIMARY is the most recent and authoritative version.
- Documents labelled FALLBACK contain earlier versions or baseline contracts; \
use them ONLY when a piece of information is absent from the PRIMARY document.

PERSONA: A line station manager asks the chatbot practical, day-to-day \
operational questions — the same questions they would ask a colleague or \
look up before approving an invoice, staffing a shift, or briefing a vendor. \
They do NOT quote exhibit numbers, amendment titles, or legal clauses in their \
questions.  They use plain language and operational shorthand.

Examples of the tone and style to match:
- "What do we pay G2 for a cleaning agent per hour at SEA?"
- "When did the new rates kick in for Swissport at AMS?"
- "How many FTEs should be on the floor for a 7-day SEA cabin cleaning rotation?"
- "What's the cancellation charge if we cancel a turn within 2 hours of arrival?"
- "What's the current de-icing rate at YYZ?"
- "Who do I contact at the vendor if there's a dispute?"

Guidelines:
- Every question must sound like a manager typing into a chat box — short, \
direct, first-person or imperative where natural.
- Cover diverse operational topics: current rates/wages, staffing levels, \
aircraft-type-specific charges, effective dates of the latest amendment, \
penalty/cancellation clauses, vendor contact details, service scope, and \
payment terms.
- Questions must be answerable from the supplied documents.
- Ground truth answers must be precise (exact dollar/euro/percentage amounts, \
dates, names, thresholds) — state the answer as the chatbot would reply.
- Each question must target a distinct fact — do not duplicate.
- Prefer facts that changed between amendment versions, as those are the \
hardest for the RAG system to answer correctly.

Output ONLY a valid JSON array — no markdown fences, no commentary — \
with exactly the number of objects requested.  Each object must have:
  {
    "question": "<conversational manager question>",
    "ground_truth": "<complete, precise answer as the chatbot would give it>",
    "category": "<one of: pricing | rates | dates | parties | services | terms | amendments | other>",
    "entity_type": "<specific entity, e.g. service_rate | hourly_rate | aircraft_type | effective_date>"
  }
"""

_USER_PROMPT_TEMPLATE = """\
Generate exactly {count} question-answer pairs for the workspace \
"{workspace}" based on the following contract documents.

{context}

Return ONLY a JSON array with {count} objects as described in the system prompt.
"""


async def _generate_questions(
    workspace: str,
    context: str,
    count: int,
) -> list[dict]:
    """Call the LLM and return parsed question dicts."""
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        count=count,
        workspace=workspace,
        context=context,
    )

    logger.info("  Calling LLM (model=%s) …", os.getenv("LLM_MODEL"))
    raw = await _call_llm(user_prompt, _SYSTEM_PROMPT)

    # The LLM may return a JSON object wrapping the array, or a bare array.
    # Normalise both.
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Try stripping markdown fences if present
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(
                f"LLM returned non-JSON content for workspace '{workspace}': {raw[:500]}"
            ) from exc

    if isinstance(parsed, dict):
        # Unwrap {"test_cases": [...]} or {"questions": [...]} or similar
        for key in ("test_cases", "questions", "items", "results"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            # Try first list value
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
            else:
                parsed = [parsed]

    if not isinstance(parsed, list):
        raise ValueError(
            f"Expected a JSON array from LLM for workspace '{workspace}', "
            f"got {type(parsed).__name__}"
        )

    return parsed


# ---------------------------------------------------------------------------
# Dataset assembly & writing
# ---------------------------------------------------------------------------


def _build_dataset(
    workspace: str,
    questions: list[dict],
    reference_date: str,
) -> dict:
    """Assemble the full dataset.json structure."""
    test_cases = []
    for i, q in enumerate(questions, start=1):
        test_cases.append(
            {
                "id": f"{workspace}_{i:03d}",
                "question": q.get("question", ""),
                "ground_truth": q.get("ground_truth", ""),
                "reference_date": reference_date,
                "workspace": workspace,
                "metadata": {
                    "category": q.get("category", "other"),
                    "entity_type": q.get("entity_type", "unknown"),
                },
            }
        )

    return {
        "workspace": workspace,
        "evaluation_type": "temporal",
        "description": f"Temporal evaluation dataset for {workspace} service contracts",
        "created_at": f"{reference_date}T00:00:00Z",
        "documentation": {
            "reference_date": "Date used to filter versioned entities. Format: YYYY-MM-DD",
            "expected_version": "Expected sequence_index of the correct entity version (optional)",
            "metadata.entity_type": "Type of entity being queried (e.g., service_rate, pricing)",
        },
        "test_cases": test_cases,
    }


def _write_dataset(output_dir: Path, workspace: str, dataset: dict) -> Path:
    """Write dataset.json to evaluation/{workspace}/dataset.json."""
    dest = output_dir / workspace / "dataset.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        json.dump(dataset, fh, indent=2, ensure_ascii=False)
    return dest


# ---------------------------------------------------------------------------
# Per-workspace orchestration
# ---------------------------------------------------------------------------


async def _process_workspace(
    workspace: str,
    output_dir: Path,
    reference_date: str,
    count: int,
    max_chars: int,
) -> bool:
    """Generate and write dataset for one workspace.  Returns True on success."""
    logger.info("Processing workspace: %s", workspace)

    # 1. Load doc ordering
    try:
        docs = _load_doc_status(workspace)
    except FileNotFoundError as exc:
        logger.error("  %s", exc)
        return False

    if not docs:
        logger.warning("  No processed documents found — skipping.")
        return False

    logger.info(
        "  Found %d processed document(s); latest sequence_index=%d",
        len(docs),
        docs[0]["sequence_index"],
    )

    # 2. Build combined context (latest first)
    context = _build_combined_context(docs, workspace, max_chars)
    if not context.strip():
        logger.error("  No readable document content found — skipping.")
        return False

    # 3. Generate questions
    try:
        questions = await _generate_questions(workspace, context, count)
    except Exception as exc:
        logger.error("  LLM call failed: %s", exc)
        return False

    if not questions:
        logger.error("  LLM returned 0 questions — skipping.")
        return False

    if len(questions) != count:
        logger.warning(
            "  Requested %d questions but LLM returned %d; proceeding with %d.",
            count,
            len(questions),
            len(questions),
        )

    # 4. Assemble and write
    dataset = _build_dataset(workspace, questions, reference_date)
    dest = _write_dataset(output_dir, workspace, dataset)
    logger.info(
        "  Written %d test cases → %s",
        len(dataset["test_cases"]),
        dest.relative_to(PROJECT_ROOT),
    )
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _discover_workspaces() -> list[str]:
    """Return all workspace directory names under inputs/."""
    if not INPUTS_DIR.is_dir():
        logger.error("inputs/ directory not found at %s", INPUTS_DIR)
        sys.exit(1)
    return sorted(p.name for p in INPUTS_DIR.iterdir() if p.is_dir())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate evaluation Q&A datasets for LightRAG workspaces.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--workspace",
        metavar="NAME",
        help="Process a single workspace (directory name under inputs/).",
    )
    scope.add_argument(
        "--all",
        action="store_true",
        help="Process all workspaces discovered under inputs/ (default when neither flag is given).",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        metavar="N",
        help="Number of Q&A pairs to generate per workspace (10-15, default: 12).",
    )
    parser.add_argument(
        "--reference-date",
        default=str(date.today()),
        metavar="YYYY-MM-DD",
        help="Reference date embedded in every test case (default: today).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "evaluation"),
        metavar="PATH",
        help="Root output directory (default: evaluation/).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        metavar="N",
        help=f"Max combined characters of document text sent to LLM (default: {DEFAULT_MAX_CHARS:,}).",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    # Validate count
    if not (10 <= args.count <= 15):
        logger.error("--count must be between 10 and 15; got %d", args.count)
        sys.exit(1)

    output_dir = Path(args.output_dir)

    # Determine workspaces to process
    if args.workspace:
        workspaces = [args.workspace]
    else:
        workspaces = _discover_workspaces()
        logger.info("Discovered %d workspace(s).", len(workspaces))

    results: dict[str, list[str]] = {"success": [], "failed": []}
    for ws in workspaces:
        ok = await _process_workspace(
            workspace=ws,
            output_dir=output_dir,
            reference_date=args.reference_date,
            count=args.count,
            max_chars=args.max_chars,
        )
        (results["success"] if ok else results["failed"]).append(ws)

    # Summary
    print(
        f"\nDone: {len(results['success'])} succeeded, {len(results['failed'])} failed."
    )
    if results["failed"]:
        print("Failed workspaces:", ", ".join(results["failed"]))
        sys.exit(1)


def main() -> None:
    args = _parse_args()
    _load_env()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
