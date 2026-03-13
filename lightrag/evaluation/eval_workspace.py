#!/usr/bin/env python3
"""
Workspace-Aware RAGAS Evaluation Script

This is the main entry point for running RAGAS evaluations with workspace support.
Supports multiple query modes including temporal, and can evaluate across workspaces.

Usage:
    # Evaluate default workspace with standard mode (mix)
    python -m lightrag.evaluation.eval_workspace

    # Evaluate specific workspace with temporal mode
    python -m lightrag.evaluation.eval_workspace --workspace contracts --mode temporal

    # Evaluate with specific reference date for temporal queries
    python -m lightrag.evaluation.eval_workspace --mode temporal --reference-date 2024-01-15

    # Evaluate all workspaces
    python -m lightrag.evaluation.eval_workspace --all-workspaces

    # List available workspaces
    python -m lightrag.evaluation.eval_workspace --list-workspaces
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lightrag.evaluation.base_evaluator import (
    RAGAS_AVAILABLE,
    BaseRAGEvaluator,
    _is_nan,
)
from lightrag.utils import logger

if RAGAS_AVAILABLE:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )


class StandardRAGEvaluator(BaseRAGEvaluator):
    """
    Standard RAGAS evaluator for non-temporal query modes.

    Supports: naive, local, global, hybrid, mix, bypass
    """

    async def evaluate_single_case(
        self,
        idx: int,
        test_case: Dict[str, Any],
        client,
        **kwargs,
    ) -> Dict[str, Any]:
        """Evaluate a single test case with standard RAGAS metrics."""
        question = test_case["question"]
        ground_truth = test_case["ground_truth"]

        try:
            # Generate RAG response
            rag_response = await self.generate_rag_response(
                question=question,
                client=client,
                mode=self.query_mode,
            )
        except Exception as e:
            logger.error(f"Error generating response for test {idx}: {str(e)}")
            return {
                "test_number": idx,
                "question": question,
                "mode": self.query_mode,
                "error": str(e),
                "metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }

        # Get retrieved contexts
        retrieved_contexts = rag_response["contexts"]

        # Prepare dataset for RAGAS evaluation
        eval_dataset = Dataset.from_dict(
            {
                "question": [question],
                "answer": [rag_response["answer"]],
                "contexts": [retrieved_contexts],
                "ground_truth": [ground_truth],
            }
        )

        try:
            # Run RAGAS evaluation
            eval_results = evaluate(
                dataset=eval_dataset,
                metrics=[
                    Faithfulness(),
                    AnswerRelevancy(),
                    ContextRecall(),
                    ContextPrecision(),
                ],
                llm=self.eval_llm,
                embeddings=self.eval_embeddings,
            )

            df = eval_results.to_pandas()
            scores_row = df.iloc[0]

            # Extract metrics
            metrics = {
                "faithfulness": float(scores_row.get("faithfulness", 0)),
                "answer_relevance": float(scores_row.get("answer_relevancy", 0)),
                "context_recall": float(scores_row.get("context_recall", 0)),
                "context_precision": float(scores_row.get("context_precision", 0)),
            }

            # Calculate RAGAS score
            valid_metrics = [v for v in metrics.values() if not _is_nan(v)]
            ragas_score = (
                sum(valid_metrics) / len(valid_metrics) if valid_metrics else 0
            )

            return {
                "test_number": idx,
                "question": question,
                "mode": self.query_mode,
                "answer": rag_response["answer"][:200] + "..."
                if len(rag_response["answer"]) > 200
                else rag_response["answer"],
                "ground_truth": ground_truth[:200] + "..."
                if len(ground_truth) > 200
                else ground_truth,
                "project": test_case.get("project", "unknown"),
                "metrics": metrics,
                "ragas_score": round(ragas_score, 4),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error evaluating test {idx}: {str(e)}")
            return {
                "test_number": idx,
                "question": question,
                "mode": self.query_mode,
                "error": str(e),
                "metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }


def list_workspaces() -> List[str]:
    """List all available workspaces with evaluation datasets."""
    datasets_dir = Path(__file__).parent / "datasets"

    if not datasets_dir.exists():
        logger.info("No datasets directory found.")
        return []

    workspaces = []
    for item in datasets_dir.iterdir():
        if item.is_dir():
            dataset_file = item / "evaluation_dataset.json"
            if dataset_file.exists():
                try:
                    with open(dataset_file) as f:
                        data = json.load(f)
                    test_count = len(data.get("test_cases", []))
                    eval_type = data.get("evaluation_type", "standard")
                    description = data.get("description", "")
                    workspaces.append(
                        {
                            "name": item.name,
                            "test_cases": test_count,
                            "type": eval_type,
                            "description": description[:50] + "..."
                            if len(description) > 50
                            else description,
                        }
                    )
                except Exception as e:
                    workspaces.append(
                        {
                            "name": item.name,
                            "test_cases": "?",
                            "type": "error",
                            "description": str(e)[:50],
                        }
                    )

    return workspaces


def print_workspaces(workspaces: List[Dict[str, Any]]):
    """Print available workspaces in a formatted table."""
    if not workspaces:
        logger.info("No workspaces with evaluation datasets found.")
        logger.info("")
        logger.info("To create a workspace dataset:")
        logger.info(
            "  1. Create directory: lightrag/evaluation/datasets/{workspace_name}/"
        )
        logger.info("  2. Add evaluation_dataset.json with test_cases array")
        return

    logger.info("")
    logger.info("=" * 80)
    logger.info("📁 Available Workspaces for Evaluation")
    logger.info("=" * 80)
    logger.info(f"{'Workspace':<20} {'Tests':<8} {'Type':<12} {'Description'}")
    logger.info("-" * 80)

    for ws in workspaces:
        logger.info(
            f"{ws['name']:<20} {ws['test_cases']:<8} {ws['type']:<12} {ws['description']}"
        )

    logger.info("=" * 80)
    logger.info("")


async def run_evaluation(
    workspace: str = "default",
    mode: str = "mix",
    dataset_path: Optional[str] = None,
    rag_api_url: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run evaluation for a single workspace.

    Args:
        workspace: Workspace name
        mode: Query mode (naive, local, global, hybrid, mix, temporal, bypass)
        dataset_path: Optional custom dataset path
        rag_api_url: Optional custom RAG API URL
        reference_date: Reference date for temporal queries

    Returns:
        Evaluation results dictionary
    """
    if mode == "temporal":
        from lightrag.evaluation.temporal_evaluator import TemporalRAGEvaluator

        evaluator = TemporalRAGEvaluator(
            workspace=workspace,
            test_dataset_path=dataset_path,
            rag_api_url=rag_api_url,
            default_reference_date=reference_date,
        )
    else:
        evaluator = StandardRAGEvaluator(
            workspace=workspace,
            test_dataset_path=dataset_path,
            rag_api_url=rag_api_url,
            query_mode=mode,
        )

    return await evaluator.run()


