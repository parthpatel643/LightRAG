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
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status


async def build_graph():
    """Test chronological document insertion and temporal tracking."""

    # Initialize LightRAG with NetworkX storage and Azure OpenAI
    rag = LightRAG(
        working_dir=os.getenv("WORKING_DIR", ""),
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        entity_extract_max_gleaning=3,
        chunk_token_size=int(os.getenv("CHUNK_SIZE", 2000)),
        chunk_overlap_token_size=int(os.getenv("CHUNK_OVERLAP_SIZE", 200)),
        embedding_func_max_async=int(os.getenv("EMBEDDING_FUNC_MAX_ASYNC", 4)),
        llm_model_max_async=int(os.getenv("MAX_ASYNC", 4)),
        max_parallel_insert=int(os.getenv("MAX_PARALLEL_INSERT", 2)),
        enable_llm_cache=False,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    print("=" * 80)
    print("Building Chronological Contract Graph with Temporal Metadata Tracking")
    print("=" * 80)

    # Simulate contract document chronology
    documents = [
        {
            "name": "base_agreement",
            "path": "data/processed/sea-cabin-cleaning/CW54832-Aircraft-Appearance-Janitorial-G2-SEA-Signed.md",
        },
        {
            "name": "amendment_1",
            "path": "data/processed/sea-cabin-cleaning/SEA_-_G2_Cabin_Cleaning_and_Janitorial_Amendment_2023 - G2 Signed.md",
        },
        {
            "name": "amendment_2",
            "path": "data/processed/sea-cabin-cleaning/CW54832-2_-_G2_-_Aircraft_Appearance___Janitorial_-_SEA_READONLY.md",
        },
        {
            "name": "amendment_3",
            "path": "data/processed/sea-cabin-cleaning/CW54832-2_-_G2_-_Aircraft_Appearance___Janitorial_-_SEA_Fully Executed.md",
        },
    ]

    # Insert documents sequentially
    print("\n📄 Inserting documents in chronological order...")
    for i, doc in enumerate(documents, 1):
        print(f"\n{i}. Inserting: {doc['name']}")
        with open(doc["path"], "r", encoding="utf-8") as f:
            content = f.read()
        await rag.ainsert(content, file_paths=[doc["path"]])
        print(f"   ✓ Insertion order: {rag._document_insertion_counter}")

    print("\n" + "=" * 80)
    print("✅ All documents inserted successfully")
    print("=" * 80)

    await rag.finalize_storages()

    return rag


if __name__ == "__main__":
    # Run the test
    asyncio.run(build_graph())
