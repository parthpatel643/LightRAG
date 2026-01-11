"""
Test script for chronological contract RAG functionality.

This script demonstrates:
1. Sequential document insertion with automatic chronological tracking
2. Temporal metadata propagation to entities and relationships
3. Retrieval of most recent entity information
4. Update history tracking

Usage:
    python build_graph.py
"""

import asyncio
import os

from functions import embedding_func, llm_model_func
from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status


async def query_graph():
    """Test chronological document insertion and temporal tracking."""

    # Initialize LightRAG with NetworkX storage and Azure OpenAI
    rag = LightRAG(
        working_dir=os.getenv("WORKING_DIR", ""),
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        chunk_top_k=int(os.getenv("CHUNK_TOP_K", 5)),
        max_total_tokens=int(os.getenv("MAX_TOTAL_TOKENS", 30000)),
        enable_llm_cache=False,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    # Test actual queries with temporal awareness
    print("\n" + "=" * 80)
    print("🔍 Testing Temporal Query Results")
    print("=" * 80)

    test_queries = [
        "What are the latest rates for Boeing 787 flights that remain overnight and undergo cabin cleaning with lavatory service?",
        "What are the latest rates for Airbus flights that remain overnight and undergo cabin cleaning with lavatory service?",
        "What are the latest rates for a narrow body with water service only?",
        "What are the latest rates for a wide body with lavatory service only?",
        "Tell me about the contract termination conditions?",
    ]

    for query in test_queries:
        print(f"\n❓ Query: {query}")
        print("-" * 80)
        result = await rag.aquery(
            query, param=QueryParam(mode="mix", enable_rerank=False)
        )
        print(f"📝 Answer: {result}")
        print()

    await rag.finalize_storages()

    print("\n" + "=" * 80)
    print("✅ Test completed successfully!")
    print("=" * 80)

    return rag


if __name__ == "__main__":
    # Run the test
    asyncio.run(query_graph())
