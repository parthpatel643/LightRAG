#!/usr/bin/env python
"""
build_graph.py - Data Ingestion Script for Temporal RAG

This script ingests versioned documents into LightRAG, creating a temporal knowledge graph.
Documents are sequenced and processed with metadata to enable version-aware retrieval.

Usage:
    # Ingest all files in a directory (auto-sequencing by filename)
    python build_graph.py --input-dir ./test_temporal_ingest --working-dir ./rag_storage

    # Ingest specific files in order
    python build_graph.py --files Base.md Amendment1.md Amendment2.md --working-dir ./rag_storage

    # Use data sequencer for automatic metadata extraction
    python build_graph.py --input-dir ./contracts --use-sequencer --working-dir ./rag_storage
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from lightrag import LightRAG
from lightrag.functions import embedding_func, llm_model_func
from lightrag.utils import logger


async def ingest_documents(
    rag: LightRAG,
    file_paths: List[Path],
    use_sequencer: bool = False,
):
    """
    Ingest documents into LightRAG with temporal metadata.

    Args:
        rag: LightRAG instance
        file_paths: List of file paths to ingest (in user-defined order)
        use_sequencer: Whether to use ContractSequencer for metadata extraction
    """
    if use_sequencer:
        # Use ContractSequencer for automatic metadata extraction
        try:
            from data_prep import ContractSequencer

            logger.info("Using ContractSequencer for metadata extraction...")
            sequencer = ContractSequencer(
                files=[str(p) for p in file_paths], order=[p.name for p in file_paths]
            )
            sequenced_docs = sequencer.prepare_for_ingestion()

            # Insert documents with extracted metadata
            for doc_data in sequenced_docs:
                logger.info(
                    f"Ingesting: {doc_data['metadata']['source']} (v{doc_data['metadata']['sequence_index']})"
                )
                await rag.ainsert(
                    input=doc_data["content"],
                    file_paths=doc_data["metadata"][
                        "source"
                    ],  # Pass source filename for citations
                    metadata=doc_data["metadata"],
                )

        except ImportError:
            logger.error("data_prep.py not found. Install or use --no-sequencer flag.")
            sys.exit(1)
    else:
        # User-defined sequential ingestion
        for idx, file_path in enumerate(file_paths, start=1):
            logger.info(
                f"Ingesting: {file_path.name} (sequence {idx}/{len(file_paths)})"
            )

            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Insert without metadata (or add minimal metadata)
            await rag.ainsert(input=content)

    logger.info("✅ All documents ingested successfully!")


async def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into LightRAG with temporal support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest all markdown files in directory
  python build_graph.py --input-dir ./contracts
  
  # Ingest specific files in order
  python build_graph.py --files Base.md Amend1.md Amend2.md
  
  # Use ContractSequencer for metadata extraction
  python build_graph.py --input-dir ./contracts --use-sequencer
  
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
    parser.add_argument(
        "--use-sequencer",
        action="store_true",
        help="Use ContractSequencer for automatic metadata extraction",
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
        entity_extract_max_gleaning=5,
        chunk_token_size=int(os.getenv("CHUNK_SIZE", 2000)),
        chunk_overlap_token_size=int(os.getenv("CHUNK_OVERLAP_SIZE", 200)),
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
        use_sequencer=args.use_sequencer,
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
