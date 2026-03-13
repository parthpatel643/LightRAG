#!/usr/bin/env python
"""
LightRAG Unified CLI - Main Entry Point

This module provides a unified command-line interface for LightRAG operations,
simplifying document ingestion and knowledge graph querying.

Commands:
    build       - Build knowledge graph from documents
    query       - Query the knowledge graph
    interactive - Interactive query session
    info        - Show graph statistics
    config      - Manage configuration

Usage:
    lightrag build --input ./docs
    lightrag query "What is the parking fee?"
    lightrag interactive
"""

import sys
from typing import Optional

import typer
from rich.console import Console

from lightrag import __version__

# Create main app and console
app = typer.Typer(
    name="lightrag",
    help="LightRAG - Simple and Fast Retrieval-Augmented Generation",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"LightRAG version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (can be repeated: -vv, -vvv)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output",
    ),
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        "-w",
        help="LightRAG working directory",
    ),
    config_file: Optional[str] = typer.Option(
        None,
        "--config",
        help="Load configuration from file",
    ),
    trace: bool = typer.Option(
        False,
        "--trace",
        help="Enable MLflow tracing for observability",
    ),
    trace_name: Optional[str] = typer.Option(
        None,
        "--trace-name",
        help="Custom name for MLflow trace",
    ),
):
    """
    LightRAG - Simple and Fast Retrieval-Augmented Generation

    A unified CLI for building knowledge graphs and querying them with temporal support.
    """
    # Store global options in context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["working_dir"] = working_dir
    ctx.obj["config_file"] = config_file
    ctx.obj["trace"] = trace
    ctx.obj["trace_name"] = trace_name


# Import and register subcommands
from lightrag.cli.build import app as build_app
from lightrag.cli.config import app as config_app
from lightrag.cli.info import app as info_app
from lightrag.cli.interactive import app as interactive_app
from lightrag.cli.query import app as query_app

app.add_typer(build_app, name="build", help="Build knowledge graph from documents")
app.add_typer(query_app, name="query", help="Query the knowledge graph")
app.add_typer(interactive_app, name="interactive", help="Interactive query session")
app.add_typer(info_app, name="info", help="Show graph statistics and information")
app.add_typer(config_app, name="config", help="Manage configuration")


def cli():
    """Main CLI entry point."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()

# Made with Bob
