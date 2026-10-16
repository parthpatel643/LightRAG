"""Vector-search chunks must carry their document version into the context.

Vector-store metadata holds only full_doc_id/content/file_path, so chunks found
by similarity search arrived with sequence_index 0. The reference list then
showed the newest document twice — once as "[1] file [v8]" (entity-linked
chunks) and once unversioned (vector chunks) — and the answer model treated
the latest rate table as non-authoritative.
"""

import pytest

from lightrag.base import QueryParam
from lightrag.operate import _format_reference_path, _merge_all_chunks

pytestmark = pytest.mark.offline


class AlignedChunkStore:
    """get_by_ids aligned with the requested ids (None for unknown ids)."""

    def __init__(self, rows: dict):
        self.rows = rows
        self.global_config = {}

    async def get_by_ids(self, ids):
        return [self.rows.get(i) for i in ids]


@pytest.mark.asyncio
async def test_vector_chunks_get_their_stored_sequence_index():
    store = AlignedChunkStore(
        {
            "doc-a-chunk-006": {"content": "B757 RON MXN 10,000.00", "sequence_index": 8},
        }
    )
    merged = await _merge_all_chunks(
        filtered_entities=[],
        filtered_relations=[],
        vector_chunks=[
            {
                "chunk_id": "doc-a-chunk-006",
                "content": "B757 RON MXN 10,000.00",
                "file_path": "Amendment No.7.md",
            },
            {"chunk_id": "doc-x-chunk-001", "content": "orphan", "file_path": "x.md"},
        ],
        query="",
        text_chunks_db=store,
        query_param=QueryParam(mode="agentic", enable_rerank=False),
        chunk_tracking={},
    )

    by_id = {c["chunk_id"]: c for c in merged}
    assert by_id["doc-a-chunk-006"]["sequence_index"] == 8
    assert by_id["doc-x-chunk-001"]["sequence_index"] == 0


@pytest.mark.asyncio
async def test_chunks_carry_their_document_effective_date():
    store = AlignedChunkStore(
        {
            "doc-p-chunk-001": {
                "content": "entered into this 15th day of March, 2010",
                "sequence_index": 1,
                "effective_date": "2010-03-15",
            },
            "doc-q-chunk-002": {"content": "x", "sequence_index": 2, "effective_date": "unknown"},
        }
    )
    merged = await _merge_all_chunks(
        filtered_entities=[],
        filtered_relations=[],
        vector_chunks=[
            {"chunk_id": "doc-p-chunk-001", "content": "a", "file_path": "PHX.md"},
            {"chunk_id": "doc-q-chunk-002", "content": "b", "file_path": "Q.md"},
        ],
        query="",
        text_chunks_db=store,
        query_param=QueryParam(mode="agentic", enable_rerank=False),
        chunk_tracking={},
    )

    by_id = {c["chunk_id"]: c for c in merged}
    assert by_id["doc-p-chunk-001"]["effective_date"] == "2010-03-15"
    assert by_id["doc-q-chunk-002"].get("effective_date") in (None, "unknown")


@pytest.mark.parametrize(
    "seq, date, expected",
    [
        (1, "2010-03-15", "PHX.md [v1] (effective 2010-03-15)"),
        (3, "unknown", "PHX.md [v3]"),
        (0, None, "PHX.md"),
        (0, "2025-01-01", "PHX.md (effective 2025-01-01)"),
    ],
)
def test_reference_path_shows_version_and_known_effective_date(seq, date, expected):
    assert _format_reference_path("PHX.md", seq, date) == expected
