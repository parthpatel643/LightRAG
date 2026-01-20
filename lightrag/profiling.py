"""
profiling.py - Comprehensive Profiling Utilities for LightRAG

This module provides profiling utilities including:
- cProfile-based function profiling
- Memory profiling with memory_profiler
- Timing analysis with detailed breakdowns
- Profile statistics analysis and export
"""

import cProfile
import io
import pstats
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Optional

from lightrag.utils import logger


class ProfileStats:
    """Container for profiling statistics."""

    def __init__(self, profile_file: str = None, prof: cProfile.Profile = None):
        self.profile_file = profile_file
        self.prof = prof
        self.stats = None
        if prof:
            self.stats = pstats.Stats(prof)

    def print_stats(
        self, sort_by: str = "cumulative", top_n: int = 20, strip_dirs: bool = True
    ):
        """
        Print profiling statistics to console.

        Args:
            sort_by: Sort key ('cumulative', 'time', 'calls')
            top_n: Number of top functions to display
            strip_dirs: Strip directory names from file paths
        """
        if not self.stats:
            logger.warning("No profiling stats available")
            return

        logger.info("\n" + "=" * 80)
        logger.info("PROFILING STATISTICS")
        logger.info("=" * 80)

        if strip_dirs:
            self.stats.strip_dirs()

        self.stats.sort_stats(sort_by)
        self.stats.print_stats(top_n)
        logger.info("=" * 80 + "\n")

    def save_stats(self, output_file: str, format_type: str = "prof"):
        """
        Save profiling statistics to file.

        Args:
            output_file: Output file path
            format_type: Format type ('prof' for binary, 'txt' for text)
        """
        if not self.prof and not self.stats:
            logger.warning("No profiling data to save")
            return

        if format_type == "prof":
            self.prof.dump_stats(output_file)
            logger.info(f"Profile data saved to {output_file}")
            logger.info(f"View with: python -m pstats {output_file}")
        elif format_type == "txt":
            with open(output_file, "w") as f:
                s = io.StringIO()
                ps = pstats.Stats(self.prof, stream=s)
                ps.strip_dirs()
                ps.sort_stats("cumulative")
                ps.print_stats()
                f.write(s.getvalue())
            logger.info(f"Profile stats saved to {output_file}")

    def get_top_functions(self, n: int = 10) -> list[tuple]:
        """
        Get top N functions by cumulative time.

        Returns:
            List of tuples: (filename, lineno, funcname, ncalls, tottime, cumtime)
        """
        if not self.stats:
            return []

        self.stats.sort_stats("cumulative")
        stats_list = []
        for func, stat in list(self.stats.stats.items())[:n]:
            filename, lineno, funcname = func
            stats_list.append((filename, lineno, funcname, stat[0], stat[2], stat[3]))
        return stats_list


class TimingBreakdown:
    """Track and report timing breakdowns for code sections."""

    def __init__(self, name: str = "Timing Breakdown"):
        self.name = name
        self.sections = {}
        self.start_time = None

    def mark(self, section_name: str):
        """Mark start/end of a section."""
        current_time = time.time()

        if section_name not in self.sections:
            self.sections[section_name] = {
                "start": current_time,
                "duration": 0,
                "count": 0,
            }
        else:
            # End section
            duration = current_time - self.sections[section_name]["start"]
            self.sections[section_name]["duration"] += duration
            self.sections[section_name]["count"] += 1

    def report(self):
        """Print timing report."""
        logger.info("\n" + "=" * 60)
        logger.info(f"{self.name}")
        logger.info("=" * 60)

        total_time = sum(s["duration"] for s in self.sections.values())

        for section_name, data in sorted(
            self.sections.items(), key=lambda x: x[1]["duration"], reverse=True
        ):
            duration = data["duration"]
            count = data["count"]
            percentage = (duration / total_time * 100) if total_time > 0 else 0

            logger.info(
                f"  {section_name:30} {duration:8.3f}s ({percentage:6.2f}%) "
                f"[{count} calls]"
            )

        logger.info("-" * 60)
        logger.info(f"  Total: {total_time:.3f}s")
        logger.info("=" * 60 + "\n")

    @contextmanager
    def section(self, name: str):
        """Context manager for timing a section."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            if name not in self.sections:
                self.sections[name] = {"duration": 0, "count": 0}
            self.sections[name]["duration"] += duration
            self.sections[name]["count"] += 1


def profile_function(
    output_file: Optional[str] = None, sort_by: str = "cumulative", top_n: int = 20
):
    """
    Decorator for profiling a function using cProfile.

    Args:
        output_file: Optional file to save profile data
        sort_by: Sort key for stats ('cumulative', 'time', 'calls')
        top_n: Number of top functions to display

    Example:
        @profile_function(output_file='profile.prof')
        def my_function():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            prof = cProfile.Profile()
            prof.enable()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                prof.disable()

                # Display stats
                profile_stats = ProfileStats(prof=prof)
                profile_stats.print_stats(sort_by=sort_by, top_n=top_n, strip_dirs=True)

                # Save if requested
                if output_file:
                    profile_stats.save_stats(output_file, format_type="prof")
                    profile_stats.save_stats(
                        output_file.replace(".prof", ".txt"), format_type="txt"
                    )

        return wrapper

    return decorator


