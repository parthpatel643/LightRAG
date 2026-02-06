"""
AWS Neptune graph storage implementation using Gremlin (Apache TinkerPop).

Neptune supports both Gremlin and SPARQL query languages. This implementation
uses Gremlin for better property graph support.
"""

import asyncio
import configparser
import os
from dataclasses import dataclass, field
from typing import final

from gremlin_python.driver import client, serializer  # type: ignore
from gremlin_python.driver.driver_remote_connection import (  # type: ignore
    DriverRemoteConnection,
)
from gremlin_python.process.anonymous_traversal import traversal  # type: ignore
from gremlin_python.process.graph_traversal import (  # type: ignore
    GraphTraversalSource,
    __,
)
from gremlin_python.process.traversal import Order, P, T  # type: ignore

from ..base import BaseGraphStorage
from ..types import KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode
from ..utils import logger

config = configparser.ConfigParser()
config.read("config.ini", "utf-8")


class NeptuneClientManager:
    """Client manager for AWS Neptune connections."""

    _instances = {"client": None, "connection": None, "g": None, "ref_count": 0}
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> tuple[client.Client, GraphTraversalSource]:
        """Get or create Neptune client and graph traversal source."""
        async with cls._lock:
            if cls._instances["client"] is None:
                # Neptune connection parameters
                endpoint = os.environ.get(
                    "NEPTUNE_ENDPOINT",
                    config.get("neptune", "endpoint", fallback="localhost"),
                )
                port = int(
                    os.environ.get(
                        "NEPTUNE_PORT", config.get("neptune", "port", fallback="8182")
                    )
                )
                use_ssl = (
                    os.environ.get(
                        "NEPTUNE_USE_SSL",
                        config.get("neptune", "use_ssl", fallback="true"),
                    ).lower()
                    == "true"
                )

                # Build connection string
                protocol = "wss" if use_ssl else "ws"
                connection_string = f"{protocol}://{endpoint}:{port}/gremlin"

                logger.info(f"Connecting to Neptune at {connection_string}")

                # Create Gremlin client for direct queries
                gremlin_client = client.Client(
                    connection_string,
                    "g",
                    message_serializer=serializer.GraphSONSerializersV3d0(),
                )

                # Create remote connection for graph traversal
                remote_connection = DriverRemoteConnection(connection_string, "g")
                g = traversal().withRemote(remote_connection)

                cls._instances["client"] = gremlin_client
                cls._instances["connection"] = remote_connection
                cls._instances["g"] = g
                cls._instances["ref_count"] = 0

                logger.info("Successfully connected to Neptune")

            cls._instances["ref_count"] += 1
            return cls._instances["client"], cls._instances["g"]

    @classmethod
    async def release_client(cls):
        """Release Neptune client."""
        async with cls._lock:
            cls._instances["ref_count"] -= 1
            if cls._instances["ref_count"] == 0:
                if cls._instances["connection"]:
                    cls._instances["connection"].close()
                if cls._instances["client"]:
                    cls._instances["client"].close()
                cls._instances["client"] = None
                cls._instances["connection"] = None
                cls._instances["g"] = None


