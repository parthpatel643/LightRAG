"""
LightRAG Evaluation Module

Provides evaluation frameworks for assessing RAG system quality:
- SemanticEquivalenceEvaluator: LLM-based semantic equivalence evaluation for temporal queries
- TemporalRAGEvaluator: Temporal/versioned entity evaluation using traditional RAGAS metrics
- BaseRAGEvaluator: Base class with shared evaluation infrastructure

Usage:
    # LLM-based semantic equivalence evaluation (recommended)
    from lightrag.evaluation import SemanticEquivalenceEvaluator

    evaluator = SemanticEquivalenceEvaluator(
        workspace="my_workspace",
        test_dataset_path="path/to/qa.json",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()

    # Temporal evaluation with RAGAS metrics
    from lightrag.evaluation import TemporalRAGEvaluator

    evaluator = TemporalRAGEvaluator(
        workspace="my_workspace",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()

Note: Evaluators are imported lazily to avoid import errors
when ragas/datasets dependencies are not installed.
"""

__all__ = [
    "SemanticEquivalenceEvaluator",
    "TemporalRAGEvaluator",
    "BaseRAGEvaluator",
]


def __getattr__(name):
    """Lazy import to avoid dependency errors when ragas is not installed."""
    if name == "SemanticEquivalenceEvaluator":
        from .semantic_equivalence_evaluator import SemanticEquivalenceEvaluator

        return SemanticEquivalenceEvaluator
    if name == "TemporalRAGEvaluator":
        from .temporal_evaluator import TemporalRAGEvaluator

        return TemporalRAGEvaluator
    if name == "BaseRAGEvaluator":
        from .base_evaluator import BaseRAGEvaluator

        return BaseRAGEvaluator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
