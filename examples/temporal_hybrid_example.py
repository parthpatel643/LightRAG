"""
Temporal-Hybrid Retrieval Example (NetworkX + NanoVector + JSON)

This script demonstrates chronology-aware retrieval using:
- Graph: NetworkXStorage (local GraphML)
- Vector: NanoVectorDBStorage (local JSON)
- KV: default JSON storages

It inserts two small documents with effective_date and order_index metadata,
then queries in temporal_hybrid mode using latest_only and query_date.

Run:
  uvicorn lightrag.api.lightrag_server:app --reload   # optional API
Or run the script directly:
  python examples/temporal_hybrid_example.py
"""

import asyncio
from datetime import datetime
from typing import List

from lightrag.base import QueryParam
from lightrag.functions import embedding_func, llm_model_func
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.lightrag import DocumentInput, DocumentMetadata, LightRAG


async def main():
    rag = LightRAG(
        working_dir="./rag_storage",
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
        kv_storage="JsonKVStorage",
        doc_status_storage="JsonDocStatusStorage",
        workspace="demo",
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
    )

    await rag.initialize_storages()
    await initialize_pipeline_status()

    # Prepare two docs representing base lease and an amendment
    docs: List[DocumentInput] = [
        DocumentInput(
            text="""
            ---
            title: Base Lease
            clause: Basic Rent (Base)
            ---
            The Basic Rent is USD 100,000 per month.
            """.strip(),
            metadata=DocumentMetadata(
                doc_type="lease",
                effective_date=datetime.fromisoformat("2024-01-01"),
                order_index=1,
                source_url=None,
            ),
        ),
        DocumentInput(
            text="""
            ---
            title: Amendment 2
            clause: Basic Rent (Amended)
            ---
            The Basic Rent is updated to USD 110,000 per month.
            """.strip(),
            metadata=DocumentMetadata(
                doc_type="amendment",
                effective_date=datetime.fromisoformat("2024-07-01"),
                order_index=2,
                source_url=None,
            ),
        ),
    ]

    # Insert with chronology metadata
    track_id = await rag.ainsert(docs)
    print(f"Inserted docs track_id: {track_id}")

    # Latest-only query: returns only the latest doc_order_index per file
    param_latest = QueryParam(
        mode="temporal_hybrid", latest_only=True, include_references=True
    )
    latest_result = await rag.aquery_data(
        "What is the current basic rent?", param=param_latest
    )
    print("\nLatest-only result:")
    print(latest_result.get("metadata"))
    print([c.get("content") for c in latest_result.get("data", {}).get("chunks", [])])

    # As-of-date query: returns CURRENT as of the given date
    param_asof = QueryParam(
        mode="temporal_hybrid", query_date="2024-06-30", include_references=True
    )
    asof_result = await rag.aquery_data(
        "What was the basic rent as of 2024-06-30?", param=param_asof
    )
    print("\nAs-of-date result:")
    print(asof_result.get("metadata"))
    print([c.get("content") for c in asof_result.get("data", {}).get("chunks", [])])

    response = await rag.aquery(
        "What was the basic rent as of 2024-06-30?", param=param_asof
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
