#!/usr/bin/env python3
"""
Temporal RAGAS Evaluator for Versioned Entity Queries

This module extends the base evaluator with temporal-specific functionality:
- Version accuracy metrics
- Reference date filtering evaluation
- Sequence index tracking
- Temporal precision metrics

Usage:
    from lightrag.evaluation.temporal_evaluator import TemporalRAGEvaluator

    evaluator = TemporalRAGEvaluator(
        workspace="contracts_2024",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()

    # Or with per-test-case reference dates in dataset
    # Just set mode="temporal" and include reference_date in each test case
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from lightrag.utils import logger

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lightrag.evaluation.base_evaluator import (
    RAGAS_AVAILABLE,
    BaseRAGEvaluator,
    _is_nan,
)

if RAGAS_AVAILABLE:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )


class TemporalRAGEvaluator(BaseRAGEvaluator):
    """
    Evaluator for temporal/versioned entity queries.

    Extends BaseRAGEvaluator with:
    - Temporal-specific metrics (version accuracy, temporal precision)
    - Reference date handling
    - Version tracking in results
    """

    def __init__(
        self,
        workspace: str = "default",
        test_dataset_path: Optional[str] = None,
        rag_api_url: Optional[str] = None,
        default_reference_date: Optional[str] = None,
        track_versions: bool = True,
    ):
        """
        Initialize the temporal evaluator.

        Args:
            workspace: Workspace name for data isolation
            test_dataset_path: Path to test dataset JSON file
            rag_api_url: LightRAG API endpoint URL
            default_reference_date: Default reference date for temporal queries
                                   (YYYY-MM-DD format, used when test case doesn't specify)
            track_versions: Whether to track and report version information
        """
        super().__init__(
            workspace=workspace,
            test_dataset_path=test_dataset_path,
            rag_api_url=rag_api_url,
            query_mode="temporal",
        )

        self.default_reference_date = default_reference_date or os.getenv(
            "EVAL_DEFAULT_REFERENCE_DATE", datetime.now().strftime("%Y-%m-%d")
        )
        self.track_versions = track_versions

        logger.info(f"  • Default Reference Date: {self.default_reference_date}")
        logger.info(f"  • Track Versions:         {self.track_versions}")

    async def evaluate_single_case(
        self,
        idx: int,
        test_case: Dict[str, Any],
        client,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Evaluate a single temporal test case.

        This method:
        1. Queries with temporal mode and reference_date
        2. Runs standard RAGAS metrics
        3. Calculates temporal-specific metrics
        4. Tracks version information
        """
        question = test_case["question"]
        ground_truth = test_case["ground_truth"]

        # Get reference date from test case or use default
        reference_date = test_case.get("reference_date", self.default_reference_date)
        expected_version = test_case.get("expected_version")

        try:
            # Generate RAG response with temporal mode
            rag_response = await self.generate_rag_response(
                question=question,
                client=client,
                mode="temporal",
                reference_date=reference_date,
            )
        except Exception as e:
            logger.error(f"Error generating response for test {idx}: {str(e)}")
            return {
                "test_number": idx,
                "question": question,
                "reference_date": reference_date,
                "error": str(e),
                "metrics": {},
                "temporal_metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }

        # Get retrieved contexts
        retrieved_contexts = rag_response["contexts"]
        version_info = rag_response.get("version_info", [])

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

            # Standard RAGAS metrics
            metrics = {
                "faithfulness": float(scores_row.get("faithfulness", 0)),
                "answer_relevance": float(scores_row.get("answer_relevancy", 0)),
                "context_recall": float(scores_row.get("context_recall", 0)),
                "context_precision": float(scores_row.get("context_precision", 0)),
            }

            # Calculate temporal-specific metrics
            temporal_metrics = self._calculate_temporal_metrics(
                version_info=version_info,
                expected_version=expected_version,
                reference_date=reference_date,
            )

            # Calculate combined RAGAS score
            valid_metrics = [v for v in metrics.values() if not _is_nan(v)]
            ragas_score = (
                sum(valid_metrics) / len(valid_metrics) if valid_metrics else 0
            )

            result = {
                "test_number": idx,
                "question": question,
                "reference_date": reference_date,
                "expected_version": expected_version,
                "mode": "temporal",
                "answer": rag_response["answer"][:200] + "..."
                if len(rag_response["answer"]) > 200
                else rag_response["answer"],
                "ground_truth": ground_truth[:200] + "..."
                if len(ground_truth) > 200
                else ground_truth,
                "metrics": metrics,
                "temporal_metrics": temporal_metrics,
                "ragas_score": round(ragas_score, 4),
                "timestamp": datetime.now().isoformat(),
            }

            # Add version info if tracking enabled
            if self.track_versions and version_info:
                result["retrieved_versions"] = version_info

            return result

        except Exception as e:
            logger.error(f"Error evaluating test {idx}: {str(e)}")
            return {
                "test_number": idx,
                "question": question,
                "reference_date": reference_date,
                "error": str(e),
                "metrics": {},
                "temporal_metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }

    def _calculate_temporal_metrics(
        self,
        version_info: List[Dict[str, Any]],
        expected_version: Optional[int],
        reference_date: str,
    ) -> Dict[str, Any]:
        """
        Calculate temporal-specific metrics.

        Metrics calculated:
        - version_accuracy: Did we retrieve the expected version? (0 or 1)
        - temporal_precision: Percentage of retrieved chunks with valid effective_date
        - sequence_consistency: Are versions properly ordered by sequence_index?
        - max_retrieved_version: Highest sequence_index in retrieved results
        """
        if not version_info:
            return {
                "version_accuracy": None,
                "temporal_precision": None,
                "sequence_consistency": None,
                "max_retrieved_version": None,
            }

        # Extract sequence indices
        sequence_indices = [
            v.get("sequence_index")
            for v in version_info
            if v.get("sequence_index") is not None
        ]

        # Extract effective dates
        effective_dates = [
            v.get("effective_date") for v in version_info if v.get("effective_date")
        ]

        # Calculate version accuracy (if expected_version provided)
        version_accuracy = None
        if expected_version is not None and sequence_indices:
            max_retrieved = max(sequence_indices)
            version_accuracy = 1.0 if max_retrieved == expected_version else 0.0

        # Calculate temporal precision
        # (percentage of chunks with effective_date <= reference_date)
        temporal_precision = None
        if effective_dates and reference_date:
            valid_dates = sum(
                1 for ed in effective_dates if ed and ed <= reference_date
            )
            temporal_precision = valid_dates / len(effective_dates)

        # Calculate sequence consistency
        # (are the retrieved versions in expected order?)
        sequence_consistency = None
        if len(sequence_indices) > 1:
            # Check if all unique - if so, they should be sorted
            sorted_indices = sorted(sequence_indices, reverse=True)
            sequence_consistency = 1.0 if sequence_indices == sorted_indices else 0.0

        # Get max retrieved version
        max_retrieved_version = max(sequence_indices) if sequence_indices else None

        return {
            "version_accuracy": version_accuracy,
            "temporal_precision": temporal_precision,
            "sequence_consistency": sequence_consistency,
            "max_retrieved_version": max_retrieved_version,
        }

    def _calculate_benchmark_stats(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate benchmark statistics including temporal metrics.
        """
        # Get base stats
        base_stats = super()._calculate_benchmark_stats(results)

        # Calculate temporal-specific averages
        valid_results = [r for r in results if r.get("temporal_metrics")]

        if not valid_results:
            base_stats["temporal_metrics"] = {
                "avg_version_accuracy": None,
                "avg_temporal_precision": None,
                "avg_sequence_consistency": None,
            }
            return base_stats

        temporal_data = {
            "version_accuracy": {"sum": 0.0, "count": 0},
            "temporal_precision": {"sum": 0.0, "count": 0},
            "sequence_consistency": {"sum": 0.0, "count": 0},
        }

        for result in valid_results:
            tm = result.get("temporal_metrics", {})

            for metric_name, data in temporal_data.items():
                value = tm.get(metric_name)
                if value is not None and not _is_nan(value):
                    data["sum"] += value
                    data["count"] += 1

        avg_temporal = {}
        for metric_name, data in temporal_data.items():
            if data["count"] > 0:
                avg_temporal[f"avg_{metric_name}"] = round(
                    data["sum"] / data["count"], 4
                )
            else:
                avg_temporal[f"avg_{metric_name}"] = None

        base_stats["temporal_metrics"] = avg_temporal
        return base_stats

    def _print_summary(
        self,
        results: List[Dict[str, Any]],
        benchmark_stats: Dict[str, Any],
        elapsed_time: float,
        json_path,
        csv_path,
    ):
        """Print evaluation summary including temporal metrics."""
        super()._print_summary(
            results, benchmark_stats, elapsed_time, json_path, csv_path
        )

        # Add temporal metrics summary
        temporal = benchmark_stats.get("temporal_metrics", {})
        if any(v is not None for v in temporal.values()):
            logger.info("")
            logger.info("⏱️ TEMPORAL METRICS (Average)")
            logger.info("-" * 70)

            if temporal.get("avg_version_accuracy") is not None:
                logger.info(
                    f"Version Accuracy:     {temporal['avg_version_accuracy']:.4f}"
                )

            if temporal.get("avg_temporal_precision") is not None:
                logger.info(
                    f"Temporal Precision:   {temporal['avg_temporal_precision']:.4f}"
                )

            if temporal.get("avg_sequence_consistency") is not None:
                logger.info(
                    f"Sequence Consistency: {temporal['avg_sequence_consistency']:.4f}"
                )

            logger.info("=" * 70)


class WorkspaceEvaluator:
    """
    Utility class to evaluate across multiple workspaces.

    Usage:
        evaluator = WorkspaceEvaluator()
        results = await evaluator.evaluate_all_workspaces()
    """

    def __init__(
        self,
        workspaces: Optional[List[str]] = None,
        rag_api_url: Optional[str] = None,
        mode: str = "temporal",
    ):
        """
        Initialize workspace evaluator.

        Args:
            workspaces: List of workspace names to evaluate.
                       If None, discovers workspaces from datasets directory.
            rag_api_url: LightRAG API endpoint URL
            mode: Query mode for evaluation
        """
        self.rag_api_url = rag_api_url or os.getenv(
            "LIGHTRAG_API_URL", "http://localhost:9621"
        )
        self.mode = mode

        if workspaces:
            self.workspaces = workspaces
        else:
            self.workspaces = self._discover_workspaces()

    def _discover_workspaces(self) -> List[str]:
        """Discover workspaces from datasets directory."""
        datasets_dir = Path(__file__).parent / "datasets"

        if not datasets_dir.exists():
            return ["default"]

        workspaces = []
        for item in datasets_dir.iterdir():
            if item.is_dir() and (item / "evaluation_dataset.json").exists():
                workspaces.append(item.name)

        return workspaces if workspaces else ["default"]

    async def evaluate_workspace(
        self,
        workspace: str,
        reference_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate a single workspace."""
        if self.mode == "temporal":
            evaluator = TemporalRAGEvaluator(
                workspace=workspace,
                rag_api_url=self.rag_api_url,
                default_reference_date=reference_date,
            )
        else:
            # Import here to avoid circular dependency
            from lightrag.evaluation.eval_workspace import StandardRAGEvaluator

            evaluator = StandardRAGEvaluator(
                workspace=workspace,
                rag_api_url=self.rag_api_url,
                query_mode=self.mode,
            )

        return await evaluator.run()

    async def evaluate_all_workspaces(
        self,
        reference_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate all discovered workspaces."""
        all_results = {}

        for workspace in self.workspaces:
            logger.info(f"\n🔄 Evaluating workspace: {workspace}")
            try:
                results = await self.evaluate_workspace(workspace, reference_date)
                all_results[workspace] = results
            except Exception as e:
                logger.error(f"Failed to evaluate workspace {workspace}: {e}")
                all_results[workspace] = {"error": str(e)}

        # Save aggregate results
        self._save_aggregate_results(all_results)

        return all_results

    def _save_aggregate_results(self, all_results: Dict[str, Any]):
        """Save aggregate results across all workspaces."""
        aggregate_dir = Path(__file__).parent / "results" / "aggregate"
        aggregate_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        aggregate_path = aggregate_dir / f"aggregate_results_{timestamp}.json"

        import json

        with open(aggregate_path, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "mode": self.mode,
                    "workspaces_evaluated": list(all_results.keys()),
                    "results": all_results,
                },
                f,
                indent=2,
            )

        logger.info(f"\n📁 Aggregate results saved to: {aggregate_path}")


async def main():
    """Main entry point for temporal RAGAS evaluation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Temporal RAGAS Evaluation for LightRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate default workspace with temporal mode
  python -m lightrag.evaluation.temporal_evaluator

  # Evaluate specific workspace
  python -m lightrag.evaluation.temporal_evaluator --workspace contracts_2024

  # Evaluate with specific reference date
  python -m lightrag.evaluation.temporal_evaluator --reference-date 2024-01-15

  # Evaluate all workspaces
  python -m lightrag.evaluation.temporal_evaluator --all-workspaces
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
        "--dataset",
        "-d",
        type=str,
        default=None,
        help="Path to test dataset JSON file",
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

    args = parser.parse_args()

    try:
        if args.all_workspaces:
            evaluator = WorkspaceEvaluator(
                rag_api_url=args.ragendpoint,
                mode="temporal",
            )
            await evaluator.evaluate_all_workspaces(args.reference_date)
        else:
            evaluator = TemporalRAGEvaluator(
                workspace=args.workspace,
                test_dataset_path=args.dataset,
                rag_api_url=args.ragendpoint,
                default_reference_date=args.reference_date,
            )
            await evaluator.run()

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
