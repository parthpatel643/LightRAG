"""
LightRAG CLI - Interactive Command

Interactive query session for conversational querying.
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
)
from lightrag.functions import embedding_func, llm_model_func

app = typer.Typer(help="Interactive query session")


async def interactive_session(
    rag: LightRAG,
    default_mode: str,
    default_date: Optional[str],
):
    """
    Run interactive query session.

    Args:
        rag: LightRAG instance
        default_mode: Default query mode
        default_date: Default reference date
    """
    current_mode = default_mode
    current_date = default_date or datetime.now().strftime("%Y-%m-%d")
    current_working_dir = rag.working_dir

    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]       INTERACTIVE QUERY MODE[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print(f"[bold]Default mode:[/bold] {current_mode}")
    if current_mode == "temporal":
        console.print(f"[bold]Default date:[/bold] {current_date}")
    console.print(f"[bold]Working directory:[/bold] {current_working_dir}")

    console.print("\n[bold]Commands:[/bold]")
    console.print("  /mode <mode>       - Change query mode")
    console.print("  /date <YYYY-MM-DD> - Set reference date")
    console.print("  /latest            - Set date to today")
    console.print("  /graph <dir>       - Switch working directory")
    console.print("  /graphs            - List available graphs")
    console.print("  /help              - Show this help")
    console.print("  /quit or /exit     - Exit interactive mode")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════[/bold cyan]\n"
    )

    while True:
        try:
            # Get user input
            prompt_text = f"[{current_mode}] Query: "
            user_input = console.input(f"[bold cyan]{prompt_text}[/bold cyan]").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower()

                if cmd in ["/quit", "/exit"]:
                    console.print("[yellow]Exiting interactive mode...[/yellow]")
                    break

                elif cmd == "/help":
                    console.print("\n[bold]Commands:[/bold]")
                    console.print("  /mode <mode>       - Change query mode")
                    console.print("  /date <YYYY-MM-DD> - Set reference date")
                    console.print("  /latest            - Set date to today")
                    console.print("  /graph <dir>       - Switch working directory")
                    console.print("  /graphs            - List available graphs")
                    console.print("  /help              - Show this help")
                    console.print("  /quit or /exit     - Exit interactive mode\n")
                    continue

                elif cmd == "/mode":
                    if len(cmd_parts) < 2:
                        print_error(
                            "Usage: /mode <local|global|hybrid|temporal|naive|mix>"
                        )
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
                        print_success(f"Mode changed to: {current_mode}")
                    else:
                        print_error(f"Invalid mode: {new_mode}")
                    continue

                elif cmd == "/date":
                    if len(cmd_parts) < 2:
                        print_error("Usage: /date <YYYY-MM-DD>")
                        continue
                    try:
                        datetime.strptime(cmd_parts[1], "%Y-%m-%d")
                        current_date = cmd_parts[1]
                        print_success(f"Reference date set to: {current_date}")
                        if current_mode != "temporal":
                            print_info("Note: Date only applies in temporal mode")
                    except ValueError:
                        print_error(f"Invalid date format: {cmd_parts[1]}")
                        print_info("Expected format: YYYY-MM-DD")
                    continue

                elif cmd == "/latest":
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    print_success(f"Date set to today: {current_date}")
                    continue

                elif cmd == "/graph":
                    if len(cmd_parts) < 2:
                        print_error("Usage: /graph <directory>")
                        continue
                    new_dir = Path(cmd_parts[1])
                    if not new_dir.exists():
                        print_error(f"Directory not found: {new_dir}")
                        continue
                    try:
                        # Reinitialize with new directory
                        rag.working_dir = str(new_dir)
                        await rag.initialize_storages()
                        current_working_dir = str(new_dir)
                        print_success(
                            f"Switched to working directory: {current_working_dir}"
                        )
                    except Exception as e:
                        print_error(f"Failed to switch directory: {e}")
                    continue

                elif cmd == "/graphs":
                    graphs = list_available_graphs()
                    if not graphs:
                        print_info("No knowledge graphs found")
                    else:
                        console.print("\n[bold]Available graphs:[/bold]")
                        for path, status in graphs:
                            status_icon = "✅" if status == "valid" else "📁"
                            is_current = str(path) == current_working_dir
                            marker = " [current]" if is_current else ""
                            console.print(f"  {status_icon} {path}{marker}")
                        console.print()
                    continue

                else:
                    print_error(f"Unknown command: {cmd}")
                    print_info("Type /help for available commands")
                    continue

            # Execute query
            param = QueryParam(
                mode=current_mode,
                reference_date=current_date if current_mode == "temporal" else None,
            )

            try:
                response = await rag.aquery(user_input, param=param)

                console.print(
                    "\n[bold cyan]─────────────────────────────────────────────────────────[/bold cyan]"
                )
                console.print("[bold cyan]RESPONSE[/bold cyan]")
                console.print(
                    "[bold cyan]─────────────────────────────────────────────────────────[/bold cyan]"
                )
                console.print(response)
                console.print(
                    "[bold cyan]─────────────────────────────────────────────────────────[/bold cyan]\n"
                )

            except Exception as e:
                print_error(f"Query failed: {e}")
                continue

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Exiting interactive mode...[/yellow]")
            break
        except EOFError:
            console.print("\n[yellow]Exiting interactive mode...[/yellow]")
            break


@app.command()
def main(
    ctx: typer.Context,
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        "-m",
        help="Default query mode",
    ),
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Default reference date for temporal mode",
    ),
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        "-w",
        help="LightRAG working directory",
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
    Start interactive query session.

    Examples:

        # Start interactive mode
        lightrag interactive

        # With temporal mode
        lightrag interactive --mode temporal --date 2024-01-01

        # With specific working directory
        lightrag interactive --working-dir ./contracts_rag
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    working_dir = working_dir or global_opts.get("working_dir")
    trace = trace or global_opts.get("trace", False)
    trace_name = trace_name or global_opts.get("trace_name")

    # Detect working directory
    work_dir = detect_working_dir(working_dir)

    if not work_dir.exists():
        print_error(f"Working directory not found: {work_dir}")
        console.print("\n[yellow]Suggestions:[/yellow]")
        console.print(
            "  1. Run [cyan]lightrag build[/cyan] to create a knowledge graph"
        )
        console.print(
            "  2. Specify directory: [cyan]lightrag interactive --working-dir ./path[/cyan]"
        )
        raise typer.Exit(1)

    # Initialize LightRAG
    print_info(f"Initializing LightRAG (working_dir: {work_dir})...")

    try:
        rag = LightRAG(
            working_dir=str(work_dir),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            enable_llm_cache=False,
        )

        # Run async initialization
        asyncio.run(rag.initialize_storages())
        print_success("LightRAG initialized")

    except Exception as e:
        print_error(f"Failed to initialize LightRAG: {e}")
        raise typer.Exit(1)

    # Start interactive session
    try:
        asyncio.run(interactive_session(rag, mode, date))
    except Exception as e:
        print_error(f"Interactive session failed: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

# Made with Bob
