#!/usr/bin/env python
"""
build_graph.py - Data Ingestion Script for LightRAG with Automatic Versioning

This script ingests documents into LightRAG with fully automatic versioning. Each document
automatically receives a unique version number (v1, v2, v3, ...) during ingestion.

The script prompts the user to specify the insertion order, which determines versioning:
- First file in sequence gets v1
- Second file gets v2, etc.

This allows users to control which version each document represents.

Configuration is sourced from .env file (primary) with fallback to constants.py defaults.

Environment Variables (.env):
    INPUT_DIR: Directory containing documents to ingest (default: ./inputs)
    WORKING_DIR: LightRAG working directory (default: ./rag_storage)
    CHUNK_SIZE: Document chunk size in tokens (default: 2000)
    CHUNK_OVERLAP_SIZE: Chunk overlap in tokens (default: 200)
    ENTITY_EXTRACT_MAX_GLEANING: Entity extraction gleaning iterations (default: 5)

Usage:
    # Run with .env configuration and specify insertion order interactively
    python build_graph.py

    # Then respond to prompt:
    # Found 4 files in ./inputs:
    #   1. Base.md
    #   2. Amendment1.md
    #   3. Amendment2.md
    #   4. Amendment3.md
    #
    # Enter the insertion order (e.g., '1 2 3' or '3 2 1'): 1 2 3 4
    #
    # v1: Base.md
    # v2: Amendment1.md
    # v3: Amendment2.md
    # v4: Amendment3.md
"""

import asyncio
import os
import sys
from pathlib import Path

from lightrag import LightRAG
from lightrag.constants import (
    DEFAULT_CHUNK_OVERLAP_SIZE,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_ENTITY_EXTRACT_MAX_GLEANING,
    DEFAULT_INPUT_DIR,
    DEFAULT_WORKING_DIR,
)
from lightrag.functions import embedding_func, llm_model_func
from lightrag.hierarchical_chunker import create_hierarchical_chunking_func
from lightrag.utils import logger


async def ingest_documents(
    rag: LightRAG,
    file_paths: list[Path],
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


async def _ingest_files_sequentially(rag: LightRAG, file_paths: list[Path]):
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
    """
    Main entry point. Configuration sourced from .env with fallback to constants.
    """
    # Get configuration from .env or use defaults from constants
    input_dir = os.getenv("INPUT_DIR", DEFAULT_INPUT_DIR)
    working_dir = os.getenv("WORKING_DIR", DEFAULT_WORKING_DIR)
    chunk_size = int(os.getenv("CHUNK_SIZE", DEFAULT_CHUNK_SIZE))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP_SIZE", DEFAULT_CHUNK_OVERLAP_SIZE))
    extract_gleaning = int(
        os.getenv("ENTITY_EXTRACT_MAX_GLEANING", DEFAULT_ENTITY_EXTRACT_MAX_GLEANING)
    )

    logger.info("=" * 60)
    logger.info("LightRAG Document Ingestion")
    logger.info("=" * 60)
    logger.info(f"Input Directory: {input_dir}")
    logger.info(f"Working Directory: {working_dir}")
    logger.info(f"Chunk Size: {chunk_size}")
    logger.info(f"Chunk Overlap: {chunk_overlap}")

    # Gather file paths
    file_paths = []
    input_path = Path(input_dir)
    if not input_path.exists():
        logger.error(f"Input directory not found: {input_dir}")
        logger.info(f"Please set INPUT_DIR in .env or create {input_dir}")
        sys.exit(1)

    # Gather all markdown and text files
    available_files = sorted(
        list(input_path.glob("*.md")) + list(input_path.glob("*.txt"))
    )

    if not available_files:
        logger.error(f"No .md or .txt files found in {input_dir}")
        sys.exit(1)

    # Display available files and ask user for insertion order
    logger.info(f"\nFound {len(available_files)} files in {input_dir}:")
    for idx, fp in enumerate(available_files, start=1):
        logger.info(f"  {idx}. {fp.name}")

    # Get insertion order from user
    logger.info("\n" + "=" * 60)
    logger.info("Enter the insertion order (e.g., '1 2 3' or '3 2 1')")
    logger.info("This determines versioning: first file gets v1, second gets v2, etc.")
    logger.info("=" * 60)

    while True:
        try:
            user_input = input("\nInsertion order (space or comma-separated): ").strip()
            if not user_input:
                logger.error("Please enter at least one file number")
                continue

            # Parse space or comma-separated numbers
            import re

            indices = re.split(r"[,\s]+", user_input)
            indices = [int(i.strip()) for i in indices if i.strip()]

            # Validate indices
            if not indices:
                logger.error("No valid numbers found")
                continue

            if any(i < 1 or i > len(available_files) for i in indices):
                logger.error(f"Invalid indices. Use numbers 1-{len(available_files)}")
                continue

            # Build file_paths in specified order
            file_paths = [available_files[i - 1] for i in indices]

            logger.info("\n✅ Ingestion order selected:")
            for idx, fp in enumerate(file_paths, start=1):
                logger.info(f"  v{idx}: {fp.name}")

            break

        except ValueError:
            logger.error(
                "Invalid input. Please enter numbers separated by spaces or commas"
            )

    # Initialize LightRAG
    logger.info(f"\nInitializing LightRAG (working_dir: {working_dir})...")

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        chunking_func=create_hierarchical_chunking_func(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ),
        entity_extract_max_gleaning=extract_gleaning,
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
    logger.info(f"  2. Example: python query_graph.py --working-dir {working_dir}")


if __name__ == "__main__":
    asyncio.run(main())
