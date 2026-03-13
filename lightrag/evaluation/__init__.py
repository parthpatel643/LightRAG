"""
LightRAG Evaluation Module

RAGAS-based evaluation framework for assessing RAG system quality.
Supports workspace-specific evaluation datasets and temporal query evaluation.

Usage:
    # Standard evaluation
    from lightrag.evaluation import RAGEvaluator
    evaluator = RAGEvaluator()
    results = await evaluator.run()

    # Temporal evaluation (for versioned entities)
    from lightrag.evaluation import TemporalRAGEvaluator
    evaluator = TemporalRAGEvaluator(
        workspace="my_workspace",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()

    # Workspace evaluation CLI
    python -m lightrag.evaluation.eval_workspace --workspace my_workspace --mode temporal

Note: Evaluators are imported lazily to avoid import errors
when ragas/datasets dependencies are not installed.
"""

__all__ = [
    "RAGEvaluator",
    "BaseRAGEvaluator",
    "TemporalRAGEvaluator",
    "StandardRAGEvaluator",
]


def __getattr__(name):
    """Lazy import to avoid dependency errors when ragas is not installed."""
    if name == "RAGEvaluator":
        from .eval_rag_quality import RAGEvaluator

        return RAGEvaluator
    if name == "BaseRAGEvaluator":
        from .base_evaluator import BaseRAGEvaluator

        return BaseRAGEvaluator
    if name == "TemporalRAGEvaluator":
        from .temporal_evaluator import TemporalRAGEvaluator

        return TemporalRAGEvaluator
    if name == "StandardRAGEvaluator":
        from .eval_workspace import StandardRAGEvaluator

        return StandardRAGEvaluator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
