# Migration Guide: Old Scripts → Unified CLI

This guide helps you migrate from the old `build_graph.py` and `query_graph.py` scripts to the new unified `lightrag` CLI.

## Overview

The new CLI provides:
- ✅ Single entry point (`lightrag` command)
- ✅ Intuitive subcommands
- ✅ Smart defaults and auto-detection
- ✅ Better error messages
- ✅ MLflow tracing support
- ✅ Interactive mode improvements
- ✅ Working directory switching

## Quick Migration

### Old Way
```bash
python build_graph.py --input-dir ./docs
python query_graph.py --query "test" --mode temporal --date 2024-01-01
```

### New Way
```bash
lightrag build --input ./docs
lightrag query "test" --as-of 2024-01-01
```

## Command Mapping

### Build Command

| Old (`build_graph.py`) | New (`lightrag build`) |
|------------------------|------------------------|
| `python build_graph.py` | `lightrag build` |
| `--input-dir DIR` | `--input DIR` or `-i DIR` |
| `--working-dir DIR` | `--working-dir DIR` or `-w DIR` |
| `--profile` | `--profile` |
| `--timing` | `--timing` |
| N/A | `--files FILE [FILE ...]` (new!) |
| N/A | `--suggest-order` (new!) |
| N/A | `--dry-run` (new!) |
| N/A | `--trace` (new!) |

**Examples:**

```bash
# Old
python build_graph.py --input-dir ./contracts --working-dir ./rag

# New
lightrag build --input ./contracts --working-dir ./rag

# New: Explicit file order (recommended)
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# New: With tracing
lightrag build --input ./docs --trace --trace-name "ingestion-v1"
```

### Query Command

| Old (`query_graph.py`) | New (`lightrag query`) |
|------------------------|------------------------|
| `python query_graph.py --query "text"` | `lightrag query "text"` |
| `--query TEXT` | `"TEXT"` (positional) or `--query TEXT` |
| `--mode MODE` | `--mode MODE` or `-m MODE` |
| `--date DATE` | `--date DATE` or `--as-of DATE` |
| `--working-dir DIR` | `--working-dir DIR` or `-w DIR` |
| `--stream` | `--stream` or `-s` |
| `--profile` | `--profile` |
| `--timing` | `--timing` |
| N/A | `--latest` (new!) |
| N/A | `--list-graphs` (new!) |
| N/A | `--output FILE` (new!) |
| N/A | `--trace` (new!) |

**Examples:**

```bash
# Old
python query_graph.py --query "What is the fee?" --mode temporal --date 2024-01-01

# New (simpler)
lightrag query "What is the fee?" --as-of 2024-01-01

# New: Latest version
lightrag query "What is the current fee?" --latest

# New: Different working directory
lightrag query "test" --working-dir ./contracts_rag

# New: List available graphs
lightrag query --list-graphs

# New: Save to file
lightrag query "List fees" --output fees.txt

# New: With tracing
lightrag query "What changed?" --trace --trace-name "comparison"
```

### Interactive Mode

| Old (`query_graph.py --interactive`) | New (`lightrag interactive`) |
|--------------------------------------|------------------------------|
| `python query_graph.py --interactive` | `lightrag interactive` |
| `--mode MODE` | `--mode MODE` or `-m MODE` |
| `--date DATE` | `--date DATE` or `-d DATE` |
| `--working-dir DIR` | `--working-dir DIR` or `-w DIR` |
| N/A | `/graph <dir>` (new!) |
| N/A | `/graphs` (new!) |
| N/A | `--trace` (new!) |

**Examples:**

```bash
# Old
python query_graph.py --interactive --mode temporal

# New
lightrag interactive --mode temporal

# New: With working directory switching
lightrag interactive
[hybrid] Query: /graph ./contracts_rag
[hybrid] Query: What is the fee?
```

## New Features

### 1. Explicit File Ordering

**Old Way:** Manual interactive prompting every time
```bash
python build_graph.py
# Then manually enter: 1 2 3 4
```

**New Way:** Specify files directly
```bash
lightrag build --files base.pdf amendment1.pdf amendment2.pdf
```

### 2. Working Directory Switching

**Old Way:** Restart script with different directory
```bash
python query_graph.py --query "test" --working-dir ./graph1
python query_graph.py --query "test" --working-dir ./graph2
```

**New Way:** Switch in interactive mode
```bash
lightrag interactive
[hybrid] Query: What is the fee?
[hybrid] Query: /graph ./graph2
[hybrid] Query: What is the fee?
```

### 3. Graph Discovery

**Old Way:** Manually remember directories
```bash
ls -d *_rag
```

**New Way:** Built-in listing
```bash
lightrag query --list-graphs
```

### 4. MLflow Tracing

**Old Way:** Not available
```bash
# No tracing support
```

