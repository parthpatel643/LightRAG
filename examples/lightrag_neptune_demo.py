"""
Example script demonstrating how to use AWS Neptune storage with LightRAG.

Prerequisites:
1. AWS Neptune cluster created and accessible
2. AWS credentials configured (AWS_PROFILE, IAM role, or access keys)
3. VPC access to Neptune cluster (VPN, bastion host, or running in AWS)
4. Dependencies installed: pip install lightrag-hku[offline-storage]

Environment variables required:
- NEPTUNE_ENDPOINT: Your Neptune cluster endpoint
- NEPTUNE_PORT: Neptune port (usually 8182)
- NEPTUNE_REGION: AWS region (e.g., us-east-1)
- NEPTUNE_USE_IAM: Set to 'true' for IAM authentication
- AWS credentials (AWS_PROFILE, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, or IAM role)
"""

import asyncio
import os

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

# Configure working directory
WORKING_DIR = "./neptune_rag_storage"

# Ensure environment variables are set
required_env_vars = ["NEPTUNE_ENDPOINT", "NEPTUNE_PORT", "NEPTUNE_REGION"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing_vars)}\n"
        f"Please set them in your .env file or export them in your shell."
    )


async def main():
    """Main example function demonstrating Neptune storage."""

    # Initialize LightRAG with Neptune storage
    print("Initializing LightRAG with AWS Neptune storage...")
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=gpt_4o_mini_complete,
        embedding_func=openai_embed,
        graph_storage="NeptuneGraphStorage",  # Use Neptune for graph storage
        workspace="neptune_demo",  # Workspace for data isolation
    )

    try:
        # Initialize storage connections (includes IAM authentication)
        print("Connecting to Neptune cluster...")
        await rag.initialize_storages()
        print("✓ Successfully connected to Neptune!")

        # Insert sample data
        print("\nInserting sample document...")
        sample_text = """
        Amazon Neptune is a fast, reliable, fully managed graph database service 
        that makes it easy to build and run applications that work with highly 
        connected datasets. Neptune supports both property graph and RDF graph models, 
        and provides query languages including Gremlin and SPARQL. Neptune is designed 
        for high availability with read replicas, point-in-time recovery, continuous 
        backup to Amazon S3, and replication across Availability Zones.
        """

        await rag.ainsert(sample_text)
        print("✓ Document inserted successfully!")

        # Query the knowledge graph
        print("\nQuerying knowledge graph...")
        query = "What is Amazon Neptune and what are its key features?"

        result = await rag.aquery(
            query,
            param=QueryParam(
                mode="hybrid",  # Use hybrid mode combining local and global search
                top_k=10,
                chunk_top_k=5,
            ),
        )

        print(f"\nQuery: {query}")
        print(f"\nAnswer:\n{result}")

        # Optional: Get storage statistics
        print("\n" + "=" * 80)
        print("Storage Information:")
        print(f"Workspace: {rag.workspace}")
        print("Graph Storage: NeptuneGraphStorage")
        print(f"Neptune Endpoint: {os.getenv('NEPTUNE_ENDPOINT')}")
        print(f"Neptune Region: {os.getenv('NEPTUNE_REGION')}")
        print(f"IAM Authentication: {os.getenv('NEPTUNE_USE_IAM', 'true')}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        # Clean up connections
        print("\nClosing Neptune connection...")
        await rag.finalize_storages()
        print("✓ Connection closed")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
