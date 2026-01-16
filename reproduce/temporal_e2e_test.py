import os
from datetime import datetime

from lightrag.base import QueryParam
from lightrag.lightrag import DocumentInput, DocumentMetadata, LightRAG
from lightrag.llm.openai import azure_openai_complete, azure_openai_embed


def main():
    work_dir = "temp/temporal_e2e"
    os.makedirs(work_dir, exist_ok=True)

    p1 = "data/processed/test/CW54832-2_-_G2_-_Aircraft_Appearance___Janitorial_-_SEA_Fully Executed.md"
    p2 = "data/processed/test/CW54832-2_-_G2_-_Aircraft_Appearance___Janitorial_-_SEA_READONLY.md"

    with open(p1, "r", encoding="utf-8") as f:
        t1 = f.read()
    with open(p2, "r", encoding="utf-8") as f:
        t2 = f.read()

    # Use Azure OpenAI embedding configured via .env
    rag = LightRAG(
        working_dir=work_dir,
        embedding_func=azure_openai_embed,
        llm_model_func=azure_openai_complete,
    )

    d1 = DocumentInput(
        text=t2,
        metadata=DocumentMetadata(
            doc_type="Contract",
            effective_date=datetime.fromisoformat("2024-06-01"),
            order_index=1,
            source_url=p2,
        ),
    )
    d2 = DocumentInput(
        text=t1,
        metadata=DocumentMetadata(
            doc_type="Contract",
            effective_date=datetime.fromisoformat("2025-01-15"),
            order_index=2,
            source_url=p1,
        ),
    )

    # Initialize storages before insert
    import asyncio

    asyncio.run(rag.initialize_storages())
    track = rag.insert([d1, d2])
    print("Inserted track:", track)

    # Latest-only query
    param_latest = QueryParam()
    param_latest.mode = "temporal_hybrid"
    param_latest.latest_only = True
    param_latest.include_references = True
    # Provide LLM function via param to enable keyword extraction and answering
    param_latest.model_func = azure_openai_complete
    res1 = rag.query("Summarize the current janitorial scope for SEA.", param_latest)
    print("\nLATEST-ONLY RESPONSE:\n")
    print(res1[:800])

    # As-of-date query
    param_date = QueryParam()
    param_date.mode = "temporal_hybrid"
    param_date.query_date = "2025-01-01"
    param_date.include_references = True
    param_date.model_func = azure_openai_complete
    res2 = rag.query("What was the janitorial scope as of 2025-01-01?", param_date)
    print("\nAS-OF-DATE RESPONSE (2025-01-01):\n")
    print(res2[:800])


if __name__ == "__main__":
    main()
