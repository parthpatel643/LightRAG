#!/usr/bin/env python3
"""
LightRAG Production Performance Benchmarking Script

This script performs comprehensive performance testing of the LightRAG system
with AWS infrastructure (Neptune, DocumentDB, Milvus).

Usage:
    python benchmark_production.py --url https://api.your-domain.com --token YOUR_TOKEN
    python benchmark_production.py --config benchmark_config.json
    python benchmark_production.py --quick  # Quick test (5 minutes)
    python benchmark_production.py --full   # Full test (1 hour)
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List

import aiohttp

try:
    import numpy as np
    from tabulate import tabulate
except ImportError:
    print("Installing required packages...")
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy", "tabulate"])
    import numpy as np
    from tabulate import tabulate


@dataclass
class BenchmarkResult:
    """Results from a single benchmark test"""

    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    requests_per_second: float
    avg_response_time_ms: float
    p50_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    error_rate_percent: float
    timestamp: str


class LightRAGBenchmark:
    """Performance benchmarking suite for LightRAG"""

    def __init__(self, base_url: str, token: str, verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verbose = verbose
        self.results: List[BenchmarkResult] = []

    def log(self, message: str):
        """Log message if verbose mode enabled"""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def _make_request(
        self, session: aiohttp.ClientSession, method: str, endpoint: str, **kwargs
    ) -> tuple[bool, float]:
        """
        Make HTTP request and return (success, response_time_ms)
        """
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"

        start_time = time.time()
        try:
            async with session.request(
                method, url, headers=headers, **kwargs
            ) as response:
                await response.text()
                elapsed_ms = (time.time() - start_time) * 1000
                return (response.status < 400, elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            if self.verbose:
                print(f"Request failed: {e}")
            return (False, elapsed_ms)

    async def benchmark_health_check(self, num_requests: int = 100) -> BenchmarkResult:
        """Benchmark health check endpoint"""
        self.log(f"Running health check benchmark ({num_requests} requests)...")

        response_times = []
        successful = 0
        failed = 0

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            tasks = []
            for _ in range(num_requests):
                task = self._make_request(session, "GET", "/health")
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            for success, response_time in results:
                response_times.append(response_time)
                if success:
                    successful += 1
                else:
                    failed += 1

        duration = time.time() - start_time

        result = BenchmarkResult(
            test_name="Health Check",
            total_requests=num_requests,
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=duration,
            requests_per_second=num_requests / duration,
            avg_response_time_ms=statistics.mean(response_times),
            p50_response_time_ms=np.percentile(response_times, 50),
            p95_response_time_ms=np.percentile(response_times, 95),
            p99_response_time_ms=np.percentile(response_times, 99),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            error_rate_percent=(failed / num_requests) * 100,
            timestamp=datetime.now().isoformat(),
        )

        self.results.append(result)
        return result

    async def benchmark_query(
        self,
        query: str,
        mode: str = "hybrid",
        num_requests: int = 50,
        concurrent: int = 10,
    ) -> BenchmarkResult:
        """Benchmark query endpoint with concurrency"""
        self.log(
            f"Running query benchmark ({num_requests} requests, {concurrent} concurrent)..."
        )

        response_times = []
        successful = 0
        failed = 0

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            # Run in batches to control concurrency
            for i in range(0, num_requests, concurrent):
                batch_size = min(concurrent, num_requests - i)
                tasks = []

                for _ in range(batch_size):
                    task = self._make_request(
                        session, "POST", "/query", json={"query": query, "mode": mode}
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks)

                for success, response_time in results:
                    response_times.append(response_time)
                    if success:
                        successful += 1
                    else:
                        failed += 1

        duration = time.time() - start_time

        result = BenchmarkResult(
            test_name=f"Query ({mode} mode, {concurrent} concurrent)",
            total_requests=num_requests,
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=duration,
            requests_per_second=num_requests / duration,
            avg_response_time_ms=statistics.mean(response_times),
            p50_response_time_ms=np.percentile(response_times, 50),
            p95_response_time_ms=np.percentile(response_times, 95),
            p99_response_time_ms=np.percentile(response_times, 99),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            error_rate_percent=(failed / num_requests) * 100,
            timestamp=datetime.now().isoformat(),
        )

        self.results.append(result)
        return result

    async def benchmark_document_list(self, num_requests: int = 100) -> BenchmarkResult:
        """Benchmark document listing endpoint"""
        self.log(f"Running document list benchmark ({num_requests} requests)...")

        response_times = []
        successful = 0
        failed = 0

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            tasks = []
            for _ in range(num_requests):
                task = self._make_request(session, "GET", "/documents")
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            for success, response_time in results:
                response_times.append(response_time)
                if success:
                    successful += 1
                else:
                    failed += 1

        duration = time.time() - start_time

        result = BenchmarkResult(
            test_name="Document List",
            total_requests=num_requests,
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=duration,
            requests_per_second=num_requests / duration,
            avg_response_time_ms=statistics.mean(response_times),
            p50_response_time_ms=np.percentile(response_times, 50),
            p95_response_time_ms=np.percentile(response_times, 95),
            p99_response_time_ms=np.percentile(response_times, 99),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            error_rate_percent=(failed / num_requests) * 100,
            timestamp=datetime.now().isoformat(),
        )

        self.results.append(result)
        return result

    async def stress_test(
        self, duration_seconds: int = 300, target_rps: int = 50
    ) -> BenchmarkResult:
        """
        Stress test: Maintain target requests per second for specified duration
        """
        self.log(f"Running stress test ({duration_seconds}s at {target_rps} req/s)...")

        response_times = []
        successful = 0
        failed = 0

        start_time = time.time()
        end_time = start_time + duration_seconds

        async with aiohttp.ClientSession() as session:
            while time.time() < end_time:
                batch_start = time.time()

                # Send batch of requests
                tasks = []
                for _ in range(target_rps):
                    task = self._make_request(
                        session,
                        "POST",
                        "/query",
                        json={"query": "test query", "mode": "hybrid"},
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks)

                for success, response_time in results:
                    response_times.append(response_time)
                    if success:
                        successful += 1
                    else:
                        failed += 1

                # Sleep to maintain target RPS
                batch_duration = time.time() - batch_start
                sleep_time = max(0, 1.0 - batch_duration)
                await asyncio.sleep(sleep_time)

        duration = time.time() - start_time
        total_requests = successful + failed

        result = BenchmarkResult(
            test_name=f"Stress Test ({target_rps} req/s)",
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=duration,
            requests_per_second=total_requests / duration,
            avg_response_time_ms=statistics.mean(response_times),
            p50_response_time_ms=np.percentile(response_times, 50),
            p95_response_time_ms=np.percentile(response_times, 95),
            p99_response_time_ms=np.percentile(response_times, 99),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            error_rate_percent=(failed / total_requests) * 100
            if total_requests > 0
            else 0,
            timestamp=datetime.now().isoformat(),
        )

        self.results.append(result)
        return result

    def print_results(self):
        """Print benchmark results in table format"""
        if not self.results:
            print("No benchmark results available")
            return

        # Prepare table data
        headers = [
            "Test Name",
            "Requests",
            "Success",
            "Failed",
            "Duration (s)",
            "RPS",
            "Avg (ms)",
            "P50 (ms)",
            "P95 (ms)",
            "P99 (ms)",
            "Error %",
        ]

        rows = []
        for result in self.results:
            rows.append(
                [
                    result.test_name,
                    result.total_requests,
                    result.successful_requests,
                    result.failed_requests,
                    f"{result.duration_seconds:.2f}",
                    f"{result.requests_per_second:.2f}",
                    f"{result.avg_response_time_ms:.2f}",
                    f"{result.p50_response_time_ms:.2f}",
                    f"{result.p95_response_time_ms:.2f}",
                    f"{result.p99_response_time_ms:.2f}",
                    f"{result.error_rate_percent:.2f}",
                ]
            )

        print("\n" + "=" * 120)
        print("BENCHMARK RESULTS")
        print("=" * 120)
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        print("=" * 120 + "\n")

    def save_results(self, filename: str = "benchmark_results.json"):
        """Save results to JSON file"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "results": [asdict(r) for r in self.results],
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        self.log(f"Results saved to {filename}")

    def check_sla_compliance(self) -> Dict[str, bool]:
        """
        Check if results meet SLA requirements:
        - P95 response time < 500ms
        - Error rate < 0.1%
        - Throughput > 50 req/s
        """
        compliance = {}

        for result in self.results:
            test_compliance = {
                "p95_under_500ms": result.p95_response_time_ms < 500,
                "error_rate_under_0.1%": result.error_rate_percent < 0.1,
                "throughput_over_50rps": result.requests_per_second > 50,
            }

            compliance[result.test_name] = all(test_compliance.values())

            if not compliance[result.test_name]:
                self.log(f"⚠️  SLA violation in {result.test_name}:")
                if not test_compliance["p95_under_500ms"]:
                    self.log(
                        f"   - P95 response time: {result.p95_response_time_ms:.2f}ms (target: <500ms)"
                    )
                if not test_compliance["error_rate_under_0.1%"]:
                    self.log(
                        f"   - Error rate: {result.error_rate_percent:.2f}% (target: <0.1%)"
                    )
                if not test_compliance["throughput_over_50rps"]:
                    self.log(
                        f"   - Throughput: {result.requests_per_second:.2f} req/s (target: >50 req/s)"
                    )

        return compliance


