"""
Connectivity tests for DocumentDB, Neptune (with OpenSearch), and Milvus.

These are integration tests that verify real connections to external services.
Credentials are loaded from the .env file.

Run with:
    pytest tests/test_connectivity.py -v --run-integration
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# DocumentDB Connectivity Tests
# ---------------------------------------------------------------------------


class TestDocumentDBConnectivity:
    """Test connectivity to AWS DocumentDB (MongoDB-compatible)."""

    @pytest.fixture(autouse=True)
    def _check_env(self):
        """Skip if DocumentDB credentials are not configured."""
        if not os.environ.get("MONGO_URI"):
            pytest.skip("MONGO_URI not set in .env")

    def test_documentdb_ping(self):
        """Verify basic connectivity to DocumentDB via ping command."""
        pymongo = pytest.importorskip("pymongo", reason="pymongo required")

        mongo_uri = os.environ["MONGO_URI"]
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)

        try:
            result = client.admin.command("ping")
            assert result.get("ok") == 1.0, f"Ping failed: {result}"
        finally:
            client.close()

    def test_documentdb_list_databases(self):
        """Verify we can list databases on DocumentDB."""
        pymongo = pytest.importorskip("pymongo", reason="pymongo required")

        mongo_uri = os.environ["MONGO_URI"]
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)

        try:
            db_names = client.list_database_names()
            assert isinstance(db_names, list), "Expected list of database names"
        finally:
            client.close()

    def test_documentdb_target_database_accessible(self):
        """Verify the configured target database is accessible."""
        pymongo = pytest.importorskip("pymongo", reason="pymongo required")

        mongo_uri = os.environ["MONGO_URI"]
        db_name = os.environ.get("MONGO_DATABASE", "documents")
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)

        try:
            db = client[db_name]
            # list_collection_names will fail if we can't access the database
            collections = db.list_collection_names()
            assert isinstance(collections, list), "Expected list of collection names"
        finally:
            client.close()

    def test_documentdb_write_read_delete(self):
        """Verify write/read/delete round-trip on DocumentDB."""
        pymongo = pytest.importorskip("pymongo", reason="pymongo required")

        mongo_uri = os.environ["MONGO_URI"]
        db_name = os.environ.get("MONGO_DATABASE", "documents")
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)

        try:
            db = client[db_name]
            test_collection = db["_connectivity_test"]
            test_doc = {"_id": "connectivity_test_probe", "status": "ok"}

            # Insert
            test_collection.replace_one(
                {"_id": test_doc["_id"]}, test_doc, upsert=True
            )

            # Read back
            found = test_collection.find_one({"_id": test_doc["_id"]})
            assert found is not None, "Failed to read back test document"
            assert found["status"] == "ok"

            # Delete
            test_collection.delete_one({"_id": test_doc["_id"]})
            assert test_collection.find_one({"_id": test_doc["_id"]}) is None
        finally:
            client.close()


# ---------------------------------------------------------------------------
# Neptune + OpenSearch Connectivity Tests
# ---------------------------------------------------------------------------


class TestNeptuneConnectivity:
    """Test connectivity to AWS Neptune graph database."""

    @pytest.fixture(autouse=True)
    def _check_env(self):
        """Skip if Neptune credentials are not configured."""
        if not os.environ.get("NEPTUNE_ENDPOINT"):
            pytest.skip("NEPTUNE_ENDPOINT not set in .env")

    def _get_neptune_client(self):
        """Create a Neptune Gremlin client with IAM auth."""
        from gremlin_python.driver import client as gremlin_client, serializer

        endpoint = os.environ["NEPTUNE_ENDPOINT"]
        port = int(os.environ.get("NEPTUNE_PORT", "8182"))
        region = os.environ.get("NEPTUNE_REGION", "us-east-1")
        use_iam = os.environ.get("NEPTUNE_USE_IAM", "true").lower() in (
            "true", "1", "yes", "on"
        )

        url = f"wss://{endpoint}:{port}/gremlin"
        headers = {}

        if use_iam:
            from lightrag.kg.neptune_impl import NeptuneIAMAuth

            iam_auth = NeptuneIAMAuth(endpoint, port, region)
            headers = iam_auth.get_signed_headers()

        return gremlin_client.Client(
            url=url,
            traversal_source="g",
            message_serializer=serializer.GraphSONSerializersV3d0(),
            headers=headers if headers else None,
        )

    def test_neptune_gremlin_connection(self):
        """Verify basic Gremlin connectivity to Neptune."""
        pytest.importorskip("gremlin_python", reason="gremlin_python required")
        pytest.importorskip("boto3", reason="boto3 required for IAM auth")

        client = self._get_neptune_client()

        try:
            # Simple traversal to verify connectivity
            result = client.submit("g.V().limit(1).count()").all().result()
            assert result is not None, "Expected non-None result from Neptune"
        finally:
            client.close()

    def test_neptune_vertex_count(self):
        """Verify we can count vertices in Neptune."""
        pytest.importorskip("gremlin_python", reason="gremlin_python required")
        pytest.importorskip("boto3", reason="boto3 required for IAM auth")

        client = self._get_neptune_client()

        try:
            result = client.submit("g.V().count()").all().result()
            assert len(result) > 0, "Expected count result"
            count = result[0]
            assert isinstance(count, int), f"Expected int count, got {type(count)}"
            assert count >= 0, "Vertex count should be non-negative"
        finally:
            client.close()

    def test_neptune_edge_count(self):
        """Verify we can count edges in Neptune."""
        pytest.importorskip("gremlin_python", reason="gremlin_python required")
        pytest.importorskip("boto3", reason="boto3 required for IAM auth")

        client = self._get_neptune_client()

        try:
            result = client.submit("g.E().count()").all().result()
            assert len(result) > 0, "Expected count result"
            count = result[0]
            assert isinstance(count, int), f"Expected int count, got {type(count)}"
            assert count >= 0, "Edge count should be non-negative"
        finally:
            client.close()

    def test_neptune_status_endpoint(self):
        """Verify Neptune cluster status via HTTP endpoint."""
        pytest.importorskip("requests", reason="requests required")
        pytest.importorskip("boto3", reason="boto3 required for IAM auth")
        import requests
        import boto3
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        endpoint = os.environ["NEPTUNE_ENDPOINT"]
        port = int(os.environ.get("NEPTUNE_PORT", "8182"))
        region = os.environ.get("NEPTUNE_REGION", "us-east-1")

        url = f"https://{endpoint}:{port}/status"

        session = boto3.Session()
        credentials = session.get_credentials()
        request = AWSRequest(method="GET", url=url, headers={"host": f"{endpoint}:{port}"})
        SigV4Auth(credentials, "neptune-db", region).add_auth(request)

        response = requests.get(url, headers=dict(request.headers), timeout=10)
        assert response.status_code == 200, f"Status endpoint returned {response.status_code}"

        status_data = response.json()
        assert status_data.get("status") == "healthy", f"Neptune not healthy: {status_data}"


class TestNeptuneOpenSearchConnectivity:
    """Test connectivity to OpenSearch (used alongside Neptune for full-text search)."""

    @pytest.fixture(autouse=True)
    def _check_env(self):
        """Skip if OpenSearch endpoint is not configured."""
        endpoint = os.environ.get("NEPTUNE_OPENSEARCH_ENDPOINT") or os.environ.get(
            "OPENSEARCH_HOSTS"
        )
        if not endpoint:
            pytest.skip("NEPTUNE_OPENSEARCH_ENDPOINT/OPENSEARCH_HOSTS not set in .env")

    def _get_opensearch_endpoint(self):
        """Get the OpenSearch endpoint URL."""
        return os.environ.get("NEPTUNE_OPENSEARCH_ENDPOINT") or os.environ.get(
            "OPENSEARCH_HOSTS", ""
        )

    def _build_opensearch_client(self):
        """Build an OpenSearch client from environment variables.

        Uses the sync OpenSearch client with RequestsHttpConnection which
        properly supports AWSV4SignerAuth for AWS OpenSearch Serverless.
        """
        from opensearchpy import OpenSearch, RequestsHttpConnection

        endpoint = self._get_opensearch_endpoint()
        use_ssl = os.environ.get("OPENSEARCH_USE_SSL", "true").lower() in (
            "true", "1", "yes"
        )
        verify_certs = os.environ.get("OPENSEARCH_VERIFY_CERTS", "false").lower() in (
            "true", "1", "yes"
        )
        username = os.environ.get("OPENSEARCH_USER", "")
        password = os.environ.get("OPENSEARCH_PASSWORD", "")

        # Determine auth method
        http_auth = None
        if username and password:
            http_auth = (username, password)
        else:
            # Use AWSV4SignerAuth for AWS OpenSearch Serverless
            try:
                import boto3
                from opensearchpy import AWSV4SignerAuth

                session = boto3.Session()
                credentials = session.get_credentials()
                region = os.environ.get("NEPTUNE_REGION", "us-east-1")
                http_auth = AWSV4SignerAuth(credentials, region, "aoss")
            except (ImportError, Exception):
                pass

        return OpenSearch(
            hosts=[endpoint],
            http_auth=http_auth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            ssl_show_warn=False,
            connection_class=RequestsHttpConnection,
            timeout=15,
        )

    def test_opensearch_connectivity(self):
        """Verify connectivity to OpenSearch / AOSS by performing a search.

        AWS OpenSearch Serverless (AOSS) does not support GET / or _cat APIs,
        so we use a wildcard search request to verify the connection is live
        and IAM auth is working.
        """
        pytest.importorskip("opensearchpy", reason="opensearchpy required")

        client = self._build_opensearch_client()

        # A match_all search against a wildcard index pattern works on both
        # standard OpenSearch and AOSS.  AOSS returns 404 if no indices match
        # the pattern, which still proves auth + connectivity succeeded.
        from opensearchpy.exceptions import NotFoundError

        try:
            result = client.search(
                index="*",
                body={"query": {"match_all": {}}, "size": 0},
            )
            assert "hits" in result, "Expected 'hits' in search response"
        except NotFoundError:
            # 404 on AOSS means auth worked, but no indices exist yet -- still a pass.
            pass

    def test_opensearch_index_operations(self):
        """Verify we can check if an index exists on OpenSearch."""
        pytest.importorskip("opensearchpy", reason="opensearchpy required")

        client = self._build_opensearch_client()

        # Use indices.exists which is supported on both OpenSearch and AOSS.
        # Even a False result proves auth + connectivity works.
        exists = client.indices.exists(index="_connectivity_test_probe")
        assert isinstance(exists, bool), "Expected boolean from indices.exists"


# ---------------------------------------------------------------------------
# Milvus Connectivity Tests
# ---------------------------------------------------------------------------


class TestMilvusConnectivity:
    """Test connectivity to Milvus vector database."""

    @pytest.fixture(autouse=True)
    def _check_env(self):
        """Skip if Milvus credentials are not configured."""
        if not os.environ.get("MILVUS_URI"):
            pytest.skip("MILVUS_URI not set in .env")

    def _get_milvus_client(self):
        """Create a Milvus client from environment variables."""
        from pymilvus import MilvusClient

        uri = os.environ["MILVUS_URI"]
        user = os.environ.get("MILVUS_USER", "")
        password = os.environ.get("MILVUS_PASSWORD", "")
        db_name = os.environ.get("MILVUS_DB_NAME", "default")
        token = os.environ.get("MILVUS_TOKEN", "")

        kwargs = {"uri": uri, "db_name": db_name}
        if token:
            kwargs["token"] = token
        elif user and password:
            kwargs["token"] = f"{user}:{password}"

        return MilvusClient(**kwargs)

    def test_milvus_connection(self):
        """Verify basic connectivity to Milvus."""
        pytest.importorskip("pymilvus", reason="pymilvus required")

        client = self._get_milvus_client()

        try:
            # list_collections is a lightweight call to verify connectivity
            collections = client.list_collections()
            assert isinstance(collections, list), "Expected list of collections"
        finally:
            client.close()

    def test_milvus_list_collections(self):
        """Verify we can enumerate collections in Milvus."""
        pytest.importorskip("pymilvus", reason="pymilvus required")

        client = self._get_milvus_client()

        try:
            collections = client.list_collections()
            assert isinstance(collections, list)
            # Log collections for debugging
            print(f"Milvus collections: {collections}")
        finally:
            client.close()

    def test_milvus_server_version(self):
        """Verify Milvus server version is accessible."""
        pytest.importorskip("pymilvus", reason="pymilvus required")

        client = self._get_milvus_client()

        try:
            version = client.get_server_version()
            assert version, "Expected non-empty server version"
            print(f"Milvus server version: {version}")
        finally:
            client.close()

    def test_milvus_database_exists(self):
        """Verify the configured database is accessible."""
        pytest.importorskip("pymilvus", reason="pymilvus required")
        from pymilvus import MilvusClient

        uri = os.environ["MILVUS_URI"]
        user = os.environ.get("MILVUS_USER", "")
        password = os.environ.get("MILVUS_PASSWORD", "")
        db_name = os.environ.get("MILVUS_DB_NAME", "default")
        token = os.environ.get("MILVUS_TOKEN", "")

        kwargs = {"uri": uri}
        if token:
            kwargs["token"] = token
        elif user and password:
            kwargs["token"] = f"{user}:{password}"

        # Connect without specifying db to list databases
        client = MilvusClient(**kwargs)

        try:
            databases = client.list_databases()
            db_names = [db["name"] if isinstance(db, dict) else str(db) for db in databases]
            assert db_name in db_names, (
                f"Database '{db_name}' not found. Available: {db_names}"
            )
        finally:
            client.close()

    def test_milvus_collection_schema(self):
        """Verify collection schemas are retrievable for existing collections."""
        pytest.importorskip("pymilvus", reason="pymilvus required")

        client = self._get_milvus_client()

        try:
            collections = client.list_collections()
            if not collections:
                pytest.skip("No collections exist in Milvus to inspect")

            # Inspect the first collection
            collection_name = collections[0]
            info = client.describe_collection(collection_name)
            assert info is not None, f"Failed to describe collection '{collection_name}'"
            print(f"Collection '{collection_name}' info: {info}")
        finally:
            client.close()
