#!/usr/bin/env python
"""
debug_query_process.py - Debug Script for LightRAG Query Process

This script helps new users understand and inspect each step of the LightRAG query process.
It provides detailed logging, intermediate result storage, and step-by-step execution tracking.

Usage:
    # Run with default settings
    python tests/debug_query_process.py --query "What is the service fee?"

    # Run with custom working directory
    python tests/debug_query_process.py --query "What are the key terms?" --working-dir "data/output/my-project"

    # Run with specific query mode
    python tests/debug_query_process.py --query "Tell me about changes" --mode temporal --date 2024-01-01

    # Keep intermediate results in debug output
    python tests/debug_query_process.py --query "What happened?" --keep-results

    # Verbose debug output with API details
    python tests/debug_query_process.py --query "Query" --verbose
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from lightrag import LightRAG, QueryParam
from lightrag.functions import embedding_func, llm_model_func

# ============================================================================
# Debug Logger Configuration
# ============================================================================


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for better readability."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
        "STEP": "\033[94m",  # Blue
        "DATA": "\033[92m",  # Light Green
        "SEPARATOR": "\033[90m",  # Dark Gray
    }

    def format(self, record):
        if record.levelname == "INFO":
            # Check if it's a step marker
            if "[STEP]" in record.msg:
                color = self.COLORS["STEP"]
            else:
                color = self.COLORS["INFO"]
        else:
            color = self.COLORS.get(record.levelname, self.COLORS["RESET"])

        record.msg = f"{color}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)


def setup_debug_logger(debug_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Set up a debug logger that logs to both file and console.

    Args:
        debug_dir: Directory to store debug logs
        verbose: If True, show more detailed debug output

    Returns:
        Configured logger instance
    """
    debug_dir.mkdir(parents=True, exist_ok=True)

    debug_logger = logging.getLogger("lightrag_debug")
    debug_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Clear existing handlers
    debug_logger.handlers.clear()

    # File handler
    log_file = debug_dir / "debug.log"
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    debug_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    console_formatter = ColoredFormatter(
        "%(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    debug_logger.addHandler(console_handler)

    return debug_logger


# ============================================================================
# Debug State Management
# ============================================================================


class DebugState:
    """Manages debug execution state and intermediate results."""

    def __init__(self, debug_dir: Path):
        self.debug_dir = debug_dir
        self.results: Dict[str, Any] = {}
        self.step_count = 0
        self.timings: Dict[str, float] = {}
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def log_step(self, step_name: str, description: str) -> None:
        """Log the start of a debug step."""
        self.step_count += 1
        print(
            f"\n{ColoredFormatter.COLORS['STEP']}{'=' * 70}{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['STEP']}[STEP {self.step_count}] {step_name}{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['STEP']}{description}{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['STEP']}{'=' * 70}{ColoredFormatter.COLORS['RESET']}\n"
        )

    def store_result(self, key: str, value: Any, save_to_file: bool = True) -> None:
        """
        Store an intermediate result.

        Args:
            key: Result identifier
            value: Result value (dict, list, str, etc.)
            save_to_file: Whether to save to JSON file
        """
        self.results[key] = value

        if save_to_file:
            result_file = self.debug_dir / f"{key}.json"
            try:
                if isinstance(value, (dict, list)):
                    with open(result_file, "w") as f:
                        json.dump(value, f, indent=2, default=str)
                else:
                    with open(result_file, "w") as f:
                        json.dump({"value": str(value)}, f, indent=2)
            except Exception as e:
                print(f"⚠️  Could not save {key} to file: {e}")

    def store_timing(self, key: str, duration: float) -> None:
        """Store execution timing for a step."""
        self.timings[key] = duration

    def print_summary(self) -> None:
        """Print a summary of all debug information."""
        print(
            f"\n{ColoredFormatter.COLORS['SEPARATOR']}{'=' * 70}{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['SEPARATOR']}DEBUG SUMMARY{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['SEPARATOR']}{'=' * 70}{ColoredFormatter.COLORS['RESET']}\n"
        )

        # Timings
        if self.timings:
            print(
                f"{ColoredFormatter.COLORS['DATA']}Execution Timings:{ColoredFormatter.COLORS['RESET']}"
            )
            total_time = sum(self.timings.values())
            for step, duration in self.timings.items():
                percentage = (duration / total_time * 100) if total_time > 0 else 0
                print(f"  • {step}: {duration:.3f}s ({percentage:.1f}%)")
            print(f"  • TOTAL: {total_time:.3f}s\n")

        # Stored results
        if self.results:
            print(
                f"{ColoredFormatter.COLORS['DATA']}Stored Results:{ColoredFormatter.COLORS['RESET']}"
            )
            for key in self.results.keys():
                print(f"  • {key} → {self.debug_dir / f'{key}.json'}")
            print()

        # Log file
        print(
            f"{ColoredFormatter.COLORS['DATA']}Debug Log:{ColoredFormatter.COLORS['RESET']}"
        )
        print(f"  → {self.debug_dir / 'debug.log'}\n")


# ============================================================================
# Query Process Debugging
# ============================================================================


class QueryDebugger:
    """Orchestrates the debug query process with step-by-step execution."""

    def __init__(
        self,
        working_dir: str,
        debug_dir: Path,
        verbose: bool = False,
    ):
        self.working_dir = Path(working_dir)
        self.debug_dir = debug_dir
        self.debug_logger = setup_debug_logger(debug_dir, verbose)
        self.state = DebugState(debug_dir)
        self.rag: Optional[LightRAG] = None
        self.verbose = verbose

    async def step_1_validate_environment(self) -> bool:
        """Step 1: Validate working directory and environment."""
        self.state.log_step(
            "Environment Validation",
            "Checking working directory and LightRAG environment...",
        )

        start_time = datetime.now()

        try:
            # Check working directory
            if not self.working_dir.exists():
                self.debug_logger.error(
                    f"❌ Working directory not found: {self.working_dir}"
                )
                self.debug_logger.error(
                    "💡 Please run build_graph.py first to ingest documents"
                )
                return False

            self.debug_logger.info(f"✓ Working directory exists: {self.working_dir}")

            # Check for storage files
            rag_storage = self.working_dir / "rag_storage"
            if rag_storage.exists():
                storage_files = list(rag_storage.rglob("*"))
                self.debug_logger.info(f"✓ Found {len(storage_files)} storage files")
                self.state.store_result(
                    "storage_scan",
                    {
                        "location": str(rag_storage),
                        "file_count": len(storage_files),
                        "files": [
                            str(f.relative_to(rag_storage)) for f in storage_files[:20]
                        ],  # First 20
                    },
                )

            # Check for configuration
            config_files = list(self.working_dir.glob("*.ini")) + list(
                self.working_dir.glob("config.*")
            )
            if config_files:
                self.debug_logger.info(f"✓ Found {len(config_files)} config files")
                self.state.store_result(
                    "config_files", [str(f.name) for f in config_files]
                )

            self.debug_logger.info("✅ Environment validation passed")

            duration = (datetime.now() - start_time).total_seconds()
            self.state.store_timing("Step 1: Environment Validation", duration)
            return True

        except Exception as e:
            self.debug_logger.error(f"❌ Environment validation failed: {e}")
            return False

    async def step_2_initialize_lightrag(self) -> bool:
        """Step 2: Initialize LightRAG instance."""
        self.state.log_step(
            "LightRAG Initialization",
            "Creating LightRAG instance with embedding and LLM functions...",
        )

        start_time = datetime.now()

        try:
            self.debug_logger.info(f"📁 Working directory: {self.working_dir}")
            self.debug_logger.info(
                "🔧 Initializing with default embedding and LLM functions..."
            )

            self.rag = LightRAG(
                working_dir=str(self.working_dir),
                llm_model_func=llm_model_func,
                embedding_func=embedding_func,
                enable_llm_cache=False,
            )

            self.debug_logger.info("✓ LightRAG instance created")

            # Store initialization info
            init_info = {
                "working_dir": str(self.working_dir),
                "llm_model_func": llm_model_func.__name__,
                "embedding_func": embedding_func.__name__,
                "llm_cache_enabled": False,
            }
            self.state.store_result("lightrag_init", init_info)

            self.debug_logger.info("✅ LightRAG initialization completed")

            duration = (datetime.now() - start_time).total_seconds()
            self.state.store_timing("Step 2: LightRAG Initialization", duration)
            return True

        except Exception as e:
            self.debug_logger.error(f"❌ LightRAG initialization failed: {e}")
            import traceback

            self.debug_logger.debug(traceback.format_exc())
            return False

    async def step_3_initialize_storages(self) -> bool:
        """Step 3: Initialize storage backends."""
        self.state.log_step(
            "Storage Initialization",
            "Initializing vector, graph, and KV storage backends...",
        )

        start_time = datetime.now()

        try:
            if not self.rag:
                raise RuntimeError("LightRAG not initialized")

            self.debug_logger.info("🗄️  Initializing storage backends...")
            await self.rag.initialize_storages()
            self.debug_logger.info("✓ Storages initialized")

            # Get storage status
            if hasattr(self.rag, "storage_status"):
                status = await self.rag.storage_status()
                self.debug_logger.info(f"✓ Storage status: {status}")
                self.state.store_result("storage_status", status, save_to_file=False)

            self.debug_logger.info("✅ Storage initialization completed")

            duration = (datetime.now() - start_time).total_seconds()
            self.state.store_timing("Step 3: Storage Initialization", duration)
            return True

        except Exception as e:
            self.debug_logger.error(f"❌ Storage initialization failed: {e}")
            import traceback

            self.debug_logger.debug(traceback.format_exc())
            return False

    async def step_4_prepare_query(
        self, query: str, mode: str, date: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Step 4: Prepare and validate query parameters."""
        self.state.log_step(
            "Query Preparation",
            f"Preparing query with mode '{mode}' and date '{date}'...",
        )

        start_time = datetime.now()

        try:
            query_info = {
                "query_text": query,
                "mode": mode,
                "reference_date": date if mode == "temporal" else None,
                "timestamp": datetime.now().isoformat(),
            }

            self.debug_logger.info(f"📝 Query text: {query}")
            self.debug_logger.info(f"🔄 Query mode: {mode}")
            if mode == "temporal" and date:
                self.debug_logger.info(f"📅 Reference date: {date}")

            # Create QueryParam
            param = QueryParam(
                mode=mode, reference_date=date if mode == "temporal" else None
            )

            query_info["query_param"] = {
                "mode": param.mode,
                "reference_date": param.reference_date,
            }

            self.state.store_result("query_info", query_info)
            self.debug_logger.info("✅ Query preparation completed")

            duration = (datetime.now() - start_time).total_seconds()
            self.state.store_timing("Step 4: Query Preparation", duration)

            return query_info

        except Exception as e:
            self.debug_logger.error(f"❌ Query preparation failed: {e}")
            import traceback

            self.debug_logger.debug(traceback.format_exc())
            return None

    async def step_5_execute_query(
        self, query: str, mode: str, date: Optional[str]
    ) -> Optional[str]:
        """Step 5: Execute the actual query."""
        self.state.log_step(
            "Query Execution", "Executing the query and retrieving results..."
        )

        start_time = datetime.now()

        try:
            if not self.rag:
                raise RuntimeError("LightRAG not initialized")

            param = QueryParam(
                mode=mode, reference_date=date if mode == "temporal" else None
            )

            self.debug_logger.info("⏳ Executing query (this may take a moment)...")
            response = await self.rag.aquery(query, param=param)

            duration = (datetime.now() - start_time).total_seconds()
            self.state.store_timing("Step 5: Query Execution", duration)

            self.debug_logger.info(f"✓ Query completed in {duration:.2f}s")

            # Store response
            response_info = {
                "response_text": response,
                "length": len(response) if response else 0,
                "execution_time": duration,
            }
            self.state.store_result("query_response", response_info)

            return response

        except Exception as e:
            self.debug_logger.error(f"❌ Query execution failed: {e}")
            import traceback

            self.debug_logger.debug(traceback.format_exc())
            return None

    async def step_6_analyze_results(self, response: str) -> bool:
        """Step 6: Analyze and store query results."""
        self.state.log_step(
            "Results Analysis",
            "Analyzing query results and storing intermediate data...",
        )

        try:
            self.debug_logger.info(f"📊 Response length: {len(response)} characters")
            self.debug_logger.info(f"📝 Response preview: {response[:200]}...")

            # Count words and sentences
            words = len(response.split())
            sentences = len([s for s in response.split(".") if s.strip()])

            analysis = {
                "total_characters": len(response),
                "total_words": words,
                "total_sentences": sentences,
                "avg_word_length": len(response) / words if words > 0 else 0,
            }

            self.debug_logger.info("📈 Statistics:")
            for key, value in analysis.items():
                self.debug_logger.info(f"   • {key}: {value}")

            self.state.store_result("response_analysis", analysis)
            self.debug_logger.info("✅ Results analysis completed")

            return True

        except Exception as e:
            self.debug_logger.error(f"❌ Results analysis failed: {e}")
            return False

    async def run_debug_query(
        self,
        query: str,
        mode: str = "hybrid",
        date: Optional[str] = None,
    ) -> bool:
        """
        Run the complete debug query process.

        Args:
            query: Query string
            mode: Query mode
            date: Reference date for temporal mode

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"\n{ColoredFormatter.COLORS['SEPARATOR']}")
            print(
                f"{ColoredFormatter.COLORS['SEPARATOR']}🔍 LIGHTRAG DEBUG QUERY PROCESS"
            )
            print(
                f"{ColoredFormatter.COLORS['SEPARATOR']}Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print(
                f"{ColoredFormatter.COLORS['SEPARATOR']}"
                + "=" * 70
                + f"{ColoredFormatter.COLORS['RESET']}\n"
            )

            # Step 1: Environment validation
            if not await self.step_1_validate_environment():
                return False

            # Step 2: Initialize LightRAG
            if not await self.step_2_initialize_lightrag():
                return False

            # Step 3: Initialize storages
            if not await self.step_3_initialize_storages():
                return False

            # Step 4: Prepare query
            query_info = await self.step_4_prepare_query(query, mode, date)
            if not query_info:
                return False

            # Step 5: Execute query
            response = await self.step_5_execute_query(query, mode, date)
            if response is None:
                return False

            # Step 6: Analyze results
            await self.step_6_analyze_results(response)

            # Print final result
            print(f"\n{ColoredFormatter.COLORS['DATA']}{'=' * 70}")
            print("🎯 FINAL RESPONSE")
            print(f"{'=' * 70}{ColoredFormatter.COLORS['RESET']}\n")
            print(response)
            print(
                f"\n{ColoredFormatter.COLORS['DATA']}{'=' * 70}{ColoredFormatter.COLORS['RESET']}\n"
            )

            # Print summary
            self.state.print_summary()

            print(
                f"{ColoredFormatter.COLORS['SEPARATOR']}✅ Debug query process completed successfully"
            )
            print(
                f"{ColoredFormatter.COLORS['SEPARATOR']}End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{ColoredFormatter.COLORS['RESET']}\n"
            )

            return True

        except Exception as e:
            self.debug_logger.error(f"❌ Unexpected error in debug query process: {e}")
            import traceback

            self.debug_logger.debug(traceback.format_exc())
            return False


# ============================================================================
# Main Entry Point
# ============================================================================


async def main():
    parser = argparse.ArgumentParser(
        description="Debug LightRAG Query Process",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic query
  python tests/debug_query_process.py --query "What is the service fee?"
  
  # With temporal mode and date
  python tests/debug_query_process.py --query "What changed?" --mode temporal --date 2024-01-01
  
  # Verbose output with custom working directory
  python tests/debug_query_process.py --query "Query text" --working-dir "data/output/project" --verbose
        """,
    )

    parser.add_argument(
        "--query", type=str, required=True, help="Query string to debug"
    )
    parser.add_argument(
        "--working-dir",
        type=str,
        default="data/output/sea-cabin-cleaning",
        help="LightRAG working directory (default: data/output/sea-cabin-cleaning)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="hybrid",
        choices=["local", "global", "hybrid", "temporal", "naive", "mix", "bypass"],
        help="Query mode (default: hybrid)",
    )
    parser.add_argument(
        "--date", type=str, help="Reference date for temporal mode (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose debug output"
    )
    parser.add_argument(
        "--debug-dir",
        type=str,
        default="temp/debug_output",
        help="Directory to store debug output (default: temp/debug_output)",
    )
    parser.add_argument(
        "--keep-results",
        action="store_true",
        help="Keep intermediate results for inspection",
    )

    args = parser.parse_args()

    # Create debug directory
    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Create debugger
    debugger = QueryDebugger(
        working_dir=args.working_dir,
        debug_dir=debug_dir,
        verbose=args.verbose,
    )

    # Run debug query
    success = await debugger.run_debug_query(
        query=args.query,
        mode=args.mode,
        date=args.date,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
