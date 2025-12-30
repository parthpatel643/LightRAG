import os
from dataclasses import dataclass
from typing import final

import networkx as nx
from dotenv import load_dotenv

from lightrag.base import BaseGraphStorage
from lightrag.types import KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode
from lightrag.utils import logger

from .shared_storage import (
    get_namespace_lock,
    get_update_flag,
    set_all_update_flags,
)

# use the .env that is inside the current folder
# allows to use different .env file for each lightrag instance
# the OS environment variables take precedence over the .env file
load_dotenv(dotenv_path=".env", override=False)


@final
@dataclass
class NetworkXStorage(BaseGraphStorage):
    @staticmethod
    def load_nx_graph(file_name) -> nx.Graph:
        if os.path.exists(file_name):
            return nx.read_graphml(file_name)
        return None

    @staticmethod
    def write_nx_graph(graph: nx.Graph, file_name, workspace="_"):
        logger.info(
            f"[{workspace}] Writing graph with {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
        )
        nx.write_graphml(graph, file_name)

    def __post_init__(self):
        working_dir = self.global_config["working_dir"]
        if self.workspace:
            # Include workspace in the file path for data isolation
            workspace_dir = os.path.join(working_dir, self.workspace)
        else:
            # Default behavior when workspace is empty
            workspace_dir = working_dir
            self.workspace = ""

        os.makedirs(workspace_dir, exist_ok=True)
        self._graphml_xml_file = os.path.join(
            workspace_dir, f"graph_{self.namespace}.graphml"
        )
        self._storage_lock = None
        self.storage_updated = None
        self._graph = None

        # Load initial graph
        preloaded_graph = NetworkXStorage.load_nx_graph(self._graphml_xml_file)
        if preloaded_graph is not None:
            logger.info(
                f"[{self.workspace}] Loaded graph from {self._graphml_xml_file} with {preloaded_graph.number_of_nodes()} nodes, {preloaded_graph.number_of_edges()} edges"
            )
        else:
            logger.info(
                f"[{self.workspace}] Created new empty graph file: {self._graphml_xml_file}"
            )
        self._graph = preloaded_graph or nx.Graph()

    async def initialize(self):
        """Initialize storage data"""
        # Get the update flag for cross-process update notification
        self.storage_updated = await get_update_flag(
            self.namespace, workspace=self.workspace
        )
        # Get the storage lock for use in other methods
        self._storage_lock = get_namespace_lock(
            self.namespace, workspace=self.workspace
        )

    async def _get_graph(self):
        """Check if the storage should be reloaded"""
        # Acquire lock to prevent concurrent read and write
        async with self._storage_lock:
            # Check if data needs to be reloaded
            if self.storage_updated.value:
                logger.info(
                    f"[{self.workspace}] Process {os.getpid()} reloading graph {self._graphml_xml_file} due to modifications by another process"
                )
                # Reload data
                self._graph = (
                    NetworkXStorage.load_nx_graph(self._graphml_xml_file) or nx.Graph()
                )
                # Reset update flag
                self.storage_updated.value = False

            return self._graph

    async def has_node(self, node_id: str) -> bool:
        graph = await self._get_graph()
        return graph.has_node(node_id)

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        graph = await self._get_graph()
        return graph.has_edge(source_node_id, target_node_id)

    async def get_node(self, node_id: str) -> dict[str, str] | None:
        graph = await self._get_graph()
        return graph.nodes.get(node_id)

    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict]:
        """
        Get nodes as a batch with automatic temporal filtering.
        
        This override ensures that when multiple versions of the same entity exist
        (from different document versions), only the most recent version based on
        insertion_order is returned. This is critical for chronological contract RAG
        where later documents should override information from earlier ones.
        
        Args:
            node_ids: List of node IDs to retrieve
            
        Returns:
            Dictionary mapping node_id to node data. Nodes without insertion_order
            metadata are returned as-is. For nodes with temporal metadata, only the
            version with the highest insertion_order is included.
        """
        graph = await self._get_graph()
        result = {}
        
        for node_id in node_ids:
            node_data = graph.nodes.get(node_id)
            if node_data is not None:
                # If node has temporal metadata, it's already the latest version
                # (because upsert_node keeps the maximum insertion_order)
                result[node_id] = dict(node_data)
        
        return result

    async def node_degree(self, node_id: str) -> int:
        graph = await self._get_graph()
        return graph.degree(node_id)

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        graph = await self._get_graph()
        src_degree = graph.degree(src_id) if graph.has_node(src_id) else 0
        tgt_degree = graph.degree(tgt_id) if graph.has_node(tgt_id) else 0
        return src_degree + tgt_degree

    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, str] | None:
        graph = await self._get_graph()
        return graph.edges.get((source_node_id, target_node_id))

    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]] | None:
        graph = await self._get_graph()
        if graph.has_node(source_node_id):
            return list(graph.edges(source_node_id))
        return None

    async def upsert_node(self, node_id: str, node_data: dict[str, str]) -> None:
        """
        Upsert a node with temporal tracking support.
        
        Temporal fields supported:
        - insertion_order: Sequential order of document insertion (integer)
        - insertion_timestamp: Unix timestamp when document was inserted (integer)
        - update_history: String of source_ids separated by GRAPH_FIELD_SEP (string)
        
        Importance notes:
        1. Changes will be persisted to disk during the next index_done_callback
        2. Only one process should updating the storage at a time before index_done_callback,
           KG-storage-log should be used to avoid data corruption
        """
        from lightrag.constants import GRAPH_FIELD_SEP
        
        graph = await self._get_graph()
        
        # Convert update_history list to string if needed (for GraphML compatibility)
        if 'update_history' in node_data and isinstance(node_data['update_history'], list):
            node_data['update_history'] = GRAPH_FIELD_SEP.join(node_data['update_history'])
        
        # Handle temporal fields when merging with existing node
        if graph.has_node(node_id):
            existing_node = graph.nodes[node_id]
            
            # Merge update_history if present (both stored as strings)
            if 'update_history' in node_data and 'update_history' in existing_node:
                # Parse existing history from string
                existing_history_str = existing_node.get('update_history', '')
                existing_list = existing_history_str.split(GRAPH_FIELD_SEP) if existing_history_str else []
                
                # Parse new history from string (already converted above)
                new_history_str = node_data.get('update_history', '')
                new_list = new_history_str.split(GRAPH_FIELD_SEP) if new_history_str else []
                
                # Combine and deduplicate while preserving order
                combined = existing_list + new_list
                seen = set()
                unique_list = [x for x in combined if x and not (x in seen or seen.add(x))]
                
                # Convert back to string
                node_data['update_history'] = GRAPH_FIELD_SEP.join(unique_list)
            
            # Keep maximum insertion_order (most recent)
            if 'insertion_order' in node_data and 'insertion_order' in existing_node:
                node_data['insertion_order'] = max(
                    int(node_data['insertion_order']),
                    int(existing_node['insertion_order'])
                )
            
            # Keep maximum insertion_timestamp (most recent)
            if 'insertion_timestamp' in node_data and 'insertion_timestamp' in existing_node:
                node_data['insertion_timestamp'] = max(
                    int(node_data['insertion_timestamp']),
                    int(existing_node['insertion_timestamp'])
                )
        
        graph.add_node(node_id, **node_data)

    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ) -> None:
        """
        Upsert an edge with temporal tracking support.
        
        Temporal fields supported:
        - insertion_order: Sequential order of document insertion (integer)
        - insertion_timestamp: Unix timestamp when document was inserted (integer)
        - update_history: String of source_ids separated by GRAPH_FIELD_SEP (string)
        
        Importance notes:
        1. Changes will be persisted to disk during the next index_done_callback
        2. Only one process should updating the storage at a time before index_done_callback,
           KG-storage-log should be used to avoid data corruption
        """
        from lightrag.constants import GRAPH_FIELD_SEP
        
        graph = await self._get_graph()
        
        # Convert update_history list to string if needed (for GraphML compatibility)
        if 'update_history' in edge_data and isinstance(edge_data['update_history'], list):
            edge_data['update_history'] = GRAPH_FIELD_SEP.join(edge_data['update_history'])
        
        # Handle temporal fields when merging with existing edge
        if graph.has_edge(source_node_id, target_node_id):
            existing_edge = graph.edges[source_node_id, target_node_id]
            
            # Merge update_history if present (both stored as strings)
            if 'update_history' in edge_data and 'update_history' in existing_edge:
                # Parse existing history from string
                existing_history_str = existing_edge.get('update_history', '')
                existing_list = existing_history_str.split(GRAPH_FIELD_SEP) if existing_history_str else []
                
                # Parse new history from string (already converted above)
                new_history_str = edge_data.get('update_history', '')
                new_list = new_history_str.split(GRAPH_FIELD_SEP) if new_history_str else []
                
                # Combine and deduplicate while preserving order
                combined = existing_list + new_list
                seen = set()
                unique_list = [x for x in combined if x and not (x in seen or seen.add(x))]
                
                # Convert back to string
                edge_data['update_history'] = GRAPH_FIELD_SEP.join(unique_list)
            
            # Keep maximum insertion_order (most recent)
            if 'insertion_order' in edge_data and 'insertion_order' in existing_edge:
                edge_data['insertion_order'] = max(
                    int(edge_data['insertion_order']),
                    int(existing_edge['insertion_order'])
                )
            
            # Keep maximum insertion_timestamp (most recent)
            if 'insertion_timestamp' in edge_data and 'insertion_timestamp' in existing_edge:
                edge_data['insertion_timestamp'] = max(
                    int(edge_data['insertion_timestamp']),
                    int(existing_edge['insertion_timestamp'])
                )
        
        graph.add_edge(source_node_id, target_node_id, **edge_data)

    async def delete_node(self, node_id: str) -> None:
        """
        Importance notes:
        1. Changes will be persisted to disk during the next index_done_callback
        2. Only one process should updating the storage at a time before index_done_callback,
           KG-storage-log should be used to avoid data corruption
        """
        graph = await self._get_graph()
        if graph.has_node(node_id):
            graph.remove_node(node_id)
            logger.debug(f"[{self.workspace}] Node {node_id} deleted from the graph")
        else:
            logger.warning(
                f"[{self.workspace}] Node {node_id} not found in the graph for deletion"
            )

    async def remove_nodes(self, nodes: list[str]):
        """Delete multiple nodes

        Importance notes:
        1. Changes will be persisted to disk during the next index_done_callback
        2. Only one process should updating the storage at a time before index_done_callback,
           KG-storage-log should be used to avoid data corruption

        Args:
            nodes: List of node IDs to be deleted
        """
        graph = await self._get_graph()
        for node in nodes:
            if graph.has_node(node):
                graph.remove_node(node)

    async def remove_edges(self, edges: list[tuple[str, str]]):
        """Delete multiple edges

        Importance notes:
        1. Changes will be persisted to disk during the next index_done_callback
        2. Only one process should updating the storage at a time before index_done_callback,
           KG-storage-log should be used to avoid data corruption

        Args:
            edges: List of edges to be deleted, each edge is a (source, target) tuple
        """
        graph = await self._get_graph()
        for source, target in edges:
            if graph.has_edge(source, target):
                graph.remove_edge(source, target)

    async def get_all_labels(self) -> list[str]:
        """
        Get all node labels in the graph
        Returns:
            [label1, label2, ...]  # Alphabetically sorted label list
        """
        graph = await self._get_graph()
        labels = set()
        for node in graph.nodes():
            labels.add(str(node))  # Add node id as a label

        # Return sorted list
        return sorted(list(labels))

    async def get_popular_labels(self, limit: int = 300) -> list[str]:
        """
        Get popular labels by node degree (most connected entities)

        Args:
            limit: Maximum number of labels to return

        Returns:
            List of labels sorted by degree (highest first)
        """
        graph = await self._get_graph()

        # Get degrees of all nodes and sort by degree descending
        degrees = dict(graph.degree())
        sorted_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)

        # Return top labels limited by the specified limit
        popular_labels = [str(node) for node, _ in sorted_nodes[:limit]]

        logger.debug(
            f"[{self.workspace}] Retrieved {len(popular_labels)} popular labels (limit: {limit})"
        )

        return popular_labels

    async def search_labels(self, query: str, limit: int = 50) -> list[str]:
        """
        Search labels with fuzzy matching

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching labels sorted by relevance
        """
        graph = await self._get_graph()
        query_lower = query.lower().strip()

        if not query_lower:
            return []

        # Collect matching nodes with relevance scores
        matches = []
        for node in graph.nodes():
            node_str = str(node)
            node_lower = node_str.lower()

            # Skip if no match
            if query_lower not in node_lower:
                continue

            # Calculate relevance score
            # Exact match gets highest score
            if node_lower == query_lower:
                score = 1000
            # Prefix match gets high score
            elif node_lower.startswith(query_lower):
                score = 500
            # Contains match gets base score, with bonus for shorter strings
            else:
                # Shorter strings with matches are more relevant
                score = 100 - len(node_str)
                # Bonus for word boundary matches
                if f" {query_lower}" in node_lower or f"_{query_lower}" in node_lower:
                    score += 50

            matches.append((node_str, score))

        # Sort by relevance score (desc) then alphabetically
        matches.sort(key=lambda x: (-x[1], x[0]))

        # Return top matches limited by the specified limit
        search_results = [match[0] for match in matches[:limit]]

        logger.debug(
            f"[{self.workspace}] Search query '{query}' returned {len(search_results)} results (limit: {limit})"
        )

        return search_results

    async def get_knowledge_graph(
        self,
        node_label: str,
        max_depth: int = 3,
        max_nodes: int = None,
    ) -> KnowledgeGraph:
        """
        Retrieve a connected subgraph of nodes where the label includes the specified `node_label`.

        Args:
            node_label: Label of the starting node，* means all nodes
            max_depth: Maximum depth of the subgraph, Defaults to 3
            max_nodes: Maxiumu nodes to return by BFS, Defaults to 1000

        Returns:
            KnowledgeGraph object containing nodes and edges, with an is_truncated flag
            indicating whether the graph was truncated due to max_nodes limit
        """
        # Get max_nodes from global_config if not provided
        if max_nodes is None:
            max_nodes = self.global_config.get("max_graph_nodes", 1000)
        else:
            # Limit max_nodes to not exceed global_config max_graph_nodes
            max_nodes = min(max_nodes, self.global_config.get("max_graph_nodes", 1000))

        graph = await self._get_graph()

        result = KnowledgeGraph()

        # Handle special case for "*" label
        if node_label == "*":
            # Get degrees of all nodes
            degrees = dict(graph.degree())
            # Sort nodes by degree in descending order and take top max_nodes
            sorted_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)

            # Check if graph is truncated
            if len(sorted_nodes) > max_nodes:
                result.is_truncated = True
                logger.info(
                    f"[{self.workspace}] Graph truncated: {len(sorted_nodes)} nodes found, limited to {max_nodes}"
                )

            limited_nodes = [node for node, _ in sorted_nodes[:max_nodes]]
            # Create subgraph with the highest degree nodes
            subgraph = graph.subgraph(limited_nodes)
        else:
            # Check if node exists
            if node_label not in graph:
                logger.warning(
                    f"[{self.workspace}] Node {node_label} not found in the graph"
                )
                return KnowledgeGraph()  # Return empty graph

            # Use modified BFS to get nodes, prioritizing high-degree nodes at the same depth
            bfs_nodes = []
            visited = set()
            # Store (node, depth, degree) in the queue
            queue = [(node_label, 0, graph.degree(node_label))]

            # Flag to track if there are unexplored neighbors due to depth limit
            has_unexplored_neighbors = False

            # Modified breadth-first search with degree-based prioritization
            while queue and len(bfs_nodes) < max_nodes:
                # Get the current depth from the first node in queue
                current_depth = queue[0][1]

                # Collect all nodes at the current depth
                current_level_nodes = []
                while queue and queue[0][1] == current_depth:
                    current_level_nodes.append(queue.pop(0))

                # Sort nodes at current depth by degree (highest first)
                current_level_nodes.sort(key=lambda x: x[2], reverse=True)

                # Process all nodes at current depth in order of degree
                for current_node, depth, degree in current_level_nodes:
                    if current_node not in visited:
                        visited.add(current_node)
                        bfs_nodes.append(current_node)

                        # Only explore neighbors if we haven't reached max_depth
                        if depth < max_depth:
                            # Add neighbor nodes to queue with incremented depth
                            neighbors = list(graph.neighbors(current_node))
                            # Filter out already visited neighbors
                            unvisited_neighbors = [
                                n for n in neighbors if n not in visited
                            ]
                            # Add neighbors to the queue with their degrees
                            for neighbor in unvisited_neighbors:
                                neighbor_degree = graph.degree(neighbor)
                                queue.append((neighbor, depth + 1, neighbor_degree))
                        else:
                            # Check if there are unexplored neighbors (skipped due to depth limit)
                            neighbors = list(graph.neighbors(current_node))
                            unvisited_neighbors = [
                                n for n in neighbors if n not in visited
                            ]
                            if unvisited_neighbors:
                                has_unexplored_neighbors = True

                    # Check if we've reached max_nodes
                    if len(bfs_nodes) >= max_nodes:
                        break

            # Check if graph is truncated - either due to max_nodes limit or depth limit
            if (queue and len(bfs_nodes) >= max_nodes) or has_unexplored_neighbors:
                if len(bfs_nodes) >= max_nodes:
                    result.is_truncated = True
                    logger.info(
                        f"[{self.workspace}] Graph truncated: max_nodes limit {max_nodes} reached"
                    )
                else:
                    logger.info(
                        f"[{self.workspace}] Graph truncated: found {len(bfs_nodes)} nodes within max_depth {max_depth}"
                    )

            # Create subgraph with BFS discovered nodes
            subgraph = graph.subgraph(bfs_nodes)

        # Add nodes to result
        seen_nodes = set()
        seen_edges = set()
        for node in subgraph.nodes():
            if str(node) in seen_nodes:
                continue

            node_data = dict(subgraph.nodes[node])
            # Get entity_type as labels
            labels = []
            if "entity_type" in node_data:
                if isinstance(node_data["entity_type"], list):
                    labels.extend(node_data["entity_type"])
                else:
                    labels.append(node_data["entity_type"])

            # Create node with properties
            node_properties = {k: v for k, v in node_data.items()}

            result.nodes.append(
                KnowledgeGraphNode(
                    id=str(node), labels=[str(node)], properties=node_properties
                )
            )
            seen_nodes.add(str(node))

        # Add edges to result
        for edge in subgraph.edges():
            source, target = edge
            # Esure unique edge_id for undirect graph
            if str(source) > str(target):
                source, target = target, source
            edge_id = f"{source}-{target}"
            if edge_id in seen_edges:
                continue

            edge_data = dict(subgraph.edges[edge])

            # Create edge with complete information
            result.edges.append(
                KnowledgeGraphEdge(
                    id=edge_id,
                    type="DIRECTED",
                    source=str(source),
                    target=str(target),
                    properties=edge_data,
                )
            )
            seen_edges.add(edge_id)

        logger.info(
            f"[{self.workspace}] Subgraph query successful | Node count: {len(result.nodes)} | Edge count: {len(result.edges)}"
        )
        return result

    async def get_all_nodes(self) -> list[dict]:
        """Get all nodes in the graph.

        Returns:
            A list of all nodes, where each node is a dictionary of its properties
        """
        graph = await self._get_graph()
        all_nodes = []
        for node_id, node_data in graph.nodes(data=True):
            node_data_with_id = node_data.copy()
            node_data_with_id["id"] = node_id
            all_nodes.append(node_data_with_id)
        return all_nodes

    async def get_all_edges(self) -> list[dict]:
        """Get all edges in the graph.

        Returns:
            A list of all edges, where each edge is a dictionary of its properties
        """
        graph = await self._get_graph()
        all_edges = []
        for u, v, edge_data in graph.edges(data=True):
            edge_data_with_nodes = edge_data.copy()
            edge_data_with_nodes["source"] = u
            edge_data_with_nodes["target"] = v
            all_edges.append(edge_data_with_nodes)
        return all_edges
    
    async def get_entities_by_recency(
        self, entity_names: list[str], return_latest_only: bool = True
    ) -> dict[str, dict]:
        """
        Get entities with temporal filtering support.
        
        Args:
            entity_names: List of entity names to retrieve
            return_latest_only: If True, returns only the most recent version of each entity
                              based on insertion_order. If False, returns all versions.
        
        Returns:
            Dictionary mapping entity_name to node data. When return_latest_only=True,
            only entities with the highest insertion_order are included.
        """
        graph = await self._get_graph()
        results = {}
        
        for entity_name in entity_names:
            if graph.has_node(entity_name):
                node_data = dict(graph.nodes[entity_name])
                node_data['entity_name'] = entity_name  # Ensure entity_name is included
                
                if return_latest_only:
                    # Check if this entity has insertion_order metadata
                    if 'insertion_order' in node_data:
                        # Only return if we don't have this entity yet, or this one is newer
                        if entity_name not in results:
                            results[entity_name] = node_data
                        elif int(node_data.get('insertion_order', 0)) > int(results[entity_name].get('insertion_order', 0)):
                            results[entity_name] = node_data
                    else:
                        # No temporal metadata, include it
                        results[entity_name] = node_data
                else:
                    # Return all versions
                    results[entity_name] = node_data
        
        return results
    
    async def get_entity_history(self, entity_name: str) -> dict:
        """
        Get the update history for a specific entity.
        
        Args:
            entity_name: Name of the entity to get history for
        
        Returns:
            Dictionary containing:
            - entity_name: Name of the entity
            - insertion_order: Most recent insertion order
            - insertion_timestamp: Most recent timestamp
            - update_history: List of all source_ids that contributed to this entity
            - update_count: Number of updates
        """
        from lightrag.constants import GRAPH_FIELD_SEP
        
        graph = await self._get_graph()
        
        if not graph.has_node(entity_name):
            return None
        
        node_data = dict(graph.nodes[entity_name])
        
        # Parse update_history from string to list
        update_history_str = node_data.get('update_history', '')
        update_history = update_history_str.split(GRAPH_FIELD_SEP) if update_history_str else []
        
        return {
            'entity_name': entity_name,
            'insertion_order': node_data.get('insertion_order'),
            'insertion_timestamp': node_data.get('insertion_timestamp'),
            'update_history': update_history,
            'update_count': len(update_history) if update_history else 0,
            'description': node_data.get('description', ''),
            'entity_type': node_data.get('entity_type', ''),
        }
    
    async def get_entities_at_time(self, insertion_order: int) -> dict[str, dict]:
        """
        Get all entities as they existed at a specific point in time.
        
        Args:
            insertion_order: Point in time represented by insertion order
        
        Returns:
            Dictionary mapping entity_name to node data for entities that existed
            at or before the specified insertion_order.
        """
        graph = await self._get_graph()
        results = {}
        
        for node_id in graph.nodes():
            node_data = dict(graph.nodes[node_id])
            node_insertion = node_data.get('insertion_order')
            
            # Include entities that existed at or before this time
            if node_insertion is not None and int(node_insertion) <= insertion_order:
                node_data['entity_name'] = node_id
                results[node_id] = node_data
        
        return results
    
    async def filter_entities_by_order(self, entity_data: list[dict], max_insertion_order: int = None, 
                                      min_insertion_order: int = None) -> list[dict]:
        """
        Filter entity data by insertion order range.
        
        Args:
            entity_data: List of entity dictionaries
            max_insertion_order: Maximum insertion order to include (inclusive)
            min_insertion_order: Minimum insertion order to include (inclusive)
        
        Returns:
            Filtered list of entity dictionaries
        """
        filtered = []
        for entity in entity_data:
            insertion_order = entity.get('insertion_order')
            if insertion_order is None:
                # No temporal metadata, include by default
                filtered.append(entity)
                continue
                
            insertion_order = int(insertion_order)
            
            # Apply filters
            if max_insertion_order is not None and insertion_order > max_insertion_order:
                continue
            if min_insertion_order is not None and insertion_order < min_insertion_order:
                continue
                
            filtered.append(entity)
        
        return filtered
    
    async def detect_entity_changes(self, entity_name: str, order1: int, order2: int) -> dict:
        """
        Detect changes in an entity between two points in time.
        
        Args:
            entity_name: Name of the entity to check
            order1: Earlier insertion order
            order2: Later insertion order
        
        Returns:
            Dictionary containing:
            - entity_name: Name of the entity
            - changed: Boolean indicating if entity changed
            - state_at_order1: Entity data at earlier time (or None)
            - state_at_order2: Entity data at later time (or None)
            - description_diff: Textual difference if descriptions changed
        """
        from lightrag.constants import GRAPH_FIELD_SEP
        
        graph = await self._get_graph()
        
        if not graph.has_node(entity_name):
            return {
                'entity_name': entity_name,
                'changed': False,
                'state_at_order1': None,
                'state_at_order2': None,
                'description_diff': None,
            }
        
        node_data = dict(graph.nodes[entity_name])
        update_history_str = node_data.get('update_history', '')
        update_history = update_history_str.split(GRAPH_FIELD_SEP) if update_history_str else []
        
        # Check if entity existed at each time point
        insertion_order = int(node_data.get('insertion_order', 0))
        
        state1 = None if insertion_order > order1 else node_data
        state2 = None if insertion_order > order2 else node_data
        
        # Detect if entity was created or modified between order1 and order2
        changed = False
        if state1 is None and state2 is not None:
            changed = True  # Entity was created
        elif state1 is not None and state2 is not None:
            # Check if update_history shows changes in this range
            # This is a simplified check - full implementation would track per-update timestamps
            changed = order1 < insertion_order <= order2
        
        return {
            'entity_name': entity_name,
            'changed': changed,
            'state_at_order1': state1,
            'state_at_order2': state2,
            'description_diff': None if not changed else f"Entity updated at order {insertion_order}",
        }
    
    async def create_supersedes_relationship(self, prev_doc_id: str, new_doc_id: str, 
                                            prev_insertion_order: int, new_insertion_order: int) -> None:
        """
        Create an explicit SUPERSEDES relationship between two document versions.
        
        Args:
            prev_doc_id: Document ID of the previous version
            new_doc_id: Document ID of the new version
            prev_insertion_order: Insertion order of previous document
            new_insertion_order: Insertion order of new document
        """
        import time
        
        # Create a special edge type for supersession
        edge_data = {
            'relationship': 'SUPERSEDES',
            'description': f'Document {new_doc_id} (order {new_insertion_order}) supersedes {prev_doc_id} (order {prev_insertion_order})',
            'keywords': 'supersedes,replaces,updates',
            'weight': '1.0',
            'insertion_order': str(new_insertion_order),
            'insertion_timestamp': str(int(time.time())),
        }
        
        await self.upsert_edge(prev_doc_id, new_doc_id, edge_data)
        logger.info(f"Created SUPERSEDES relationship: {prev_doc_id} -> {new_doc_id}")
    
    async def get_document_chain(self, doc_id: str) -> list[dict]:
        """
        Get the full chain of document versions (predecessors and successors).
        
        Args:
            doc_id: Document ID to start from
        
        Returns:
            List of documents in chronological order with their relationships
        """
        graph = await self._get_graph()
        chain = []
        
        # Find all SUPERSEDES relationships
        for source, target, edge_data in graph.edges(data=True):
            if edge_data.get('relationship') == 'SUPERSEDES':
                chain.append({
                    'prev_doc': source,
                    'new_doc': target,
                    'insertion_order': edge_data.get('insertion_order'),
                    'description': edge_data.get('description'),
                })
        
        # Sort by insertion order
        chain.sort(key=lambda x: int(x.get('insertion_order', 0)))
        return chain

    async def index_done_callback(self) -> bool:
        """Save data to disk with insertion counter persistence"""
        async with self._storage_lock:
            # Check if storage was updated by another process
            if self.storage_updated.value:
                # Storage was updated by another process, reload data instead of saving
                logger.info(
                    f"[{self.workspace}] Graph was updated by another process, reloading..."
                )
                self._graph = (
                    NetworkXStorage.load_nx_graph(self._graphml_xml_file) or nx.Graph()
                )
                # Reset update flag
                self.storage_updated.value = False
                return False  # Return error

        # Acquire lock and perform persistence
        async with self._storage_lock:
            try:
                # Save data to disk
                NetworkXStorage.write_nx_graph(
                    self._graph, self._graphml_xml_file, self.workspace
                )
                # Notify other processes that data has been updated
                await set_all_update_flags(self.namespace, workspace=self.workspace)
                # Reset own update flag to avoid self-reloading
                self.storage_updated.value = False
                return True  # Return success
            except Exception as e:
                logger.error(f"[{self.workspace}] Error saving graph: {e}")
                return False  # Return error

        return True
    
    async def save_insertion_counter(self, counter_value: int) -> None:
        """
        Save the insertion counter to graph metadata.
        
        Args:
            counter_value: Current value of the insertion counter
        """
        graph = await self._get_graph()
        graph.graph['insertion_counter'] = counter_value
        logger.debug(f"[{self.workspace}] Saved insertion counter: {counter_value}")

    async def drop(self) -> dict[str, str]:
        """Drop all graph data from storage and clean up resources

        This method will:
        1. Remove the graph storage file if it exists
        2. Reset the graph to an empty state
        3. Update flags to notify other processes
        4. Changes is persisted to disk immediately

        Returns:
            dict[str, str]: Operation status and message
            - On success: {"status": "success", "message": "data dropped"}
            - On failure: {"status": "error", "message": "<error details>"}
        """
        try:
            async with self._storage_lock:
                # delete _client_file_name
                if os.path.exists(self._graphml_xml_file):
                    os.remove(self._graphml_xml_file)
                self._graph = nx.Graph()
                # Notify other processes that data has been updated
                await set_all_update_flags(self.namespace, workspace=self.workspace)
                # Reset own update flag to avoid self-reloading
                self.storage_updated.value = False
                logger.info(
                    f"[{self.workspace}] Process {os.getpid()} drop graph file:{self._graphml_xml_file}"
                )
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(
                f"[{self.workspace}] Error dropping graph file:{self._graphml_xml_file}: {e}"
            )
            return {"status": "error", "message": str(e)}
