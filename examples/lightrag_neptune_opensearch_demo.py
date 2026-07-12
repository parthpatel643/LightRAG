"""
Example script demonstrating Neptune + OpenSearch graph storage with LightRAG.

This configuration uses:
- AWS Neptune for graph storage (Gremlin-based traversals)
- OpenSearch for full-text search over graph node descriptions and entity labels
- Default file-based stores for KV, vector, and doc-status storage

The NeptuneOpenSearchGraphStorage class extends NeptuneGraphStorage with a proper
async OpenSearch client. Node data is dual-written to both Neptune (graph) and an
OpenSearch index (search), enabling fast full-text search via search_labels() and
full_text_search() without the synchronous requests.post stub.

Prerequisites:
1. AWS Neptune cluster created and accessible
2. OpenSearch cluster created and accessible
3. AWS credentials configured (AWS_PROFILE, IAM role, or access keys)
4. VPC access to both Neptune and OpenSearch clusters
5. Dependencies installed: pip install lightrag-hku[offline-storage]

Environment variables required:
  Neptune:
    - NEPTUNE_ENDPOINT: Your Neptune cluster endpoint
    - NEPTUNE_PORT: Neptune port (usually 8182)
    - NEPTUNE_REGION: AWS region (e.g., us-east-1)
    - NEPTUNE_USE_IAM: Set to 'true' for IAM authentication (default: true)
  OpenSearch:
    - OPENSEARCH_HOSTS: Comma-separated OpenSearch host:port list
    - OPENSEARCH_USER: OpenSearch username (default: admin)
    - OPENSEARCH_PASSWORD: OpenSearch password (default: admin)
    - OPENSEARCH_USE_SSL: Whether to use SSL (default: true)
    - OPENSEARCH_VERIFY_CERTS: Whether to verify certificates (default: false)
  AWS:
    - AWS credentials (AWS_PROFILE, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, or IAM role)
"""

import asyncio
import os

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

# Configure working directory
WORKING_DIR = "./neptune_opensearch_rag_storage"

# Ensure required environment variables are set
required_env_vars = [
    "NEPTUNE_ENDPOINT",
    "NEPTUNE_PORT",
    "NEPTUNE_REGION",
    "OPENSEARCH_HOSTS",
]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing_vars)}\n"
        f"Please set them in your .env file or export them in your shell."
    )


async def main():
    """Main example function demonstrating Neptune + OpenSearch graph storage."""

    # Initialize LightRAG with Neptune+OpenSearch graph storage.
    # KV, vector, and doc-status use default file-based backends.
    print("Initializing LightRAG with Neptune + OpenSearch graph storage...")
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=gpt_4o_mini_complete,
        embedding_func=openai_embed,
        # Neptune for Gremlin traversals + OpenSearch for full-text search
        graph_storage="NeptuneOpenSearchGraphStorage",
        workspace="neptune_opensearch_demo",
    )

    try:
        # Initialize storage connections
        print("Connecting to Neptune and OpenSearch clusters...")
        await rag.initialize_storages()
        print("Successfully connected to Neptune and OpenSearch!")

        # Insert sample data
        print("\nInserting sample document...")
        sample_text = """
        Amazon Neptune is a fast, reliable, fully managed graph database service
        that makes it easy to build and run applications that work with highly
        connected datasets. Neptune supports both property graph and RDF graph models,
        and provides query languages including Gremlin and SPARQL.

        Amazon OpenSearch Service is a managed service that makes it easy to deploy,
        operate, and scale OpenSearch clusters. OpenSearch provides full-text search,
        log analytics, and k-nearest neighbor (k-NN) vector search capabilities.

        Together, Neptune and OpenSearch provide a powerful combination for knowledge
        graph applications: Neptune excels at graph traversals and relationship queries,
        while OpenSearch provides fast full-text search over entity descriptions.
        """

        await rag.ainsert(sample_text)
        print("Document inserted successfully!")

        # Query the knowledge graph
        print("\nQuerying knowledge graph...")
        query = "How do Neptune and OpenSearch complement each other?"

        result = await rag.aquery(
            query,
            param=QueryParam(
                mode="hybrid",
                top_k=10,
                chunk_top_k=5,
            ),
        )

        print(f"\nQuery: {query}")
        print(f"\nAnswer:\n{result}")

        # Display storage configuration
        print("\n" + "=" * 80)
        print("Storage Configuration:")
        print(f"  Workspace: {rag.workspace}")
        print("  Graph Storage: NeptuneOpenSearchGraphStorage")
        print("  KV Storage: default (JsonKVStorage)")
        print("  Vector Storage: default (NanoVectorDBStorage)")
        print("  Doc Status Storage: default (JsonDocStatusStorage)")
        print(f"  Neptune Endpoint: {os.getenv('NEPTUNE_ENDPOINT')}")
        print(f"  Neptune Region: {os.getenv('NEPTUNE_REGION')}")
        print(f"  OpenSearch Hosts: {os.getenv('OPENSEARCH_HOSTS')}")

    except Exception as e:
        print(f"\nError: {e}")
        raise

    finally:
        # Clean up connections
        print("\nClosing connections...")
        await rag.finalize_storages()
        print("Connections closed")


if __name__ == "__main__":
    asyncio.run(main())
