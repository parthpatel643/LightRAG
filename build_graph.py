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
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.utils import setup_logger

setup_logger("lightrag", level="WARN")

# Configuration
WORKING_DIR = "./data/storage"


async def build_graph():
    """Test chronological document insertion and temporal tracking."""

    # Initialize LightRAG with NetworkX storage and Azure OpenAI
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        entity_extract_max_gleaning=3,
        chunk_token_size=2000,
        chunk_overlap_token_size=200,
        embedding_func_max_async=4,
        llm_model_max_async=4,
        max_parallel_insert=1,
        enable_llm_cache=False
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    print("=" * 80)
    print("Building Chronological Contract Graph with Temporal Metadata Tracking")
    print("=" * 80)

    # Simulate contract document chronology
    documents = [
        # {
        #     "name": "CW54832-Aircraft-Appearance-Janitorial-G2-SEA-Signed.md",
        #     "path": "./data/processed/CW54832-Aircraft-Appearance-Janitorial-G2-SEA-Signed.md",
        # },
        {
            "name": "amendment_1",
            "path": "./data/processed/amendment_1.md",
        },
        {
            "name": "amendment_2",
            "path": "./data/processed/amendment_2.md",
        },
        {
            "name": "amendment_3",
            "path": "./data/processed/amendment_3.md",
        },
    ]

    # Insert documents sequentially
    print("\n📄 Inserting documents in chronological order...")
    for i, doc in enumerate(documents, 1):
        print(f"\n{i}. Inserting: {doc['name']}")
        with open(doc["path"], "r", encoding="utf-8") as f:
            content = f.read()
        await rag.ainsert(content, file_paths=doc["path"])
        print(f"   ✓ Insertion order: {rag._document_insertion_counter}")

    print("\n" + "=" * 80)
    print("✅ All documents inserted successfully")
    print("=" * 80)

    await rag.finalize_storages()

    return rag


if __name__ == "__main__":
    # Run the test
    asyncio.run(build_graph())