async def run_quick_benchmark(base_url: str, token: str):
    """Run quick benchmark suite (5 minutes)"""
    benchmark = LightRAGBenchmark(base_url, token)

    print("\n🚀 Running QUICK benchmark suite (5 minutes)...\n")

    # Health check
    await benchmark.benchmark_health_check(num_requests=100)

    # Query tests
    await benchmark.benchmark_query(
        query="What is the price for Boeing 787 TURN service?",
        mode="hybrid",
        num_requests=50,
        concurrent=10,
    )

    await benchmark.benchmark_query(
        query="Tell me about contract termination conditions",
        mode="local",
        num_requests=30,
        concurrent=5,
    )

    # Document list
    await benchmark.benchmark_document_list(num_requests=50)

    # Print and save results
    benchmark.print_results()
    benchmark.save_results("benchmark_quick.json")

    # Check SLA compliance
    compliance = benchmark.check_sla_compliance()
    all_compliant = all(compliance.values())

    if all_compliant:
        print("✅ All tests meet SLA requirements")
    else:
        print("❌ Some tests failed SLA requirements")

    return benchmark


async def run_full_benchmark(base_url: str, token: str):
    """Run comprehensive benchmark suite (1 hour)"""
    benchmark = LightRAGBenchmark(base_url, token)

    print("\n🚀 Running FULL benchmark suite (1 hour)...\n")

    # Health check
    await benchmark.benchmark_health_check(num_requests=500)

    # Query tests with different modes
    for mode in ["local", "global", "hybrid", "naive"]:
        await benchmark.benchmark_query(
            query="What is the price for Boeing 787 TURN service?",
            mode=mode,
            num_requests=100,
            concurrent=20,
        )

    # Concurrent query tests
    for concurrent in [5, 10, 20, 50]:
        await benchmark.benchmark_query(
            query="Tell me about contract termination conditions",
            mode="hybrid",
            num_requests=100,
            concurrent=concurrent,
        )

    # Document operations
    await benchmark.benchmark_document_list(num_requests=200)

    # Stress test (5 minutes at 50 req/s)
    await benchmark.stress_test(duration_seconds=300, target_rps=50)

    # Print and save results
    benchmark.print_results()
    benchmark.save_results("benchmark_full.json")

    # Check SLA compliance
    compliance = benchmark.check_sla_compliance()
    all_compliant = all(compliance.values())

    if all_compliant:
        print("✅ All tests meet SLA requirements")
    else:
        print("❌ Some tests failed SLA requirements")

    return benchmark


def main():
    parser = argparse.ArgumentParser(
        description="LightRAG Production Performance Benchmarking"
    )
    parser.add_argument(
        "--url", default="http://localhost:9621", help="Base URL of LightRAG API"
    )
    parser.add_argument("--token", required=True, help="Authentication token")
    parser.add_argument(
        "--quick", action="store_true", help="Run quick benchmark (5 minutes)"
    )
    parser.add_argument(
        "--full", action="store_true", help="Run full benchmark (1 hour)"
    )
    parser.add_argument("--config", help="Load configuration from JSON file")

    args = parser.parse_args()

    # Load config if provided
    if args.config:
        with open(args.config, "r") as f:
            config = json.load(f)
            args.url = config.get("url", args.url)
            args.token = config.get("token", args.token)

    # Run appropriate benchmark
    if args.full:
        asyncio.run(run_full_benchmark(args.url, args.token))
    else:
        # Default to quick benchmark
        asyncio.run(run_quick_benchmark(args.url, args.token))


if __name__ == "__main__":
    main()

#