def profile_async_function(
    output_file: Optional[str] = None, sort_by: str = "cumulative", top_n: int = 20
):
    """
    Decorator for profiling an async function using cProfile.

    Args:
        output_file: Optional file to save profile data
        sort_by: Sort key for stats
        top_n: Number of top functions to display

    Example:
        @profile_async_function(output_file='profile.prof')
        async def my_async_function():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            prof = cProfile.Profile()
            prof.enable()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                prof.disable()

                # Display stats
                profile_stats = ProfileStats(prof=prof)
                profile_stats.print_stats(sort_by=sort_by, top_n=top_n, strip_dirs=True)

                # Save if requested
                if output_file:
                    profile_stats.save_stats(output_file, format_type="prof")
                    profile_stats.save_stats(
                        output_file.replace(".prof", ".txt"), format_type="txt"
                    )

        return wrapper

    return decorator


class ProfileContext:
    """Context manager for profiling a code block."""

    def __init__(
        self,
        name: str = "Code Block",
        output_file: Optional[str] = None,
        top_n: int = 20,
        show_timing: bool = True,
    ):
        self.name = name
        self.output_file = output_file
        self.top_n = top_n
        self.show_timing = show_timing
        self.prof = cProfile.Profile()
        self.start_time = None
        self.elapsed_time = None

    def __enter__(self):
        logger.info(f"\n📊 Starting profiling: {self.name}")
        self.start_time = time.time()
        self.prof.enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.prof.disable()
        self.elapsed_time = time.time() - self.start_time

        if self.show_timing:
            logger.info(f"⏱️  Elapsed time: {self.elapsed_time:.3f}s")

        # Display stats
        profile_stats = ProfileStats(prof=self.prof)
        profile_stats.print_stats(sort_by="cumulative", top_n=self.top_n)

        # Save if requested
        if self.output_file:
            profile_stats.save_stats(self.output_file, format_type="prof")
            profile_stats.save_stats(
                self.output_file.replace(".prof", ".txt"), format_type="txt"
            )

        return False  # Don't suppress exceptions


def get_memory_usage() -> dict:
    """
    Get current memory usage.

    Returns:
        Dictionary with memory stats (requires psutil)
    """
    try:
        import psutil

        process = psutil.Process()
        info = process.memory_info()
        return {
            "rss_mb": info.rss / 1024 / 1024,  # Resident Set Size
            "vms_mb": info.vms / 1024 / 1024,  # Virtual Memory Size
            "percent": process.memory_percent(),
        }
    except ImportError:
        logger.warning("psutil not installed. Install it for memory profiling.")
        return {}


def report_memory():
    """Log current memory usage."""
    mem = get_memory_usage()
    if mem:
        logger.info(
            f"Memory: {mem['rss_mb']:.1f} MB RSS, "
            f"{mem['vms_mb']:.1f} MB VMS, {mem['percent']:.2f}%"
        )