@final
@dataclass
class NeptuneGraphStorage(BaseGraphStorage):
    """AWS Neptune implementation of graph storage using Gremlin API."""

    _client: client.Client = field(default=None)
    _g: GraphTraversalSource = field(default=None)
    _workspace_prefix: str = field(default="")

    def __post_init__(self):
        # Check for NEPTUNE_WORKSPACE environment variable first (higher priority)
        neptune_workspace = os.environ.get("NEPTUNE_WORKSPACE")
        if neptune_workspace and neptune_workspace.strip():
            effective_workspace = neptune_workspace.strip()
            logger.info(
                f"Using NEPTUNE_WORKSPACE environment variable: '{effective_workspace}'"
            )
        else:
            effective_workspace = self.workspace

        # Build workspace prefix for node/edge IDs to support multi-tenancy
        if effective_workspace:
            self._workspace_prefix = f"{effective_workspace}__"
            self.workspace = effective_workspace
            logger.debug(f"Using workspace prefix: '{self._workspace_prefix}'")
        else:
            self._workspace_prefix = ""
            self.workspace = ""

    def _prefixed_id(self, node_id: str) -> str:
        """Add workspace prefix to node/edge ID."""
        return f"{self._workspace_prefix}{node_id}"

    def _strip_prefix(self, prefixed_id: str) -> str:
        """Remove workspace prefix from node/edge ID."""
        if self._workspace_prefix and prefixed_id.startswith(self._workspace_prefix):
            return prefixed_id[len(self._workspace_prefix) :]
        return prefixed_id

    async def initialize(self):
        """Initialize Neptune connection."""
        self._client, self._g = await NeptuneClientManager.get_client()
        logger.debug(f"[{self.workspace}] Use Neptune as Graph Storage")

    async def finalize(self):
        """Close Neptune connection."""
        await NeptuneClientManager.release_client()
        self._client = None
        self._g = None

    async def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        prefixed_id = self._prefixed_id(node_id)
        result = await asyncio.to_thread(
            lambda: self._g.V(prefixed_id).hasNext().next()
        )
        return result

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        """Check if an edge exists between two nodes."""
        src_id = self._prefixed_id(source_node_id)
        tgt_id = self._prefixed_id(target_node_id)
        result = await asyncio.to_thread(
            lambda: self._g.V(src_id)
            .outE()
            .where(__.inV().hasId(tgt_id))
            .hasNext()
            .next()
        )
        return result

    async def node_degree(self, node_id: str) -> int:
        """Get the degree (number of connected edges) of a node."""
        prefixed_id = self._prefixed_id(node_id)
        try:
            # Count both incoming and outgoing edges (undirected graph)
            result = await asyncio.to_thread(
                lambda: self._g.V(prefixed_id).bothE().count().next()
            )
            return int(result)
        except Exception:
            return 0

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        """Get the total degree of an edge."""
        src_degree = await self.node_degree(src_id)
        tgt_degree = await self.node_degree(tgt_id)
        return src_degree + tgt_degree

    async def get_node(self, node_id: str) -> dict[str, str] | None:
        """Get node by its ID, returning only node properties."""
        prefixed_id = self._prefixed_id(node_id)
        try:
            result = await asyncio.to_thread(
                lambda: self._g.V(prefixed_id).valueMap().next()
            )
            # Convert Neptune property format to dict
            # Neptune returns properties as {key: [value]}
            node_data = {
                k: v[0] if isinstance(v, list) else v for k, v in result.items()
            }
            return node_data
        except StopIteration:
            return None

    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, str] | None:
        """Get edge properties between two nodes."""
        src_id = self._prefixed_id(source_node_id)
        tgt_id = self._prefixed_id(target_node_id)
        try:
            result = await asyncio.to_thread(
                lambda: self._g.V(src_id)
                .outE()
                .where(__.inV().hasId(tgt_id))
                .valueMap()
                .next()
            )
            # Convert Neptune property format to dict
            edge_data = {
                k: v[0] if isinstance(v, list) else v for k, v in result.items()
            }
            return edge_data
        except StopIteration:
            return None

    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]] | None:
        """Get all edges connected to a node."""
        prefixed_id = self._prefixed_id(source_node_id)
        try:
            # Check if node exists first
            if not await self.has_node(source_node_id):
                return None

            # Get both outgoing and incoming edges (undirected)
            result = await asyncio.to_thread(
                lambda: self._g.V(prefixed_id)
                .bothE()
                .project("src", "tgt")
                .by(__.outV().id())
                .by(__.inV().id())
                .toList()
            )

            edges = []
            for edge in result:
                src = self._strip_prefix(str(edge["src"]))
                tgt = self._strip_prefix(str(edge["tgt"]))
                edges.append((src, tgt))

            return edges
        except Exception as e:
            logger.error(f"Error getting edges for node {source_node_id}: {e}")
            return []

    async def upsert_node(self, node_id: str, node_data: dict[str, str]) -> None:
        """Insert a new node or update an existing node in the graph."""
        prefixed_id = self._prefixed_id(node_id)

        # Build Gremlin query to upsert node
        # Use fold().coalesce() pattern for upsert
        traversal_query = (
            self._g.V(prefixed_id)
            .fold()
            .coalesce(__.unfold(), __.addV("Entity").property(T.id, prefixed_id))
        )

        # Add properties
        for key, value in node_data.items():
            traversal_query = traversal_query.property(key, value)

        await asyncio.to_thread(lambda: traversal_query.next())

    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ) -> None:
        """Insert a new edge or update an existing edge in the graph."""
        src_id = self._prefixed_id(source_node_id)
        tgt_id = self._prefixed_id(target_node_id)

        # Ensure both nodes exist
        await self.upsert_node(source_node_id, {})
        await self.upsert_node(target_node_id, {})

        # Build Gremlin query to upsert edge
        # Use coalesce pattern for upsert
        traversal_query = self._g.V(src_id).coalesce(
            __.outE("RELATES_TO").where(__.inV().hasId(tgt_id)),
            __.addE("RELATES_TO").to(__.V(tgt_id)),
        )

        # Add properties
        for key, value in edge_data.items():
            traversal_query = traversal_query.property(key, value)

        await asyncio.to_thread(lambda: traversal_query.next())

    async def delete_node(self, node_id: str) -> None:
        """Delete a node from the graph."""
        prefixed_id = self._prefixed_id(node_id)
        await asyncio.to_thread(lambda: self._g.V(prefixed_id).drop().iterate())

    async def remove_nodes(self, nodes: list[str]):
        """Delete multiple nodes."""
        for node_id in nodes:
            await self.delete_node(node_id)

    async def remove_edges(self, edges: list[tuple[str, str]]):
        """Delete multiple edges."""
        for src_id, tgt_id in edges:
            prefixed_src = self._prefixed_id(src_id)
            prefixed_tgt = self._prefixed_id(tgt_id)
            await asyncio.to_thread(
                lambda: self._g.V(prefixed_src)
                .outE()
                .where(__.inV().hasId(prefixed_tgt))
                .drop()
                .iterate()
            )

    async def get_all_labels(self) -> list[str]:
        """Get all labels in the graph."""
        try:
            # Get all unique entity_type values
            results = await asyncio.to_thread(
                lambda: self._g.V()
                .has("entity_type")
                .values("entity_type")
                .dedup()
                .toList()
            )
            return sorted(results)
        except Exception:
            return []

    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 3, max_nodes: int = 1000
    ) -> KnowledgeGraph:
        """Retrieve a connected subgraph."""
        nodes = []
        edges = []
        is_truncated = False

        try:
            # Build traversal based on label
            if node_label == "*":
                # Get all nodes
                traversal_query = self._g.V()
            else:
                # Get nodes with matching entity_type
                traversal_query = self._g.V().has("entity_type", node_label)

            # Limit to max_nodes
            traversal_query = traversal_query.limit(max_nodes)

            # Get nodes
            node_results = await asyncio.to_thread(
                lambda: traversal_query.valueMap(True).toList()
            )

            visited_nodes = set()
            for node_data in node_results:
                node_id = self._strip_prefix(str(node_data[T.id]))
                visited_nodes.add(node_id)

                # Convert properties
                properties = {
                    k: v[0] if isinstance(v, list) else v
                    for k, v in node_data.items()
                    if k != T.id and k != T.label
                }

                nodes.append(
                    KnowledgeGraphNode(
                        id=node_id,
                        labels=[properties.get("entity_type", "")],
                        properties=properties,
                    )
                )

            # Get edges between visited nodes
            if visited_nodes:
                prefixed_ids = [self._prefixed_id(nid) for nid in visited_nodes]
                edge_results = await asyncio.to_thread(
                    lambda: self._g.V()
                    .hasId(*prefixed_ids)
                    .outE()
                    .where(__.inV().hasId(*prefixed_ids))
                    .valueMap(True)
                    .toList()
                )

                for edge_data in edge_results:
                    properties = {
                        k: v[0] if isinstance(v, list) else v
                        for k, v in edge_data.items()
                        if k not in [T.id, T.label]
                    }

                    # Get source and target IDs from properties or edge data
                    src_id = properties.get("source_id", "")
                    tgt_id = properties.get("target_id", "")

                    # Generate edge ID
                    edge_id = f"{src_id}-{tgt_id}"

                    edges.append(
                        KnowledgeGraphEdge(
                            id=edge_id,
                            type="RELATES_TO",
                            source=src_id,
                            target=tgt_id,
                            properties=properties,
                        )
                    )

            is_truncated = len(nodes) >= max_nodes

        except Exception as e:
            logger.error(f"Error retrieving knowledge graph: {e}")

        return KnowledgeGraph(nodes=nodes, edges=edges, is_truncated=is_truncated)

    async def get_all_nodes(self) -> list[dict]:
        """Get all nodes in the graph."""
        try:
            results = await asyncio.to_thread(
                lambda: self._g.V().valueMap(True).toList()
            )
            nodes = []
            for node_data in results:
                node_dict = {
                    k: v[0] if isinstance(v, list) else v
                    for k, v in node_data.items()
                    if k != T.label
                }
                # Strip prefix from ID
                if T.id in node_dict:
                    node_dict[T.id] = self._strip_prefix(str(node_dict[T.id]))
                nodes.append(node_dict)
            return nodes
        except Exception as e:
            logger.error(f"Error getting all nodes: {e}")
            return []

    async def get_all_edges(self) -> list[dict]:
        """Get all edges in the graph."""
        try:
            results = await asyncio.to_thread(
                lambda: self._g.E().valueMap(True).toList()
            )
            edges = []
            for edge_data in results:
                edge_dict = {
                    k: v[0] if isinstance(v, list) else v
                    for k, v in edge_data.items()
                    if k != T.label
                }
                edges.append(edge_dict)
            return edges
        except Exception as e:
            logger.error(f"Error getting all edges: {e}")
            return []

    async def get_popular_labels(self, limit: int = 300) -> list[str]:
        """Get popular labels by node degree."""
        try:
            results = await asyncio.to_thread(
                lambda: self._g.V()
                .has("entity_type")
                .group()
                .by("entity_type")
                .by(__.bothE().count())
                .unfold()
                .order()
                .by(__.select(T.value), Order.desc)
                .limit(limit)
                .select(T.key)
                .toList()
            )
            return results
        except Exception as e:
            logger.error(f"Error getting popular labels: {e}")
            return []

    async def search_labels(self, query: str, limit: int = 50) -> list[str]:
        """Search labels with fuzzy matching."""
        try:
            # Neptune doesn't have built-in fuzzy search, use contains
            results = await asyncio.to_thread(
                lambda: self._g.V()
                .has("entity_type")
                .where(__.values("entity_type").is_(P.containing(query)))
                .values("entity_type")
                .dedup()
                .limit(limit)
                .toList()
            )
            return results
        except Exception:
            # Fallback to exact match
            try:
                results = await asyncio.to_thread(
                    lambda: self._g.V()
                    .has("entity_type", query)
                    .values("entity_type")
                    .dedup()
                    .limit(limit)
                    .toList()
                )
                return results
            except Exception as e:
                logger.error(f"Error searching labels: {e}")
                return []

    async def index_done_callback(self):
        """Callback after index is done. Neptune doesn't need special handling."""
        pass

    async def drop(self):
        """Drop all data in the workspace. WARNING: Destructive operation!"""
        try:
            if self._workspace_prefix:
                # Only drop nodes with this workspace prefix
                await asyncio.to_thread(
                    lambda: self._g.V()
                    .has(T.id, P.startingWith(self._workspace_prefix))
                    .drop()
                    .iterate()
                )
            else:
                # Drop all data (use with caution!)
                await asyncio.to_thread(lambda: self._g.V().drop().iterate())
            logger.info(f"Dropped all data for workspace: {self.workspace}")
        except Exception as e:
            logger.error(f"Error dropping data: {e}")
