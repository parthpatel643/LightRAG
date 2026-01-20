#!/usr/bin/env python
"""
query_graph.py - Query Script for Temporal RAG

This script queries the LightRAG knowledge graph with support for temporal mode,
allowing chronologically accurate retrieval based on reference dates.

Usage:
    # Query with temporal mode (specific date)
    python query_graph.py --query "What is the service fee?" --mode temporal --date 2023-06-01

    # Query with hybrid mode (no temporal filtering)
    python query_graph.py --query "What are the lease terms?" --mode hybrid

    # Interactive query mode
    python query_graph.py --interactive --mode temporal

    # Compare responses at different dates
    python query_graph.py --query "How did costs change?" --mode temporal --date 2024-06-01
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from lightrag import LightRAG, QueryParam
from lightrag.functions import embedding_func, llm_model_func, rerank_model_func
from lightrag.profiling import TimingBreakdown
from lightrag.utils import logger


async def query_rag(
    rag: LightRAG,
    query: str,
    mode: str = "hybrid",
    reference_date: str = None,
    stream: bool = False,
    timing: TimingBreakdown = None,
):
    """
    Query the LightRAG knowledge graph.

    Args:
        rag: LightRAG instance
        query: Query string
        mode: Query mode (local, global, hybrid, temporal, etc.)
        reference_date: Reference date for temporal mode (YYYY-MM-DD)
        stream: Whether to stream the response
        timing: Optional TimingBreakdown object for profiling

    Returns:
        Query response string
    """
    if timing:
        timing.mark("query_prepare")

    # Build query parameters
    param = QueryParam(
        mode=mode,
        reference_date=reference_date if mode == "temporal" else None,
        enable_rerank=True,
    )

    # Log query details
    logger.info("\n" + "=" * 60)
    logger.info("QUERY")
    logger.info("=" * 60)
    logger.info(f"Mode: {mode}")
    if mode == "temporal" and reference_date:
        logger.info(f"Reference Date: {reference_date}")
    logger.info(f"Query: {query}")
    logger.info("=" * 60 + "\n")

    if timing:
        timing.mark("query_prepare")
        timing.mark("query_execute")

    # Execute query
    if stream:
        logger.info("Streaming response:\n")
        async for chunk in rag.aquery_stream(query, param=param):
            print(chunk, end="", flush=True)
        print("\n")
        response = None
    else:
        response = await rag.aquery(query, param=param)

    if timing:
        timing.mark("query_execute")

    return response


async def interactive_mode(
    rag: LightRAG,
    mode: str = "hybrid",
    default_date: str = None,
    timing: TimingBreakdown = None,
):
    """
    Interactive query mode - allows multiple queries in a session.

    Args:
        rag: LightRAG instance
        mode: Default query mode
        default_date: Default reference date for temporal mode
        timing: Optional TimingBreakdown object for profiling
    """
    print("\n" + "=" * 60)
    print("INTERACTIVE QUERY MODE")
    print("=" * 60)
    print(f"Default mode: {mode}")
    if mode == "temporal":
        print(f"Default date: {default_date or 'today'}")
    print("\nCommands:")
    print("  /mode <mode>       - Change query mode")
    print("  /date <YYYY-MM-DD> - Set reference date (temporal mode)")
    print("  /help              - Show this help")
    print("  /quit or /exit     - Exit interactive mode")
    print("=" * 60 + "\n")

    current_mode = mode
    current_date = default_date or datetime.now().strftime("%Y-%m-%d")

    while True:
        try:
            # Get user input
            user_input = input(f"\n[{current_mode}] Query: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower()

                if cmd in ["/quit", "/exit"]:
                    print("Exiting interactive mode...")
                    break

                elif cmd == "/help":
                    print("\nCommands:")
                    print("  /mode <mode>       - Change query mode")
                    print("  /date <YYYY-MM-DD> - Set reference date (temporal mode)")
                    print("  /help              - Show this help")
                    print("  /quit or /exit     - Exit interactive mode")
                    continue

                elif cmd == "/mode":
                    if len(cmd_parts) < 2:
                        print("Usage: /mode <local|global|hybrid|temporal|naive|mix>")
                        continue
                    new_mode = cmd_parts[1].lower()
                    if new_mode in [
                        "local",
                        "global",
                        "hybrid",
                        "temporal",
                        "naive",
                        "mix",
                        "bypass",
                    ]:
                        current_mode = new_mode
                        print(f"✓ Mode changed to: {current_mode}")
                    else:
                        print(f"✗ Invalid mode: {new_mode}")
                    continue

                elif cmd == "/date":
                    if len(cmd_parts) < 2:
                        print("Usage: /date <YYYY-MM-DD>")
                        continue
                    current_date = cmd_parts[1]
                    print(f"✓ Reference date set to: {current_date}")
                    if current_mode != "temporal":
                        print("  Note: Date only applies in temporal mode")
                    continue

                else:
                    print(f"Unknown command: {cmd}")
                    print("Type /help for available commands")
                    continue

            # Execute query
            response = await query_rag(
                rag=rag,
                query=user_input,
                mode=current_mode,
                reference_date=current_date if current_mode == "temporal" else None,
                stream=False,
                timing=timing,
            )

            # Display response
            print("\n" + "-" * 60)
            print("RESPONSE")
            print("-" * 60)
            print(response)
            print("-" * 60)

        except KeyboardInterrupt:
            print("\n\nExiting interactive mode...")
            break
        except Exception as e:
            logger.error(f"Error during query: {e}")
            continue


async def main():
    # The main async logic remains here
    # Validate arguments
    if not args.interactive and not args.query:
        parser.error("--query is required unless --interactive is specified")

    if args.mode == "temporal" and not args.date and not args.interactive:
        # Default to today's date for temporal mode
        args.date = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"No --date specified, using today: {args.date}")

    # Initialize timing if requested
    timing = TimingBreakdown("Query Phases") if args.timing else None

    if timing:
        timing.mark("initialization")

    # Check working directory
    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        logger.error(f"Working directory not found: {working_dir}")
        logger.error("Please run build_graph.py first to ingest documents")
        sys.exit(1)

    # Initialize LightRAG
    logger.info(f"Initializing LightRAG (working_dir: {working_dir})...")

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        rerank_model_func=rerank_model_func,
        enable_llm_cache=False,
    )

    # Initialize storages
    await rag.initialize_storages()
    logger.info("✅ LightRAG initialized\n")

    if timing:
        timing.mark("initialization")

    # Execute query or enter interactive mode
    if args.interactive:
        await interactive_mode(
            rag=rag, mode=args.mode, default_date=args.date, timing=timing
        )
    else:
        response = await query_rag(
            rag=rag,
            query=args.query,
            mode=args.mode,
            reference_date=args.date,
            stream=args.stream,
            timing=timing,
        )

        if response is not None:
            print("\n" + "=" * 60)
            print("RESPONSE")
            print("=" * 60)
            print(response)
            print("=" * 60 + "\n")

    if timing:
        timing.report()


if __name__ == "__main__":
    import argparse
    import asyncio
    import cProfile
    import sys
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Query LightRAG knowledge graph with temporal support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single query with temporal mode
  python query_graph.py --query "What is the service fee?" --mode temporal --date 2023-06-01
  
  # Interactive mode
  python query_graph.py --interactive --mode temporal --date 2024-01-01
  
  # Hybrid mode query with profiling
  python query_graph.py --query "Summarize the contract" --mode hybrid --profile
  
  # Stream response with timing breakdown
  python query_graph.py --query "What changed?" --mode temporal --date 2024-06-01 --stream --timing
        """,
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable cProfile profiling and save to profile_output.prof",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Enable detailed timing breakdown for query phases",
    )
    # Query options
    parser.add_argument(
        "--query", type=str, help="Query string (required unless --interactive)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="hybrid",
        choices=["local", "global", "hybrid", "temporal", "naive", "mix", "bypass"],
        help="Query mode (default: hybrid)",
    )
    parser.add_argument(
        "--date", type=str, help="Reference date for temporal mode (YYYY-MM-DD format)"
    )
    parser.add_argument("--stream", action="store_true", help="Stream the response")
    parser.add_argument(
        "--interactive", action="store_true", help="Enter interactive query mode"
    )

    # LightRAG options
    parser.add_argument(
        "--working-dir",
        type=str,
        default="data/output/sea-cabin-cleaning",
        help="LightRAG working directory (default: ./data/output/sea-cabin-cleaning)",
    )

    args = parser.parse_args()

    # Pass args to async main
    async def main_with_args():
        return await main()

    if args.profile:

        def runner():
            asyncio.run(main_with_args())

        profile_file = "profile_output.prof"
        cProfile.run("runner()", profile_file)
        print(f"\nProfile data saved to {profile_file}")
        print(f"View with: python -m pstats {profile_file}")
    else:
        asyncio.run(main_with_args())
