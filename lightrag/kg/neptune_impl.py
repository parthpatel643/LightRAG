"""
AWS Neptune Graph Storage Implementation for LightRAG.

This module provides graph storage backend using AWS Neptune with Gremlin queries,
IAM authentication, and OpenSearch integration for full-text search.
"""

import asyncio
import configparser
import os
from dataclasses import dataclass, field
from typing import Any, final

import pipmaster as pm
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..base import BaseGraphStorage
from ..kg.shared_storage import get_data_init_lock
from ..types import KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode
from ..utils import logger

# Install required dependencies
if not pm.is_installed("gremlin_python"):
    pm.install("gremlinpython")
if not pm.is_installed("requests_aws4auth"):
    pm.install("requests-aws4auth")

from gremlin_python.driver import client, serializer

try:
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from requests_aws4auth import AWS4Auth
except ImportError:
    boto3 = None
    SigV4Auth = None
    AWSRequest = None
    AWS4Auth = None
    logger.warning(
        "boto3 not installed. IAM authentication and OpenSearch features will be unavailable."
    )

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=False)

config = configparser.ConfigParser()
config.read("config.ini", "utf-8")


class NeptuneConnectionError(Exception):
    """Exception raised for Neptune connection errors."""

    pass


class NeptuneQueryError(Exception):
    """Exception raised for Neptune query execution errors."""

    pass


class NeptuneIAMAuth:
    """Helper class for AWS Neptune IAM authentication with SigV4 signing."""

    def __init__(self, endpoint: str, port: int, region: str):
        """
        Initialize IAM authentication helper.

        Args:
            endpoint: Neptune cluster endpoint
            port: Neptune port (usually 8182)
            region: AWS region (e.g., 'us-east-1')
        """
        self.endpoint = endpoint
        self.port = port
        self.region = region
        self.service_name = "neptune-db"

        if boto3 is None:
            raise ImportError(
                "boto3 is required for IAM authentication. Install with: pip install boto3"
            )

        # Get AWS credentials from boto3 session (respects AWS_PROFILE, env vars, etc.)
        self.session = boto3.Session()
        self.credentials = self.session.get_credentials()

        if self.credentials is None:
            raise ValueError(
                "No AWS credentials found. Configure via AWS_PROFILE, "
                "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY environment variables, "
                "or IAM role."
            )

    def get_signed_headers(self) -> dict[str, str]:
        """
        Generate signed headers for WebSocket connection using SigV4.

        Returns:
            Dictionary of HTTP headers including authorization signature
        """
        # Create canonical request for signing
        method = "GET"
        url = f"wss://{self.endpoint}:{self.port}/gremlin"
        headers = {
            "host": f"{self.endpoint}:{self.port}",
        }

        # Use SigV4Auth for signing
        request = AWSRequest(method=method, url=url, headers=headers)
        SigV4Auth(self.credentials, self.service_name, self.region).add_auth(request)

        # Return signed headers
        return dict(request.headers)


