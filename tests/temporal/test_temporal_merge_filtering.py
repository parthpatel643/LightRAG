"""
Unit tests for the temporal query pipeline's Stage 3.5 merged-chunk filter.

Tests cover the Root Cause B fix (2026-07-11): scoping the max_sequence gate
in `_apply_temporal_merged_chunk_filter` (extracted from `_build_query_context`
in lightrag/operate.py) to vector-search-path chunks only. Entity/relation-path
chunks bypass the gate, trusting filter_by_version()'s per-base-name
arbitration (lightrag/temporal/filtering.py) instead of a single global
max_sequence computed across the whole workspace.

Background: filter_by_version() keeps an entity/relation unless a newer
version of that SAME base name exists. The original (pre-fix) Stage 3.5
re-gated the fully merged chunk set (vector + entity + relation-derived
chunks) by one global max_sequence, which stripped entity/relation-path
chunks the instant ANY newer document existed anywhere in the workspace --
even when that newer document had no competing version of the entity/
relation that anchored the chunk (e.g. a small pricing-only amendment with
no Term/Notice content of its own).

Run with:
    pytest tests/test_temporal_merge_filtering.py -v
"""

import pytest

from lightrag.operate import _apply_temporal_merged_chunk_filter


class MockTextChunksDB:
    """Mock text_chunks_db exposing only get_by_ids(), the sole method
    `_apply_temporal_merged_chunk_filter` calls on it."""

    def __init__(self, chunk_data: dict):
        self._chunk_data = chunk_data

    async def get_by_ids(self, ids):
        return [self._chunk_data[cid] for cid in ids if cid in self._chunk_data]


def make_chunk(chunk_id: str, content: str = "content") -> dict:
    return {"chunk_id": chunk_id, "content": content, "file_path": "doc.md"}


class TestEntityRelationPathBypassesGate:
    """Entity/relation-path chunks with no newer-version competitor should
    survive even when max_sequence (derived from some unrelated document
    elsewhere in the workspace) is higher."""

    @pytest.mark.asyncio
    async def test_entity_path_chunk_survives_despite_lower_sequence(self):
        # chunk-005 belongs to sequence 1 (the base contract) and was
        # reached via the entity/relation path -- i.e. filter_by_version()
        # already determined its source entity is not superseded. A
        # separate, unrelated document at sequence 2 exists elsewhere in
        # the workspace, making the global max_sequence=2.
        chunk = make_chunk("chunk-005")
        merged_chunks = [chunk]
        vector_path_chunk_ids = set()  # reached via entity path only
        chunk_data = {"chunk-005": {"_id": "chunk-005", "sequence_index": 1}}
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        assert filtered == [chunk]
        assert stats["entity_relation_path_kept"] == 1
        assert stats["vector_path_kept"] == 0


class TestVectorPathStaysGated:
    """Vector-search-path chunks have no KG-aware supersession arbitration,
    so Stage 1's guarantee (only max_sequence chunks survive) must still
    hold end-to-end through Stage 3.5."""

    @pytest.mark.asyncio
    async def test_stale_vector_path_chunk_is_stripped(self):
        stale_chunk = make_chunk("chunk-v1")
        merged_chunks = [stale_chunk]
        vector_path_chunk_ids = {"chunk-v1"}
        chunk_data = {"chunk-v1": {"_id": "chunk-v1", "sequence_index": 1}}
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        assert filtered == []
        assert stats["vector_path_kept"] == 0
        assert stats["entity_relation_path_kept"] == 0

    @pytest.mark.asyncio
    async def test_current_vector_path_chunk_is_kept(self):
        current_chunk = make_chunk("chunk-v2")
        merged_chunks = [current_chunk]
        vector_path_chunk_ids = {"chunk-v2"}
        chunk_data = {"chunk-v2": {"_id": "chunk-v2", "sequence_index": 2}}
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        assert filtered == [current_chunk]
        assert stats["vector_path_kept"] == 1


