#!/usr/bin/env python3
"""
run_eval.py - Run semantic equivalence evaluation across all workspaces with per-workspace time profiling.

Usage:
    python run_eval.py [--workspace NAME] [--api-url URL]

Discovers every workspace under evaluation/, runs SemanticEquivalenceEvaluator, and
prints a time-profile table when done.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any lightrag imports so env vars are in place.
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

from lightrag.evaluation.semantic_equivalence_evaluator import SemanticEquivalenceEvaluator
from lightrag.utils import logger

EVAL_DIR = PROJECT_ROOT / "evaluation"
RESULTS_DIR = EVAL_DIR / "results"


def discover_workspaces() -> list[str]:
    """Return workspace names that have a dataset.json under evaluation/."""
    return sorted(
        p.parent.name
        for p in EVAL_DIR.glob("*/dataset.json")
    )


async def run_workspace(
    workspace: str,
    api_url: str,
) -> tuple[str, dict, float]:
    """
    Run evaluation for one workspace.

    Returns (workspace, summary_dict, elapsed_seconds).
    """
    dataset_path = EVAL_DIR / workspace / "dataset.json"

    evaluator = SemanticEquivalenceEvaluator(
        workspace=workspace,
        test_dataset_path=str(dataset_path),
        rag_api_url=api_url,
    )

    t0 = time.perf_counter()
    summary = await evaluator.run()
    elapsed = time.perf_counter() - t0

    return workspace, summary, elapsed


def print_timing_report(timing_rows: list[tuple[str, float, int, int]]) -> None:
    """Pretty-print the per-workspace timing table."""
    header = f"\n{'=' * 90}"
    header += "\nEVALUATION TIME PROFILE"
    header += f"\n{'=' * 90}"
    header += f"\n  {'Workspace':<40} {'Tests':>5}  {'Failed':>6}  {'Elapsed':>10}  {'Avg/Test':>10}"
    header += f"\n  {'-' * 40}  {'-' * 5}  {'-' * 6}  {'-' * 10}  {'-' * 10}"

    rows = []
    total_elapsed = 0.0
    total_tests = 0
    total_failed = 0

    for workspace, elapsed, tests, failed in timing_rows:
        avg = elapsed / tests if tests > 0 else 0.0
        rows.append(
            f"  {workspace:<40} {tests:>5}  {failed:>6}  {elapsed:>9.2f}s  {avg:>9.2f}s"
        )
        total_elapsed += elapsed
        total_tests += tests
        total_failed += failed

    total_avg = total_elapsed / total_tests if total_tests > 0 else 0.0
    footer = f"\n  {'─' * 40}  {'─' * 5}  {'─' * 6}  {'─' * 10}  {'─' * 10}"
    footer += f"\n  {'TOTAL':<40} {total_tests:>5}  {total_failed:>6}  {total_elapsed:>9.2f}s  {total_avg:>9.2f}s"
    footer += f"\n{'=' * 90}"

    logger.info(header + "\n" + "\n".join(rows) + footer)


async def main(workspaces: list[str], api_url: str) -> None:
    timing_rows: list[tuple[str, float, int, int]] = []
    all_summaries: dict[str, dict] = {}

    for workspace in workspaces:
        logger.info(f"\n{'─' * 60}")
        logger.info(f"Evaluating workspace: {workspace}")
        logger.info(f"{'─' * 60}")

        try:
            ws, summary, elapsed = await run_workspace(workspace, api_url)

            stats = summary.get("statistics", {})
            tests = stats.get("total_tests", 0)
            failed = stats.get("failed_tests", 0)

            timing_rows.append((workspace, elapsed, tests, failed))
            all_summaries[workspace] = summary

        except Exception as exc:
            logger.error(f"Workspace {workspace} failed: {exc}")
            timing_rows.append((workspace, 0.0, 0, 0))
            all_summaries[workspace] = {"error": str(exc)}

    # Print timing profile
    print_timing_report(timing_rows)

    # Save aggregate summary
    agg_path = RESULTS_DIR / f"aggregate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    with agg_path.open("w") as fh:
        json.dump(
            {
                "run_at": datetime.now().isoformat(),
                "api_url": api_url,
                "workspaces": [
                    {
                        "workspace": ws,
                        "elapsed_s": round(el, 2),
                        "tests": t,
                        "failed": f,
                        "avg_per_test_s": round(el / t, 2) if t > 0 else 0.0,
                    }
                    for ws, el, t, f in timing_rows
                ],
                "summaries": all_summaries,
            },
            fh,
            indent=2,
        )
    logger.info(f"\nAggregate results saved → {agg_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run semantic equivalence evaluation across workspaces with time profiling.",
    )
    parser.add_argument(
        "--workspace",
        metavar="NAME",
        help="Evaluate a single workspace (default: all).",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:9621",
        help="LightRAG API base URL (default: http://localhost:9621).",
    )
    args = parser.parse_args()

    if args.workspace:
        workspaces = [args.workspace]
    else:
        workspaces = discover_workspaces()
        if not workspaces:
            logger.error(f"No dataset.json files found under {EVAL_DIR}")
            sys.exit(1)
        logger.info(f"Discovered {len(workspaces)} workspace(s): {', '.join(workspaces)}")

    asyncio.run(main(workspaces, args.api_url))
