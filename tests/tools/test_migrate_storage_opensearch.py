"""OpenSearch node seeding in scripts/migrate_storage.py."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

opensearchpy_helpers = pytest.importorskip("opensearchpy.helpers")

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_storage.py"
_spec = importlib.util.spec_from_file_location("migrate_storage_under_test", _SCRIPT)
migrate_storage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_storage)


def _helper():
    helper = migrate_storage.OpenSearchHelper()
    helper._client = object()
    helper._index_name = "ws_chunk_entity_relation-nodes"
    return helper


NODES = {f"N{i}": {"entity_type": "data", "description": f"node {i}"} for i in range(5)}


def test_rejected_documents_fail_loudly(monkeypatch):
    """A capacity-limited AOSS collection rejects documents per item; bulk()
    with raise_on_error=False returns them instead of raising, and the seeding
    step used to report every node as indexed."""

    def fake_bulk(client, actions, raise_on_error):
        assert raise_on_error is False
        errors = [
            {
                "index": {
                    "_id": a["_id"],
                    "status": 402,
                    "error": "maximum OCU capacity reached",
                }
            }
            for a in actions
            if a["_id"] in {"N1", "N3"}
        ]
        return len(actions) - len(errors), errors

    monkeypatch.setattr(opensearchpy_helpers, "bulk", fake_bulk)
    with pytest.raises(RuntimeError, match=r"2 of 5 .*maximum OCU capacity reached"):
        _helper().bulk_index_nodes(NODES, batch_size=2)


def test_transport_failure_fails_loudly(monkeypatch):
    def fake_bulk(client, actions, raise_on_error):
        raise ConnectionError("endpoint unreachable")

    monkeypatch.setattr(opensearchpy_helpers, "bulk", fake_bulk)
    with pytest.raises(RuntimeError, match=r"5 of 5 .*endpoint unreachable"):
        _helper().bulk_index_nodes(NODES, batch_size=2)


def test_successful_seed_returns_indexed_count(monkeypatch):
    seen = []

    def fake_bulk(client, actions, raise_on_error):
        seen.extend(a["_id"] for a in actions)
        return len(actions), []

    monkeypatch.setattr(opensearchpy_helpers, "bulk", fake_bulk)
    assert _helper().bulk_index_nodes(NODES, batch_size=2) == 5
    assert sorted(seen) == sorted(NODES)


def test_dry_run_touches_nothing(monkeypatch):
    def fake_bulk(*args, **kwargs):
        raise AssertionError("dry run must not call bulk")

    monkeypatch.setattr(opensearchpy_helpers, "bulk", fake_bulk)
    assert _helper().bulk_index_nodes(NODES, batch_size=2, dry_run=True) == 5
