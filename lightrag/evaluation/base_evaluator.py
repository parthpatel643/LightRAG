#!/usr/bin/env python3
"""
Base RAGAS Evaluator with Workspace Support

This module provides a base evaluator class that supports:
- Workspace-specific evaluation datasets and results
- Multiple query modes including temporal
- Consistent evaluation metrics across all modes

Usage:
    from lightrag.evaluation.base_evaluator import BaseRAGEvaluator

    evaluator = BaseRAGEvaluator(workspace="my_workspace")
    results = await evaluator.run()
"""

import asyncio
import csv
import json
import math
import os
import sys
import time
import warnings
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

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

# Connection timeouts
CONNECT_TIMEOUT_SECONDS = 30.0
READ_TIMEOUT_SECONDS = 180.0
TOTAL_TIMEOUT_SECONDS = 210.0

# Query modes supported
QueryMode = Literal["local", "global", "hybrid", "naive", "mix", "temporal", "bypass"]


def _is_nan(value: Any) -> bool:
    """Return True when value is a float NaN."""
    return isinstance(value, float) and math.isnan(value)


# Conditional imports - will raise ImportError if dependencies not installed
try:
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import SimpleCriteriaScore
    from tqdm.auto import tqdm

    RAGAS_AVAILABLE = True

except ImportError as e:
    RAGAS_AVAILABLE = False
    Dataset = None
    evaluate = None
    LangchainLLMWrapper = None
    SimpleCriteriaScore = None
    logger.warning(
        f"RAGAS dependencies not installed: {e}\n"
        "Install with: pip install -e '.[evaluation]'"
    )


