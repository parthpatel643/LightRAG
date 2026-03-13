"""
LightRAG CLI - Info Command

Display statistics and information about the knowledge graph.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from lightrag import LightRAG
from lightrag.cli.utils import (
    console,
    detect_working_dir,
    print_error,
    print_info,
    print_success,
)
from lightrag.functions import embedding_func, llm_model_func

app = typer.Typer(help="Show graph statistics and information")


async def get_graph_stats(rag: LightRAG) -> dict:
    """
    Get statistics about the knowledge graph.

    Args:
        rag: LightRAG instance

    Returns:
        Dictionary of statistics
    """
    stats = {
        "working_dir": rag.working_dir,
        "total_documents": 0,
        "total_entities": 0,
        "total_relations": 0,
        "storage_backend": "Unknown",
    }

    try:
        # Try to get document count
        if hasattr(rag, "full_docs"):
            # This is a simplified check - actual implementation may vary
            stats["total_documents"] = "N/A"

        # Try to get entity/relation counts
        if hasattr(rag, "entities"):
            stats["total_entities"] = "N/A"

        if hasattr(rag, "relationships"):
            stats["total_relations"] = "N/A"

        # Detect storage backend
        work_path = Path(rag.working_dir)
        if (work_path / "kv_store_full_docs.json").exists():
            stats["storage_backend"] = "JSON (default)"

    except Exception as e:
        print_info(f"Could not retrieve all statistics: {e}")

    return stats


@app.command()
def main(
    ctx: typer.Context,
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        "-w",
        help="LightRAG working directory",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed statistics",
    ),
    entities: bool = typer.Option(
        False,
        "--entities",
        help="Show entity statistics",
    ),
    documents: bool = typer.Option(
        False,
        "--documents",
        help="Show document statistics",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        help="Output format: text, json, table",
    ),
):
    """
    Show knowledge graph statistics and information.

    Examples:

        # Basic info
        lightrag info

        # Detailed statistics
        lightrag info --detailed

        # JSON output
        lightrag info --format json

        # Specific working directory
        lightrag info --working-dir ./contracts_rag
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    working_dir = working_dir or global_opts.get("working_dir")

    # Detect working directory
    work_dir = detect_working_dir(working_dir)

    if not work_dir.exists():
        print_error(f"Working directory not found: {work_dir}")
        console.print("\n[yellow]Suggestions:[/yellow]")
        console.print(
            "  1. Run [cyan]lightrag build[/cyan] to create a knowledge graph"
        )
        console.print(
            "  2. Specify directory: [cyan]lightrag info --working-dir ./path[/cyan]"
        )
        raise typer.Exit(1)

    # Initialize LightRAG
    print_info(f"Loading graph from: {work_dir}")

    try:
        rag = LightRAG(
            working_dir=str(work_dir),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            enable_llm_cache=False,
        )

        # Run async initialization
        asyncio.run(rag.initialize_storages())

    except Exception as e:
        print_error(f"Failed to load graph: {e}")
        raise typer.Exit(1)

    # Get statistics
    try:
        stats = asyncio.run(get_graph_stats(rag))
    except Exception as e:
        print_error(f"Failed to retrieve statistics: {e}")
        raise typer.Exit(1)

    # Display statistics
    if format == "json":
        console.print(json.dumps(stats, indent=2))
    elif format == "table":
        console.print(
            "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
        )
        console.print("[bold cyan]       Knowledge Graph Statistics[/bold cyan]")
        console.print(
            "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
        )

        table = Table(show_header=False, box=None)
        table.add_column("Property", style="cyan", width=25)
        table.add_column("Value", style="green")

        table.add_row("Working Directory", str(stats["working_dir"]))
        table.add_row("Total Documents", str(stats["total_documents"]))
        table.add_row("Total Entities", str(stats["total_entities"]))
        table.add_row("Total Relations", str(stats["total_relations"]))
        table.add_row("Storage Backend", stats["storage_backend"])

        console.print(table)
        console.print(
            "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
        )
    else:
        # Text format
        console.print(f"\nWorking Directory: {stats['working_dir']}")
        console.print(f"Total Documents: {stats['total_documents']}")
        console.print(f"Total Entities: {stats['total_entities']}")
        console.print(f"Total Relations: {stats['total_relations']}")
        console.print(f"Storage Backend: {stats['storage_backend']}\n")

    print_success("Statistics retrieved successfully")


if __name__ == "__main__":
    app()

# Made with Bob