async def run_all_workspaces(
    mode: str = "mix",
    rag_api_url: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run evaluation for all discovered workspaces.

    Returns:
        Dictionary with results for each workspace
    """
    workspaces = list_workspaces()

    if not workspaces:
        logger.error("No workspaces found to evaluate.")
        return {}

    all_results = {}

    for ws in workspaces:
        workspace_name = ws["name"]
        logger.info(f"\n{'=' * 70}")
        logger.info(f"🔄 Evaluating workspace: {workspace_name}")
        logger.info(f"{'=' * 70}")

        try:
            results = await run_evaluation(
                workspace=workspace_name,
                mode=mode,
                rag_api_url=rag_api_url,
                reference_date=reference_date,
            )
            all_results[workspace_name] = results
        except Exception as e:
            logger.error(f"Failed to evaluate workspace {workspace_name}: {e}")
            all_results[workspace_name] = {"error": str(e)}

    # Save aggregate results
    aggregate_dir = Path(__file__).parent / "results" / "aggregate"
    aggregate_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    aggregate_path = aggregate_dir / f"aggregate_{mode}_{timestamp}.json"

    with open(aggregate_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
                "reference_date": reference_date,
                "workspaces_evaluated": [ws["name"] for ws in workspaces],
                "results": all_results,
            },
            f,
            indent=2,
        )

    logger.info(f"\n📁 Aggregate results saved to: {aggregate_path}")

    # Print summary comparison
    _print_workspace_comparison(all_results)

    return all_results


def _print_workspace_comparison(all_results: Dict[str, Any]):
    """Print a comparison table of results across workspaces."""
    logger.info("")
    logger.info("=" * 90)
    logger.info("📊 Cross-Workspace Comparison")
    logger.info("=" * 90)
    logger.info(
        f"{'Workspace':<20} {'Tests':<8} {'Success%':<10} "
        f"{'Faith':<8} {'AnswRel':<8} {'CtxRec':<8} {'RAGAS':<8}"
    )
    logger.info("-" * 90)

    for workspace, results in all_results.items():
        if "error" in results:
            logger.info(f"{workspace:<20} ERROR: {results['error'][:50]}")
            continue

        stats = results.get("benchmark_stats", {})
        avg = stats.get("average_metrics", {})

        logger.info(
            f"{workspace:<20} "
            f"{stats.get('total_tests', 0):<8} "
            f"{stats.get('success_rate', 0):<10.1f} "
            f"{avg.get('faithfulness', 0):<8.4f} "
            f"{avg.get('answer_relevance', 0):<8.4f} "
            f"{avg.get('context_recall', 0):<8.4f} "
            f"{avg.get('ragas_score', 0):<8.4f}"
        )

    logger.info("=" * 90)


async def main():
    """Main entry point for workspace evaluation."""
    parser = argparse.ArgumentParser(
        description="Workspace-Aware RAGAS Evaluation for LightRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available workspaces
  python -m lightrag.evaluation.eval_workspace --list-workspaces

  # Evaluate default workspace with mix mode
  python -m lightrag.evaluation.eval_workspace

  # Evaluate specific workspace with temporal mode
  python -m lightrag.evaluation.eval_workspace --workspace contracts --mode temporal

  # Evaluate with reference date
  python -m lightrag.evaluation.eval_workspace --mode temporal --reference-date 2024-01-15

  # Evaluate all workspaces
  python -m lightrag.evaluation.eval_workspace --all-workspaces --mode temporal

  # Custom dataset and endpoint
  python -m lightrag.evaluation.eval_workspace -d my_dataset.json -r http://localhost:9621
        """,
    )

    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default="default",
        help="Workspace name to evaluate (default: default)",
    )

    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        default="mix",
        choices=["naive", "local", "global", "hybrid", "mix", "temporal", "bypass"],
        help="Query mode for evaluation (default: mix)",
    )

    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        default=None,
        help="Path to custom test dataset JSON file",
    )

    parser.add_argument(
        "--ragendpoint",
        "-r",
        type=str,
        default=None,
        help="LightRAG API endpoint URL",
    )

    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        help="Reference date for temporal queries (YYYY-MM-DD format)",
    )

    parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Evaluate all discovered workspaces",
    )

    parser.add_argument(
        "--list-workspaces",
        action="store_true",
        help="List available workspaces and exit",
    )

    args = parser.parse_args()

    # List workspaces doesn't require RAGAS
    if args.list_workspaces:
        workspaces = list_workspaces()
        print_workspaces(workspaces)
        return

    # Check RAGAS availability for actual evaluation
    if not RAGAS_AVAILABLE:
        logger.error(
            "RAGAS dependencies not installed.\n"
            "Install with: pip install -e '.[evaluation]'"
        )
        sys.exit(1)

    try:
        if args.all_workspaces:
            await run_all_workspaces(
                mode=args.mode,
                rag_api_url=args.ragendpoint,
                reference_date=args.reference_date,
            )
        else:
            await run_evaluation(
                workspace=args.workspace,
                mode=args.mode,
                dataset_path=args.dataset,
                rag_api_url=args.ragendpoint,
                reference_date=args.reference_date,
            )

    except KeyboardInterrupt:
        logger.info("\nEvaluation cancelled by user.")
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
