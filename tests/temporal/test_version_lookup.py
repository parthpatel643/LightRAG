"""Version lookup, [vN] enforcement, as-of filtering and nearest-earlier linking."""

from __future__ import annotations

import pytest

from lightrag.operate import (
    _create_version_link_edges,
    _enforce_version_suffix,
    filter_by_version,
    get_version_history,
)

pytestmark = pytest.mark.offline


class _FakeGraph:
    """Just enough graph storage: nodes by name, edge upserts recorded."""

    def __init__(self, names):
        self.nodes = {name: {"description": f"node {name}"} for name in names}
        self.edges = []
        self.batch_calls = 0

    async def get_nodes_batch(self, node_ids):
        self.batch_calls += 1
        return {nid: self.nodes[nid] for nid in node_ids if nid in self.nodes}

    async def get_node(self, node_id):  # must not be used on the query path
        raise AssertionError("per-node reads are not allowed")

    async def upsert_edge(self, src, tgt, edge_data):
        self.edges.append((src, tgt, edge_data))


def _entity(name):
    return {"entity_name": name}


@pytest.mark.asyncio
async def test_versions_beyond_twenty_are_found_in_one_batched_pass():
    graph = _FakeGraph(["Fee [v3]", "Fee [v35]", "Fee [v120]"])
    entities, _ = await filter_by_version(
        [_entity("Fee [v3]")], [], None, None, graph, known_sequences=[3, 35, 120]
    )
    assert [e["entity_name"] for e in entities] == ["Fee [v120]"]
    assert graph.batch_calls <= 2  # versions + unversioned fallback, not 21 reads


@pytest.mark.asyncio
async def test_cutoff_selects_the_version_in_force_on_the_date():
    graph = _FakeGraph(["Fee [v1]", "Fee [v2]", "Fee [v3]"])
    entities, _ = await filter_by_version(
        [_entity("Fee [v3]")],
        [],
        "2024-06-01",
        None,
        graph,
        known_sequences=[1, 2, 3],
        cutoff_sequence=2,
    )
    assert [e["entity_name"] for e in entities] == ["Fee [v2]"]


@pytest.mark.asyncio
async def test_nothing_versioned_is_in_force_before_the_first_document():
    graph = _FakeGraph(["Fee [v1]"])
    entities, _ = await filter_by_version(
        [_entity("Fee [v1]")], [], "2000-01-01", None, graph,
        known_sequences=[1], cutoff_sequence=0,
    )
    assert entities == []


@pytest.mark.asyncio
async def test_unversioned_node_is_the_fallback():
    graph = _FakeGraph(["Policy"])
    entities, _ = await filter_by_version(
        [_entity("Policy")], [], None, None, graph, known_sequences=[1, 2]
    )
    assert [e["entity_name"] for e in entities] == ["Policy"]


@pytest.mark.asyncio
async def test_relations_survive_only_between_selected_versions():
    graph = _FakeGraph(["A [v2]", "B [v2]", "A [v1]", "B [v1]"])
    relations = [
        {"src_id": "A [v1]", "tgt_id": "B [v1]"},
        {"src_id": "A [v2]", "tgt_id": "B [v2]"},
    ]
    _, kept = await filter_by_version(
        [_entity("A [v1]"), _entity("B [v1]")], relations, None, None, graph,
        known_sequences=[1, 2],
    )
    assert kept == [{"src_id": "A [v2]", "tgt_id": "B [v2]"}]


@pytest.mark.asyncio
async def test_storage_errors_propagate_instead_of_hiding_newer_versions():
    class _Broken(_FakeGraph):
        async def get_nodes_batch(self, node_ids):
            raise RuntimeError("graph down")

    with pytest.raises(RuntimeError):
        await filter_by_version(
            [_entity("Fee [v1]")], [], None, None, _Broken([]), known_sequences=[1]
        )


@pytest.mark.asyncio
async def test_version_history_uses_a_large_default_ceiling():
    graph = _FakeGraph(["Fee [v2]", "Fee [v250]"])
    history = await get_version_history("Fee", graph)
    assert [h["version"] for h in history] == [250, 2]


@pytest.mark.asyncio
async def test_link_goes_to_the_nearest_earlier_version_across_gaps():
    graph = _FakeGraph(["Fee [v3]", "Fee [v7]"])
    assert await _create_version_link_edges("Fee [v7]", graph) is True
    src, tgt, data = graph.edges[0]
    assert (src, tgt) == ("Fee [v7]", "Fee [v3]")
    assert data["relationship_type"] == "SUPERSEDES"


@pytest.mark.asyncio
async def test_no_link_when_no_earlier_version_exists():
    graph = _FakeGraph(["Fee [v4]"])
    assert await _create_version_link_edges("Fee [v4]", graph) is False
    assert graph.edges == []


def test_suffix_is_enforced_on_missing_wrong_and_correct_names():
    nodes = {
        "Parking Fee": [{"entity_name": "Parking Fee", "description": "d1"}],
        "Gate [v1]": [{"entity_name": "Gate [v1]", "description": "d2"}],
        "Dock [v4]": [{"entity_name": "Dock [v4]", "description": "d3"}],
    }
    edges = {
        ("Parking Fee", "Gate [v1]"): [
            {"src_id": "Parking Fee", "tgt_id": "Gate [v1]", "description": "r"}
        ],
        ("Dock [v4]", "Dock"): [{"src_id": "Dock [v4]", "tgt_id": "Dock"}],
    }
    new_nodes, new_edges = _enforce_version_suffix(nodes, edges, 4)

    assert set(new_nodes) == {"Parking Fee [v4]", "Gate [v4]", "Dock [v4]"}
    assert new_nodes["Gate [v4]"][0]["entity_name"] == "Gate [v4]"
    assert ("Parking Fee [v4]", "Gate [v4]") in new_edges
    edge = new_edges[("Parking Fee [v4]", "Gate [v4]")][0]
    assert (edge["src_id"], edge["tgt_id"]) == ("Parking Fee [v4]", "Gate [v4]")
    # Both endpoints collapse to the same tagged entity: the self-loop is dropped.
    assert ("Dock [v4]", "Dock [v4]") not in new_edges


def test_suffix_enforcement_is_a_noop_for_unversioned_documents():
    nodes = {"Fee": [{"entity_name": "Fee"}]}
    assert _enforce_version_suffix(nodes, {}, 0) == (nodes, {})
