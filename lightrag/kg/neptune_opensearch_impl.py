"""
Neptune + OpenSearch Graph Storage Implementation for LightRAG.

This module provides NeptuneOpenSearchGraphStorage, which extends NeptuneGraphStorage
with a properly initialized async OpenSearch client for full-text search operations.
Neptune remains the primary graph store (Gremlin traversals, node/edge CRUD), while
OpenSearch provides full-text search over node descriptions and entity labels.

Node data is dual-written to both Neptune (graph) and an OpenSearch nodes index
(search) so that search_labels() and full_text_search() can leverage OpenSearch's
text analysis capabilities instead of the raw requests.post stub in the base module.

Users pair this graph storage with whatever KV, vector, and doc-status backends
they prefer (e.g. the default Json/NanoVectorDB file-based stores, Mongo, Redis, etc.).

Environment variables:
    Neptune: NEPTUNE_ENDPOINT, NEPTUNE_PORT, NEPTUNE_REGION, NEPTUNE_USE_IAM
    OpenSearch: OPENSEARCH_HOSTS, OPENSEARCH_USER, OPENSEARCH_PASSWORD,
                OPENSEARCH_USE_SSL, OPENSEARCH_VERIFY_CERTS
"""

from dataclasses import dataclass, field
from typing import Any

from ..utils import logger
from .opensearch_impl import (
    ClientManager,
    _build_index_name,
)
from .neptune_impl import NeptuneGraphStorage