@final
@dataclass
class NeptuneGraphStorage(BaseGraphStorage):
    """
    AWS Neptune graph storage implementation using Gremlin queries.

    Features:
    - IAM-based authentication with SigV4 signing
    - Property-based workspace isolation
    - Async operations via thread pool
    - OpenSearch integration for full-text search
    - Batch operations for performance
    """

    _client: Any = field(default=None, repr=False, init=False, compare=False)
    _connection: Any = field(default=None, repr=False, init=False, compare=False)
    _g: Any = field(default=None, repr=False, init=False, compare=False)
    _opensearch_client: Any = field(default=None, repr=False, init=False, compare=False)
    _endpoint: str = field(default=None, repr=False, init=False, compare=False)
    _port: int = field(default=8182, repr=False, init=False, compare=False)
    _region: str = field(default=None, repr=False, init=False, compare=False)
    _opensearch_endpoint: str = field(
        default=None, repr=False, init=False, compare=False
    )
    _use_iam: bool = field(default=True, repr=False, init=False, compare=False)

    def _get_workspace_label(self) -> str:
        """Get the workspace identifier for isolating data."""
        return self.workspace if self.workspace else "base"

    async def initialize(self):
        """Initialize Neptune connection with IAM authentication."""
        async with get_data_init_lock():
            # Get configuration from environment or config file
            self._endpoint = os.environ.get(
                "NEPTUNE_ENDPOINT", config.get("neptune", "endpoint", fallback=None)
            )
            self._port = int(
                os.environ.get(
                    "NEPTUNE_PORT", config.get("neptune", "port", fallback=8182)
                )
            )
            self._region = os.environ.get(
                "NEPTUNE_REGION", config.get("neptune", "region", fallback="us-east-1")
            )
            self._use_iam = os.environ.get(
                "NEPTUNE_USE_IAM", config.get("neptune", "use_iam", fallback="true")
            ).lower().strip() in ("true", "1", "yes", "on")
            self._opensearch_endpoint = os.environ.get(
                "NEPTUNE_OPENSEARCH_ENDPOINT",
                config.get("neptune", "opensearch_endpoint", fallback=None),
            )

            if not self._endpoint:
                raise ValueError(
                    "NEPTUNE_ENDPOINT must be set in environment or config.ini"
                )

            workspace_label = self._get_workspace_label()
            logger.info(
                f"Initializing Neptune storage with workspace: {workspace_label}"
            )

            try:
                # Build WebSocket URL
                url = f"wss://{self._endpoint}:{self._port}/gremlin"

                # Setup IAM authentication if enabled
                headers = {}
                if self._use_iam:
                    try:
                        iam_auth = NeptuneIAMAuth(
                            self._endpoint, self._port, self._region
                        )
                        headers = iam_auth.get_signed_headers()
                        logger.info("Using IAM authentication for Neptune")
                    except Exception as e:
                        logger.error(f"Failed to setup IAM authentication: {e}")
                        raise NeptuneConnectionError(
                            f"IAM authentication failed: {e}"
                        ) from e

                # Create Gremlin client
                try:
                    self._client = client.Client(
                        url=url,
                        traversal_source="g",
                        message_serializer=serializer.GraphSONSerializersV3d0(),
                        headers=headers if headers else None,
                    )
                    logger.info(f"Connected to Neptune at {url}")
                except Exception as e:
                    logger.error(f"Failed to create Neptune client: {e}")
                    raise NeptuneConnectionError(
                        f"Failed to connect to Neptune: {e}"
                    ) from e

                # Test connection
                try:
                    await asyncio.to_thread(
                        lambda: self._client.submit("g.V().limit(1)").all().result()
                    )
                    logger.info("Neptune connection verified")
                except Exception as e:
                    logger.error(f"Failed to verify Neptune connection: {e}")
                    raise NeptuneConnectionError(
                        f"Connection verification failed: {e}"
                    ) from e

                # Initialize OpenSearch client if endpoint provided
                if self._opensearch_endpoint and boto3:
                    try:
                        session = boto3.Session()
                        credentials = session.get_credentials()
                        awsauth = AWS4Auth(
                            credentials.access_key,
                            credentials.secret_key,
                            self._region,
                            "es",
                            session_token=credentials.token,
                        )
                        # Store auth for later use with requests
                        self._opensearch_client = {
                            "endpoint": self._opensearch_endpoint,
                            "auth": awsauth,
                        }
                        logger.info(
                            f"OpenSearch integration enabled: {self._opensearch_endpoint}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to initialize OpenSearch client: {e}. Full-text search will use fallback."
                        )
                        self._opensearch_client = None

            except Exception as e:
                logger.error(f"Neptune initialization failed: {e}")
                raise

    async def finalize(self):
        """Close Neptune connection and cleanup resources."""
        if self._client:
            try:
                await asyncio.to_thread(self._client.close)
                logger.info("Neptune connection closed")
            except Exception as e:
                logger.error(f"Error closing Neptune connection: {e}")
            finally:
                self._client = None
                self._connection = None
                self._g = None

    async def index_done_callback(self):
        """
        Callback after indexing completion.
        Neptune auto-commits, so this is a no-op.
        """
        logger.debug("Index done callback (Neptune auto-commits)")

    async def _submit_query(self, query: str) -> Any:
        """
        Submit a Gremlin query and return results.

        Args:
            query: Gremlin traversal query string

        Returns:
            Query results
        """
        try:
            result = await asyncio.to_thread(
                lambda: self._client.submit(query).all().result()
            )
            return result
        except Exception as e:
            logger.error(f"Neptune query failed: {query[:100]}... Error: {e}")
            raise NeptuneQueryError(f"Query execution failed: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        workspace = self._get_workspace_label()
        query = f"g.V().has('entity_id', '{node_id}').has('workspace', '{workspace}').hasNext()"
        result = await self._submit_query(query)
        return result[0] if result else False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        """Check if an edge exists between two nodes."""
        workspace = self._get_workspace_label()
        # Escape single quotes in node IDs
        src_escaped = source_node_id.replace("'", "\\'")
        tgt_escaped = target_node_id.replace("'", "\\'")

        query = f"""g.V().has('entity_id', '{src_escaped}').has('workspace', '{workspace}')
                    .outE().where(inV().has('entity_id', '{tgt_escaped}').has('workspace', '{workspace}'))
                    .hasNext()"""
        result = await self._submit_query(query)
        return result[0] if result else False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def node_degree(self, node_id: str) -> int:
        """Get the degree (number of edges) of a node."""
        workspace = self._get_workspace_label()
        node_id_escaped = node_id.replace("'", "\\'")

        # Count both incoming and outgoing edges in the workspace
        query = f"""g.V().has('entity_id', '{node_id_escaped}').has('workspace', '{workspace}')
                    .bothE().has('workspace', '{workspace}').count()"""
        result = await self._submit_query(query)
        return int(result[0]) if result else 0

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        """Get the sum of degrees of source and target nodes."""
        src_degree = await self.node_degree(src_id)
        tgt_degree = await self.node_degree(tgt_id)
        return src_degree + tgt_degree

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def get_node(self, node_id: str) -> dict[str, str] | None:
        """Retrieve a node's properties."""
        workspace = self._get_workspace_label()
        node_id_escaped = node_id.replace("'", "\\'")

        query = f"""g.V().has('entity_id', '{node_id_escaped}').has('workspace', '{workspace}')
                    .valueMap().by(unfold())"""
        result = await self._submit_query(query)

        if not result:
            return None

        # Convert Gremlin result to dict
        node_data = result[0] if result else {}
        # Gremlin returns properties as lists, flatten them
        flattened = {}
        for key, value in node_data.items():
            if isinstance(value, list) and len(value) > 0:
                flattened[key] = value[0]
            else:
                flattened[key] = value

        return flattened if flattened else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, str] | None:
        """Retrieve an edge's properties."""
        workspace = self._get_workspace_label()
        src_escaped = source_node_id.replace("'", "\\'")
        tgt_escaped = target_node_id.replace("'", "\\'")

        query = f"""g.V().has('entity_id', '{src_escaped}').has('workspace', '{workspace}')
                    .outE().where(inV().has('entity_id', '{tgt_escaped}').has('workspace', '{workspace}'))
                    .has('workspace', '{workspace}')
                    .valueMap().by(unfold())"""
        result = await self._submit_query(query)

        if not result:
            return None

        # Flatten properties
        edge_data = result[0] if result else {}
        flattened = {}
        for key, value in edge_data.items():
            if isinstance(value, list) and len(value) > 0:
                flattened[key] = value[0]
            else:
                flattened[key] = value

        return flattened if flattened else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]] | None:
        """Get all edges for a given node."""
        workspace = self._get_workspace_label()
        node_id_escaped = source_node_id.replace("'", "\\'")

        # Get both outgoing and incoming edges
        query = f"""g.V().has('entity_id', '{node_id_escaped}').has('workspace', '{workspace}')
                    .bothE().has('workspace', '{workspace}')
                    .project('source', 'target')
                    .by(outV().values('entity_id'))
                    .by(inV().values('entity_id'))"""
        result = await self._submit_query(query)

        if not result:
            return None

        edges = []
        for edge_info in result:
            src = edge_info.get("source")
            tgt = edge_info.get("target")
            if src and tgt:
                edges.append((src, tgt))

        return edges if edges else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def upsert_node(self, node_id: str, node_data: dict[str, str]):
        """Insert or update a node."""
        workspace = self._get_workspace_label()
        node_id_escaped = node_id.replace("'", "\\'")

        # Build property list
        props = [f"property('entity_id', '{node_id_escaped}')"]
        props.append(f"property('workspace', '{workspace}')")

        for key, value in node_data.items():
            if key not in ["entity_id", "workspace"]:
                # Escape single quotes in values
                value_escaped = str(value).replace("'", "\\'")
                props.append(f"property('{key}', '{value_escaped}')")

        props_str = ".".join(props)

        # Use fold/coalesce pattern for upsert
        query = f"""g.V().has('entity_id', '{node_id_escaped}').has('workspace', '{workspace}')
                    .fold()
                    .coalesce(
                        unfold(),
                        addV('Entity').{props_str}
                    )
                    .{props_str}"""

        await self._submit_query(query)
        logger.debug(f"Upserted node: {node_id}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ):
        """Insert or update an edge between two nodes."""
        workspace = self._get_workspace_label()
        src_escaped = source_node_id.replace("'", "\\'")
        tgt_escaped = target_node_id.replace("'", "\\'")

        # Ensure both nodes exist first
        await self.upsert_node(source_node_id, {"entity_id": source_node_id})
        await self.upsert_node(target_node_id, {"entity_id": target_node_id})

        # Build edge properties
        props = [f"property('workspace', '{workspace}')"]
        for key, value in edge_data.items():
            if key != "workspace":
                value_escaped = str(value).replace("'", "\\'")
                props.append(f"property('{key}', '{value_escaped}')")

        props_str = ".".join(props) if props else ""

        # Create or update edge
        query = f"""g.V().has('entity_id', '{src_escaped}').has('workspace', '{workspace}').as('src')
                    .V().has('entity_id', '{tgt_escaped}').has('workspace', '{workspace}').as('tgt')
                    .coalesce(
                        __.select('src').outE('RELATES_TO').where(inV().as('tgt')).has('workspace', '{workspace}'),
                        __.select('src').addE('RELATES_TO').to(__.select('tgt')).{props_str}
                    )
                    .{props_str}"""

        await self._submit_query(query)
        logger.debug(f"Upserted edge: {source_node_id} -> {target_node_id}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((NeptuneConnectionError, NeptuneQueryError)),
    )
    async def delete_node(self, node_id: str):
        """Delete a node and its edges."""
        workspace = self._get_workspace_label()
        node_id_escaped = node_id.replace("'", "\\'")

        # Delete node and all connected edges
        query = f"""g.V().has('entity_id', '{node_id_escaped}').has('workspace', '{workspace}')
                    .drop()"""
        await self._submit_query(query)
        logger.debug(f"Deleted node: {node_id}")

    async def remove_nodes(self, nodes: list[str]):
        """Batch delete nodes."""
        for node_id in nodes:
            await self.delete_node(node_id)

    async def remove_edges(self, edges: list[tuple[str, str]]):
        """Batch delete edges."""
        workspace = self._get_workspace_label()

        for src, tgt in edges:
            src_escaped = src.replace("'", "\\'")
            tgt_escaped = tgt.replace("'", "\\'")

            query = f"""g.V().has('entity_id', '{src_escaped}').has('workspace', '{workspace}')
                        .outE().where(inV().has('entity_id', '{tgt_escaped}').has('workspace', '{workspace}'))
                        .has('workspace', '{workspace}')
                        .drop()"""
            await self._submit_query(query)

        logger.debug(f"Deleted {len(edges)} edges")

    async def get_all_labels(self) -> list[str]:
        """
        Get all unique entity labels (DEPRECATED for large graphs).

        Warning: This operation can be slow on large graphs.
        Consider using get_popular_labels() instead.
        """
        logger.warning(
            "get_all_labels() is deprecated for large graphs. Use get_popular_labels() instead."
        )

        workspace = self._get_workspace_label()
        query = f"""g.V().has('workspace', '{workspace}')
                    .values('entity_id')
                    .dedup()"""

        result = await self._submit_query(query)
        return result if result else []

    async def get_all_nodes(self) -> list[dict]:
        """Get all nodes in the workspace."""
        workspace = self._get_workspace_label()

        # Use pagination to avoid memory issues
        query = f"""g.V().has('workspace', '{workspace}')
                    .valueMap().by(unfold())
                    .limit(10000)"""

        result = await self._submit_query(query)

        # Flatten properties
        nodes = []
        for node_data in result:
            flattened = {}
            for key, value in node_data.items():
                if isinstance(value, list) and len(value) > 0:
                    flattened[key] = value[0]
                else:
                    flattened[key] = value
            nodes.append(flattened)

        return nodes

    async def get_all_edges(self) -> list[dict]:
        """Get all edges in the workspace."""
        workspace = self._get_workspace_label()

        # Use pagination
        query = f"""g.E().has('workspace', '{workspace}')
                    .project('source', 'target', 'properties')
                    .by(outV().values('entity_id'))
                    .by(inV().values('entity_id'))
                    .by(valueMap().by(unfold()))
                    .limit(10000)"""

        result = await self._submit_query(query)

        edges = []
        for edge_data in result:
            edge_dict = {
                "source": edge_data.get("source"),
                "target": edge_data.get("target"),
            }
            # Flatten properties
            props = edge_data.get("properties", {})
            for key, value in props.items():
                if isinstance(value, list) and len(value) > 0:
                    edge_dict[key] = value[0]
                else:
                    edge_dict[key] = value
            edges.append(edge_dict)

        return edges

    async def get_popular_labels(self, limit: int = 100) -> list[str]:
        """Get the most connected entity labels."""
        workspace = self._get_workspace_label()

        # Get entities ordered by degree (connection count)
        query = f"""g.V().has('workspace', '{workspace}')
                    .project('entity_id', 'degree')
                    .by(values('entity_id'))
                    .by(bothE().has('workspace', '{workspace}').count())
                    .order().by(select('degree'), desc)
                    .limit({limit})
                    .select('entity_id')"""

        result = await self._submit_query(query)
        return result if result else []

    async def search_labels(self, query: str, limit: int = 10) -> list[str]:
        """
        Search for entity labels using fuzzy matching.

        If OpenSearch is configured, uses full-text search.
        Otherwise, falls back to client-side filtering.
        """
        workspace = self._get_workspace_label()

        # Try OpenSearch if available
        if self._opensearch_client:
            try:
                return await self._opensearch_search(query, limit)
            except Exception as e:
                logger.warning(f"OpenSearch search failed, using fallback: {e}")

        # Fallback: Get all labels and filter client-side
        all_labels = await self.get_all_labels()

        # Simple case-insensitive substring matching
        query_lower = query.lower()
        matches = [label for label in all_labels if query_lower in label.lower()]

        return matches[:limit]

    async def _opensearch_search(self, query: str, limit: int) -> list[str]:
        """Search using Neptune's OpenSearch integration."""
        if not self._opensearch_client:
            raise ValueError("OpenSearch client not initialized")

        import requests

        endpoint = self._opensearch_client["endpoint"]
        auth = self._opensearch_client["auth"]

        # Build OpenSearch query
        search_body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["entity_id^2", "description"],
                    "fuzziness": "AUTO",
                }
            },
            "size": limit,
        }

        url = f"{endpoint}/_search"
        response = await asyncio.to_thread(
            requests.post, url, auth=auth, json=search_body, timeout=10
        )

        if response.status_code != 200:
            raise Exception(f"OpenSearch query failed: {response.text}")

        results = response.json()
        hits = results.get("hits", {}).get("hits", [])

        # Extract entity IDs from results
        entity_ids = [hit["_source"]["entity_id"] for hit in hits if "_source" in hit]

        return entity_ids

    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 2, max_nodes: int = 100
    ) -> KnowledgeGraph:
        """
        Retrieve a subgraph starting from a given node.

        Args:
            node_label: Starting node entity_id
            max_depth: Maximum traversal depth
            max_nodes: Maximum number of nodes to return

        Returns:
            KnowledgeGraph object with nodes and edges
        """
        workspace = self._get_workspace_label()
        node_label_escaped = node_label.replace("'", "\\'")

        # BFS traversal from starting node
        query = f"""g.V().has('entity_id', '{node_label_escaped}').has('workspace', '{workspace}')
                    .repeat(both().has('workspace', '{workspace}').simplePath()).times({max_depth})
                    .limit({max_nodes})
                    .path()"""

        result = await self._submit_query(query)

        # Extract unique nodes and edges from paths
        nodes_dict = {}
        edges_dict = {}

        for path in result if result else []:
            # Path contains alternating vertices and edges
            for i, element in enumerate(path):
                # Check if it's a vertex (has properties)
                if hasattr(element, "id"):
                    # Get vertex properties
                    vertex_query = f"g.V({element.id}).valueMap().by(unfold())"
                    vertex_data = await self._submit_query(vertex_query)

                    if vertex_data:
                        props = vertex_data[0]
                        flattened = {}
                        for key, value in props.items():
                            if isinstance(value, list) and len(value) > 0:
                                flattened[key] = value[0]
                            else:
                                flattened[key] = value

                        entity_id = flattened.get("entity_id")
                        if entity_id and entity_id not in nodes_dict:
                            nodes_dict[entity_id] = KnowledgeGraphNode(
                                id=entity_id,
                                entity_type=flattened.get("entity_type", "unknown"),
                                description=flattened.get("description", ""),
                                source_id=flattened.get("source_id", ""),
                            )

        # Get edges between collected nodes
        node_ids = list(nodes_dict.keys())
        if node_ids:
            # Build query to get edges between these nodes
            ids_str = "', '".join([nid.replace("'", "\\'") for nid in node_ids])
            edges_query = f"""g.V().has('entity_id', within('{ids_str}')).has('workspace', '{workspace}')
                            .outE().has('workspace', '{workspace}')
                            .where(inV().has('entity_id', within('{ids_str}')))
                            .project('source', 'target', 'props')
                            .by(outV().values('entity_id'))
                            .by(inV().values('entity_id'))
                            .by(valueMap().by(unfold()))"""

            edges_result = await self._submit_query(edges_query)

            for edge_data in edges_result if edges_result else []:
                src = edge_data.get("source")
                tgt = edge_data.get("target")
                props = edge_data.get("props", {})

                # Flatten properties
                flattened_props = {}
                for key, value in props.items():
                    if isinstance(value, list) and len(value) > 0:
                        flattened_props[key] = value[0]
                    else:
                        flattened_props[key] = value

                edge_key = (src, tgt)
                if edge_key not in edges_dict:
                    edges_dict[edge_key] = KnowledgeGraphEdge(
                        source_id=src,
                        target_id=tgt,
                        description=flattened_props.get("description", ""),
                        keywords=flattened_props.get("keywords", ""),
                        weight=float(flattened_props.get("weight", 1.0)),
                        source_id_in_doc=flattened_props.get("source_id", ""),
                    )

        return KnowledgeGraph(
            nodes=list(nodes_dict.values()), edges=list(edges_dict.values())
        )

    # Batch operation methods for better performance
    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict]:
        """Batch retrieve multiple nodes."""
        workspace = self._get_workspace_label()

        # Escape and build ID list
        ids_escaped = [nid.replace("'", "\\'") for nid in node_ids]
        ids_str = "', '".join(ids_escaped)

        query = f"""g.V().has('entity_id', within('{ids_str}')).has('workspace', '{workspace}')
                    .project('id', 'props')
                    .by(values('entity_id'))
                    .by(valueMap().by(unfold()))"""

        result = await self._submit_query(query)

        nodes_dict = {}
        for node_data in result if result else []:
            node_id = node_data.get("id")
            props = node_data.get("props", {})

            # Flatten properties
            flattened = {}
            for key, value in props.items():
                if isinstance(value, list) and len(value) > 0:
                    flattened[key] = value[0]
                else:
                    flattened[key] = value

            if node_id:
                nodes_dict[node_id] = flattened

        return nodes_dict

    async def node_degrees_batch(self, node_ids: list[str]) -> dict[str, int]:
        """Batch retrieve node degrees."""
        workspace = self._get_workspace_label()

        ids_escaped = [nid.replace("'", "\\'") for nid in node_ids]
        ids_str = "', '".join(ids_escaped)

        query = f"""g.V().has('entity_id', within('{ids_str}')).has('workspace', '{workspace}')
                    .project('id', 'degree')
                    .by(values('entity_id'))
                    .by(bothE().has('workspace', '{workspace}').count())"""

        result = await self._submit_query(query)

        degrees = {}
        for data in result if result else []:
            node_id = data.get("id")
            degree = data.get("degree", 0)
            if node_id:
                degrees[node_id] = int(degree)

        return degrees

    async def edge_degrees_batch(
        self, edge_pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        """Batch retrieve edge degrees (sum of source and target node degrees)."""
        # Collect unique node IDs
        node_ids = set()
        for src, tgt in edge_pairs:
            node_ids.add(src)
            node_ids.add(tgt)

        # Get degrees for all nodes
        node_degrees = await self.node_degrees_batch(list(node_ids))

        # Calculate edge degrees
        edge_degrees = {}
        for src, tgt in edge_pairs:
            src_degree = node_degrees.get(src, 0)
            tgt_degree = node_degrees.get(tgt, 0)
            edge_degrees[(src, tgt)] = src_degree + tgt_degree

        return edge_degrees

    async def get_edges_batch(
        self, pairs: list[dict[str, str]]
    ) -> dict[tuple[str, str], dict]:
        """Batch retrieve multiple edges."""
        workspace = self._get_workspace_label()
        edges_dict = {}

        # Build batch query
        for pair_dict in pairs:
            src = pair_dict.get("source")
            tgt = pair_dict.get("target")

            if not src or not tgt:
                continue

            src_escaped = src.replace("'", "\\'")
            tgt_escaped = tgt.replace("'", "\\'")

            query = f"""g.V().has('entity_id', '{src_escaped}').has('workspace', '{workspace}')
                        .outE().where(inV().has('entity_id', '{tgt_escaped}').has('workspace', '{workspace}'))
                        .has('workspace', '{workspace}')
                        .valueMap().by(unfold())"""

            result = await self._submit_query(query)

            if result:
                edge_data = result[0]
                flattened = {}
                for key, value in edge_data.items():
                    if isinstance(value, list) and len(value) > 0:
                        flattened[key] = value[0]
                    else:
                        flattened[key] = value

                edges_dict[(src, tgt)] = flattened

        return edges_dict

    async def get_nodes_edges_batch(
        self, node_ids: list[str]
    ) -> dict[str, list[tuple[str, str]]]:
        """Batch retrieve edges for multiple nodes."""
        workspace = self._get_workspace_label()

        ids_escaped = [nid.replace("'", "\\'") for nid in node_ids]
        ids_str = "', '".join(ids_escaped)

        query = f"""g.V().has('entity_id', within('{ids_str}')).has('workspace', '{workspace}')
                    .project('node_id', 'edges')
                    .by(values('entity_id'))
                    .by(bothE().has('workspace', '{workspace}')
                        .project('source', 'target')
                        .by(outV().values('entity_id'))
                        .by(inV().values('entity_id'))
                        .fold())"""

        result = await self._submit_query(query)

        node_edges_dict = {}
        for data in result if result else []:
            node_id = data.get("node_id")
            edges_list = data.get("edges", [])

            edge_tuples = []
            for edge_info in edges_list:
                src = edge_info.get("source")
                tgt = edge_info.get("target")
                if src and tgt:
                    edge_tuples.append((src, tgt))

            if node_id:
                node_edges_dict[node_id] = edge_tuples

        return node_edges_dict

    async def drop(self) -> dict[str, str]:
        """Delete all data in the current workspace."""
        workspace = self._get_workspace_label()

        try:
            # Delete all vertices (and their edges) in this workspace
            query = f"g.V().has('workspace', '{workspace}').drop()"
            await self._submit_query(query)

            # Also delete any orphaned edges
            query = f"g.E().has('workspace', '{workspace}').drop()"
            await self._submit_query(query)

            logger.info(f"Dropped all data for workspace: {workspace}")
            return {"status": "success", "message": f"Workspace '{workspace}' cleared"}

        except Exception as e:
            logger.error(f"Failed to drop workspace data: {e}")
            return {"status": "error", "message": str(e)}
