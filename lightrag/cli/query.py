"""
LightRAG CLI - Query Command

Query the knowledge graph with various modes and options.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from lightrag import LightRAG, QueryParam
from lightrag.cli.utils import (
    console,
    detect_working_dir,
    list_available_graphs,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from lightrag.functions import embedding_func, llm_model_func, rerank_model_func
from lightrag.profiling import TimingBreakdown

app = typer.Typer(help="Query the knowledge graph")


async def execute_query(
    rag: LightRAG,
    query: str,
    mode: str,
    reference_date: Optional[str],
    stream: bool,
    timing: Optional[TimingBreakdown] = None,
) -> Optional[str]:
    """
    Execute a query against the knowledge graph.

    Args:
        rag: LightRAG instance
        query: Query string
        mode: Query mode
        reference_date: Reference date for temporal mode
        stream: Whether to stream response
        timing: Optional timing breakdown

    Returns:
        Query response or None if streaming
    """
    if timing:
        timing.mark("query_prepare")

    # Build query parameters
    param = QueryParam(
        mode=mode,
        reference_date=reference_date if mode == "temporal" else None,
    )

    # Log query details
    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]       QUERY[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print(f"[bold]Mode:[/bold] {mode}")
    if mode == "temporal" and reference_date:
        console.print(f"[bold]Reference Date:[/bold] {reference_date}")
    console.print(f"[bold]Query:[/bold] {query}")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
    )

    if timing:
        timing.mark("query_prepare")
        timing.mark("query_execute")

    # Execute query
    try:
        if stream:
            console.print("[bold]Streaming response:[/bold]\n")
            async for chunk in rag.aquery_stream(query, param=param):
                console.print(chunk, end="")
            console.print("\n")
            response = None
        else:
            response = await rag.aquery(query, param=param)
    except Exception as e:
        print_error(f"Query failed: {e}")
        raise

    if timing:
        timing.mark("query_execute")

    return response


@app.command()
def main(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Query string",
    ),
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        "-m",
        help="Query mode: local, global, hybrid, temporal, naive, mix, bypass",
    ),
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Reference date for temporal mode (YYYY-MM-DD)",
    ),
    as_of: Optional[str] = typer.Option(
        None,
        "--as-of",
        help="Alias for --date (more intuitive)",
    ),
    latest: bool = typer.Option(
        False,
        "--latest",
        help="Use latest version (temporal mode with today's date)",
    ),
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        "-w",
        help="LightRAG working directory",
    ),
    list_graphs: bool = typer.Option(
        False,
        "--list-graphs",
        help="List available working directories",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        "-s",
        help="Stream the response",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save response to file",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown",
    ),
    profile: bool = typer.Option(
        False,
        "--profile",
        help="Enable cProfile profiling",
    ),
    timing: bool = typer.Option(
        False,
        "--timing",
        help="Show timing breakdown",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Disable query cache",
    ),
    trace: bool = typer.Option(
        False,
        "--trace",
        help="Enable MLflow tracing",
    ),
    trace_name: Optional[str] = typer.Option(
        None,
        "--trace-name",
        help="Custom name for MLflow trace",
    ),
):
    """
    Query the knowledge graph.

    Examples:

        # Simple query
        lightrag query "What is the parking fee?"

        # Temporal query
        lightrag query "What was the fee?" --as-of 2024-01-01

        # Latest version
        lightrag query "What is the current fee?" --latest

        # Different working directory
        lightrag query "test" --working-dir ./contracts_rag

        # List available graphs
        lightrag query --list-graphs
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    working_dir = working_dir or global_opts.get("working_dir")
    trace = trace or global_opts.get("trace", False)
    trace_name = trace_name or global_opts.get("trace_name")

    # Handle --list-graphs
    if list_graphs:
        graphs = list_available_graphs()
        if not graphs:
            print_warning("No knowledge graphs found")
            console.print("\n[yellow]Create one with:[/yellow] lightrag build")
            return

        console.print("\n[bold]Available Knowledge Graphs:[/bold]\n")
        for path, status in graphs:
            status_icon = "✅" if status == "valid" else "📁"
            console.print(f"  {status_icon} {path} [{status}]")
        console.print()
        return

    # Validate query
    if not query:
        print_error("Query is required")
        console.print('\n[yellow]Usage:[/yellow] lightrag query "your question"')
        console.print("[yellow]Or:[/yellow] lightrag query --list-graphs")
        raise typer.Exit(1)

    # Detect working directory
    work_dir = detect_working_dir(working_dir)

    if not work_dir.exists():
        print_error(f"Working directory not found: {work_dir}")
        console.print("\n[yellow]Suggestions:[/yellow]")
        console.print(
            "  1. Run [cyan]lightrag build[/cyan] to create a knowledge graph"
        )
        console.print(
            '  2. Specify directory: [cyan]lightrag query "test" --working-dir ./path[/cyan]'
        )
        console.print("  3. List available: [cyan]lightrag query --list-graphs[/cyan]")
        raise typer.Exit(1)

    # Handle date options
    reference_date = as_of or date
    if latest:
        reference_date = datetime.now().strftime("%Y-%m-%d")
        mode = "temporal"
    elif mode == "temporal" and not reference_date:
        reference_date = datetime.now().strftime("%Y-%m-%d")
        print_info(f"No date specified, using today: {reference_date}")

    # Validate date format
    if reference_date:
        try:
            datetime.strptime(reference_date, "%Y-%m-%d")
        except ValueError:
            print_error(f"Invalid date format: {reference_date}")
            console.print("\n[yellow]Expected format:[/yellow] YYYY-MM-DD")
            console.print("[yellow]Example:[/yellow] 2024-01-01")
            raise typer.Exit(1)

    # Initialize timing if requested
    timing_obj = TimingBreakdown("Query Phases") if timing else None

    if timing_obj:
        timing_obj.mark("initialization")

    # Initialize LightRAG
    print_info(f"Initializing LightRAG (working_dir: {work_dir})...")

    try:
        rag = LightRAG(
            working_dir=str(work_dir),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            rerank_model_func=rerank_model_func,
            enable_llm_cache=not no_cache,
        )

        # Run async initialization
        asyncio.run(rag.initialize_storages())
        print_success("LightRAG initialized")

    except Exception as e:
        print_error(f"Failed to initialize LightRAG: {e}")
        raise typer.Exit(1)

    if timing_obj:
        timing_obj.mark("initialization")

    # Execute query
    try:
        response = asyncio.run(
            execute_query(rag, query, mode, reference_date, stream, timing_obj)
        )
    except Exception as e:
        print_error(f"Query execution failed: {e}")
        raise typer.Exit(1)

    # Display response
    if response is not None:
        console.print(
            "\n[bold green]═══════════════════════════════════════════════════════[/bold green]"
        )
        console.print("[bold green]       RESPONSE[/bold green]")
        console.print(
            "[bold green]═══════════════════════════════════════════════════════[/bold green]\n"
        )
        console.print(response)
        console.print(
            "\n[bold green]═══════════════════════════════════════════════════════[/bold green]\n"
        )

        # Save to file if requested
        if output:
            try:
                output_path = Path(output)
                output_path.write_text(response)
                print_success(f"Response saved to: {output}")
            except Exception as e:
                print_error(f"Failed to save response: {e}")

    if timing_obj:
        console.print()
        timing_obj.report()


if __name__ == "__main__":
    app()

# Made with Bob
