#!/usr/bin/env python3
"""
LightRAG Local-to-Cloud Storage Migration Tool

Migrates data from local storage backends (JSON KV, NanoVectorDB, NetworkX GraphML)
to cloud storage backends (MongoDB, Milvus, Neptune).

Target cloud configuration:
    kv_storage      = MongoKVStorage
    vector_storage  = MilvusVectorDBStorage
    graph_storage   = NeptuneGraphStorage
    doc_status_storage = MongoDocStatusStorage

Modes:
    delete  – Wipe cloud workspace collections / databases only.
    fresh   – Delete cloud data then upload the full local workspace.
    delta   – Upload new and changed records; optionally remove orphans.
    info    – Show counts and schema details for cloud data (read-only).

Required environment variables (set before running):
    MONGO_URI, MONGO_DATABASE
    MILVUS_URI             (optionally MILVUS_DB_NAME)
    NEPTUNE_ENDPOINT, NEPTUNE_PORT, NEPTUNE_REGION

Usage examples:
    # Fresh upload of workspace "my_ws" from ./rag_storage
    python migrate_storage.py --working-dir ./rag_storage --workspace my_ws --mode fresh

    # Delta sync (incremental)
    python migrate_storage.py --working-dir ./rag_storage --workspace my_ws --mode delta

    # Delete cloud data only
    python migrate_storage.py --working-dir ./rag_storage --workspace my_ws --mode delete

    # Dry-run (read local, report counts, touch nothing in cloud)
    python migrate_storage.py --working-dir ./rag_storage --workspace my_ws --mode fresh --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
import zlib
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("migrate_storage")

# ---------------------------------------------------------------------------
# Namespace constants (mirrors lightrag/namespace.py)
# ---------------------------------------------------------------------------
KV_NAMESPACES = [
    "full_docs",
    "text_chunks",
    "llm_response_cache",
    "full_entities",
    "full_relations",
    "entity_chunks",
    "relation_chunks",
]

VECTOR_NAMESPACES = ["entities", "relationships", "chunks"]

GRAPH_NAMESPACE = "chunk_entity_relation"

DOC_STATUS_NAMESPACE = "doc_status"

# Meta fields expected per vector namespace (must match lightrag.py init)
VECTOR_META_FIELDS: dict[str, set[str]] = {
    "entities": {"entity_name", "source_id", "content", "file_path"},
    "relationships": {"src_id", "tgt_id", "source_id", "content", "file_path"},
    "chunks": {"full_doc_id", "content", "file_path"},
}

# ---------------------------------------------------------------------------
# Local readers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.warning("File not found, skipping: %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        logger.warning(
            "Expected dict at top level in %s, got %s", path, type(data).__name__
        )
        return {}
    return data


def read_local_kv(workspace_dir: Path, namespace: str) -> dict[str, dict[str, Any]]:
    """Load a kv_store_{namespace}.json file and return {id: {fields…}}."""
    path = workspace_dir / f"kv_store_{namespace}.json"
    return _load_json(path)


def read_local_doc_status(workspace_dir: Path) -> dict[str, dict[str, Any]]:
    """Load kv_store_doc_status.json."""
    return read_local_kv(workspace_dir, DOC_STATUS_NAMESPACE)


def _decompress_vector(encoded: str) -> list[float]:
    """Decode a NanoVectorDB compressed vector → float32 list."""
    raw = base64.b64decode(encoded)
    decompressed = zlib.decompress(raw)
    arr = np.frombuffer(decompressed, dtype=np.float16).astype(np.float32)
    return arr.tolist()


def read_local_vectors(workspace_dir: Path, namespace: str) -> list[dict[str, Any]]:
    """
    Load vdb_{namespace}.json via NanoVectorDB internals.
    Returns list of dicts with keys: __id__, __created_at__, vector (float32 list), + meta fields.
    """
    path = workspace_dir / f"vdb_{namespace}.json"
    if not path.exists():
        logger.warning("Vector file not found, skipping: %s", path)
        return []

    try:
        import importlib.util

        if importlib.util.find_spec("nano_vectordb") is None:
            raise ImportError("nano_vectordb not installed")
    except ImportError:
        logger.error(
            "nano_vectordb is required to read local vector files. pip install nano-vectordb"
        )
        sys.exit(1)

    # We need the embedding dim, but we can infer it from the first record.
    # Load via NanoVectorDB with a dummy dim then adjust.
    # Peek at the raw JSON to discover the dimension.
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # NanoVectorDB stores {"data": [...], "matrix": <base64>} or similar.
    # However the internal structure may vary by version.  We'll use the
    # public API instead: instantiate with the correct dim.
    data_records: list[dict] = raw.get("data", [])

    if not data_records:
        logger.info("No vector records in %s", path)
        return []

    meta_fields = VECTOR_META_FIELDS.get(namespace, set())
    results: list[dict[str, Any]] = []

    for rec in data_records:
        entry: dict[str, Any] = {
            "__id__": rec["__id__"],
            "__created_at__": rec.get("__created_at__", 0),
        }
        # Copy meta fields
        for mf in meta_fields:
            if mf in rec:
                entry[mf] = rec[mf]

        # Decompress vector
        encoded_vector = rec.get("vector")
        if encoded_vector and isinstance(encoded_vector, str):
            entry["vector"] = _decompress_vector(encoded_vector)
        elif "__vector__" in rec:
            # Runtime float list (if saved un-compressed)
            v = rec["__vector__"]
            entry["vector"] = list(v) if not isinstance(v, list) else v
        else:
            logger.warning(
                "Record %s in %s has no vector, skipping", rec.get("__id__"), namespace
            )
            continue

        results.append(entry)

    logger.info("Read %d vector records from %s", len(results), path)
    return results


def read_local_graph(
    workspace_dir: Path,
) -> tuple[dict[str, dict], list[tuple[str, str, dict]]]:
    """
    Load graph_chunk_entity_relation.graphml.
    Returns (nodes_dict, edges_list):
        nodes_dict = {node_id: {attr_key: attr_value, …}}
        edges_list = [(source, target, {attr…}), …]
    """
    path = workspace_dir / f"graph_{GRAPH_NAMESPACE}.graphml"
    if not path.exists():
        logger.warning("Graph file not found, skipping: %s", path)
        return {}, []

    G = nx.read_graphml(path)
    nodes = {str(nid): dict(attrs) for nid, attrs in G.nodes(data=True)}
    edges = [(str(u), str(v), dict(d)) for u, v, d in G.edges(data=True)]
    logger.info("Read graph: %d nodes, %d edges", len(nodes), len(edges))
    return nodes, edges


# ---------------------------------------------------------------------------
# Cloud helpers – MongoDB
# ---------------------------------------------------------------------------


async def _get_mongo_db():
    """Return an async MongoDB database handle."""
    try:
        from pymongo import AsyncMongoClient
    except ImportError:
        logger.error("pymongo is required. pip install pymongo")
        sys.exit(1)

    uri = os.environ.get("MONGO_URI", "mongodb://root:root@localhost:27017/")
    db_name = os.environ.get("MONGO_DATABASE", "LightRAG")
    client = AsyncMongoClient(uri)
    return client, client.get_database(db_name)


def _mongo_collection_name(workspace: str, namespace: str) -> str:
    return f"{workspace}_{namespace}" if workspace else namespace


async def mongo_drop_collections(
    workspace: str, namespaces: list[str], *, dry_run: bool = False
):
    """Drop (clear) MongoDB collections for a workspace."""
    client, db = await _get_mongo_db()
    try:
        for ns in namespaces:
            col_name = _mongo_collection_name(workspace, ns)
            if dry_run:
                logger.info("[DRY-RUN] Would drop MongoDB collection: %s", col_name)
            else:
                result = await db[col_name].delete_many({})
                logger.info(
                    "Dropped %d documents from MongoDB collection: %s",
                    result.deleted_count,
                    col_name,
                )
    finally:
        await client.close()


async def mongo_upsert_batch(
    workspace: str,
    namespace: str,
    data: dict[str, dict[str, Any]],
    batch_size: int = 500,
    *,
    dry_run: bool = False,
):
    """Bulk upsert data into a MongoDB collection."""
    if not data:
        return
    from pymongo import UpdateOne

    client, db = await _get_mongo_db()
    col_name = _mongo_collection_name(workspace, namespace)
    collection = db[col_name]

    try:
        items = list(data.items())
        current_time = int(time.time())
        total = 0

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            if dry_run:
                total += len(batch)
                continue

            operations = []
            for k, v in batch:
                doc = v.copy()
                doc["_id"] = k
                doc["update_time"] = current_time
                doc.pop("create_time", None)
                operations.append(
                    UpdateOne(
                        {"_id": k},
                        {
                            "$set": doc,
                            "$setOnInsert": {"create_time": current_time},
                        },
                        upsert=True,
                    )
                )
            await collection.bulk_write(operations)
            total += len(batch)

        action = "Would upsert" if dry_run else "Upserted"
        logger.info("[MongoDB] %s %d documents into %s", action, total, col_name)
    finally:
        await client.close()


async def mongo_get_all_ids(workspace: str, namespace: str) -> set[str]:
    """Return all _id values in a MongoDB collection."""
    client, db = await _get_mongo_db()
    col_name = _mongo_collection_name(workspace, namespace)
    try:
        cursor = db[col_name].find({}, {"_id": 1})
        docs = await cursor.to_list(length=None)
        return {str(d["_id"]) for d in docs}
    finally:
        await client.close()


async def mongo_get_update_times(workspace: str, namespace: str) -> dict[str, int]:
    """Return {_id: update_time} for all docs in a collection."""
    client, db = await _get_mongo_db()
    col_name = _mongo_collection_name(workspace, namespace)
    try:
        cursor = db[col_name].find({}, {"_id": 1, "update_time": 1})
        docs = await cursor.to_list(length=None)
        return {str(d["_id"]): d.get("update_time", 0) for d in docs}
    finally:
        await client.close()


async def mongo_delete_ids(
    workspace: str, namespace: str, ids: list[str], *, dry_run: bool = False
):
    """Delete specific documents by _id."""
    if not ids:
        return
    client, db = await _get_mongo_db()
    col_name = _mongo_collection_name(workspace, namespace)
    try:
        if dry_run:
            logger.info(
                "[DRY-RUN] Would delete %d documents from %s", len(ids), col_name
            )
        else:
            result = await db[col_name].delete_many({"_id": {"$in": ids}})
            logger.info("Deleted %d documents from %s", result.deleted_count, col_name)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Cloud helpers – Milvus
# ---------------------------------------------------------------------------


def _get_milvus_client():
    """Create a pymilvus MilvusClient from environment."""
    try:
        from pymilvus import MilvusClient
    except ImportError:
        logger.error("pymilvus is required. pip install pymilvus")
        sys.exit(1)

    kwargs: dict[str, Any] = {
        "uri": os.environ.get("MILVUS_URI", "http://localhost:19530"),
    }
    user = os.environ.get("MILVUS_USER")
    password = os.environ.get("MILVUS_PASSWORD")
    token = os.environ.get("MILVUS_TOKEN")
    db_name = os.environ.get("MILVUS_DB_NAME")

    if user:
        kwargs["user"] = user
    if password:
        kwargs["password"] = password
    if token:
        kwargs["token"] = token
    if db_name:
        kwargs["db_name"] = db_name

    return MilvusClient(**kwargs)


def _milvus_collection_name(workspace: str, namespace: str) -> str:
    return f"{workspace}_{namespace}" if workspace else namespace


def milvus_drop_collections(
    workspace: str, namespaces: list[str], *, dry_run: bool = False
):
    """Drop Milvus collections for each vector namespace (including stale _old/_temp)."""
    mc = _get_milvus_client()
    try:
        for ns in namespaces:
            col_name = _milvus_collection_name(workspace, ns)
            # Drop the main collection plus any stale migration leftovers
            for suffix in ["", "_old", "_temp"]:
                name = col_name + suffix
                if dry_run:
                    logger.info("[DRY-RUN] Would drop Milvus collection: %s", name)
                else:
                    if mc.has_collection(name):
                        mc.drop_collection(name)
                        logger.info("Dropped Milvus collection: %s", name)
    finally:
        mc.close()


def _ensure_milvus_collection(mc, col_name: str, namespace: str, dim: int):
    """Create a Milvus collection with the correct schema if it doesn't exist."""
    if mc.has_collection(col_name):
        return

    from pymilvus import CollectionSchema, DataType, FieldSchema

    base_fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="created_at", dtype=DataType.INT64),
    ]

    if namespace.endswith("entities"):
        extra = [
            FieldSchema(
                name="entity_name",
                dtype=DataType.VARCHAR,
                max_length=512,
                nullable=True,
            ),
            FieldSchema(
                name="file_path",
                dtype=DataType.VARCHAR,
                max_length=32768,
                nullable=True,
            ),
        ]
        desc = "LightRAG entities vector storage"
    elif namespace.endswith("relationships"):
        extra = [
            FieldSchema(
                name="src_id", dtype=DataType.VARCHAR, max_length=512, nullable=True
            ),
            FieldSchema(
                name="tgt_id", dtype=DataType.VARCHAR, max_length=512, nullable=True
            ),
            FieldSchema(
                name="file_path",
                dtype=DataType.VARCHAR,
                max_length=32768,
                nullable=True,
            ),
        ]
        desc = "LightRAG relationships vector storage"
    elif namespace.endswith("chunks"):
        extra = [
            FieldSchema(
                name="full_doc_id", dtype=DataType.VARCHAR, max_length=64, nullable=True
            ),
            FieldSchema(
                name="file_path",
                dtype=DataType.VARCHAR,
                max_length=32768,
                nullable=True,
            ),
        ]
        desc = "LightRAG chunks vector storage"
    else:
        extra = [
            FieldSchema(
                name="file_path",
                dtype=DataType.VARCHAR,
                max_length=32768,
                nullable=True,
            ),
        ]
        desc = "LightRAG generic vector storage"

    schema = CollectionSchema(
        fields=base_fields + extra, description=desc, enable_dynamic_field=True
    )
    mc.create_collection(collection_name=col_name, schema=schema)

    # Create vector index (AUTOINDEX / COSINE by default)
    index_params = mc.prepare_index_params()
    index_params.add_index(
        field_name="vector", index_type="AUTOINDEX", metric_type="COSINE"
    )
    mc.create_index(collection_name=col_name, index_params=index_params)
    mc.load_collection(col_name)
    logger.info("Created Milvus collection: %s (dim=%d)", col_name, dim)


