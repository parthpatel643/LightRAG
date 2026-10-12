"""Neptune: Gremlin escaping, and the OpenSearch mirror's retry / replay queue."""

from __future__ import annotations

import pytest

from lightrag.kg.neptune_impl import NeptuneGraphStorage, _gremlin_escape
from lightrag.kg.neptune_opensearch_impl import NeptuneOpenSearchGraphStorage

pytestmark = pytest.mark.offline


def test_gremlin_escape_handles_quotes_and_line_breaks():
    assert _gremlin_escape("a'b") == "a\\'b"
    assert _gremlin_escape("a\\b") == "a\\\\b"
    assert _gremlin_escape("line1\nline2\r\t") == "line1\\nline2\\r\\t"


@pytest.mark.asyncio
async def test_has_node_escapes_its_argument():
    storage = NeptuneGraphStorage.__new__(NeptuneGraphStorage)
    storage.workspace = "ws"
    captured = {}

    async def fake_submit(query):
        captured["query"] = query
        return [False]

    storage._submit_query = fake_submit
    await NeptuneGraphStorage.has_node.__wrapped__(storage, "x').drop().V('y")
    assert "x\\').drop().V(\\'y" in captured["query"]


class _FlakyOpenSearch:
    def __init__(self, failures=0):
        self.failures = failures
        self.indexed = {}

    async def index(self, index, id, body):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("cluster unavailable")
        self.indexed[id] = body

    async def delete(self, index, id, params=None):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("cluster unavailable")
        self.indexed.pop(id, None)


def _storage(client):
    storage = NeptuneOpenSearchGraphStorage.__new__(NeptuneOpenSearchGraphStorage)
    storage._os_client = client
    storage._os_nodes_index = "nodes"
    storage._MIRROR_BACKOFF_SECONDS = 0
    return storage


@pytest.mark.asyncio
async def test_transient_failures_are_retried_without_queueing():
    client = _FlakyOpenSearch(failures=2)
    storage = _storage(client)
    await storage._mirror("n1", {"entity_id": "n1"})
    assert client.indexed == {"n1": {"entity_id": "n1"}}
    assert storage.mirror_backlog() == 0


@pytest.mark.asyncio
async def test_persistent_failure_is_queued_then_replayed_on_flush():
    client = _FlakyOpenSearch(failures=3)
    storage = _storage(client)
    await storage._mirror("n1", {"entity_id": "n1"})
    assert storage.mirror_backlog() == 1 and client.indexed == {}

    await storage._replay_pending()  # cluster healthy again
    assert client.indexed == {"n1": {"entity_id": "n1"}}
    assert storage.mirror_backlog() == 0


@pytest.mark.asyncio
async def test_last_write_for_a_node_wins_in_the_queue():
    client = _FlakyOpenSearch(failures=100)
    storage = _storage(client)
    await storage._mirror("n1", {"entity_id": "n1", "v": 1})
    await storage._mirror("n1", None)  # then it was deleted
    assert storage._pending() == {"n1": None}
    client.failures = 0
    await storage._replay_pending()
    assert client.indexed == {} and storage.mirror_backlog() == 0


@pytest.mark.asyncio
async def test_replay_stops_at_the_first_failure_and_keeps_the_rest():
    client = _FlakyOpenSearch(failures=100)
    storage = _storage(client)
    await storage._mirror("n1", {"entity_id": "n1"})
    await storage._mirror("n2", {"entity_id": "n2"})
    assert storage.mirror_backlog() == 2
    await storage._replay_pending()
    assert storage.mirror_backlog() == 2
