"""
LightRAG CLI - Config Command

Manage LightRAG configuration and settings.
"""

from pathlib import Path
from typing import Optional

import typer

from lightrag.cli.utils import (
    console,
    print_error,
    print_info,
    print_success,
)

app = typer.Typer(help="Manage configuration")


def get_config_file() -> Path:
    """Get path to configuration file."""
    return Path.home() / ".lightrag" / "config"


def load_config() -> dict:
    """Load configuration from file."""
    config_file = get_config_file()
    config = {}

    if config_file.exists():
        try:
            with open(config_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print_error(f"Failed to load config: {e}")

    return config


def save_config(config: dict):
    """Save configuration to file."""
    config_file = get_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(config_file, "w") as f:
            f.write("# LightRAG Configuration\n")
            f.write("# This file is automatically managed by 'lightrag config'\n\n")
            for key, value in sorted(config.items()):
                f.write(f"{key}={value}\n")
        print_success(f"Configuration saved to: {config_file}")
    except Exception as e:
        print_error(f"Failed to save config: {e}")
        raise typer.Exit(1)


@app.command("show")
def show_config():
    """Show current configuration."""
    config = load_config()

    if not config:
        print_info("No configuration found")
        console.print(
            "\n[yellow]Set values with:[/yellow] lightrag config set <key> <value>"
        )
        return

    console.print("\n[bold]Current Configuration:[/bold]\n")
    for key, value in sorted(config.items()):
        console.print(f"  [cyan]{key}[/cyan] = [green]{value}[/green]")
    console.print()


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set a configuration value."""
    config = load_config()
    config[key] = value
    save_config(config)
    print_success(f"Set {key} = {value}")


@app.command("get")
def get_config(
    key: str = typer.Argument(..., help="Configuration key"),
):
    """Get a configuration value."""
    config = load_config()

    if key in config:
        console.print(config[key])
    else:
        print_error(f"Key not found: {key}")
        raise typer.Exit(1)


@app.command("list")
def list_keys():
    """List all configuration keys."""
    console.print("\n[bold]Available Configuration Keys:[/bold]\n")
    console.print("  [cyan]working-dir[/cyan]        - Default working directory")
    console.print("  [cyan]input-dir[/cyan]          - Default input directory")
    console.print("  [cyan]default-mode[/cyan]       - Default query mode")
    console.print("  [cyan]chunk-size[/cyan]         - Default chunk size")
    console.print("  [cyan]chunk-overlap[/cyan]      - Default chunk overlap")
    console.print("  [cyan]llm-binding[/cyan]        - LLM provider")
    console.print("  [cyan]embedding-binding[/cyan]  - Embedding provider")
    console.print()


@app.command("reset")
def reset_config(
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation",
    ),
):
    """Reset configuration to defaults."""
    if not confirm:
        if not typer.confirm("Are you sure you want to reset configuration?"):
            print_info("Operation cancelled")
            return

    config_file = get_config_file()
    if config_file.exists():
        config_file.unlink()
        print_success("Configuration reset")
    else:
        print_info("No configuration to reset")


@app.command("validate")
def validate_config():
    """Validate configuration."""
    config = load_config()

    if not config:
        print_info("No configuration to validate")
        return

    console.print("\n[bold]Validating Configuration:[/bold]\n")

    valid = True

    # Check working-dir
    if "working-dir" in config:
        work_dir = Path(config["working-dir"])
        if work_dir.exists():
            print_success(f"working-dir: {work_dir} [exists]")
        else:
            print_error(f"working-dir: {work_dir} [not found]")
            valid = False

    # Check input-dir
    if "input-dir" in config:
        input_dir = Path(config["input-dir"])
        if input_dir.exists():
            print_success(f"input-dir: {input_dir} [exists]")
        else:
            print_error(f"input-dir: {input_dir} [not found]")
            valid = False

    # Check mode
    if "default-mode" in config:
        mode = config["default-mode"]
        valid_modes = [
            "local",
            "global",
            "hybrid",
            "temporal",
            "naive",
            "mix",
            "bypass",
        ]
        if mode in valid_modes:
            print_success(f"default-mode: {mode} [valid]")
        else:
            print_error(f"default-mode: {mode} [invalid]")
            print_info(f"Valid modes: {', '.join(valid_modes)}")
            valid = False

    console.print()
    if valid:
        print_success("Configuration is valid")
    else:
        print_error("Configuration has errors")
        raise typer.Exit(1)


@app.command("init")
def init_project(
    directory: Optional[str] = typer.Argument(
        None,
        help="Project directory (default: current directory)",
    ),
):
    """Initialize a new LightRAG project."""
    project_dir = Path(directory) if directory else Path.cwd()

    console.print(f"\n[bold]Initializing LightRAG project in:[/bold] {project_dir}\n")

    # Create directories
    (project_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (project_dir / "rag_storage").mkdir(parents=True, exist_ok=True)

    # Create .env file
    env_file = project_dir / ".env"
    if not env_file.exists():
        env_content = """# LightRAG Configuration

# LLM Configuration
LLM_BINDING=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key_here

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small

# Directories
INPUT_DIR=./inputs
WORKING_DIR=./rag_storage

# Chunking
CHUNK_SIZE=2000
CHUNK_OVERLAP_SIZE=200

# MLflow (optional)
# MLFLOW_TRACKING_URI=http://localhost:5000
"""
        env_file.write_text(env_content)
        print_success(f"Created: {env_file}")
    else:
        print_info(f"Exists: {env_file}")

    # Create README
    readme_file = project_dir / "README.md"
    if not readme_file.exists():
        readme_content = """# LightRAG Project

## Quick Start

1. Configure your API keys in `.env`
2. Place documents in `./inputs/`
3. Build the knowledge graph:
   ```bash
   lightrag build
   ```
4. Query the graph:
   ```bash
   lightrag query "your question"
   ```

## Commands

- `lightrag build` - Ingest documents
- `lightrag query "question"` - Query the graph
- `lightrag interactive` - Interactive mode
- `lightrag info` - Show statistics

## Documentation

See https://github.com/HKUDS/LightRAG for full documentation.
"""
        readme_file.write_text(readme_content)
        print_success(f"Created: {readme_file}")
    else:
        print_info(f"Exists: {readme_file}")

    console.print("\n[bold green]✅ Project initialized successfully![/bold green]\n")
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Edit [cyan].env[/cyan] with your API keys")
    console.print("  2. Place documents in [cyan]./inputs/[/cyan]")
    console.print("  3. Run [cyan]lightrag build[/cyan]")
    console.print()


if __name__ == "__main__":
    app()

# Made with Bob
