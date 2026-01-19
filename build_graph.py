#!/usr/bin/env python
"""
build_graph.py - Data Ingestion Script for LightRAG with Automatic Versioning

This script ingests documents into LightRAG with fully automatic versioning. Each document
automatically receives a unique version number (v1, v2, v3, ...) during ingestion. Users
simply provide documents in order and versioning is handled transparently without requiring
any metadata or configuration.

Versioning is internalized in the graph and enables version-aware retrieval automatically.

Usage:
    # Ingest all files in a directory (auto-versioning)
    python build_graph.py --input-dir ./contracts --working-dir ./rag_storage

    # Ingest specific files in order (auto-versioning)
    python build_graph.py --files Base.md Amendment1.md Amendment2.md --working-dir ./rag_storage
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from lightrag import LightRAG
from lightrag.functions import embedding_func, llm_model_func
from lightrag.hierarchical_chunker import create_hierarchical_chunking_func
from lightrag.utils import logger


async def ingest_documents(
    rag: LightRAG,
    file_paths: List[Path],
):
    """
    Ingest documents into LightRAG with automatic versioning.

    Documents are ingested sequentially, and each automatically receives a unique
    version number (v1, v2, v3, ...). Versioning is internalized in the graph
    and transparent to the user.

    Args:
        rag: LightRAG instance
        file_paths: List of file paths to ingest in order (sequence auto-assigned internally)
    """
    await _ingest_files_sequentially(rag, file_paths)
    logger.info("✅ All documents ingested successfully!")


async def _ingest_files_sequentially(rag: LightRAG, file_paths: List[Path]):
    """
    Ingest files sequentially with automatic sequence_index assignment.

    Each document automatically receives a unique version number without
    requiring explicit metadata from the user.

    Args:
        rag: LightRAG instance
        file_paths: List of file paths to ingest in order
    """
    for file_path in file_paths:
        logger.info(f"Ingesting: {file_path.name}")

        # Read file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Insert without metadata - sequence_index will be auto-assigned
        await rag.ainsert(input=content, file_paths=str(file_path))


async def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into LightRAG with automatic versioning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest all markdown files in directory (auto-versioned)
  python build_graph.py --input-dir ./contracts
  
  # Ingest specific files in order (auto-versioned)
  python build_graph.py --files Base.md Amend1.md Amend2.md
  
  # Specify custom working directory
  python build_graph.py --input-dir ./contracts --working-dir ./custom_rag
        """,
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-dir",
        type=str,
        help="Directory containing documents to ingest (will process all .md, .txt files)",
    )
    input_group.add_argument(
        "--files",
        nargs="+",
        type=str,
        help="Specific files to ingest (space-separated, in order)",
    )

    # Processing options
    parser.add_argument(
        "--working-dir",
        type=str,
        default="./rag_storage",
        help="LightRAG working directory (default: ./rag_storage)",
    )

    args = parser.parse_args()

    # Gather file paths
    file_paths = []
    if args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            logger.error(f"Input directory not found: {input_dir}")
            sys.exit(1)

        # Gather all markdown and text files
        file_paths = sorted(
            list(input_dir.glob("*.md")) + list(input_dir.glob("*.txt"))
        )

        if not file_paths:
            logger.error(f"No .md or .txt files found in {input_dir}")
            sys.exit(1)

        logger.info(f"Found {len(file_paths)} files in {input_dir}")
    else:
        file_paths = [Path(f) for f in args.files]
        for fp in file_paths:
            if not fp.exists():
                logger.error(f"File not found: {fp}")
                sys.exit(1)

    logger.info(f"Files to ingest ({len(file_paths)}):")
    for idx, fp in enumerate(file_paths, start=1):
        logger.info(f"  {idx}. {fp.name}")

    # Initialize LightRAG
    working_dir = os.getenv("WORKING_DIR", args.working_dir)

    logger.info(f"\nInitializing LightRAG (working_dir: {working_dir})...")

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        chunking_func=create_hierarchical_chunking_func(
            chunk_size=int(os.getenv("CHUNK_SIZE", 2000)),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP_SIZE", 200)),
        ),
        entity_extract_max_gleaning=5,
        enable_llm_cache=False,
    )

    # Initialize storages
    await rag.initialize_storages()
    logger.info("✅ LightRAG initialized")

    # Ingest documents
    logger.info("\n" + "=" * 60)
    logger.info("INGESTING DOCUMENTS")
    logger.info("=" * 60 + "\n")

    await ingest_documents(
        rag=rag,
        file_paths=file_paths,
    )

    await rag.finalize_storages()
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Documents ingested: {len(file_paths)}")
    logger.info(f"Working directory: {working_dir}")
    logger.info("\nNext steps:")
    logger.info("  1. Use query_graph.py to query the knowledge graph")
    logger.info(
        f"  2. Example: python query_graph.py --working-dir {working_dir} --mode temporal"
    )


if __name__ == "__main__":
    asyncio.run(main())