def milvus_upsert_vectors(
    workspace: str,
    namespace: str,
    records: list[dict[str, Any]],
    batch_size: int = 500,
    *,
    dry_run: bool = False,
):
    """Insert pre-computed vectors into Milvus (bypasses embedding)."""
    if not records:
        return

    mc = _get_milvus_client()
    col_name = _milvus_collection_name(workspace, namespace)
    meta_fields = VECTOR_META_FIELDS.get(namespace, set())

    try:
        # Determine dimension from first record
        dim = len(records[0]["vector"])
        _ensure_milvus_collection(mc, col_name, namespace, dim)

        total = 0
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            if dry_run:
                total += len(batch)
                continue

            rows = []
            for rec in batch:
                row: dict[str, Any] = {
                    "id": rec["__id__"],
                    "vector": rec["vector"],
                    "created_at": rec.get("__created_at__", 0),
                }
                for mf in meta_fields:
                    if mf in rec:
                        row[mf] = rec[mf]
                rows.append(row)

            mc.upsert(collection_name=col_name, data=rows)
            total += len(batch)

        action = "Would upsert" if dry_run else "Upserted"
        logger.info("[Milvus] %s %d vectors into %s", action, total, col_name)
    finally:
        mc.close()


def milvus_get_all_ids(workspace: str, namespace: str) -> set[str]:
    """Query all primary keys from a Milvus collection (paginated)."""
    mc = _get_milvus_client()
    col_name = _milvus_collection_name(workspace, namespace)
    PAGE_SIZE = 16000  # Milvus max is 16384
    try:
        if not mc.has_collection(col_name):
            return set()
        mc.load_collection(col_name)
        all_ids: set[str] = set()
        offset = 0
        while True:
            results = mc.query(
                collection_name=col_name,
                filter="",
                output_fields=["id"],
                limit=PAGE_SIZE,
                offset=offset,
            )
            if not results:
                break
            all_ids.update(str(r["id"]) for r in results)
            if len(results) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return all_ids
    finally:
        mc.close()


