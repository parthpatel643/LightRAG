#!/usr/bin/env python3
"""
Aviation Contracts RAGAS Evaluation Script

Evaluates LightRAG's RAG response quality for aviation contract questions
using custom Azure OpenAI LLM functions from lightrag/functions.py.

Usage:
    # Use default dataset and endpoint
    python lightrag/evaluation/eval_aviation_contracts.py

    # Specify custom dataset
    python lightrag/evaluation/eval_aviation_contracts.py --dataset path/to/dataset.json

    # Specify custom RAG endpoint
    python lightrag/evaluation/eval_aviation_contracts.py --ragendpoint http://localhost:9621

    # Both custom dataset and endpoint
    python lightrag/evaluation/eval_aviation_contracts.py -d dataset.json -r http://localhost:9621

Results are saved to: lightrag/evaluation/results/
    - results_YYYYMMDD_HHMMSS.csv   (CSV export for analysis)
    - results_YYYYMMDD_HHMMSS.json  (Full results with details)
"""

import argparse
import asyncio
import csv
import json
import math
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lightrag.utils import logger

# Suppress deprecation warnings
warnings.filterwarnings(
    "ignore",
    message=".*LangchainLLMWrapper is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*Unexpected type for token usage.*",
    category=UserWarning,
)

# Load environment variables
load_dotenv(dotenv_path=".env", override=False)

# Conditional imports - will raise ImportError if dependencies not installed
try:
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )
    from tqdm.auto import tqdm

    RAGAS_AVAILABLE = True

except ImportError as e:
    RAGAS_AVAILABLE = False
    logger.error(
        f"RAGAS dependencies not installed: {e}\n"
        "Install with: pip install -e '.[evaluation]'"
    )
    sys.exit(1)

# Connection timeouts
CONNECT_TIMEOUT_SECONDS = 30.0
READ_TIMEOUT_SECONDS = 180.0
TOTAL_TIMEOUT_SECONDS = 210.0


def _is_nan(value):
    """Check if value is NaN."""
    return value != value or (isinstance(value, float) and math.isnan(value))


