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

from functions_openai import embedding_func, llm_model_func
from lightrag import LightRAG, QueryParam
from lightrag.kg.networkx_impl import NetworkXStorage
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import setup_logger

setup_logger("lightrag", level="WARN")

# Configuration
WORKING_DIR = "./data/storage"

async def query_graph():
    """Test chronological document insertion and temporal tracking."""

    # Initialize LightRAG with NetworkX storage and Azure OpenAI
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        # rerank_model_func=rerank_model_func,
        entity_extract_max_gleaning=3,
        chunk_token_size=2000,
        chunk_overlap_token_size=200,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status() 

    # Test temporal queries
    print("\n🔍 Testing temporal query capabilities...\n")

    # Get graph storage to test temporal methods
    graph: NetworkXStorage = rag.chunk_entity_relation_graph
    graph_data = await graph._get_graph()

    print(f"Total entities in graph: {graph_data.number_of_nodes()}")
    print(f"Total relationships in graph: {graph_data.number_of_edges()}")

    # Test actual queries with temporal awareness
    print("\n" + "=" * 80)
    print("🔍 Testing Temporal Query Results")
    print("=" * 80)

    test_queries = [
        "What are the latest rates for Boeing 787 flights that remain overnight and undergo cabin cleaning with lavatory service?",
        # "What are the latest rates for Airbus flights that remain overnight and undergo cabin cleaning with lavatory service?",
        # "What are the latest rates for a narrow body with water service only?",
        # "Tell me about the contract termination conditions?",
    ]

    for query in test_queries:
        print(f"\n❓ Query: {query}")
        print("-" * 80)
        result = await rag.aquery(query, param=QueryParam(mode="mix", enable_rerank=False))
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