def milvus_delete_ids(
    workspace: str, namespace: str, ids: list[str], *, dry_run: bool = False
):
    """Delete vectors by primary key."""
    if not ids:
        return
    mc = _get_milvus_client()
    col_name = _milvus_collection_name(workspace, namespace)
    try:
        if dry_run:
            logger.info("[DRY-RUN] Would delete %d vectors from %s", len(ids), col_name)
        else:
            mc.delete(collection_name=col_name, pks=ids)
            logger.info("[Milvus] Deleted %d vectors from %s", len(ids), col_name)
    finally:
        mc.close()


# ---------------------------------------------------------------------------
# Cloud helpers – Neptune
# ---------------------------------------------------------------------------


class NeptuneHelper:
    """Thin async wrapper around Neptune Gremlin for migration tasks."""

    def __init__(self):
        self._client = None
        self._endpoint = os.environ.get("NEPTUNE_ENDPOINT")
        self._port = int(os.environ.get("NEPTUNE_PORT", "8182"))
        self._region = os.environ.get("NEPTUNE_REGION", "us-east-1")
        self._use_iam = os.environ.get("NEPTUNE_USE_IAM", "true").lower() in (
            "true",
            "1",
            "yes",
        )

    async def connect(self):
        try:
            from gremlin_python.driver import client, serializer
        except ImportError:
            logger.error("gremlinpython is required. pip install gremlinpython")
            sys.exit(1)

        if not self._endpoint:
            raise ValueError("NEPTUNE_ENDPOINT environment variable must be set")

        url = f"wss://{self._endpoint}:{self._port}/gremlin"
        headers = {}

        if self._use_iam:
            try:
                from lightrag.kg.neptune_impl import NeptuneIAMAuth

                iam_auth = NeptuneIAMAuth(self._endpoint, self._port, self._region)
                headers = iam_auth.get_signed_headers()
            except Exception as e:
                logger.error("IAM auth setup failed: %s", e)
                raise

        self._client = client.Client(
            url=url,
            traversal_source="g",
            message_serializer=serializer.GraphSONSerializersV3d0(),
            headers=headers if headers else None,
        )
        logger.info("Connected to Neptune at %s", url)

    async def close(self):
        if self._client:
            await asyncio.to_thread(self._client.close)
            self._client = None

    async def _submit(self, query: str, retries: int = 5):
        for attempt in range(retries):
            try:
                return await asyncio.to_thread(
                    lambda q=query: self._client.submit(q).all().result()
                )
            except Exception as e:
                if (
                    "ConcurrentModificationException" in str(e)
                    and attempt < retries - 1
                ):
                    wait = 0.5 * (2**attempt)
                    logger.warning(
                        "[Neptune] ConcurrentModificationException, retry %d/%d in %.1fs",
                        attempt + 1,
                        retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

    async def drop_workspace(self, workspace: str, *, dry_run: bool = False):
        ws = workspace or "base"
        if dry_run:
            logger.info("[DRY-RUN] Would drop Neptune workspace: %s", ws)
            return
        await self._submit(f"g.V().has('workspace', '{ws}').drop()")
        await self._submit(f"g.E().has('workspace', '{ws}').drop()")
        logger.info("Dropped Neptune workspace: %s", ws)

    async def upsert_node(
        self, workspace: str, node_id: str, node_data: dict[str, str]
    ):
        ws = workspace or "base"
        nid = node_id.replace("'", "\\'")
        props = [f"property('entity_id', '{nid}')"]
        props.append(f"property('workspace', '{ws}')")
        for k, v in node_data.items():
            if k not in ("entity_id", "workspace"):
                v_esc = str(v).replace("'", "\\'")
                props.append(f"property('{k}', '{v_esc}')")
        ps = ".".join(props)
        query = (
            f"g.V().has('entity_id', '{nid}').has('workspace', '{ws}')"
            f".fold().coalesce(unfold(), addV('Entity').{ps}).{ps}"
        )
        await self._submit(query)

    async def upsert_edge(
        self, workspace: str, source: str, target: str, edge_data: dict[str, str]
    ):
        ws = workspace or "base"
        src = source.replace("'", "\\'")
        tgt = target.replace("'", "\\'")
        props = [f"property('workspace', '{ws}')"]
        for k, v in edge_data.items():
            if k != "workspace":
                v_esc = str(v).replace("'", "\\'")
                props.append(f"property('{k}', '{v_esc}')")
        ps = ".".join(props) if props else ""
        query = (
            f"g.V().has('entity_id', '{src}').has('workspace', '{ws}').as('src')"
            f".V().has('entity_id', '{tgt}').has('workspace', '{ws}').as('tgt')"
            f".coalesce("
            f"  __.select('src').outE('RELATES_TO').where(inV().as('tgt')).has('workspace', '{ws}'),"
            f"  __.select('src').addE('RELATES_TO').to(__.select('tgt')).{ps}"
            f").{ps}"
        )
        await self._submit(query)

    async def get_all_node_ids(self, workspace: str) -> set[str]:
        ws = workspace or "base"
        result = await self._submit(
            f"g.V().has('workspace', '{ws}').values('entity_id').dedup()"
        )
        return set(result) if result else set()

    async def get_all_edge_keys(self, workspace: str) -> set[tuple[str, str]]:
        ws = workspace or "base"
        result = await self._submit(
            f"g.E().has('workspace', '{ws}')"
            f".project('source','target')"
            f".by(outV().values('entity_id'))"
            f".by(inV().values('entity_id'))"
        )
        if not result:
            return set()
        return {(e["source"], e["target"]) for e in result}

    async def delete_nodes(
        self, workspace: str, node_ids: list[str], *, dry_run: bool = False
    ):
        if not node_ids:
            return
        ws = workspace or "base"
        if dry_run:
            logger.info("[DRY-RUN] Would delete %d Neptune nodes", len(node_ids))
            return
        for nid in node_ids:
            nid_esc = nid.replace("'", "\\'")
            await self._submit(
                f"g.V().has('entity_id', '{nid_esc}').has('workspace', '{ws}').drop()"
            )
        logger.info("[Neptune] Deleted %d nodes", len(node_ids))

    async def delete_edges(
        self, workspace: str, edge_keys: list[tuple[str, str]], *, dry_run: bool = False
    ):
        if not edge_keys:
            return
        ws = workspace or "base"
        if dry_run:
            logger.info("[DRY-RUN] Would delete %d Neptune edges", len(edge_keys))
            return
        for src, tgt in edge_keys:
            src_esc = src.replace("'", "\\'")
            tgt_esc = tgt.replace("'", "\\'")
            await self._submit(
                f"g.V().has('entity_id', '{src_esc}').has('workspace', '{ws}')"
                f".outE().where(inV().has('entity_id', '{tgt_esc}').has('workspace', '{ws}'))"
                f".has('workspace', '{ws}').drop()"
            )
        logger.info("[Neptune] Deleted %d edges", len(edge_keys))


# ---------------------------------------------------------------------------
# High-level migration operations
# ---------------------------------------------------------------------------


async def do_delete(workspace: str, *, dry_run: bool = False):
    """Delete all cloud data for the workspace."""
    logger.info("=== DELETE mode: wiping cloud workspace '%s' ===", workspace)

    # MongoDB KV + doc_status
    all_mongo_ns = KV_NAMESPACES + [DOC_STATUS_NAMESPACE]
    await mongo_drop_collections(workspace, all_mongo_ns, dry_run=dry_run)

    # Milvus vectors
    milvus_drop_collections(workspace, VECTOR_NAMESPACES, dry_run=dry_run)

    # Neptune graph
    neptune = NeptuneHelper()
    await neptune.connect()
    try:
        await neptune.drop_workspace(workspace, dry_run=dry_run)
    finally:
        await neptune.close()

    logger.info("=== DELETE complete ===")


async def do_fresh(
    workspace_dir: Path, workspace: str, batch_size: int, *, dry_run: bool = False
):
    """Delete cloud data then upload full local workspace."""
    logger.info("=== FRESH mode: full upload of '%s' ===", workspace)

    # Step 1: delete existing cloud data
    await do_delete(workspace, dry_run=dry_run)

    # Step 2: upload KV namespaces
    for ns in KV_NAMESPACES:
        data = read_local_kv(workspace_dir, ns)
        if data:
            logger.info("Uploading KV namespace '%s': %d records", ns, len(data))
            await mongo_upsert_batch(workspace, ns, data, batch_size, dry_run=dry_run)
        else:
            logger.info("KV namespace '%s' is empty, skipping", ns)

    # Step 3: upload doc_status
    doc_data = read_local_doc_status(workspace_dir)
    if doc_data:
        logger.info("Uploading doc_status: %d records", len(doc_data))
        await mongo_upsert_batch(
            workspace, DOC_STATUS_NAMESPACE, doc_data, batch_size, dry_run=dry_run
        )

    # Step 4: upload vectors
    for ns in VECTOR_NAMESPACES:
        records = read_local_vectors(workspace_dir, ns)
        if records:
            logger.info("Uploading vectors '%s': %d records", ns, len(records))
            milvus_upsert_vectors(workspace, ns, records, batch_size, dry_run=dry_run)
        else:
            logger.info("Vector namespace '%s' is empty, skipping", ns)

    # Step 5: upload graph
    nodes, edges = read_local_graph(workspace_dir)
    if nodes or edges:
        logger.info("Uploading graph: %d nodes, %d edges", len(nodes), len(edges))
        neptune = NeptuneHelper()
        await neptune.connect()
        try:
            if not dry_run:
                # Upload nodes sequentially to avoid ConcurrentModificationException
                for i, (nid, ndata) in enumerate(nodes.items(), 1):
                    await neptune.upsert_node(workspace, nid, ndata)
                    if i % 500 == 0:
                        logger.info("[Neptune] Uploaded %d / %d nodes", i, len(nodes))
                logger.info("[Neptune] Uploaded %d nodes", len(nodes))

                # Upload edges sequentially
                for i, (s, t, d) in enumerate(edges, 1):
                    await neptune.upsert_edge(workspace, s, t, d)
                    if i % 500 == 0:
                        logger.info("[Neptune] Uploaded %d / %d edges", i, len(edges))
                logger.info("[Neptune] Uploaded %d edges", len(edges))
            else:
                logger.info(
                    "[DRY-RUN] Would upload %d nodes and %d edges to Neptune",
                    len(nodes),
                    len(edges),
                )
        finally:
            await neptune.close()

    logger.info("=== FRESH upload complete ===")


async def do_delta(
    workspace_dir: Path,
    workspace: str,
    batch_size: int,
    *,
    dry_run: bool = False,
    delete_orphans: bool = True,
):
    """Incremental sync: upload new/changed, optionally remove orphans."""
    logger.info("=== DELTA mode: incremental sync of '%s' ===", workspace)

    # --- KV namespaces ---
    for ns in KV_NAMESPACES:
        local_data = read_local_kv(workspace_dir, ns)
        if not local_data:
            logger.info("KV '%s': local is empty, skipping", ns)
            continue

        local_ids = set(local_data.keys())
        cloud_times = await mongo_get_update_times(workspace, ns)
        cloud_ids = set(cloud_times.keys())

        new_ids = local_ids - cloud_ids
        common_ids = local_ids & cloud_ids
        orphan_ids = cloud_ids - local_ids

        # Detect changed records by comparing update_time
        changed_ids = set()
        for cid in common_ids:
            local_ut = local_data[cid].get("update_time", 0)
            cloud_ut = cloud_times.get(cid, 0)
            if local_ut > cloud_ut:
                changed_ids.add(cid)

        upsert_ids = new_ids | changed_ids
        upsert_data = {k: local_data[k] for k in upsert_ids}

        logger.info(
            "KV '%s': %d new, %d changed, %d unchanged, %d orphan",
            ns,
            len(new_ids),
            len(changed_ids),
            len(common_ids - changed_ids),
            len(orphan_ids),
        )

        if upsert_data:
            await mongo_upsert_batch(
                workspace, ns, upsert_data, batch_size, dry_run=dry_run
            )

        if delete_orphans and orphan_ids:
            await mongo_delete_ids(workspace, ns, list(orphan_ids), dry_run=dry_run)

    # --- Doc status ---
    local_doc = read_local_doc_status(workspace_dir)
    if local_doc:
        local_ids = set(local_doc.keys())
        cloud_doc_times = await mongo_get_update_times(workspace, DOC_STATUS_NAMESPACE)
        cloud_ids = set(cloud_doc_times.keys())

        new_ids = local_ids - cloud_ids
        orphan_ids = cloud_ids - local_ids

        # For doc_status, upsert everything new + anything with updated_at change
        changed_ids = set()
        for cid in local_ids & cloud_ids:
            local_ut = local_doc[cid].get(
                "updated_at", local_doc[cid].get("update_time", "")
            )
            cloud_ut = cloud_doc_times.get(cid, 0)
            # Compare as strings or ints depending on format
            if str(local_ut) != str(cloud_ut):
                changed_ids.add(cid)

        upsert_ids = new_ids | changed_ids
        upsert_data = {k: local_doc[k] for k in upsert_ids}

        logger.info(
            "doc_status: %d new, %d changed, %d orphan",
            len(new_ids),
            len(changed_ids),
            len(orphan_ids),
        )

        if upsert_data:
            await mongo_upsert_batch(
                workspace,
                DOC_STATUS_NAMESPACE,
                upsert_data,
                batch_size,
                dry_run=dry_run,
            )

        if delete_orphans and orphan_ids:
            await mongo_delete_ids(
                workspace, DOC_STATUS_NAMESPACE, list(orphan_ids), dry_run=dry_run
            )

    # --- Vectors ---
    for ns in VECTOR_NAMESPACES:
        local_records = read_local_vectors(workspace_dir, ns)
        if not local_records:
            logger.info("Vector '%s': local is empty, skipping", ns)
            continue

        local_ids = {r["__id__"] for r in local_records}
        cloud_ids = milvus_get_all_ids(workspace, ns)

        new_ids = local_ids - cloud_ids
        orphan_ids = cloud_ids - local_ids

        # For vectors, we re-upload new records. Detecting "changed" vectors is
        # expensive (would need to compare embeddings), so we upload all new and
        # let Milvus upsert handle duplicates idempotently.
        new_records = [r for r in local_records if r["__id__"] in new_ids]

        logger.info(
            "Vector '%s': %d new, %d existing, %d orphan",
            ns,
            len(new_ids),
            len(local_ids & cloud_ids),
            len(orphan_ids),
        )

        if new_records:
            milvus_upsert_vectors(
                workspace, ns, new_records, batch_size, dry_run=dry_run
            )

        if delete_orphans and orphan_ids:
            milvus_delete_ids(workspace, ns, list(orphan_ids), dry_run=dry_run)

    # --- Graph ---
    local_nodes, local_edges = read_local_graph(workspace_dir)
    if local_nodes or local_edges:
        neptune = NeptuneHelper()
        await neptune.connect()
        try:
            local_node_ids = set(local_nodes.keys())
            local_edge_keys = {(s, t) for s, t, _ in local_edges}

            cloud_node_ids = await neptune.get_all_node_ids(workspace)
            cloud_edge_keys = await neptune.get_all_edge_keys(workspace)

            new_node_ids = local_node_ids - cloud_node_ids
            orphan_node_ids = cloud_node_ids - local_node_ids
            new_edge_keys = local_edge_keys - cloud_edge_keys
            orphan_edge_keys = cloud_edge_keys - local_edge_keys

            logger.info(
                "Graph: %d new nodes, %d orphan nodes, %d new edges, %d orphan edges",
                len(new_node_ids),
                len(orphan_node_ids),
                len(new_edge_keys),
                len(orphan_edge_keys),
            )

            if not dry_run:
                # Upload new nodes sequentially
                if new_node_ids:
                    for i, nid in enumerate(new_node_ids, 1):
                        await neptune.upsert_node(workspace, nid, local_nodes[nid])
                        if i % 500 == 0:
                            logger.info(
                                "[Neptune] Uploaded %d / %d new nodes",
                                i,
                                len(new_node_ids),
                            )
                    logger.info("[Neptune] Uploaded %d new nodes", len(new_node_ids))

                # Upload new edges sequentially
                edge_lookup = {(s, t): d for s, t, d in local_edges}
                if new_edge_keys:
                    for i, (src, tgt) in enumerate(new_edge_keys, 1):
                        await neptune.upsert_edge(
                            workspace, src, tgt, edge_lookup[(src, tgt)]
                        )
                        if i % 500 == 0:
                            logger.info(
                                "[Neptune] Uploaded %d / %d new edges",
                                i,
                                len(new_edge_keys),
                            )
                    logger.info("[Neptune] Uploaded %d new edges", len(new_edge_keys))

                # Remove orphans
                if delete_orphans:
                    await neptune.delete_edges(
                        workspace, list(orphan_edge_keys), dry_run=dry_run
                    )
                    await neptune.delete_nodes(
                        workspace, list(orphan_node_ids), dry_run=dry_run
                    )
            else:
                logger.info(
                    "[DRY-RUN] Would upload %d nodes, %d edges; delete %d nodes, %d edges",
                    len(new_node_ids),
                    len(new_edge_keys),
                    len(orphan_node_ids),
                    len(orphan_edge_keys),
                )
        finally:
            await neptune.close()

    logger.info("=== DELTA sync complete ===")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


async def do_verify(workspace_dir: Path, workspace: str):
    """Spot-check cloud storage to verify data was migrated correctly."""
    logger.info("=== VERIFY mode: checking cloud data for '%s' ===", workspace)
    issues = 0

    # --- MongoDB ---
    logger.info("--- MongoDB verification ---")
    for ns in KV_NAMESPACES + [DOC_STATUS_NAMESPACE]:
        cloud_ids = await mongo_get_all_ids(workspace, ns)
        local_data = read_local_kv(workspace_dir, ns)
        local_count = len(local_data)
        cloud_count = len(cloud_ids)
        status = "OK" if cloud_count == local_count else "MISMATCH"
        if status == "MISMATCH":
            issues += 1
        logger.info(
            "  [%s] %s: local=%d, cloud=%d", status, ns, local_count, cloud_count
        )

    # --- Milvus ---
    logger.info("--- Milvus verification ---")
    mc = _get_milvus_client()
    try:
        for ns in VECTOR_NAMESPACES:
            col_name = _milvus_collection_name(workspace, ns)
            local_records = read_local_vectors(workspace_dir, ns)

            if not mc.has_collection(col_name):
                logger.info("  [MISSING] %s: collection does not exist!", ns)
                issues += 1
                continue

            mc.load_collection(col_name)

            # Check count via stats
            stats = mc.get_collection_stats(col_name)
            cloud_count = int(stats.get("row_count", 0))
            local_count = len(local_records)
            status = "OK" if cloud_count == local_count else "MISMATCH"
            if status == "MISMATCH":
                issues += 1
            logger.info(
                "  [%s] %s: local=%d, cloud=%d",
                status,
                ns,
                local_count,
                cloud_count,
            )

            # Spot-check: pick first record, search by its vector
            if local_records and cloud_count > 0:
                sample = local_records[0]
                sample_id = sample["__id__"]
                sample_vec = sample["vector"]

                # Verify the record exists by ID
                id_result = mc.query(
                    collection_name=col_name,
                    filter=f'id == "{sample_id}"',
                    output_fields=["id", "created_at"],
                    limit=1,
                )
                if id_result:
                    logger.info("    ID lookup for '%s': FOUND", sample_id)
                else:
                    logger.info("    ID lookup for '%s': NOT FOUND", sample_id)
                    issues += 1

                # Verify vector search returns results
                search_results = mc.search(
                    collection_name=col_name,
                    data=[sample_vec],
                    limit=5,
                    output_fields=["id"],
                    search_params={
                        "metric_type": "COSINE",
                        "params": {"radius": 0.2},
                    },
                )
                hits = len(search_results[0]) if search_results else 0
                if hits > 0:
                    distances = [h["distance"] for h in search_results[0][:3]]
                    logger.info(
                        "    Vector search (cosine≥0.8): %d hits, top distances=%s",
                        hits,
                        distances,
                    )
                else:
                    logger.info("    Vector search: 0 hits — VECTORS MAY BE CORRUPT")
                    issues += 1
    finally:
        mc.close()

    # --- Neptune ---
    logger.info("--- Neptune verification ---")
    local_nodes, local_edges = read_local_graph(workspace_dir)

    neptune = NeptuneHelper()
    await neptune.connect()
    try:
        cloud_node_ids = await neptune.get_all_node_ids(workspace)
        cloud_edge_keys = await neptune.get_all_edge_keys(workspace)

        local_node_count = len(local_nodes)
        local_edge_count = len(local_edges)
        cloud_node_count = len(cloud_node_ids)
        cloud_edge_count = len(cloud_edge_keys)

        n_status = "OK" if cloud_node_count == local_node_count else "MISMATCH"
        e_status = "OK" if cloud_edge_count == local_edge_count else "MISMATCH"
        if n_status == "MISMATCH":
            issues += 1
        if e_status == "MISMATCH":
            issues += 1

        logger.info(
            "  [%s] Nodes: local=%d, cloud=%d",
            n_status,
            local_node_count,
            cloud_node_count,
        )
        logger.info(
            "  [%s] Edges: local=%d, cloud=%d",
            e_status,
            local_edge_count,
            cloud_edge_count,
        )

        # Spot check: pick a node that has edges locally and check Neptune
        if local_edges:
            sample_src = local_edges[0][0]
            local_edge_count_for_node = sum(
                1 for s, t, _ in local_edges if s == sample_src or t == sample_src
            )
            result = await neptune._submit(
                f"g.V().has('entity_id', '{sample_src.replace(chr(39), chr(92) + chr(39))}')"
                f".has('workspace', '{workspace or 'base'}').bothE().count()"
            )
            cloud_edges_for_node = result[0] if result else 0
            logger.info(
                "    Spot-check node '%s': local edges=%d, cloud edges=%d",
                sample_src[:50],
                local_edge_count_for_node,
                cloud_edges_for_node,
            )
            if cloud_edges_for_node == 0 and local_edge_count_for_node > 0:
                issues += 1
    finally:
        await neptune.close()

    logger.info("=== VERIFY complete: %d issue(s) found ===", issues)
    return issues


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


async def do_info(workspace: str):
    """Report counts and schema details for cloud data (read-only)."""
    logger.info("=== INFO mode: cloud data for '%s' ===", workspace)

    # --- MongoDB ---
    logger.info("--- MongoDB ---")
    mongo_total = 0
    for ns in KV_NAMESPACES + [DOC_STATUS_NAMESPACE]:
        cloud_ids = await mongo_get_all_ids(workspace, ns)
        count = len(cloud_ids)
        mongo_total += count
        logger.info("  %s: %d documents", ns, count)
    logger.info("  MongoDB total: %d documents", mongo_total)

    # --- Milvus ---
    logger.info("--- Milvus ---")
    mc = _get_milvus_client()
    milvus_total = 0
    try:
        for ns in VECTOR_NAMESPACES:
            col_name = _milvus_collection_name(workspace, ns)
            if not mc.has_collection(col_name):
                logger.info("  %s: collection does not exist", ns)
                continue
            mc.load_collection(col_name)
            stats = mc.get_collection_stats(col_name)
            row_count = int(stats.get("row_count", 0))
            milvus_total += row_count

            # Get schema details
            info = mc.describe_collection(col_name)
            dim = None
            fields_summary = []
            for f in info.get("fields", []):
                fname = f["name"]
                if fname == "vector":
                    dim = f.get("params", {}).get("dim")
                    fields_summary.append(f"vector(dim={dim})")
                else:
                    fields_summary.append(fname)

            logger.info(
                "  %s: %d vectors, dim=%s, fields=[%s]",
                ns,
                row_count,
                dim or "?",
                ", ".join(fields_summary),
            )
    finally:
        mc.close()
    logger.info("  Milvus total: %d vectors", milvus_total)

    # --- Neptune ---
    logger.info("--- Neptune ---")
    neptune = NeptuneHelper()
    await neptune.connect()
    try:
        node_ids = await neptune.get_all_node_ids(workspace)
        edge_keys = await neptune.get_all_edge_keys(workspace)
        logger.info("  Nodes: %d", len(node_ids))
        logger.info("  Edges: %d", len(edge_keys))
    finally:
        await neptune.close()

    logger.info("=== INFO complete ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate LightRAG local storage to cloud (MongoDB + Milvus + Neptune).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--working-dir",
        default=os.environ.get("WORKING_DIR"),
        help="Path to LightRAG working directory (default: WORKING_DIR from .env).",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("WORKSPACE"),
        help="Workspace name (default: WORKSPACE from .env).",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["delete", "fresh", "delta", "verify", "info"],
        help="Migration mode: delete | fresh | delta | verify | info.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for bulk upload operations (default: 500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without touching cloud storage.",
    )
    parser.add_argument(
        "--no-delete-orphans",
        action="store_true",
        help="In delta mode, keep cloud records that no longer exist locally.",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Skip the llm_response_cache KV namespace (can be very large).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    if not args.working_dir and args.mode != "info":
        logger.error("--working-dir is required (or set WORKING_DIR in .env)")
        sys.exit(1)
    if not args.workspace:
        logger.error("--workspace is required (or set WORKSPACE in .env)")
        sys.exit(1)

    # Info mode only needs workspace, not working-dir
    if args.mode == "info":
        if not args.workspace:
            logger.error("--workspace is required (or set WORKSPACE in .env)")
            sys.exit(1)
        logger.info("Workspace   : %s", args.workspace)
        logger.info("Mode        : %s", args.mode)
        await do_info(args.workspace)
        return

    working_dir = Path(args.working_dir).resolve()
    workspace_dir = working_dir / args.workspace

    if not workspace_dir.is_dir():
        logger.error("Workspace directory does not exist: %s", workspace_dir)
        sys.exit(1)

    logger.info("Working dir : %s", working_dir)
    logger.info("Workspace   : %s", args.workspace)
    logger.info("Workspace dir: %s", workspace_dir)
    logger.info("Mode        : %s", args.mode)
    logger.info("Batch size  : %d", args.batch_size)
    logger.info("Dry run     : %s", args.dry_run)

    # Optionally skip the LLM cache namespace
    global KV_NAMESPACES
    if args.skip_cache:
        KV_NAMESPACES = [ns for ns in KV_NAMESPACES if ns != "llm_response_cache"]
        logger.info("Skipping llm_response_cache namespace")

    if args.mode == "delete":
        await do_delete(args.workspace, dry_run=args.dry_run)

    elif args.mode == "fresh":
        await do_fresh(
            workspace_dir, args.workspace, args.batch_size, dry_run=args.dry_run
        )

    elif args.mode == "delta":
        await do_delta(
            workspace_dir,
            args.workspace,
            args.batch_size,
            dry_run=args.dry_run,
            delete_orphans=not args.no_delete_orphans,
        )

    elif args.mode == "verify":
        await do_verify(workspace_dir, args.workspace)


if __name__ == "__main__":
    asyncio.run(main())
