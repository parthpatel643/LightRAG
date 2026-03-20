#!/usr/bin/env python3
"""
LLM-based Semantic Equivalence Evaluator for Workspace-level Temporal Queries

This module provides a focused evaluator that:
- Takes a JSON file with Q&A pairs as input
- Runs temporal queries against a LightRAG workspace
- Uses LLM-based semantic equivalence (not embedding similarity) to compare
  RAG answers against ground truth

The evaluator leverages the existing llm_model_func from lightrag/functions.py
for all LLM calls, maintaining consistency with the main LightRAG system.

Usage:
    from lightrag.evaluation.semantic_equivalence_evaluator import SemanticEquivalenceEvaluator

    evaluator = SemanticEquivalenceEvaluator(
        workspace="my_workspace",
        test_dataset_path="path/to/qa_pairs.json",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()

CLI:
    python -m lightrag.evaluation.semantic_equivalence_evaluator \\
        --workspace my_workspace \\
        --dataset path/to/qa_pairs.json \\
        --reference-date 2024-01-15

Input JSON format:
    {
        "test_cases": [
            {
                "question": "What is the price for Boeing 787 service?",
                "ground_truth": "$227.24 per event",
                "reference_date": "2024-01-15"  // optional, uses default if missing
            }
        ]
    }

Output:
    - JSON file with per-case semantic equivalence scores and aggregate stats
    - CSV file for easy analysis
"""

import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lightrag.functions import llm_model_func
from lightrag.utils import logger

# Load environment variables
load_dotenv(dotenv_path=".env", override=False)

# Connection timeouts
CONNECT_TIMEOUT_SECONDS = 30.0
READ_TIMEOUT_SECONDS = 180.0
TOTAL_TIMEOUT_SECONDS = 210.0

# Default pass threshold for semantic equivalence (0.0 - 1.0)
DEFAULT_PASS_THRESHOLD = 0.7

# Prompt template for LLM-based semantic equivalence evaluation
SEMANTIC_EQUIVALENCE_SYSTEM_PROMPT = """You are an expert evaluator tasked with assessing semantic equivalence between two texts.

Your job is to determine if the ANSWER semantically matches the GROUND_TRUTH, considering:
1. Core factual content (numbers, names, dates, amounts)
2. Logical meaning and intent
3. Completeness of information

You should be lenient on:
- Minor wording differences
- Extra context that doesn't contradict the ground truth
- Formatting differences (e.g., "$227.24" vs "227.24 dollars")

You should penalize:
- Wrong factual information (different numbers, names, etc.)
- Missing critical information from ground truth
- Contradictory statements

Respond with ONLY a JSON object in this exact format:
{
    "score": <number from 0 to 5>,
    "reasoning": "<brief explanation>"
}

Score guide:
- 5: Perfect match - identical meaning and all facts correct
- 4: Excellent - same core facts with minor omissions or additions
- 3: Good - mostly correct with some missing or extra information
- 2: Partial - some correct information but significant gaps or errors
- 1: Poor - minimal overlap, major errors or omissions
- 0: No match - completely different or contradictory"""

SEMANTIC_EQUIVALENCE_USER_PROMPT = """Evaluate the semantic equivalence:

QUESTION: {question}

GROUND_TRUTH: {ground_truth}

ANSWER: {answer}

Provide your evaluation as a JSON object with "score" (0-5) and "reasoning"."""