**New Way:** Built-in observability
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
lightrag build --trace --trace-name "ingestion-v1"
lightrag query "test" --trace --trace-name "query-test"
```

### 5. Configuration Management

**Old Way:** Edit .env manually
```bash
nano .env
```

**New Way:** CLI commands
```bash
lightrag config set working-dir ./my_rag
lightrag config set default-mode temporal
lightrag config show
```

### 6. Project Initialization

**Old Way:** Manual setup
```bash
mkdir inputs rag_storage
cp .env.example .env
nano .env
```

**New Way:** One command
```bash
lightrag config init ./my_project
cd my_project
# Edit .env and start using
```

## Backward Compatibility

The old scripts still work! You can use both:

```bash
# Old scripts (still work)
python build_graph.py --input-dir ./docs
python query_graph.py --query "test"

# New CLI (recommended)
lightrag build --input ./docs
lightrag query "test"
```

**Note:** Old scripts will show a deprecation notice in future versions.

## Migration Checklist

- [ ] Install new CLI: `pip install -e .`
- [ ] Test new commands: `lightrag --help`
- [ ] Update scripts/aliases to use `lightrag` command
- [ ] Migrate environment variables (if needed)
- [ ] Update documentation/README
- [ ] Train team on new commands
- [ ] Set up MLflow (optional)
- [ ] Configure defaults: `lightrag config set ...`

## Common Migration Scenarios

### Scenario 1: Simple Build & Query

**Before:**
```bash
#!/bin/bash
python build_graph.py --input-dir ./contracts
python query_graph.py --query "What is the fee?" --mode hybrid
```

**After:**
```bash
#!/bin/bash
lightrag build --input ./contracts
lightrag query "What is the fee?"
```

### Scenario 2: Temporal Analysis

**Before:**
```bash
#!/bin/bash
python build_graph.py --input-dir ./docs
python query_graph.py --query "What was the fee?" --mode temporal --date 2024-01-01
python query_graph.py --query "What was the fee?" --mode temporal --date 2024-06-01
```

**After:**
```bash
#!/bin/bash
lightrag build --input ./docs
lightrag query "What was the fee?" --as-of 2024-01-01
lightrag query "What was the fee?" --as-of 2024-06-01
```

### Scenario 3: Multiple Graphs

**Before:**
```bash
#!/bin/bash
python build_graph.py --input-dir ./contract1 --working-dir ./graph1
python build_graph.py --input-dir ./contract2 --working-dir ./graph2
python query_graph.py --query "test" --working-dir ./graph1
python query_graph.py --query "test" --working-dir ./graph2
```

**After:**
```bash
#!/bin/bash
lightrag build --input ./contract1 --working-dir ./graph1
lightrag build --input ./contract2 --working-dir ./graph2
lightrag query "test" --working-dir ./graph1
lightrag query "test" --working-dir ./graph2

# Or use interactive mode
lightrag interactive
```

### Scenario 4: Production Pipeline

**Before:**
```bash
#!/bin/bash
python build_graph.py --input-dir ./data --profile --timing
python query_graph.py --query "test" --mode hybrid --profile
```

**After:**
```bash
#!/bin/bash
export MLFLOW_TRACKING_URI=http://mlflow.example.com
lightrag build --input ./data --profile --timing --trace
lightrag query "test" --mode hybrid --profile --trace
```

## Environment Variables

Most environment variables remain the same:

| Variable | Old | New | Notes |
|----------|-----|-----|-------|
| `INPUT_DIR` | ✅ | ✅ | Same |
| `WORKING_DIR` | ✅ | ✅ | Same |
| `LIGHTRAG_WORKING_DIR` | ❌ | ✅ | New alternative |
| `CHUNK_SIZE` | ✅ | ✅ | Same |
| `CHUNK_OVERLAP_SIZE` | ✅ | ✅ | Same |
| `LLM_BINDING` | ✅ | ✅ | Same |
| `LLM_MODEL` | ✅ | ✅ | Same |
| `MLFLOW_TRACKING_URI` | ❌ | ✅ | New for tracing |

## Troubleshooting

### "Command not found: lightrag"

```bash
# Solution 1: Reinstall
pip install -e .

# Solution 2: Check installation
pip show lightrag-hku

# Solution 3: Use full path
python -m lightrag.cli
```

### "Import errors" when running CLI

```bash
# Install missing dependencies
pip install typer rich mlflow

# Or reinstall with all dependencies
pip install -e .
```

### Old scripts not working

```bash
# Old scripts should still work
python build_graph.py --help
python query_graph.py --help

# If not, check Python path
which python
python --version
```

## Getting Help

```bash
# General help
lightrag --help

# Command-specific help
lightrag build --help
lightrag query --help
lightrag interactive --help

# Show version
lightrag --version

# Configuration help
lightrag config --help
```

## Resources

- [CLI Reference](CLI_REFERENCE.md) - Complete command documentation
- [Getting Started](GETTING_STARTED.md) - Quick start guide
- [User Guide](USER_GUIDE.md) - Comprehensive usage guide
- [CLI Design](CLI_DESIGN.md) - Design specification

## Feedback

Found an issue or have suggestions? Please:
1. Check [CLI Reference](CLI_REFERENCE.md) for documentation
2. Open an issue on GitHub
3. Join our community discussions

---

**Last Updated:** March 12, 2026

**Migration Support:** The old scripts will be maintained for 2-3 releases before deprecation.