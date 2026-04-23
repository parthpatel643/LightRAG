"""
profiling.py - RAG Pipeline Profiler for LightRAG

Tracks wall-clock time for:
  - RAG instance initialization (constructor + storage init)
  - Per-query pipeline phases:
      * entities_vdb       – entity vector DB retrieval (_get_node_data)
      * relationships_vdb  – relationship vector DB retrieval (_get_edge_data)
      * chunks_vdb         – chunk vector DB retrieval (_get_vector_context)
      * rerank             – reranking step
      * llm                – answer generation (LLM call)
      * local_computation  – remaining time (filtering, merging, prompt assembly, etc.)

Usage
-----
    from lightrag.profiling import RAGProfiler

    profiler = RAGProfiler()

    # --- Initialization ---
    with profiler.track_init():
        rag = LightRAG(...)
        await rag.initialize_storages()

    # --- Per-query ---
    with profiler.track_query("What is the service fee?"):
        response = await rag.aquery(query, param=param)

    profiler.report()           # pretty-print to logger
    profiler.as_dict()          # raw numbers as a dict
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

from lightrag.utils import logger

# ---------------------------------------------------------------------------
# ContextVar that operate.py reads to record phase timings.
# The value is a _QueryTrace instance (set by RAGProfiler.track_query) or None.
# ---------------------------------------------------------------------------
_active_trace: ContextVar[Optional["_QueryTrace"]] = ContextVar(
    "_active_trace", default=None
)


@dataclass
class _QueryTrace:
    """Mutable accumulator for a single query's phase timings (in seconds)."""

    query: str
    entities_vdb: float = 0.0
    relationships_vdb: float = 0.0
    chunks_vdb: float = 0.0
    rerank: float = 0.0
    llm: float = 0.0
    total: float = 0.0


@dataclass
class RAGProfiler:
    """
    Lightweight wall-clock profiler for LightRAG instantiation and query phases.

    Thread / asyncio safety: uses a ContextVar so concurrent queries each get
    their own trace without interfering with each other.
    """

    init_time: Optional[float] = field(default=None, init=False)
    _queries: list[_QueryTrace] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    # Public context managers
    # ------------------------------------------------------------------

    @contextmanager
    def track_init(self):
        """
        Context manager that measures the time to build a LightRAG instance
        (construction + storage initialisation).

        Example::

            with profiler.track_init():
                rag = LightRAG(...)
                await rag.initialize_storages()
        """
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.init_time = time.perf_counter() - t0

    @contextmanager
    def track_query(self, query: str):
        """
        Context manager that enables per-phase timing for one query.
        Must wrap the full ``rag.aquery(...)`` call.

        Example::

            with profiler.track_query(query):
                response = await rag.aquery(query, param=param)
        """
        trace = _QueryTrace(query=query)
        token = _active_trace.set(trace)
        t0 = time.perf_counter()
        try:
            yield trace
        finally:
            trace.total = time.perf_counter() - t0
            _active_trace.reset(token)
            self._queries.append(trace)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def _local_computation(t: _QueryTrace) -> float:
        """Time not accounted for by tracked phases (filtering, merging, prompt assembly, etc.)."""
        tracked = t.entities_vdb + t.relationships_vdb + t.chunks_vdb + t.rerank + t.llm
        return max(t.total - tracked, 0.0)

    def report(self) -> None:
        """Print a formatted timing report to the logger."""
        lines = ["\n" + "=" * 65, "RAG PROFILER REPORT", "=" * 65]

        if self.init_time is not None:
            lines.append(f"  {'Initialization':<30} {self.init_time:>8.3f}s")
            lines.append("-" * 65)

        for i, t in enumerate(self._queries, 1):
            local = self._local_computation(t)
            short_q = t.query if len(t.query) <= 50 else t.query[:47] + "..."
            lines.append(f"\n  Query {i}: {short_q}")
            lines.append(f"  {'  entities_vdb retrieval':<30} {t.entities_vdb:>8.3f}s")
            lines.append(
                f"  {'  relationships_vdb retrieval':<30} {t.relationships_vdb:>8.3f}s"
            )
            lines.append(f"  {'  chunks_vdb retrieval':<30} {t.chunks_vdb:>8.3f}s")
            lines.append(f"  {'  rerank':<30} {t.rerank:>8.3f}s")
            lines.append(f"  {'  answer generation (LLM)':<30} {t.llm:>8.3f}s")
            lines.append(f"  {'  local computation':<30} {local:>8.3f}s")
            lines.append(f"  {'  ── total query':<30} {t.total:>8.3f}s")

        lines.append("=" * 65)
        logger.info("\n".join(lines))

    def as_dict(self) -> dict:
        """Return all timings as a plain dictionary."""
        return {
            "init_time": self.init_time,
            "queries": [
                {
                    "query": t.query,
                    "entities_vdb_s": t.entities_vdb,
                    "relationships_vdb_s": t.relationships_vdb,
                    "chunks_vdb_s": t.chunks_vdb,
                    "rerank_s": t.rerank,
                    "llm_s": t.llm,
                    "local_computation_s": self._local_computation(t),
                    "total_s": t.total,
                }
                for t in self._queries
            ],
        }


# ---------------------------------------------------------------------------
# Internal helpers used by operate.py to record phase timings
# ---------------------------------------------------------------------------

@contextmanager
def _phase(name: str):
    """
    Context manager used inside operate.py to time a named phase.
    No-ops when no profiler trace is active.

    Recognised names: entities_vdb, relationships_vdb, chunks_vdb, rerank, llm
    """
    trace = _active_trace.get()
    if trace is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        current = getattr(trace, name, 0.0)
        setattr(trace, name, current + elapsed)


# ---------------------------------------------------------------------------
# TimingBreakdown – simple lap-timer used by the CLI (build.py / query.py)
# ---------------------------------------------------------------------------

class TimingBreakdown:
    """
    Simple paired-mark lap timer for coarse CLI-level phase reporting.

    Call ``mark(phase_name)`` twice with the same name to record a lap:
    the first call starts the timer, the second call stops it.

    Example::

        t = TimingBreakdown("Query Phases")
        t.mark("initialization")
        ...do work...
        t.mark("initialization")
        t.report()
    """

    def __init__(self, title: str = "Timing") -> None:
        self.title = title
        self._pending: dict[str, float] = {}
        self._laps: list[tuple[str, float]] = []

    def mark(self, name: str) -> None:
        if name in self._pending:
            elapsed = time.perf_counter() - self._pending.pop(name)
            self._laps.append((name, elapsed))
        else:
            self._pending[name] = time.perf_counter()

    def report(self) -> None:
        from lightrag.utils import logger as _logger

        lines = ["\n" + "=" * 55, self.title, "=" * 55]
        total = 0.0
        for name, elapsed in self._laps:
            lines.append(f"  {name:<28} {elapsed:>8.3f}s")
            total += elapsed
        lines.append("-" * 55)
        lines.append(f"  {'total':<28} {total:>8.3f}s")
        lines.append("=" * 55)
        _logger.info("\n".join(lines))