class SemanticEquivalenceEvaluator:
    """
    LLM-based Semantic Equivalence Evaluator for temporal queries.

    This evaluator:
    - Queries LightRAG using temporal mode
    - Uses LLM to judge semantic equivalence between answer and ground truth
    - Outputs detailed results in JSON and CSV formats
    """

    def __init__(
        self,
        workspace: str = "default",
        test_dataset_path: Optional[str] = None,
        rag_api_url: Optional[str] = None,
        default_reference_date: Optional[str] = None,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
        enable_rerank: Optional[bool] = None,
        max_concurrent: int = 3,
    ):
        """
        Initialize the semantic equivalence evaluator.

        Args:
            workspace: Workspace name for data isolation
            test_dataset_path: Path to test dataset JSON file
            rag_api_url: LightRAG API endpoint URL
            default_reference_date: Default reference date for temporal queries
                                   (YYYY-MM-DD format, used when test case doesn't specify)
            pass_threshold: Minimum normalized score (0.0-1.0) to count as a "pass"
            enable_rerank: Whether to enable reranking in queries
            max_concurrent: Maximum number of concurrent evaluations (default: 3)
        """
        self.workspace = workspace
        self.rag_api_url = rag_api_url or os.getenv(
            "LIGHTRAG_API_URL", "http://localhost:9621"
        )
        self.default_reference_date = default_reference_date or os.getenv(
            "EVAL_DEFAULT_REFERENCE_DATE", datetime.now().strftime("%Y-%m-%d")
        )
        self.pass_threshold = pass_threshold
        self.enable_rerank = enable_rerank
        self.max_concurrent = max_concurrent

        # Set up paths
        self._setup_paths(test_dataset_path)

        # Load test dataset
        self.test_cases = self._load_test_dataset()

        # Display configuration
        self._display_configuration()

    def _setup_paths(self, test_dataset_path: Optional[str]):
        """Set up paths for datasets and results."""
        # Use project root evaluation folder, not lightrag/evaluation
        eval_dir = Path(__file__).parent.parent.parent / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)

        # Results directory: workspace-specific
        self.results_dir = eval_dir / "results" / self.workspace
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Dataset path
        if test_dataset_path:
            self.test_dataset_path = Path(test_dataset_path)
        else:
            # Try workspace-specific dataset
            workspace_dataset = (
                eval_dir / "datasets" / self.workspace / "evaluation_dataset.json"
            )
            if workspace_dataset.exists():
                self.test_dataset_path = workspace_dataset
            else:
                # Fall back to default temporal dataset or raise error
                temporal_dataset = (
                    eval_dir / "datasets" / "temporal" / "evaluation_dataset.json"
                )
                if temporal_dataset.exists():
                    self.test_dataset_path = temporal_dataset
                else:
                    raise FileNotFoundError(
                        f"No evaluation dataset found for workspace '{self.workspace}' "
                        f"and no temporal dataset at {temporal_dataset}"
                    )

    def _load_test_dataset(self) -> List[Dict[str, Any]]:
        """Load test dataset from JSON file."""
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(f"Test dataset not found: {self.test_dataset_path}")

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("test_cases", [])

    def _display_configuration(self):
        """Display evaluation configuration."""
        logger.info("=" * 70)
        logger.info(f"🎯 Semantic Equivalence Evaluator - Workspace: {self.workspace}")
        logger.info("=" * 70)
        logger.info("Configuration:")
        logger.info("  • Query Mode:           temporal (fixed)")
        logger.info(f"  • Default Ref Date:     {self.default_reference_date}")
        logger.info(f"  • Pass Threshold:       {self.pass_threshold:.2f}")
        logger.info(f"  • Enable Rerank:        {self.enable_rerank}")
        logger.info(f"  • Max Concurrent:       {self.max_concurrent}")
        logger.info(f"  • LightRAG API:         {self.rag_api_url}")
        logger.info("Test Configuration:")
        logger.info(f"  • Total Test Cases:     {len(self.test_cases)}")
        logger.info(f"  • Test Dataset:         {self.test_dataset_path.name}")
        logger.info(f"  • Results Directory:    {self.results_dir}")
        logger.info("=" * 70)

    def _get_request_headers(self) -> Dict[str, str]:
        """Get HTTP headers including workspace and authentication."""
        headers = {}

        # Add workspace header if not default
        if self.workspace and self.workspace != "default":
            headers["LIGHTRAG-WORKSPACE"] = self.workspace

        # Note: Authentication disabled on server, no auth headers needed

        return headers

    async def _generate_rag_response(
        self,
        question: str,
        client: httpx.AsyncClient,
        reference_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query LightRAG API with temporal mode.

        Args:
            question: Question to query
            client: HTTP client
            reference_date: Reference date for temporal query

        Returns:
            Dictionary with 'answer' and metadata
        """
        try:
            # Build query payload - always temporal mode
            payload = {
                "query": question,
                "mode": "temporal",
                "only_need_context": False,
                "stream": False,
                "include_references": True,
                "include_chunk_content": True,
                "top_k": int(os.getenv("EVAL_QUERY_TOP_K", "10")),
            }

            # Add enable_rerank if specified
            if self.enable_rerank is not None:
                payload["enable_rerank"] = self.enable_rerank
            elif "EVAL_ENABLE_RERANK" in os.environ:
                payload["enable_rerank"] = (
                    os.getenv("EVAL_ENABLE_RERANK", "true").lower() == "true"
                )

            # Add reference_date for temporal query
            ref_date = reference_date or self.default_reference_date
            if ref_date:
                payload["reference_date"] = ref_date

            # Make request
            response = await client.post(
                f"{self.rag_api_url}/query",
                json=payload,
                headers=self._get_request_headers(),
                timeout=TOTAL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            result = response.json()

            return {
                "answer": result.get("response", ""),
                "references": result.get("references", []),
            }

        except httpx.ConnectError as e:
            raise Exception(
                f"Cannot connect to LightRAG API at {self.rag_api_url}: {str(e)}"
            )
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"LightRAG API error {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            raise Exception(f"Error calling LightRAG API: {type(e).__name__}: {str(e)}")

    async def _calculate_semantic_equivalence(
        self,
        question: str,
        answer: str,
        ground_truth: str,
    ) -> Dict[str, Any]:
        """
        Calculate LLM-based semantic equivalence between answer and ground truth.

        Uses llm_model_func from lightrag/functions.py for consistency with the
        main LightRAG system.

        Args:
            question: Original question (for context)
            answer: Generated answer from RAG system
            ground_truth: Reference/expected answer

        Returns:
            Dictionary with:
            - score: Normalized semantic equivalence score (0.0 - 1.0)
            - raw_score: Original LLM score (0 - 5)
            - reasoning: LLM's explanation
            - passed: Whether score meets pass_threshold
        """
        try:
            # Format the user prompt
            user_prompt = SEMANTIC_EQUIVALENCE_USER_PROMPT.format(
                question=question,
                ground_truth=ground_truth,
                answer=answer,
            )

            # Call LLM using existing llm_model_func from functions.py
            response = await llm_model_func(
                prompt=user_prompt,
                system_prompt=SEMANTIC_EQUIVALENCE_SYSTEM_PROMPT,
                history_messages=[],
            )

            # Parse JSON response
            try:
                # Try to extract JSON from response (handle potential markdown wrapping)
                response_text = response.strip()
                if response_text.startswith("```"):
                    # Remove markdown code block
                    lines = response_text.split("\n")
                    json_lines = [line for line in lines if not line.startswith("```")]
                    response_text = "\n".join(json_lines)

                result = json.loads(response_text)
                raw_score = float(result.get("score", 0))
                reasoning = result.get("reasoning", "No reasoning provided")

            except (json.JSONDecodeError, KeyError, TypeError) as parse_error:
                # Fallback: try to extract score from text
                logger.warning(
                    f"Failed to parse JSON response, attempting fallback: {parse_error}"
                )
                raw_score = self._extract_score_from_text(response)
                reasoning = f"Parse fallback - Original response: {response[:200]}"

            # Normalize score to 0.0 - 1.0 range
            raw_score = max(0, min(5, raw_score))  # Clamp to 0-5
            normalized_score = raw_score / 5.0

            return {
                "score": round(normalized_score, 4),
                "raw_score": raw_score,
                "reasoning": reasoning,
                "passed": normalized_score >= self.pass_threshold,
            }

        except Exception as e:
            logger.error(f"Error calculating semantic equivalence: {e}")
            return {
                "score": 0.0,
                "raw_score": 0,
                "reasoning": f"Error: {str(e)}",
                "passed": False,
            }

    def _extract_score_from_text(self, text: str) -> float:
        """Fallback method to extract score from unstructured LLM response."""
        import re

        # Look for patterns like "score: 4", "Score: 4/5", "4 out of 5", etc.
        patterns = [
            r"score[:\s]+(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*(?:out of|/)\s*5",
            r"rating[:\s]+(\d+(?:\.\d+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return float(match.group(1))

        # Default to 0 if no score found
        return 0.0

    async def _evaluate_single_case(
        self,
        idx: int,
        test_case: Dict[str, Any],
        client: httpx.AsyncClient,
    ) -> Dict[str, Any]:
        """
        Evaluate a single test case.

        Args:
            idx: Test case index (1-based)
            test_case: Test case dictionary with question, ground_truth, etc.
            client: HTTP client

        Returns:
            Evaluation result dictionary
        """
        question = test_case["question"]
        ground_truth = test_case["ground_truth"]
        reference_date = test_case.get("reference_date", self.default_reference_date)

        try:
            # Generate RAG response with temporal mode
            rag_response = await self._generate_rag_response(
                question=question,
                client=client,
                reference_date=reference_date,
            )

            answer = rag_response["answer"]

            # Calculate LLM-based semantic equivalence
            semantic_result = await self._calculate_semantic_equivalence(
                question=question,
                answer=answer,
                ground_truth=ground_truth,
            )

            return {
                "test_number": idx,
                "question": question,
                "reference_date": reference_date,
                "mode": "temporal",
                "workspace": test_case.get("workspace", self.workspace),
                "answer": answer[:500] + "..." if len(answer) > 500 else answer,
                "ground_truth": ground_truth[:500] + "..."
                if len(ground_truth) > 500
                else ground_truth,
                "semantic_equivalence": {
                    "score": semantic_result["score"],
                    "raw_score": semantic_result["raw_score"],
                    "reasoning": semantic_result["reasoning"],
                    "passed": semantic_result["passed"],
                },
                "status": "success",
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error evaluating test {idx}: {str(e)}")
            return {
                "test_number": idx,
                "question": question,
                "reference_date": reference_date,
                "error": str(e),
                "semantic_equivalence": {
                    "score": 0.0,
                    "raw_score": 0,
                    "reasoning": f"Evaluation failed: {str(e)}",
                    "passed": False,
                },
                "status": "error",
                "timestamp": datetime.now().isoformat(),
            }

    async def evaluate_responses(self) -> List[Dict[str, Any]]:
        """
        Evaluate all test cases in parallel.

        Returns:
            List of evaluation results
        """
        # Create a semaphore to limit concurrent evaluations
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results_dict = {}

        async def evaluate_with_semaphore(
            idx: int, test_case: Dict[str, Any], client: httpx.AsyncClient
        ):
            """Evaluate a single case with semaphore to limit concurrency."""
            async with semaphore:
                logger.info(f"Evaluating test {idx}/{len(self.test_cases)}...")
                result = await self._evaluate_single_case(idx, test_case, client)
                results_dict[idx] = result

                # Log progress
                se = result.get("semantic_equivalence", {})
                status = "✓" if se.get("passed", False) else "✗"
                score = se.get("score", 0)
                logger.info(
                    f"  {status} Score: {score:.2f} - {result['question'][:50]}..."
                )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT_SECONDS,
                read=READ_TIMEOUT_SECONDS,
                write=30.0,
                pool=30.0,
            ),
            trust_env=False
        ) as client:
                # Create all evaluation tasks
                tasks = [
                    evaluate_with_semaphore(idx, test_case, client)
                    for idx, test_case in enumerate(self.test_cases, 1)
                ]

                # Run all tasks concurrently with the semaphore limit
                await asyncio.gather(*tasks)

        # Return results in order
        return [results_dict[i] for i in range(1, len(self.test_cases) + 1)]

    def _calculate_statistics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate aggregate statistics from results.

        Args:
            results: List of evaluation results

        Returns:
            Dictionary with aggregate statistics
        """
        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") == "error"]

        if not successful:
            return {
                "total_tests": len(results),
                "successful_tests": 0,
                "failed_tests": len(failed),
                "success_rate": 0.0,
                "average_score": 0.0,
                "pass_count": 0,
                "pass_rate": 0.0,
                "min_score": None,
                "max_score": None,
            }

        scores = [
            r["semantic_equivalence"]["score"]
            for r in successful
            if "semantic_equivalence" in r
        ]
        passed = [
            r
            for r in successful
            if r.get("semantic_equivalence", {}).get("passed", False)
        ]

        return {
            "total_tests": len(results),
            "successful_tests": len(successful),
            "failed_tests": len(failed),
            "success_rate": round(len(successful) / len(results) * 100, 2),
            "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "pass_count": len(passed),
            "pass_rate": round(len(passed) / len(successful) * 100, 2)
            if successful
            else 0.0,
            "pass_threshold": self.pass_threshold,
            "min_score": round(min(scores), 4) if scores else None,
            "max_score": round(max(scores), 4) if scores else None,
        }

    def _export_results(
        self,
        results: List[Dict[str, Any]],
        stats: Dict[str, Any],
        elapsed_time: float,
    ) -> tuple[Path, Path]:
        """
        Export results to JSON and CSV files.

        Args:
            results: List of evaluation results
            stats: Aggregate statistics
            elapsed_time: Total evaluation time in seconds

        Returns:
            Tuple of (json_path, csv_path)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON export
        json_path = self.results_dir / f"semantic_eval_{timestamp}.json"
        json_data = {
            "workspace": self.workspace,
            "query_mode": "temporal",
            "default_reference_date": self.default_reference_date,
            "pass_threshold": self.pass_threshold,
            "timestamp": datetime.now().isoformat(),
            "elapsed_time_seconds": round(elapsed_time, 2),
            "statistics": stats,
            "results": results,
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # CSV export
        csv_path = self.results_dir / f"semantic_eval_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(
                [
                    "test_number",
                    "question",
                    "reference_date",
                    "score",
                    "raw_score",
                    "passed",
                    "reasoning",
                    "status",
                    "timestamp",
                ]
            )

            # Rows
            for r in results:
                se = r.get("semantic_equivalence", {})
                writer.writerow(
                    [
                        r.get("test_number", ""),
                        r.get("question", "")[:100],
                        r.get("reference_date", ""),
                        se.get("score", ""),
                        se.get("raw_score", ""),
                        se.get("passed", ""),
                        se.get("reasoning", "")[:200],
                        r.get("status", ""),
                        r.get("timestamp", ""),
                    ]
                )

        return json_path, csv_path

    def _print_summary(
        self,
        stats: Dict[str, Any],
        elapsed_time: float,
        json_path: Path,
        csv_path: Path,
    ):
        """Print evaluation summary."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("📊 SEMANTIC EQUIVALENCE EVALUATION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Workspace:            {self.workspace}")
        logger.info("Query Mode:           temporal")
        logger.info(f"Pass Threshold:       {self.pass_threshold:.2f}")
        logger.info(f"Total Time:           {elapsed_time:.2f} seconds")
        logger.info("-" * 70)
        logger.info(f"Total Tests:          {stats['total_tests']}")
        logger.info(f"Successful:           {stats['successful_tests']}")
        logger.info(f"Failed:               {stats['failed_tests']}")
        logger.info(f"Success Rate:         {stats['success_rate']:.1f}%")
        logger.info("-" * 70)
        logger.info("📈 SEMANTIC EQUIVALENCE METRICS")
        logger.info("-" * 70)
        logger.info(f"Average Score:        {stats['average_score']:.4f}")
        logger.info(
            f"Pass Count:           {stats['pass_count']} / {stats['successful_tests']}"
        )
        logger.info(f"Pass Rate:            {stats['pass_rate']:.1f}%")
        if stats["min_score"] is not None:
            logger.info(f"Min Score:            {stats['min_score']:.4f}")
            logger.info(f"Max Score:            {stats['max_score']:.4f}")
        logger.info("-" * 70)
        logger.info("📁 Results saved to:")
        logger.info(f"   JSON: {json_path}")
        logger.info(f"   CSV:  {csv_path}")
        logger.info("=" * 70)

    async def run(self) -> Dict[str, Any]:
        """
        Run the full evaluation pipeline.

        Returns:
            Dictionary with results and statistics
        """
        logger.info("\n🚀 Starting Semantic Equivalence Evaluation...")

        start_time = time.time()

        # Run evaluations
        results = await self.evaluate_responses()

        # Calculate statistics
        stats = self._calculate_statistics(results)

        elapsed_time = time.time() - start_time

        # Export results
        json_path, csv_path = self._export_results(results, stats, elapsed_time)

        # Print summary
        self._print_summary(stats, elapsed_time, json_path, csv_path)

        return {
            "workspace": self.workspace,
            "statistics": stats,
            "results": results,
            "json_path": str(json_path),
            "csv_path": str(csv_path),
        }


async def main():
    """Main entry point for semantic equivalence evaluation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM-based Semantic Equivalence Evaluation for LightRAG Temporal Queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate default workspace
  python -m lightrag.evaluation.semantic_equivalence_evaluator

  # Evaluate specific workspace with custom dataset
  python -m lightrag.evaluation.semantic_equivalence_evaluator \\
      --workspace contracts_2024 \\
      --dataset path/to/qa_pairs.json

  # Evaluate with specific reference date and pass threshold
  python -m lightrag.evaluation.semantic_equivalence_evaluator \\
      --workspace my_workspace \\
      --reference-date 2024-01-15 \\
      --threshold 0.8

  # Evaluate with higher concurrency (faster)
  python -m lightrag.evaluation.semantic_equivalence_evaluator \\
      --workspace sea_cabin_cleaning \\
      --max-concurrent 5
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
        help="Path to test dataset JSON file with Q&A pairs",
    )

    parser.add_argument(
        "--ragendpoint",
        "-r",
        type=str,
        default=None,
        help="LightRAG API endpoint URL (default: http://localhost:9621)",
    )

    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        help="Default reference date for temporal queries (YYYY-MM-DD format)",
    )

    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=DEFAULT_PASS_THRESHOLD,
        help=f"Pass threshold for semantic equivalence (0.0-1.0, default: {DEFAULT_PASS_THRESHOLD})",
    )

    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Enable reranking in queries",
    )

    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disable reranking in queries",
    )

    parser.add_argument(
        "--max-concurrent",
        "-c",
        type=int,
        default=3,
        help="Maximum number of concurrent evaluations (default: 3)",
    )

    args = parser.parse_args()

    # Determine rerank setting
    enable_rerank = None
    if args.rerank:
        enable_rerank = True
    elif args.no_rerank:
        enable_rerank = False

    try:
        evaluator = SemanticEquivalenceEvaluator(
            workspace=args.workspace,
            test_dataset_path=args.dataset,
            rag_api_url=args.ragendpoint,
            default_reference_date=args.reference_date,
            pass_threshold=args.threshold,
            enable_rerank=enable_rerank,
            max_concurrent=args.max_concurrent,
        )
        await evaluator.run()

    except FileNotFoundError as e:
        logger.error(f"Dataset not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