class BaseRAGEvaluator(ABC):
    """
    Base class for RAGAS evaluation with workspace support.

    This class provides:
    - Workspace-specific results directories
    - Common evaluation infrastructure
    - Support for multiple query modes
    - Extensible for temporal and other specialized evaluators
    """

    def __init__(
        self,
        workspace: str = "default",
        test_dataset_path: Optional[str] = None,
        rag_api_url: Optional[str] = None,
        query_mode: QueryMode = "mix",
    ):
        """
        Initialize the base evaluator.

        Args:
            workspace: Workspace name for data isolation
            test_dataset_path: Path to test dataset JSON file
            rag_api_url: LightRAG API endpoint URL
            query_mode: Default query mode for evaluation
        """
        if not RAGAS_AVAILABLE:
            raise ImportError(
                "RAGAS dependencies not installed. "
                "Install with: pip install -e '.[evaluation]'"
            )

        self.workspace = workspace
        self.query_mode = query_mode
        self.rag_api_url = rag_api_url or os.getenv(
            "LIGHTRAG_API_URL", "http://localhost:9621"
        )

        # Initialize LLM and embeddings for RAGAS
        self._init_eval_models()

        # Set up paths
        self._setup_paths(test_dataset_path)

        # Load test dataset
        self.test_cases = self._load_test_dataset()

        # Display configuration
        self._display_configuration()

    def _init_eval_models(self):
        """Initialize LLM and embedding models for RAGAS evaluation."""
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
        self.eval_model = os.getenv("EVAL_LLM_MODEL", "gpt-4o-mini")
        self.eval_llm_base_url = os.getenv("EVAL_LLM_BINDING_HOST") or os.getenv(
            "LLM_BINDING_HOST"
        )

        # Embedding configuration (fallback to LLM config)
        eval_embedding_api_key = (
            os.getenv("EVAL_EMBEDDING_BINDING_API_KEY") or eval_llm_api_key
        )
        self.eval_embedding_model = os.getenv(
            "EVAL_EMBEDDING_MODEL", "text-embedding-3-large"
        )
        self.eval_embedding_base_url = (
            os.getenv("EVAL_EMBEDDING_BINDING_HOST") or self.eval_llm_base_url
        )

        # LLM kwargs
        self.eval_max_retries = int(os.getenv("EVAL_LLM_MAX_RETRIES", "5"))
        self.eval_timeout = int(os.getenv("EVAL_LLM_TIMEOUT", "180"))

        # Custom headers for authentication (e.g., Nestle internal APIs)
        extra_headers = {
            "client_id": os.getenv("NESGEN_CLIENT_ID", ""),
            "client_secret": os.getenv("NESGEN_CLIENT_SECRET", ""),
        }

        llm_kwargs = {
            "model": self.eval_model,
            "api_key": eval_llm_api_key,
            "timeout": self.eval_timeout,
            "max_retries": self.eval_max_retries,
        }
        if self.eval_llm_base_url:
            llm_kwargs["base_url"] = self.eval_llm_base_url
        if extra_headers.get("client_id"):  # Only add headers if they exist
            llm_kwargs["default_headers"] = extra_headers

        # Embedding kwargs
        embedding_kwargs = {
            "model": self.eval_embedding_model,
            "api_key": eval_embedding_api_key,
        }
        if self.eval_embedding_base_url:
            embedding_kwargs["base_url"] = self.eval_embedding_base_url
        if extra_headers.get("client_id"):  # Only add headers if they exist
            embedding_kwargs["default_headers"] = extra_headers

        # Initialize LLM and Embeddings for RAGAS
        try:
            base_llm = ChatOpenAI(**llm_kwargs)
            self.eval_embeddings = OpenAIEmbeddings(**embedding_kwargs)

            # Wrap for RAGAS compatibility with bypass_n mode
            try:
                self.eval_llm = LangchainLLMWrapper(
                    langchain_llm=base_llm,
                    bypass_n=True,
                )
            except Exception:
                self.eval_llm = LangchainLLMWrapper(base_llm)

            logger.info("✓ Evaluation LLM and Embeddings initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize evaluation models: {e}")
            raise

    def _setup_paths(self, test_dataset_path: Optional[str]):
        """Set up paths for datasets and results."""
        eval_dir = Path(__file__).parent

        # Results directory: workspace-specific
        self.results_dir = eval_dir / "results" / self.workspace
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Dataset path: check workspace-specific first, then default
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
                # Fall back to default
                self.test_dataset_path = eval_dir / "sample_dataset.json"

    def _display_configuration(self):
        """Display evaluation configuration."""
        logger.info("=" * 70)
        logger.info(f"🔍 RAGAS Evaluation - Workspace: {self.workspace}")
        logger.info("=" * 70)
        logger.info("Evaluation Models:")
        logger.info(f"  • LLM Model:            {self.eval_model}")
        logger.info(f"  • Embedding Model:      {self.eval_embedding_model}")
        logger.info(
            f"  • LLM Endpoint:         {self.eval_llm_base_url or 'OpenAI Official API'}"
        )
        logger.info(
            f"  • Embedding Endpoint:   {self.eval_embedding_base_url or 'OpenAI Official API'}"
        )
        logger.info("Query Settings:")
        logger.info(f"  • Query Mode:           {self.query_mode}")
        logger.info(f"  • Query Top-K:          {os.getenv('EVAL_QUERY_TOP_K', '10')}")
        logger.info("Performance Settings:")
        logger.info(f"  • LLM Max Retries:      {self.eval_max_retries}")
        logger.info(f"  • LLM Timeout:          {self.eval_timeout} seconds")
        logger.info(
            f"  • Max Concurrent:       {os.getenv('EVAL_MAX_CONCURRENT', '2')}"
        )
        logger.info("Test Configuration:")
        logger.info(f"  • Total Test Cases:     {len(self.test_cases)}")
        logger.info(f"  • Test Dataset:         {self.test_dataset_path.name}")
        logger.info(f"  • LightRAG API:         {self.rag_api_url}")
        logger.info(f"  • Results Directory:    {self.results_dir}")
        logger.info("=" * 70)

    def _load_test_dataset(self) -> List[Dict[str, Any]]:
        """Load test dataset from JSON file."""
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(f"Test dataset not found: {self.test_dataset_path}")

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("test_cases", [])

    def _get_request_headers(self) -> Dict[str, str]:
        """Get HTTP headers including workspace and authentication."""
        headers = {}

        # Add workspace header if not default
        if self.workspace and self.workspace != "default":
            headers["LIGHTRAG-WORKSPACE"] = self.workspace

        # Add API key if configured
        api_key = os.getenv("LIGHTRAG_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key

        return headers

    async def generate_rag_response(
        self,
        question: str,
        client: httpx.AsyncClient,
        mode: Optional[QueryMode] = None,
        reference_date: Optional[str] = None,
        enable_rerank: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Query LightRAG API and get response with contexts.

        Args:
            question: Question to query
            client: HTTP client
            mode: Query mode (defaults to self.query_mode)
            reference_date: Reference date for temporal queries
            enable_rerank: Whether to enable reranking (defaults to env EVAL_ENABLE_RERANK or RERANK_BY_DEFAULT)

        Returns:
            Dictionary with 'answer', 'contexts', and metadata
        """
        try:
            # Build query payload
            payload = {
                "query": question,
                "mode": mode or self.query_mode,
                "only_need_context": False,
                "stream": False,
                "include_references": True,
                "include_chunk_content": True,
                "top_k": int(os.getenv("EVAL_QUERY_TOP_K", "10")),
            }

            # Add enable_rerank if specified
            if enable_rerank is not None:
                payload["enable_rerank"] = enable_rerank
            elif "EVAL_ENABLE_RERANK" in os.environ:
                payload["enable_rerank"] = (
                    os.getenv("EVAL_ENABLE_RERANK", "true").lower() == "true"
                )

            # Add reference_date for temporal queries
            if reference_date and payload["mode"] == "temporal":
                payload["reference_date"] = reference_date

            # Make request
            response = await client.post(
                f"{self.rag_api_url}/query",
                json=payload,
                headers=self._get_request_headers(),
                timeout=TOTAL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            result = response.json()

            # Extract answer
            answer = result.get("response", "")

            # Extract contexts from references
            references = result.get("references", [])
            contexts = []
            version_info = []

            for ref in references:
                content = ref.get("content", [])
                if isinstance(content, list):
                    contexts.extend(content)
                elif isinstance(content, str):
                    contexts.append(content)

                # Track version info for temporal evaluation
                if "sequence_index" in ref or "effective_date" in ref:
                    version_info.append(
                        {
                            "chunk_id": ref.get("chunk_id"),
                            "sequence_index": ref.get("sequence_index"),
                            "effective_date": ref.get("effective_date"),
                        }
                    )

            return {
                "answer": answer,
                "contexts": contexts,
                "references": references,
                "version_info": version_info,
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

    @abstractmethod
    async def evaluate_single_case(
        self,
        idx: int,
        test_case: Dict[str, Any],
        client: httpx.AsyncClient,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Evaluate a single test case.

        This method should be implemented by subclasses to provide
        specific evaluation logic (standard RAGAS, temporal, etc.).
        """
        pass

    async def evaluate_responses(self) -> List[Dict[str, Any]]:
        """Evaluate all test cases and return results."""
        max_async = int(os.getenv("EVAL_MAX_CONCURRENT", "2"))

        logger.info("=" * 70)
        logger.info(f"🚀 Starting RAGAS Evaluation - Workspace: {self.workspace}")
        logger.info(f"🔧 Query Mode: {self.query_mode}")
        logger.info(f"🔧 Concurrent Evaluations: {max_async}")
        logger.info("=" * 70)

        # Create semaphores for rate limiting
        rag_semaphore = asyncio.Semaphore(max_async * 2)
        eval_semaphore = asyncio.Semaphore(max_async)

        # Create shared HTTP client
        timeout = httpx.Timeout(
            TOTAL_TIMEOUT_SECONDS,
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
        )
        limits = httpx.Limits(
            max_connections=(max_async + 1) * 2,
            max_keepalive_connections=max_async + 1,
        )

        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            tasks = [
                self._evaluate_with_semaphores(
                    idx, test_case, client, rag_semaphore, eval_semaphore
                )
                for idx, test_case in enumerate(self.test_cases, 1)
            ]
            results = await asyncio.gather(*tasks)

        return list(results)

    async def _evaluate_with_semaphores(
        self,
        idx: int,
        test_case: Dict[str, Any],
        client: httpx.AsyncClient,
        rag_semaphore: asyncio.Semaphore,
        eval_semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """Wrapper to apply semaphores to evaluation."""
        async with rag_semaphore:
            async with eval_semaphore:
                return await self.evaluate_single_case(idx, test_case, client)

    def _export_to_csv(self, results: List[Dict[str, Any]]) -> Path:
        """Export evaluation results to CSV file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.results_dir / f"results_{timestamp}.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "test_number",
                "question",
                "mode",
                "answer_correctness",
                "answer_relevance",
                "context_quality",
                "semantic_equivalence",
                "ragas_score",
                "status",
                "timestamp",
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                metrics = result.get("metrics", {})
                writer.writerow(
                    {
                        "test_number": result.get("test_number", 0),
                        "question": result.get("question", ""),
                        "mode": result.get("mode", self.query_mode),
                        "answer_correctness": f"{metrics.get('answer_correctness', 0):.4f}",
                        "answer_relevance": f"{metrics.get('answer_relevance', 0):.4f}",
                        "context_quality": f"{metrics.get('context_quality', 0):.4f}",
                        "semantic_equivalence": f"{metrics.get('semantic_equivalence', 0):.4f}",
                        "ragas_score": f"{result.get('ragas_score', 0):.4f}",
                        "status": "success" if metrics else "error",
                        "timestamp": result.get("timestamp", ""),
                    }
                )

        return csv_path

    def _calculate_benchmark_stats(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate benchmark statistics from evaluation results."""
        valid_results = [r for r in results if r.get("metrics")]
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

        # Calculate averages for each metric
        metrics_data = {
            "answer_correctness": {"sum": 0.0, "count": 0},
            "answer_relevance": {"sum": 0.0, "count": 0},
            "context_quality": {"sum": 0.0, "count": 0},
            "semantic_equivalence": {"sum": 0.0, "count": 0},
            "ragas_score": {"sum": 0.0, "count": 0},
        }

        for result in valid_results:
            metrics = result.get("metrics", {})

            for metric_name, data in metrics_data.items():
                if metric_name == "ragas_score":
                    value = result.get("ragas_score", 0)
                else:
                    value = metrics.get(metric_name, 0)

                if not _is_nan(value):
                    data["sum"] += value
                    data["count"] += 1

        avg_metrics = {}
        for metric_name, data in metrics_data.items():
            if data["count"] > 0:
                avg_metrics[metric_name] = round(data["sum"] / data["count"], 4)
            else:
                avg_metrics[metric_name] = 0.0

        # Find min and max RAGAS scores
        ragas_scores = [
            r.get("ragas_score", 0)
            for r in valid_results
            if not _is_nan(r.get("ragas_score", 0))
        ]

        return {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": round(successful_tests / total_tests * 100, 2),
            "average_metrics": avg_metrics,
            "min_ragas_score": round(min(ragas_scores), 4) if ragas_scores else 0,
            "max_ragas_score": round(max(ragas_scores), 4) if ragas_scores else 0,
        }

    async def run(self) -> Dict[str, Any]:
        """Run complete evaluation pipeline."""
        start_time = time.time()

        # Evaluate responses
        results = await self.evaluate_responses()

        elapsed_time = time.time() - start_time

        # Calculate benchmark statistics
        benchmark_stats = self._calculate_benchmark_stats(results)

        # Save results
        summary = {
            "workspace": self.workspace,
            "query_mode": self.query_mode,
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(results),
            "elapsed_time_seconds": round(elapsed_time, 2),
            "benchmark_stats": benchmark_stats,
            "results": results,
        }

        # Save JSON results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.results_dir / f"results_{timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2)

        # Export to CSV
        csv_path = self._export_to_csv(results)

        # Print summary
        self._print_summary(results, benchmark_stats, elapsed_time, json_path, csv_path)

        return summary

    def _print_summary(
        self,
        results: List[Dict[str, Any]],
        benchmark_stats: Dict[str, Any],
        elapsed_time: float,
        json_path: Path,
        csv_path: Path,
    ):
        """Print evaluation summary to logger."""
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"📊 EVALUATION COMPLETE - Workspace: {self.workspace}")
        logger.info("=" * 70)
        logger.info(f"Query Mode:     {self.query_mode}")
        logger.info(f"Total Tests:    {len(results)}")
        logger.info(f"Successful:     {benchmark_stats['successful_tests']}")
        logger.info(f"Failed:         {benchmark_stats['failed_tests']}")
        logger.info(f"Success Rate:   {benchmark_stats['success_rate']:.2f}%")
        logger.info(f"Elapsed Time:   {elapsed_time:.2f} seconds")

        # Print benchmark metrics
        logger.info("")
        logger.info("📈 BENCHMARK RESULTS (Average)")
        logger.info("-" * 70)
        avg = benchmark_stats["average_metrics"]
        logger.info(f"Answer Correctness: {avg['answer_correctness']:.4f}")
        logger.info(f"Answer Relevance:   {avg['answer_relevance']:.4f}")
        logger.info(f"Context Quality:    {avg['context_quality']:.4f}")
        logger.info(f"Semantic Equiv:     {avg.get('semantic_equivalence', 0):.4f}")
        logger.info(f"RAGAS Score:        {avg['ragas_score']:.4f}")
        logger.info("-" * 70)
        logger.info(f"Min RAGAS Score:   {benchmark_stats['min_ragas_score']:.4f}")
        logger.info(f"Max RAGAS Score:   {benchmark_stats['max_ragas_score']:.4f}")

        logger.info("")
        logger.info("📁 GENERATED FILES")
        logger.info("-" * 70)
        logger.info(f"Results Dir: {self.results_dir}")
        logger.info(f"  • JSON: {json_path.name}")
        logger.info(f"  • CSV:  {csv_path.name}")
        logger.info("=" * 70)
