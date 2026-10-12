"""Sequence indices are derived from doc_status, under the enqueue lock, after dedupe."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from lightrag import LightRAG
from lightrag.temporal.sequence_index import (
    allocate_sequence_indices,
    collect_sequence_dates,
    resolve_cutoff_sequence,
)
from lightrag.utils import EmbeddingFunc, Tokenizer

pytestmark = pytest.mark.offline


class _Tokenizer:
    def encode(self, content: str) -> list[int]:
        return [ord(ch) for ch in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


async def _embed(texts: list[str]) -> np.ndarray:
    return np.ones((len(texts), 8), dtype=float)


async def _llm(*args, **kwargs) -> str:
    return "ok"


async def _build_rag(tmp_path) -> LightRAG:
    rag = LightRAG(
        working_dir=str(tmp_path / "wd"),
        workspace=f"seq-{uuid4().hex[:8]}",
        llm_model_func=_llm,
        embedding_func=EmbeddingFunc(embedding_dim=8, max_token_size=8192, func=_embed),
        tokenizer=Tokenizer("mock-tokenizer", _Tokenizer()),
        max_parallel_insert=1,
    )
    await rag.initialize_storages()
    return rag


def _metadata_of(rag) -> dict[str, dict]:
    return {
        doc["file_path"]: doc.get("metadata", {})
        for doc in rag.doc_status._data.values()
        if "file_path" in doc and not (doc.get("metadata") or {}).get("is_duplicate")
    }


class _FakeDocStatus:
    def __init__(self, metadatas):
        self._docs = [
            (f"doc-{i}", SimpleNamespace(metadata=m)) for i, m in enumerate(metadatas)
        ]

    async def get_docs_paginated(self, page=1, page_size=50, **_kwargs):
        start = (page - 1) * page_size
        return self._docs[start : start + page_size], len(self._docs)


@pytest.mark.asyncio
async def test_allocation_is_max_plus_one_and_skips_duplicate_rows():
    storage = _FakeDocStatus(
        [
            {"sequence_index": 1, "effective_date": "2024-01-01"},
            {"sequence_index": 4},
            {"is_duplicate": True, "sequence_index": 9},
            {"note": "no index"},
        ]
    )
    assert await collect_sequence_dates(storage) == {1: "2024-01-01", 4: "unknown"}
    assert await allocate_sequence_indices(storage, 2) == [5, 6]


@pytest.mark.asyncio
async def test_allocation_scans_every_page():
    storage = _FakeDocStatus([{"sequence_index": i} for i in range(1, 451)])
    assert await allocate_sequence_indices(storage, 1) == [451]


def test_cutoff_is_none_without_a_reference_date():
    assert resolve_cutoff_sequence({1: "2024-01-01"}, None) is None


def test_cutoff_picks_the_last_document_in_force():
    dates = {1: "2023-01-01", 2: "2024-06-01", 3: "2025-01-01"}
    assert resolve_cutoff_sequence(dates, "2024-12-31") == 2
    assert resolve_cutoff_sequence(dates, "2025-01-01") == 3
    assert resolve_cutoff_sequence(dates, "2022-12-31") == 0


def test_undated_documents_inherit_the_preceding_date():
    dates = {1: "2023-01-01", 2: "unknown", 3: "2025-01-01"}
    assert resolve_cutoff_sequence(dates, "2024-01-01") == 2
    # A leading undated base is always in force.
    assert resolve_cutoff_sequence({1: "unknown", 2: "2025-01-01"}, "2020-01-01") == 1


def test_a_malformed_reference_date_is_ignored():
    assert resolve_cutoff_sequence({1: "2023-01-01"}, "tomorrow") is None


@pytest.mark.asyncio
async def test_enqueue_numbers_documents_in_input_order_without_counter_rows(tmp_path):
    rag = await _build_rag(tmp_path)
    try:
        await rag.apipeline_enqueue_documents(
            ["first doc", "second doc"], file_paths=["a.txt", "b.txt"], track_id="t-1"
        )
        meta = _metadata_of(rag)
        assert meta["a.txt"]["sequence_index"] == 1
        assert meta["b.txt"]["sequence_index"] == 2
        assert not any(key.startswith("__") for key in rag.doc_status._data)
    finally:
        await rag.finalize_storages()


@pytest.mark.asyncio
async def test_a_duplicate_does_not_consume_an_index(tmp_path):
    rag = await _build_rag(tmp_path)
    try:
        await rag.apipeline_enqueue_documents("hello", file_paths="a.txt", track_id="t-1")
        await rag.apipeline_enqueue_documents("hello", file_paths="a.txt", track_id="t-2")
        await rag.apipeline_enqueue_documents("other", file_paths="b.txt", track_id="t-3")
        meta = _metadata_of(rag)
        assert meta["a.txt"]["sequence_index"] == 1
        assert meta["b.txt"]["sequence_index"] == 2
    finally:
        await rag.finalize_storages()


@pytest.mark.asyncio
async def test_explicit_index_and_date_alias_are_preserved(tmp_path):
    rag = await _build_rag(tmp_path)
    try:
        await rag.apipeline_enqueue_documents(
            ["amendment"],
            file_paths=["amend.txt"],
            track_id="t-1",
            metadata=[{"sequence_index": 7, "date": "2024-05-01", "doc_type": "amendment"}],
        )
        meta = _metadata_of(rag)["amend.txt"]
        assert meta["sequence_index"] == 7
        assert meta["effective_date"] == "2024-05-01"
        assert meta["doc_type"] == "amendment"
    finally:
        await rag.finalize_storages()


@pytest.mark.asyncio
async def test_date_without_index_is_not_discarded(tmp_path):
    rag = await _build_rag(tmp_path)
    try:
        await rag.apipeline_enqueue_documents(
            ["x"], file_paths=["x.txt"], track_id="t-1", metadata={"effective_date": "2024-02-02"}
        )
        meta = _metadata_of(rag)["x.txt"]
        assert meta["sequence_index"] == 1
        assert meta["effective_date"] == "2024-02-02"
    finally:
        await rag.finalize_storages()
