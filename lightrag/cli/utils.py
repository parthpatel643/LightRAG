"""
Shared utilities for LightRAG CLI.

This module provides common functionality used across CLI commands:
- Working directory detection and validation
- File sequencing and ordering
- Progress reporting and formatting
- MLflow tracing integration
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

console = Console()


def detect_working_dir(specified_dir: Optional[str] = None) -> Path:
    """
    Detect LightRAG working directory.

    Priority order:
    1. Specified directory (--working-dir flag)
    2. LIGHTRAG_WORKING_DIR environment variable
    3. .lightrag/config file in current or parent directories
    4. ./rag_storage (default)

    Args:
        specified_dir: Directory specified via CLI flag

    Returns:
        Path to working directory
    """
    # 1. Check specified directory
    if specified_dir:
        path = Path(specified_dir)
        if path.exists():
            return path.resolve()
        # Don't create yet, let caller decide
        return path

    # 2. Check environment variable
    env_dir = os.getenv("LIGHTRAG_WORKING_DIR")
    if env_dir:
        path = Path(env_dir)
        if path.exists():
            return path.resolve()

    # 3. Check for .lightrag/config in current or parent directories
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        config_file = parent / ".lightrag" / "config"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    for line in f:
                        if line.startswith("working_dir="):
                            dir_path = line.split("=", 1)[1].strip()
                            path = Path(dir_path)
                            if path.exists():
                                return path.resolve()
            except Exception:
                pass

    # 4. Default
    return Path("./rag_storage")


def detect_input_dir(specified_dir: Optional[str] = None) -> Optional[Path]:
    """
    Detect input directory for documents.

    Priority order:
    1. Specified directory (--input flag)
    2. INPUT_DIR environment variable
    3. ./inputs (if exists)
    4. None (will prompt user)

    Args:
        specified_dir: Directory specified via CLI flag

    Returns:
        Path to input directory or None
    """
    # 1. Check specified directory
    if specified_dir:
        path = Path(specified_dir)
        if path.exists() and path.is_dir():
            return path.resolve()
        return None

    # 2. Check environment variable
    env_dir = os.getenv("INPUT_DIR")
    if env_dir:
        path = Path(env_dir)
        if path.exists() and path.is_dir():
            return path.resolve()

    # 3. Check default location
    default_path = Path("./inputs")
    if default_path.exists() and default_path.is_dir():
        return default_path.resolve()

    return None


def list_available_graphs() -> List[Tuple[Path, str]]:
    """
    List available knowledge graphs (working directories).

    Returns:
        List of (path, status) tuples
    """
    graphs = []

    # Check common locations
    candidates = [
        Path("./rag_storage"),
        Path("./storage"),
        Path("./lightrag_storage"),
    ]

    # Add from environment
    env_dir = os.getenv("LIGHTRAG_WORKING_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    # Scan current directory for *_rag directories
    try:
        for item in Path.cwd().iterdir():
            if item.is_dir() and (
                "rag" in item.name.lower() or "storage" in item.name.lower()
            ):
                candidates.append(item)
    except Exception:
        pass

    # Validate and deduplicate
    seen = set()
    for path in candidates:
        if path.exists() and path.is_dir():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                # Check if it looks like a LightRAG directory
                status = (
                    "valid"
                    if (resolved / "kv_store_full_docs.json").exists()
                    else "empty"
                )
                graphs.append((resolved, status))

    return sorted(graphs, key=lambda x: x[0])


def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract date from filename using common patterns.

    Patterns:
    - YYYY-MM-DD
    - YYYYMMDD
    - YYYY_MM_DD
    - YYYY-MM
    - Month YYYY (e.g., "January 2024")

    Args:
        filename: Filename to analyze

    Returns:
        Extracted date string or None
    """
    # Pattern 1: YYYY-MM-DD
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Pattern 2: YYYYMMDD
    match = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Pattern 3: YYYY_MM_DD
    match = re.search(r"(\d{4})_(\d{2})_(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Pattern 4: YYYY-MM
    match = re.search(r"(\d{4})-(\d{2})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-01"

    # Pattern 5: Month YYYY
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    for month_name, month_num in months.items():
        pattern = rf"{month_name}[_\s-]*(\d{{4}})"
        match = re.search(pattern, filename.lower())
        if match:
            return f"{match.group(1)}-{month_num}-01"

    return None


def extract_version_from_filename(filename: str) -> Optional[int]:
    """
    Extract version number from filename.

    Patterns:
    - v1, v2, v3
    - version-1, version-2
    - amendment-1, amendment-2
    - rev1, rev2

    Args:
        filename: Filename to analyze

    Returns:
        Version number or None
    """
    # Pattern 1: v1, v2, etc.
    match = re.search(r"v(\d+)", filename.lower())
    if match:
        return int(match.group(1))

    # Pattern 2: version-1, version-2
    match = re.search(r"version[_\s-]*(\d+)", filename.lower())
    if match:
        return int(match.group(1))

    # Pattern 3: amendment-1, amendment-2
    match = re.search(r"amendment[_\s-]*(\d+)", filename.lower())
    if match:
        return int(match.group(1))

    # Pattern 4: rev1, rev2
    match = re.search(r"rev[_\s-]*(\d+)", filename.lower())
    if match:
        return int(match.group(1))

    return None


def classify_document_type(filename: str) -> str:
    """
    Classify document type based on filename.

    Types:
    - base: Original/base document
    - amendment: Amendment to existing document
    - revision: Revision/update
    - supplement: Supplementary document

    Args:
        filename: Filename to analyze

    Returns:
        Document type classification
    """
    filename_lower = filename.lower()

    if any(
        word in filename_lower for word in ["base", "original", "initial", "master"]
    ):
        return "base"
    elif any(word in filename_lower for word in ["amendment", "amend"]):
        return "amendment"
    elif any(
        word in filename_lower for word in ["revision", "rev", "update", "modified"]
    ):
        return "revision"
    elif any(word in filename_lower for word in ["supplement", "addendum", "addition"]):
        return "supplement"

    return "unknown"


def suggest_file_order(files: List[Path]) -> List[Tuple[Path, str]]:
    """
    Suggest ordering for files based on heuristics.

    Returns list of (file, reasoning) tuples.

    Args:
        files: List of file paths

    Returns:
        List of (file, reasoning) tuples in suggested order
    """
    scored_files = []

    for file in files:
        score = 0
        reasons = []

        # Check for base document indicators
        doc_type = classify_document_type(file.name)
        if doc_type == "base":
            score -= 1000  # Base documents come first
            reasons.append(f"detected: {doc_type} document")
        elif doc_type != "unknown":
            reasons.append(f"detected: {doc_type}")

        # Check for version number
        version = extract_version_from_filename(file.name)
        if version is not None:
            score += version * 100
            reasons.append(f"version {version}")

        # Check for date
        date_str = extract_date_from_filename(file.name)
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                score += (date_obj - datetime(2000, 1, 1)).days
                reasons.append(f"{date_str} date")
            except ValueError:
                pass

        # Use modification time as fallback
        if not reasons:
            mtime = file.stat().st_mtime
            score += mtime
            reasons.append("by modification time")

        reasoning = ", ".join(reasons) if reasons else "alphabetical order"
        scored_files.append((file, score, reasoning))

    # Sort by score
    scored_files.sort(key=lambda x: x[1])

    return [(f, r) for f, _, r in scored_files]


def create_progress_bar(description: str = "Processing") -> Progress:
    """
    Create a rich progress bar for CLI operations.

    Args:
        description: Description text for the progress bar

    Returns:
        Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_file_list(files: List[Tuple[Path, str]], title: str = "Files"):
    """
    Print a formatted list of files with reasoning.

    Args:
        files: List of (file, reasoning) tuples
        title: Title for the list
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("File", style="green")
    table.add_column("Reasoning", style="yellow")

    for idx, (file, reasoning) in enumerate(files, 1):
        table.add_row(str(idx), file.name, reasoning)

    console.print(table)


def print_success(message: str):
    """Print success message."""
    console.print(f"[green]✅ {message}[/green]")


def print_error(message: str):
    """Print error message."""
    console.print(f"[red]❌ {message}[/red]")


def print_warning(message: str):
    """Print warning message."""
    console.print(f"[yellow]⚠️  {message}[/yellow]")


def print_info(message: str):
    """Print info message."""
    console.print(f"[blue]ℹ️  {message}[/blue]")


# Made with Bob
