"""Reusing one LightRAG instance after ``finalize_storages()``.

The API server's workspace switch finalizes the shared instance and then
re-initializes it for another workspace. ``finalize_storages()`` shuts every
model queue (role LLMs, embedding, rerank) down for good, so the instance must
rebuild them, and the role wrappers must bind the new workspace's
``llm_response_cache`` instead of the finalized one.
"""

import numpy as np
import pytest

from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc, Tokenizer

pytestmark = pytest.mark.offline


class _CharTokenizer:
    def encode(self, content: str) -> list[int]:
        return [ord(ch) for ch in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


async def _embed(texts: list[str]) -> np.ndarray:
    return np.ones((len(texts), 16))


async def _rerank(query, documents, **kwargs):
    return [{"index": i, "relevance_score": 1.0} for i in range(len(documents))]


@pytest.mark.asyncio
async def test_reset_for_workspace_restores_model_queues_after_finalize(tmp_path):
    seen_caches = []

    async def llm(prompt, hashing_kv=None, **kwargs):
        seen_caches.append(hashing_kv)
        return "ok"

    rag = LightRAG(
        working_dir=str(tmp_path),
        workspace="ws_a",
        llm_model_func=llm,
        embedding_func=EmbeddingFunc(embedding_dim=16, max_token_size=4096, func=_embed),
        rerank_model_func=_rerank,
        tokenizer=Tokenizer("char", _CharTokenizer()),
    )
    await rag.initialize_storages()
    await rag.finalize_storages()

    rag.workspace = "ws_b"
    rag._reset_for_workspace()
    await rag.initialize_storages()
    try:
        assert await rag.role_llm_funcs["keyword"]("p") == "ok"
        assert await rag.role_llm_funcs["query"]("p") == "ok"
        assert seen_caches[-1] is rag.llm_response_cache
        assert rag.llm_response_cache.workspace == "ws_b"

        assert (await rag.embedding_func(["x"])).shape == (1, 16)
        assert rag.chunks_vdb.embedding_func is rag.embedding_func

        reranked = await rag.rerank_model_func(query="q", documents=["d"])
        assert reranked == [{"index": 0, "relevance_score": 1.0}]

        # Query-time reranking reads the function from the storages' config.
        storage_rerank = rag.text_chunks.global_config["rerank_model_func"]
        assert storage_rerank is rag.rerank_model_func
        assert await storage_rerank(query="q", documents=["d"]) == reranked
    finally:
        await rag.finalize_storages()
