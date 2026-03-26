"""
LightRAG CLI - Build Command

Ingest documents into the knowledge graph with interactive sequencing.
"""

import asyncio
from pathlib import Path
from typing import List, Optional

import typer
from rich.prompt import Confirm, Prompt

from lightrag import LightRAG
from lightrag.cli.utils import (
    console,
    create_progress_bar,
    detect_input_dir,
    detect_working_dir,
    print_error,
    print_file_list,
    print_info,
    print_success,
    print_warning,
    suggest_file_order,
)
from lightrag.constants import (
    DEFAULT_CHUNK_OVERLAP_SIZE,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_ENTITY_EXTRACT_MAX_GLEANING,
)
from lightrag.functions import embedding_func, llm_model_func
from lightrag.hierarchical_chunker import create_hierarchical_chunking_func
from lightrag.profiling import TimingBreakdown

app = typer.Typer(help="Build knowledge graph from documents")


def get_file_list(
    input_dir: Optional[Path],
    files: Optional[List[str]],
    suggest_order: bool,
) -> List[Path]:
    """
    Get and order the list of files to ingest.

    Returns:
        Ordered list of file paths
    """
    # Case 1: Explicit file list provided
    if files:
        file_paths = [Path(f) for f in files]
        # Validate all files exist
        for fp in file_paths:
            if not fp.exists():
                print_error(f"File not found: {fp}")
                raise typer.Exit(1)
        return file_paths

    # Case 2: Input directory provided or detected
    if not input_dir:
        input_dir = detect_input_dir()

    if not input_dir or not input_dir.exists():
        print_error("No input directory found")
        print_info("Please specify files with --files or set --input-dir")
        print_info("Example: lightrag build --files base.pdf amendment.pdf")
        raise typer.Exit(1)

    # Scan for documents
    available_files = sorted(
        list(input_dir.glob("*.md"))
        + list(input_dir.glob("*.txt"))
        + list(input_dir.glob("*.pdf"))
        + list(input_dir.glob("*.docx"))
    )

    if not available_files:
        print_error(f"No documents found in {input_dir}")
        print_info("Supported formats: .md, .txt, .pdf, .docx")
        raise typer.Exit(1)

    print_info(f"Found {len(available_files)} files in {input_dir}")

    # Get suggested order
    suggested = suggest_file_order(available_files)

    # Display suggested order
    console.print("\n📋 [bold]Suggested order (please review):[/bold]")
    print_file_list(suggested, title="")

    # Ask for confirmation
    if suggest_order or Confirm.ask("\n❓ Accept this order?", default=True):
        return [f for f, _ in suggested]

    # Manual ordering
    console.print("\n[yellow]Please specify the order manually:[/yellow]")
    console.print("Enter file numbers separated by spaces (e.g., '1 3 2 4')")

    while True:
        try:
            user_input = Prompt.ask("Order").strip()
            indices = [int(i.strip()) for i in user_input.split() if i.strip()]

            if not indices:
                print_error("Please enter at least one file number")
                continue

            if any(i < 1 or i > len(suggested) for i in indices):
                print_error(f"Invalid indices. Use numbers 1-{len(suggested)}")
                continue

            # Build ordered list
            ordered_files = [suggested[i - 1][0] for i in indices]

            # Show final order
            console.print("\n✓ [green]Order confirmed:[/green]")
            for idx, fp in enumerate(ordered_files, 1):
                console.print(f"  v{idx}: {fp.name}")

            return ordered_files

        except ValueError:
            print_error("Invalid input. Please enter numbers separated by spaces")
        except KeyboardInterrupt:
            print_warning("\nOperation cancelled")
            raise typer.Exit(130)