class TestMixedChunkResidualLimitation:
    """Regression test documenting the accepted residual limitation: a
    single physical chunk can only be kept or dropped as a whole. If a
    chunk contains multiple entities and only some are superseded, a stale
    fact riding along with a non-superseded entity can leak back in. This
    is unchanged by the Root Cause B fix and is explicitly out of scope
    (see plan's Root Cause A/B coupling discussion) -- it is documented
    here, not silently passed over."""

    @pytest.mark.asyncio
    async def test_mixed_chunk_with_superseded_and_current_entities_is_kept_whole(
        self,
    ):
        # One physical chunk was linked to two entities during Stage 3
        # merge: one entity has a newer-version competitor (superseded),
        # one does not. filter_by_version() arbitrates entities, not
        # chunks, so by the time _merge_all_chunks produces this chunk via
        # entity_chunks, there is no per-sentence granularity available.
        # The chunk is entity/relation-path (not vector-path), so it
        # bypasses the gate and is kept whole -- including the stale
        # sentence riding along with the still-current one.
        mixed_chunk = make_chunk(
            "chunk-mixed",
            content="Loading dock: Gate 4. Parking fee: $10/day.",
        )
        merged_chunks = [mixed_chunk]
        vector_path_chunk_ids = set()  # reached via entity path
        chunk_data = {"chunk-mixed": {"_id": "chunk-mixed", "sequence_index": 1}}
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        # Documents the accepted leak: the chunk (and its stale $10/day
        # sentence) survives because the "Loading dock" entity that
        # anchored it to entity_chunks was not itself superseded.
        assert filtered == [mixed_chunk]
        assert stats["entity_relation_path_kept"] == 1


class TestOriginalBugShapeStillGuarded:
    """Reproduce the original commit-05544610 bug shape: pure vector search
    returning both a stale and a current chunk by raw similarity, with no
    KG awareness at all. Stage 1 (upstream of this function, unmodified by
    this fix) is production's actual defense against this; this test
    proves the vector-path branch of Stage 3.5 preserves that guarantee as
    a second gate, so the fix doesn't regress the original bug this stage
    was built to close."""

    @pytest.mark.asyncio
    async def test_vector_search_stale_and_current_chunks_both_present(self):
        stale_chunk = make_chunk("v1-chunk")
        current_chunk = make_chunk("v2-chunk")
        # In production, Stage 1 (operate.py, upstream of this function)
        # would already have filtered search_result["vector_chunks"] to
        # max_sequence, so vector_path_chunk_ids would in practice only
        # ever contain "v2-chunk". This test simulates both being present
        # to prove Stage 3.5's vector-path branch is still a correct
        # independent gate for the vector path.
        merged_chunks = [stale_chunk, current_chunk]
        vector_path_chunk_ids = {"v1-chunk", "v2-chunk"}
        chunk_data = {
            "v1-chunk": {"_id": "v1-chunk", "sequence_index": 1},
            "v2-chunk": {"_id": "v2-chunk", "sequence_index": 2},
        }
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        assert filtered == [current_chunk]
        assert stats["vector_path_kept"] == 1


class TestEmptyAndEdgeCases:
    """Edge cases for the extracted filter function."""

    @pytest.mark.asyncio
    async def test_empty_merged_chunks(self):
        db = MockTextChunksDB({})
        filtered, stats = await _apply_temporal_merged_chunk_filter(
            [], set(), max_sequence=1, text_chunks_db=db
        )
        assert filtered == []
        assert stats == {
            "seq_counts": {},
            "vector_path_kept": 0,
            "entity_relation_path_kept": 0,
        }

    @pytest.mark.asyncio
    async def test_chunk_missing_from_db_is_dropped(self):
        # If a chunk_id can't be resolved in text_chunks_db at all, it is
        # silently excluded -- matches original (pre-extraction) behavior,
        # where the loop only appends when chunk_data is found.
        chunk = make_chunk("missing-chunk")
        db = MockTextChunksDB({})  # empty: get_by_ids returns nothing
        filtered, stats = await _apply_temporal_merged_chunk_filter(
            [chunk], set(), max_sequence=1, text_chunks_db=db
        )
        assert filtered == []

    @pytest.mark.asyncio
    async def test_seq_counts_tracks_both_paths(self):
        vector_chunk = make_chunk("v-chunk")
        entity_chunk = make_chunk("e-chunk")
        merged_chunks = [vector_chunk, entity_chunk]
        vector_path_chunk_ids = {"v-chunk"}
        chunk_data = {
            "v-chunk": {"_id": "v-chunk", "sequence_index": 2},
            "e-chunk": {"_id": "e-chunk", "sequence_index": 1},
        }
        db = MockTextChunksDB(chunk_data)

        filtered, stats = await _apply_temporal_merged_chunk_filter(
            merged_chunks, vector_path_chunk_ids, max_sequence=2, text_chunks_db=db
        )

        assert filtered == [vector_chunk, entity_chunk]
        assert stats["seq_counts"] == {2: 1, 1: 1}
        assert stats["vector_path_kept"] == 1
        assert stats["entity_relation_path_kept"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