class AviationContractsEvaluator:
    """RAGAS evaluator for aviation contracts using custom Azure OpenAI LLM."""

    def __init__(
        self,
        test_dataset_path: str = "lightrag/evaluation/aviation_contracts_questions.json",
        rag_api_url: str | None = None,
    ):
        """
        Initialize the evaluator.

        Args:
            test_dataset_path: Path to test dataset JSON file
            rag_api_url: LightRAG API endpoint URL
        """
        # Get evaluation LLM configuration from environment
        eval_llm_api_key = (
            os.getenv("EVAL_LLM_BINDING_API_KEY")
            or os.getenv("LLM_BINDING_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        if not eval_llm_api_key:
            raise ValueError(
                "No API key found for evaluation LLM. Set EVAL_LLM_BINDING_API_KEY, "
                "LLM_BINDING_API_KEY, or OPENAI_API_KEY environment variable."
            )

        # LLM configuration
        eval_model = os.getenv("EVAL_LLM_MODEL", "gpt-4o-mini")
        eval_llm_base_url = os.getenv("EVAL_LLM_BINDING_HOST") or os.getenv(
            "LLM_BINDING_HOST"
        )

        # Embedding configuration (fallback to LLM config)
        eval_embedding_api_key = (
            os.getenv("EVAL_EMBEDDING_BINDING_API_KEY") or eval_llm_api_key
        )
        eval_embedding_model = os.getenv(
            "EVAL_EMBEDDING_MODEL", "text-embedding-3-large"
        )
        eval_embedding_base_url = (
            os.getenv("EVAL_EMBEDDING_BINDING_HOST") or eval_llm_base_url
        )

        # LLM kwargs for Azure OpenAI compatibility
        llm_kwargs = {
            "model": eval_model,
            "api_key": eval_llm_api_key,
            "timeout": int(os.getenv("EVAL_LLM_TIMEOUT", "180")),
            "max_retries": int(os.getenv("EVAL_LLM_MAX_RETRIES", "5")),
        }
        if eval_llm_base_url:
            llm_kwargs["base_url"] = eval_llm_base_url

        # Embedding kwargs
        embedding_kwargs = {
            "model": eval_embedding_model,
            "api_key": eval_embedding_api_key,
        }
        if eval_embedding_base_url:
            embedding_kwargs["base_url"] = eval_embedding_base_url

        # Initialize LLM and Embeddings for RAGAS
        try:
            base_llm = ChatOpenAI(**llm_kwargs)
            eval_embeddings = OpenAIEmbeddings(**embedding_kwargs)

            # Wrap for RAGAS compatibility
            self.eval_llm = LangchainLLMWrapper(base_llm)

            logger.info("✓ Evaluation LLM and Embeddings initialized successfully")
            logger.info(f"  LLM Model: {eval_model}")
            logger.info(f"  Embedding Model: {eval_embedding_model}")
            if eval_llm_base_url:
                logger.info(f"  LLM Endpoint: {eval_llm_base_url}")
            if eval_embedding_base_url:
                logger.info(f"  Embedding Endpoint: {eval_embedding_base_url}")

        except Exception as e:
            logger.error(f"Failed to initialize evaluation models: {e}")
            raise

        # Store configuration
        self.test_dataset_path = Path(test_dataset_path)
        self.rag_api_url = rag_api_url or os.getenv(
            "LIGHTRAG_API_URL", "http://localhost:9621"
        )
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)

        # Load test dataset
        self.test_cases = self._load_test_dataset()

        # Store model info for display
        self.eval_model = eval_model
        self.eval_embedding_model = eval_embedding_model
        self.eval_llm_base_url = eval_llm_base_url or "OpenAI Official API"
        self.eval_embedding_base_url = (
            eval_embedding_base_url or eval_llm_base_url or "OpenAI Official API"
        )
        self.eval_max_retries = int(os.getenv("EVAL_LLM_MAX_RETRIES", "5"))
        self.eval_timeout = int(os.getenv("EVAL_LLM_TIMEOUT", "180"))

        # Display configuration
        self._display_configuration()

    def _display_configuration(self):
        """Display evaluation configuration."""
        logger.info("=" * 70)
        logger.info("🔍 Aviation Contracts RAGAS Evaluation")
        logger.info("=" * 70)
        logger.info("Evaluation Models:")
        logger.info(f"  • LLM Model:            {self.eval_model}")
        logger.info(f"  • Embedding Model:      {self.eval_embedding_model}")
        logger.info(f"  • LLM Endpoint:         {self.eval_llm_base_url}")
        logger.info(f"  • Embedding Endpoint:   {self.eval_embedding_base_url}")
        logger.info("Performance Settings:")
        logger.info(
            f"  • Query Top-K:          {os.getenv('EVAL_QUERY_TOP_K', '10')} Entities/Relations"
        )
        logger.info(f"  • LLM Max Retries:      {self.eval_max_retries}")
        logger.info(f"  • LLM Timeout:          {self.eval_timeout} seconds")
        logger.info(
            f"  • Max Concurrent:       {os.getenv('EVAL_MAX_CONCURRENT', '2')}"
        )
        logger.info("Test Configuration:")
        logger.info(f"  • Total Test Cases:     {len(self.test_cases)}")

        # Count questions with ground truth
        valid_cases = [
            tc
            for tc in self.test_cases
            if not tc.get("ground_truth", "").startswith("PENDING")
        ]
        logger.info(f"  • With Ground Truth:    {len(valid_cases)}")
        logger.info(
            f"  • Pending Answers:      {len(self.test_cases) - len(valid_cases)}"
        )
        logger.info(f"  • Test Dataset:         {self.test_dataset_path.name}")
        logger.info(f"  • LightRAG API:         {self.rag_api_url}")
        logger.info(f"  • Results Directory:    {self.results_dir}")
        logger.info("=" * 70)
        logger.info("")

    def _load_test_dataset(self) -> List[Dict[str, Any]]:
        """Load test dataset from JSON file."""
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(f"Test dataset not found: {self.test_dataset_path}")

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("test_cases", [])

    async def generate_rag_response(
        self, question: str, client: httpx.AsyncClient
    ) -> Dict[str, Any]:
        """
        Query LightRAG API and get response with contexts.

        Args:
            question: Question to query
            client: HTTP client

        Returns:
            Dictionary with 'answer' and 'contexts' keys
        """
        try:
            # Query parameters
            payload = {
                "query": question,
                "mode": "hybrid",
                "only_need_context": False,
                "stream": False,
                "top_k": int(os.getenv("EVAL_QUERY_TOP_K", "10")),
            }

            # Check if API key is required
            api_key = os.getenv("LIGHTRAG_API_KEY")
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key

            # Make request
            response = await client.post(
                f"{self.rag_api_url}/query",
                json=payload,
                headers=headers,
                timeout=TOTAL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            result = response.json()

            # Extract answer
            answer = result.get("response", "")

            # Extract contexts from references
            references = result.get("references", [])
            if references and len(references) > 0:
                first_ref = references[0]
                # Get content preview or full content
                content_preview = first_ref.get("content_preview", "")
                if not content_preview:
                    content_preview = first_ref.get("content", "")

                # For RAGAS, we need a list of context strings
                contexts = [content_preview] if content_preview else []

                # Add additional references if available
                for ref in references[1:]:
                    content = ref.get("content_preview") or ref.get("content", "")
                    if content:
                        contexts.append(content)
            else:
                contexts = []

            return {"answer": answer, "contexts": contexts}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error querying LightRAG: {e}")
            raise
        except Exception as e:
            logger.error(f"Error querying LightRAG: {e}")
            raise

    async def evaluate_single_case(
        self,
        idx: int,
        test_case: Dict[str, Any],
        rag_semaphore: asyncio.Semaphore,
        eval_semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
        progress_counter: Dict[str, int],
        position_pool: List[int],
        pbar_creation_lock: asyncio.Lock,
    ) -> Dict[str, Any]:
        """
        Evaluate a single test case.

        Args:
            idx: Test case index
            test_case: Test case dictionary
            rag_semaphore: Semaphore for RAG API calls
            eval_semaphore: Semaphore for RAGAS evaluation
            client: HTTP client
            progress_counter: Shared progress counter
            position_pool: Pool of available progress bar positions
            pbar_creation_lock: Lock for progress bar creation

        Returns:
            Evaluation result dictionary
        """
        question = test_case.get("question", "")
        ground_truth = test_case.get("ground_truth", "")

        # Skip if ground truth is pending
        if ground_truth.startswith("PENDING"):
            logger.warning(f"Skipping question {idx + 1}: Ground truth pending")
            return {
                "question": question,
                "ground_truth": ground_truth,
                "answer": "SKIPPED",
                "contexts": [],
                "metrics": {},
                "error": "Ground truth pending",
            }

        try:
            # Step 1: Query RAG system (with rate limiting)
            async with rag_semaphore:
                rag_response = await self.generate_rag_response(question, client)
        except Exception as e:
            logger.error(f"Error querying RAG for question {idx + 1}: {e}")
            return {
                "question": question,
                "ground_truth": ground_truth,
                "answer": "",
                "contexts": [],
                "metrics": {},
                "error": str(e),
            }

        # Extract answer and contexts
        retrieved_contexts = rag_response.get("contexts", [])

        # Prepare dataset for RAGAS
        eval_dataset = Dataset.from_dict(
            {
                "question": [question],
                "answer": [rag_response.get("answer", "")],
                "contexts": [retrieved_contexts],
                "ground_truth": [ground_truth],
            }
        )

        # Step 2: Evaluate with RAGAS (with rate limiting)
        async with eval_semaphore:
            # Get progress bar position
            async with pbar_creation_lock:
                if position_pool:
                    position = position_pool.pop(0)
                else:
                    position = None

            # Create progress bar for this evaluation
            pbar = tqdm(
                total=1,
                desc=f"Evaluating Q{idx + 1}",
                position=position,
                leave=False,
            )

            try:
                # Run RAGAS evaluation
                eval_results = evaluate(
                    eval_dataset,
                    metrics=[
                        Faithfulness(llm=self.eval_llm),
                        AnswerRelevancy(llm=self.eval_llm),
                        ContextRecall(llm=self.eval_llm),
                        ContextPrecision(llm=self.eval_llm),
                    ],
                )

                # Convert to pandas DataFrame
                df = eval_results.to_pandas()

                # Extract scores from first row
                scores_row = df.iloc[0]

                # Build result
                result = {
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": rag_response.get("answer", ""),
                    "contexts": retrieved_contexts,
                    "metrics": {
                        "faithfulness": scores_row.get("faithfulness", float("nan")),
                        "answer_relevancy": scores_row.get(
                            "answer_relevancy", float("nan")
                        ),
                        "context_recall": scores_row.get(
                            "context_recall", float("nan")
                        ),
                        "context_precision": scores_row.get(
                            "context_precision", float("nan")
                        ),
                    },
                }

                # Calculate RAGAS score (average of valid metrics)
                metrics = result["metrics"]
                valid_metrics = [v for v in metrics.values() if not _is_nan(v)]
                ragas_score = (
                    sum(valid_metrics) / len(valid_metrics)
                    if valid_metrics
                    else float("nan")
                )
                result["metrics"]["ragas_score"] = ragas_score

                pbar.update(1)
                pbar.close()

                # Return position to pool
                if position is not None:
                    async with pbar_creation_lock:
                        position_pool.append(position)

                # Update progress counter
                progress_counter["completed"] += 1

                return result

            except Exception as e:
                pbar.close()
                if position is not None:
                    async with pbar_creation_lock:
                        position_pool.append(position)

                logger.error(f"Error evaluating question {idx + 1}: {e}")
                return {
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": rag_response.get("answer", ""),
                    "contexts": retrieved_contexts,
                    "metrics": {},
                    "error": str(e),
                }

    async def evaluate_responses(self) -> List[Dict[str, Any]]:
        """
        Evaluate all test cases.

        Returns:
            List of evaluation results
        """
        logger.info("🚀 Starting RAGAS Evaluation of Aviation Contracts")

        # Get concurrency settings
        max_async = int(os.getenv("EVAL_MAX_CONCURRENT", "2"))

        logger.info(f"🔧 RAGAS Evaluation: {max_async} concurrent")
        logger.info("=" * 70)
        logger.info("")

        # Create semaphores for rate limiting
        rag_semaphore = asyncio.Semaphore(max_async)
        # RAGAS evaluation is more intensive, use same limit
        eval_semaphore = asyncio.Semaphore(max_async)

        # Shared progress counter
        progress_counter = {"completed": 0}

        # Pool of available progress bar positions
        position_pool = list(range(max_async))

        # Lock for progress bar creation
        pbar_creation_lock = asyncio.Lock()

        # Create HTTP client with timeouts
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=30.0,
            pool=5.0,
        )
        limits = httpx.Limits(
            max_connections=max_async * 2, max_keepalive_connections=max_async
        )

        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            # Create tasks for all test cases
            tasks = [
                self.evaluate_single_case(
                    idx,
                    test_case,
                    rag_semaphore,
                    eval_semaphore,
                    client,
                    progress_counter,
                    position_pool,
                    pbar_creation_lock,
                )
                for idx, test_case in enumerate(self.test_cases)
            ]

            # Run all tasks concurrently
            results = await asyncio.gather(*tasks)

        return results

    def _export_to_csv(self, results: List[Dict[str, Any]], csv_path: Path):
        """
        Export results to CSV file.

        Args:
            results: List of evaluation results
            csv_path: Path to CSV file
        """
        # Filter out skipped/error results for CSV
        valid_results = [
            r
            for r in results
            if "error" not in r or not r.get("ground_truth", "").startswith("PENDING")
        ]

        if not valid_results:
            logger.warning("No valid results to export to CSV")
            return

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "question",
                "ground_truth",
                "answer",
                "faithfulness",
                "answer_relevancy",
                "context_recall",
                "context_precision",
                "ragas_score",
                "error",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for idx, result in enumerate(valid_results, 1):
                metrics = result.get("metrics", {})
                writer.writerow(
                    {
                        "question": result.get("question", ""),
                        "ground_truth": result.get("ground_truth", ""),
                        "answer": result.get("answer", ""),
                        "faithfulness": metrics.get("faithfulness", ""),
                        "answer_relevancy": metrics.get("answer_relevancy", ""),
                        "context_recall": metrics.get("context_recall", ""),
                        "context_precision": metrics.get("context_precision", ""),
                        "ragas_score": metrics.get("ragas_score", ""),
                        "error": result.get("error", ""),
                    }
                )

        logger.info(f"✓ CSV results exported to: {csv_path}")

    def _format_metric(self, value, width=7):
        """Format metric value for display."""
        if _is_nan(value):
            return "N/A".rjust(width)
        elif isinstance(value, (int, float)):
            return f"{value:.4f}".rjust(width)
        else:
            return str(value).rjust(width)

    def _display_results_table(self, results: List[Dict[str, Any]]):
        """Display results in a formatted table."""
        logger.info("")
        logger.info("=" * 135)
        logger.info("📊 EVALUATION RESULTS SUMMARY")
        logger.info("=" * 135)
        logger.info(
            "#    | Question                                           |  Faith | AnswRel | CtxRec | CtxPrec |  RAGAS | Status"
        )
        logger.info("-" * 135)

        for idx, result in enumerate(results, 1):
            question = result.get("question", "")
            # Truncate question for display
            question_display = (
                question[:50] + "..." if len(question) > 50 else question.ljust(53)
            )

            # Get metrics
            metrics = result.get("metrics", {})

            # Format metric values
            faith = self._format_metric(metrics.get("faithfulness"))
            ans_rel = self._format_metric(metrics.get("answer_relevancy"))
            ctx_rec = self._format_metric(metrics.get("context_recall"))
            ctx_prec = self._format_metric(metrics.get("context_precision"))
            ragas = self._format_metric(metrics.get("ragas_score"))

            # Status
            if "error" in result:
                if result.get("ground_truth", "").startswith("PENDING"):
                    status = "PENDING"
                else:
                    status = "ERROR"
            else:
                status = "✓"

            logger.info(
                f"{str(idx).ljust(4)} | {question_display} | {faith} | {ans_rel} | {ctx_rec} | {ctx_prec} | {ragas} | {status.rjust(6)}"
            )

            # Show error details if present
            if "error" in result and not result.get("ground_truth", "").startswith(
                "PENDING"
            ):
                error = result["error"]
                error_display = error[:100] + "..." if len(error) > 100 else error
                logger.info(f"       Error: {error_display}")

        logger.info("=" * 135)

    def _calculate_benchmark_stats(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate benchmark statistics from results.

        Args:
            results: List of evaluation results

        Returns:
            Dictionary with benchmark statistics
        """
        # Filter valid results (exclude errors and pending)
        valid_results = [
            r
            for r in results
            if "error" not in r or not r.get("ground_truth", "").startswith("PENDING")
        ]

        total_tests = len(results)
        successful_tests = len(valid_results)
        failed_tests = total_tests - successful_tests

        if not valid_results:
            return {
                "total_tests": total_tests,
                "successful_tests": 0,
                "failed_tests": failed_tests,
                "success_rate": 0.0,
            }

        # Collect metrics
        metrics_data = {
            "faithfulness": [],
            "answer_relevancy": [],
            "context_recall": [],
            "context_precision": [],
            "ragas_score": [],
        }

        for result in valid_results:
            metrics = result.get("metrics", {})

            # Collect each metric if not NaN
            faithfulness = metrics.get("faithfulness")
            if not _is_nan(faithfulness):
                metrics_data["faithfulness"].append(faithfulness)

            answer_relevance = metrics.get("answer_relevancy")
            if not _is_nan(answer_relevance):
                metrics_data["answer_relevancy"].append(answer_relevance)

            context_recall = metrics.get("context_recall")
            if not _is_nan(context_recall):
                metrics_data["context_recall"].append(context_recall)

            context_precision = metrics.get("context_precision")
            if not _is_nan(context_precision):
                metrics_data["context_precision"].append(context_precision)

            ragas_score = metrics.get("ragas_score")
            if not _is_nan(ragas_score):
                metrics_data["ragas_score"].append(ragas_score)

        # Calculate averages
        avg_metrics = {}
        for metric_name, data in metrics_data.items():
            if data:
                avg_val = sum(data) / len(data)
                avg_metrics[f"avg_{metric_name}"] = avg_val
            else:
                avg_metrics[f"avg_{metric_name}"] = float("nan")

        # Get min/max RAGAS scores
        ragas_scores = metrics_data["ragas_score"]
        if ragas_scores:
            min_score = min(ragas_scores)
            max_score = max(ragas_scores)
        else:
            min_score = float("nan")
            max_score = float("nan")

        return {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": (successful_tests / total_tests * 100)
            if total_tests > 0
            else 0.0,
            **avg_metrics,
            "min_ragas_score": min_score,
            "max_ragas_score": max_score,
        }

    async def run(self) -> Dict[str, Any]:
        """
        Run the complete evaluation workflow.

        Returns:
            Dictionary with evaluation summary
        """
        # Start timer
        start_time = time.time()

        # Run evaluation
        results = await self.evaluate_responses()

        elapsed_time = time.time() - start_time

        # Calculate statistics
        benchmark_stats = self._calculate_benchmark_stats(results)

        # Prepare summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "dataset": str(self.test_dataset_path),
            "rag_api_url": self.rag_api_url,
            "elapsed_time": elapsed_time,
            "results": results,
            "statistics": benchmark_stats,
        }

        # Save results to JSON
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.results_dir / f"aviation_results_{timestamp_str}.json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ JSON results saved to: {json_path}")

        # Export to CSV
        csv_path = self.results_dir / f"aviation_results_{timestamp_str}.csv"
        self._export_to_csv(results, csv_path)

        # Display results table
        self._display_results_table(results)

        # Display summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("📊 EVALUATION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total Tests:    {benchmark_stats['total_tests']}")
        logger.info(f"Successful:     {benchmark_stats['successful_tests']}")
        logger.info(f"Failed/Pending: {benchmark_stats['failed_tests']}")
        logger.info(f"Success Rate:   {benchmark_stats['success_rate']:.2f}%")
        logger.info(f"Elapsed Time:   {elapsed_time:.2f} seconds")
        logger.info(
            f"Avg Time/Test:  {elapsed_time / benchmark_stats['total_tests']:.2f} seconds"
        )
        logger.info("")
        logger.info("=" * 70)
        logger.info("📈 BENCHMARK RESULTS (Average)")
        logger.info("=" * 70)

        for metric_name, avg in [
            ("Faithfulness", benchmark_stats.get("avg_faithfulness")),
            ("Answer Relevance", benchmark_stats.get("avg_answer_relevancy")),
            ("Context Recall", benchmark_stats.get("avg_context_recall")),
            ("Context Precision", benchmark_stats.get("avg_context_precision")),
            ("RAGAS Score", benchmark_stats.get("avg_ragas_score")),
        ]:
            if not _is_nan(avg):
                logger.info(f"Average {metric_name}: {avg:.4f}".ljust(35))
            else:
                logger.info(f"Average {metric_name}: N/A".ljust(35))

        logger.info("-" * 70)
        if not _is_nan(benchmark_stats.get("min_ragas_score")):
            logger.info(
                f"Min RAGAS Score:           {benchmark_stats['min_ragas_score']:.4f}"
            )
        if not _is_nan(benchmark_stats.get("max_ragas_score")):
            logger.info(
                f"Max RAGAS Score:           {benchmark_stats['max_ragas_score']:.4f}"
            )

        return summary


def main():
    """Main entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Evaluate LightRAG aviation contracts with RAGAS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use defaults
  python lightrag/evaluation/eval_aviation_contracts.py

  # Custom dataset
  python lightrag/evaluation/eval_aviation_contracts.py --dataset my_questions.json

  # Custom endpoint
  python lightrag/evaluation/eval_aviation_contracts.py --ragendpoint http://localhost:9621

  # Both custom
  python lightrag/evaluation/eval_aviation_contracts.py -d my_questions.json -r http://localhost:9621
        """,
    )

    parser.add_argument(
        "-d",
        "--dataset",
        type=str,
        default="lightrag/evaluation/aviation_contracts_questions.json",
        help="Path to test dataset JSON file (default: aviation_contracts_questions.json)",
    )

    parser.add_argument(
        "-r",
        "--ragendpoint",
        type=str,
        default=None,
        help="LightRAG API endpoint URL (default: http://localhost:9621 or $LIGHTRAG_API_URL)",
    )

    args = parser.parse_args()

    # Create evaluator
    try:
        evaluator = AviationContractsEvaluator(
            test_dataset_path=args.dataset, rag_api_url=args.ragendpoint
        )

        # Run evaluation
        asyncio.run(evaluator.run())

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