async def ingest_documents(
    rag: LightRAG,
    file_paths: List[Path],
    timing: Optional[TimingBreakdown] = None,
):
    """
    Ingest documents sequentially with progress tracking.

    Args:
        rag: LightRAG instance
        file_paths: Ordered list of files to ingest
        timing: Optional timing breakdown
    """
    if timing:
        timing.mark("ingestion")

    with create_progress_bar("Ingesting documents") as progress:
        task = progress.add_task("Processing...", total=len(file_paths))

        for file_path in file_paths:
            progress.update(task, description=f"Processing {file_path.name}")

            # Read file content
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try binary read for PDFs, etc.
                with open(file_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")

            # Insert document
            await rag.ainsert(input=content, file_paths=str(file_path))

            progress.advance(task)

    if timing:
        timing.mark("ingestion")


@app.command()
def main(
    ctx: typer.Context,
    input_dir: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input directory containing documents",
    ),
    files: Optional[List[str]] = typer.Option(
        None,
        "--files",
        help="Specific files to ingest (order determines sequence)",
    ),
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        "-w",
        help="LightRAG working directory",
    ),
    suggest_order: bool = typer.Option(
        False,
        "--suggest-order",
        help="Show suggested order and accept without confirmation",
    ),
    chunk_size: int = typer.Option(
        DEFAULT_CHUNK_SIZE,
        "--chunk-size",
        help="Chunk size in tokens",
    ),
    chunk_overlap: int = typer.Option(
        DEFAULT_CHUNK_OVERLAP_SIZE,
        "--chunk-overlap",
        help="Chunk overlap in tokens",
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
    force: bool = typer.Option(
        False,
        "--force",
        help="Force rebuild, ignore existing data",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without executing",
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
    Build knowledge graph from documents.

    Examples:

        # Explicit file order (recommended)
        lightrag build --files base.pdf amendment1.pdf amendment2.pdf

        # Interactive with suggestions
        lightrag build --input ./contracts

        # With profiling and timing
        lightrag build --input ./docs --profile --timing
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    working_dir = working_dir or global_opts.get("working_dir")
    trace = trace or global_opts.get("trace", False)
    trace_name = trace_name or global_opts.get("trace_name")

    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]       LightRAG Document Ingestion[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
    )

    # Detect working directory
    work_dir = detect_working_dir(working_dir)
    print_info(f"Working Directory: {work_dir}")

    if work_dir.exists() and not force:
        if not Confirm.ask(
            f"\n⚠️  Working directory exists: {work_dir}\nContinue and add documents?",
            default=True,
        ):
            print_warning("Operation cancelled")
            raise typer.Exit(0)

    # Get file list
    try:
        input_path = Path(input_dir) if input_dir else None
        file_paths = get_file_list(input_path, files, suggest_order)
    except Exception as e:
        print_error(f"Failed to get file list: {e}")
        raise typer.Exit(1)

    if dry_run:
        console.print("\n[yellow]🔍 Dry run - no changes will be made[/yellow]\n")
        console.print("[bold]Would ingest:[/bold]")
        for idx, fp in enumerate(file_paths, 1):
            console.print(f"  v{idx}: {fp.name}")
        console.print(f"\n[bold]Working directory:[/bold] {work_dir}")
        return

    # Initialize timing if requested
    timing_obj = TimingBreakdown("Build Phases") if timing else None

    if timing_obj:
        timing_obj.mark("initialization")

    # Initialize LightRAG
    print_info("Initializing LightRAG...")

    try:
        rag = LightRAG(
            working_dir=str(work_dir),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            chunking_func=create_hierarchical_chunking_func(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            entity_extract_max_gleaning=DEFAULT_ENTITY_EXTRACT_MAX_GLEANING,
            enable_llm_cache=False,
        )

        # Run async initialization
        asyncio.run(rag.initialize_storages())
        print_success("LightRAG initialized")

    except Exception as e:
        print_error(f"Failed to initialize LightRAG: {e}")
        raise typer.Exit(1)

    if timing_obj:
        timing_obj.mark("initialization")

    # Show final order with version numbers
    console.print("\n[bold]✅ Ingestion order:[/bold]")
    for idx, fp in enumerate(file_paths, 1):
        console.print(f"  v{idx}: {fp.name}")

    # Ingest documents
    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]       INGESTING DOCUMENTS[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
    )

    try:
        asyncio.run(ingest_documents(rag, file_paths, timing_obj))
        asyncio.run(rag.finalize_storages())

    except Exception as e:
        print_error(f"Ingestion failed: {e}")
        raise typer.Exit(1)

    # Summary
    console.print(
        "\n[bold green]═══════════════════════════════════════════════════════[/bold green]"
    )
    console.print("[bold green]       INGESTION COMPLETE[/bold green]")
    console.print(
        "[bold green]═══════════════════════════════════════════════════════[/bold green]\n"
    )

    print_success(f"Documents ingested: {len(file_paths)}")
    print_info(f"Working directory: {work_dir}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print('  1. Query: [cyan]lightrag query "your question"[/cyan]')
    console.print("  2. Interactive: [cyan]lightrag interactive[/cyan]")
    console.print("  3. Info: [cyan]lightrag info[/cyan]")

    if timing_obj:
        console.print()
        timing_obj.report()


if __name__ == "__main__":
    app()

# Made with Bob