@dataclass
class NeptuneOpenSearchGraphStorage(NeptuneGraphStorage):
    """
    Composite graph storage: Neptune for Gremlin traversals, OpenSearch for
    full-text search operations.

    Extends NeptuneGraphStorage with:
    - A proper AsyncOpenSearch client (via ClientManager) replacing the raw
      requests.post stub in the base class.
    - Dual-write on upsert_node / delete_node / remove_nodes so the OpenSearch
      nodes index stays in sync with Neptune.
    - search_labels() using async multi_match queries against OpenSearch.
    - full_text_search() for description-level search correlated back to
      Neptune graph nodes.
    """

    _os_client: Any = field(default=None, repr=False, init=False, compare=False)
    _os_nodes_index: str = field(default="", repr=False, init=False, compare=False)

    async def initialize(self):
        """Initialize both Neptune (Gremlin) and OpenSearch (async) clients."""
        # Initialize Neptune connection (Gremlin client, IAM auth, etc.)
        await super().initialize()

        # Initialize a proper async OpenSearch client via the shared ClientManager
        try:
            self._os_client = await ClientManager.get_client()
            logger.info(
                "NeptuneOpenSearchGraphStorage: async OpenSearch client initialized"
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenSearch client: {e}")
            raise

        # Build the nodes index name matching the OpenSearch graph storage convention
        workspace_label = self._get_workspace_label()
        _ws, _ns, base_name = _build_index_name(workspace_label, self.namespace)
        self._os_nodes_index = f"{base_name}-nodes"

        # Ensure the nodes index exists for search operations
        try:
            from opensearchpy.exceptions import RequestError

            if not await self._os_client.indices.exists(index=self._os_nodes_index):
                from .opensearch_impl import (
                    _get_index_number_of_shards,
                    _get_index_number_of_replicas,
                )

                body = {
                    "mappings": {
                        "dynamic": True,
                        "properties": {
                            "entity_id": {"type": "keyword"},
                            "entity_type": {"type": "keyword"},
                            "description": {"type": "text"},
                            "source_id": {"type": "text"},
                        },
                    },
                    "settings": {
                        "index": {
                            "number_of_shards": _get_index_number_of_shards(),
                            "number_of_replicas": _get_index_number_of_replicas(),
                        }
                    },
                }
                await self._os_client.indices.create(
                    index=self._os_nodes_index, body=body
                )
                logger.info(f"Created OpenSearch nodes index: {self._os_nodes_index}")
        except RequestError as e:
            if "resource_already_exists_exception" not in str(e):
                logger.warning(
                    f"Could not create nodes index {self._os_nodes_index}: {e}"
                )
        except Exception as e:
            logger.warning(f"Could not verify/create nodes index: {e}")

    async def finalize(self):
        """Release both Neptune and OpenSearch clients."""
        if self._os_client is not None:
            try:
                await ClientManager.release_client(self._os_client)
                logger.info(
                    "NeptuneOpenSearchGraphStorage: OpenSearch client released"
                )
            except Exception as e:
                logger.error(f"Error releasing OpenSearch client: {e}")
            finally:
                self._os_client = None

        await super().finalize()

    # ------------------------------------------------------------------
    # Dual-write: keep the OpenSearch nodes index in sync with Neptune
    # ------------------------------------------------------------------

    async def upsert_node(self, node_id: str, node_data: dict[str, str]):
        """Insert or update a node in both Neptune and the OpenSearch search index."""
        await super().upsert_node(node_id, node_data)

        if self._os_client is not None and self._os_nodes_index:
            try:
                doc = {"entity_id": node_id}
                doc.update(
                    {k: v for k, v in node_data.items() if k != "_id"}
                )
                await self._os_client.index(
                    index=self._os_nodes_index,
                    id=node_id,
                    body=doc,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to mirror node {node_id} to OpenSearch: {e}"
                )

    async def delete_node(self, node_id: str):
        """Delete a node from both Neptune and the OpenSearch search index."""
        await super().delete_node(node_id)

        if self._os_client is not None and self._os_nodes_index:
            try:
                await self._os_client.delete(
                    index=self._os_nodes_index,
                    id=node_id,
                    params={"ignore": [404]},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete node {node_id} from OpenSearch: {e}"
                )

    async def remove_nodes(self, nodes: list[str]):
        """Batch delete nodes from both Neptune and the OpenSearch search index."""
        if not nodes:
            return
        await super().remove_nodes(nodes)

        if self._os_client is not None and self._os_nodes_index:
            try:
                await self._os_client.delete_by_query(
                    index=self._os_nodes_index,
                    body={
                        "query": {
                            "terms": {"entity_id": nodes}
                        }
                    },
                    params={"ignore": [404]},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to batch-delete {len(nodes)} nodes from OpenSearch: {e}"
                )

    async def drop(self) -> dict[str, str]:
        """Delete all data from both Neptune workspace and OpenSearch nodes index."""
        result = await super().drop()

        if self._os_client is not None and self._os_nodes_index:
            try:
                if await self._os_client.indices.exists(index=self._os_nodes_index):
                    await self._os_client.indices.delete(index=self._os_nodes_index)
                    logger.info(
                        f"Dropped OpenSearch nodes index: {self._os_nodes_index}"
                    )
            except Exception as e:
                logger.warning(f"Failed to drop OpenSearch nodes index: {e}")

        return result

    async def index_done_callback(self):
        """Refresh the OpenSearch nodes index after indexing completion."""
        await super().index_done_callback()

        if self._os_client is not None and self._os_nodes_index:
            try:
                await self._os_client.indices.refresh(index=self._os_nodes_index)
            except Exception as e:
                logger.warning(
                    f"Failed to refresh OpenSearch nodes index: {e}"
                )

    # ------------------------------------------------------------------
    # Full-text search via OpenSearch
    # ------------------------------------------------------------------

    async def search_labels(self, query: str, limit: int = 10) -> list[str]:
        """
        Search for entity labels using OpenSearch full-text search.

        Uses the async OpenSearch client with a multi_match query against the
        nodes index, replacing the synchronous requests.post approach in the
        base NeptuneGraphStorage.

        Falls back to Neptune client-side filtering if OpenSearch is unavailable.
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        if self._os_client is not None and self._os_nodes_index:
            try:
                body = {
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["entity_id^2", "description"],
                            "fuzziness": "AUTO",
                        }
                    },
                    "size": limit,
                    "_source": ["entity_id"],
                }
                response = await self._os_client.search(
                    index=self._os_nodes_index, body=body
                )
                hits = response.get("hits", {}).get("hits", [])
                return [
                    hit["_source"]["entity_id"]
                    for hit in hits
                    if "_source" in hit and "entity_id" in hit["_source"]
                ]
            except Exception as e:
                logger.warning(
                    f"OpenSearch search_labels failed, falling back to Neptune: {e}"
                )

        return await super().search_labels(query, limit)

    async def full_text_search(
        self, query: str, limit: int = 10, field: str = "description"
    ) -> list[dict[str, Any]]:
        """
        Search entity/node descriptions via OpenSearch full-text queries
        and correlate results back to Neptune graph nodes.

        Args:
            query: Search query string
            limit: Maximum number of results
            field: Field to search (default: "description")

        Returns:
            List of dicts with entity_id and matching properties from Neptune
        """
        if not query or not query.strip():
            return []

        if self._os_client is None:
            logger.warning("OpenSearch client not available for full_text_search")
            return []

        query = query.strip()

        body = {
            "query": {
                "match": {
                    field: {
                        "query": query,
                        "fuzziness": "AUTO",
                    }
                }
            },
            "size": limit,
            "_source": ["entity_id"],
        }

        try:
            response = await self._os_client.search(
                index=self._os_nodes_index, body=body
            )
        except Exception as e:
            logger.error(f"OpenSearch full_text_search query failed: {e}")
            return []

        hits = response.get("hits", {}).get("hits", [])
        entity_ids = [
            hit["_source"]["entity_id"]
            for hit in hits
            if "_source" in hit and "entity_id" in hit["_source"]
        ]

        if not entity_ids:
            return []

        # Correlate results back to Neptune graph nodes via batch fetch
        try:
            node_data = await self.get_nodes_batch(entity_ids)
        except Exception as e:
            logger.error(f"Failed to fetch Neptune nodes for search results: {e}")
            return []

        results = []
        for entity_id in entity_ids:
            node = node_data.get(entity_id)
            if node:
                results.append({"entity_id": entity_id, **node})
            else:
                results.append({"entity_id": entity_id})

        return results
