# LightRAG Unified CLI Design Specification

## Overview

This document specifies the design for a unified CLI interface that simplifies the LightRAG user experience by consolidating [`build_graph.py`](../build_graph.py) and [`query_graph.py`](../query_graph.py) into a single, intuitive command-line tool.

## Design Goals

1. **Simplicity** - Reduce cognitive load with smart defaults and intuitive commands
2. **Discoverability** - Built-in help and examples for all commands
3. **Flexibility** - Support both simple and advanced use cases
4. **Consistency** - Unified argument patterns across all subcommands
5. **Backward Compatibility** - Existing scripts continue to work

## Command Structure

```
lightrag [global-options] <command> [command-options] [arguments]
```

### Global Options

Available for all commands:

```bash
--working-dir PATH    # LightRAG working directory (default: auto-detect or ./rag_storage)
--config FILE         # Load configuration from file (default: .env)
--verbose, -v         # Increase verbosity (can be repeated: -vv, -vvv)
--quiet, -q           # Suppress non-error output
--trace               # Enable MLflow tracing for observability
--trace-name NAME     # Custom name for MLflow trace (default: auto-generated)
--help, -h            # Show help message
--version             # Show version information
```

## Subcommands

### 1. `lightrag build` - Build Knowledge Graph

Ingest documents into the knowledge graph with automatic versioning.

#### Basic Usage

```bash
# Auto-detect input directory and sequence files
lightrag build

# Specify input directory
lightrag build --input ./contracts

# Specify individual files (order = sequence)
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# Build with custom working directory
lightrag build --input ./docs --working-dir ./my_rag
```

#### Options

```bash
--input DIR, -i DIR              # Input directory (default: ./inputs)
--files FILE [FILE ...]          # Specific files to ingest (order determines sequence)
--working-dir DIR, -w DIR        # Working directory (default: ./rag_storage)
--suggest-order                  # Show suggested order based on heuristics (user must confirm)
--interactive                    # Prompt user to specify order (default when using --input)
--yes, -y                        # Accept suggested order without confirmation
--chunk-size N                   # Chunk size in tokens (default: 2000)
--chunk-overlap N                # Chunk overlap in tokens (default: 200)
--profile                        # Enable profiling
--timing                         # Show timing breakdown
--watch                          # Watch directory for new files (continuous mode)
--force                          # Force rebuild, ignore existing data
--dry-run                        # Show what would be done without executing
--trace                          # Enable MLflow tracing for build process
--trace-name NAME                # Custom name for MLflow trace
```

#### File Sequencing

**Important**: Document sequencing requires human SME (Subject Matter Expert) knowledge and cannot be fully automated. The system provides tools to help, but the user must verify and confirm the order.

**Sequencing Options**:

1. **Explicit file list** (Recommended) - User specifies files in order:
   ```bash
   lightrag build --files base.pdf amendment1.pdf amendment2.pdf
   ```

2. **Interactive ordering** (Default) - System shows files and prompts for order:
   ```bash
   lightrag build --input ./contracts
   # Shows numbered list, user enters sequence: "1 3 2 4"
   ```

3. **Suggested ordering** - System suggests order based on heuristics, user confirms:
   ```bash
   lightrag build --input ./contracts --suggest-order
   # Shows suggested order with reasoning, user can accept or modify
   ```

**Ordering Heuristics** (for suggestions only):
- Date patterns in filename: `2024-01-15`, `20240115`, `2024_01_15`
- Version patterns: `v1`, `v2`, `version-1`, `amendment-1`
- Keywords: `base`, `original`, `amendment`, `revision`, `update`
- File modification time (as last resort)

**Note**: These are suggestions only. The user must review and confirm the sequence since only they understand the document relationships and chronology.

#### Examples

```bash
# Simple: explicit file order (recommended)
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# Interactive: prompt for order
lightrag build --input ./contracts

# With suggested order
lightrag build --input ./contracts --suggest-order

# Accept suggestions automatically (use with caution)
lightrag build --input ./contracts --suggest-order --yes

# Custom working directory with profiling
lightrag build --input ./contracts --profile --timing

# Specific files in order
lightrag build --files \
  base-contract.pdf \
  amendment-2024-q1.pdf \
  amendment-2024-q2.pdf

# Watch directory for new files
lightrag build --input ./contracts --watch

# Dry run to preview
lightrag build --input ./contracts --dry-run
```

### 2. `lightrag query` - Query Knowledge Graph

Query the knowledge graph with various modes and options.

#### Basic Usage

```bash
# Simple query (uses smart defaults)
lightrag query "What is the parking fee?"

# Temporal query with date
lightrag query "What was the fee?" --date 2024-01-01

# Query with specific mode
lightrag query "Show all services" --mode hybrid
```

#### Options

```bash
--query TEXT, -q TEXT            # Query string (required unless --interactive)
--mode MODE, -m MODE             # Query mode: local, global, hybrid, temporal (default: hybrid)
--date DATE, -d DATE             # Reference date for temporal mode (YYYY-MM-DD)
--latest                         # Use latest version (temporal mode with today's date)
--as-of DATE                     # Alias for --date (more intuitive)
--stream, -s                     # Stream response
--output FILE, -o FILE           # Save response to file
--format FORMAT                  # Output format: text, json, markdown (default: text)
--working-dir DIR, -w DIR        # Working directory (can switch between different graphs)
--list-graphs                    # List available working directories
--profile                        # Enable profiling
--timing                         # Show timing breakdown
--no-cache                       # Disable query cache
--trace                          # Enable MLflow tracing for query
--trace-name NAME                # Custom name for MLflow trace
```

#### Query Presets

Convenient shortcuts for common scenarios:

```bash
--latest                         # Temporal mode with today's date
--as-of DATE                     # Temporal mode with specific date
--compare DATE1 DATE2            # Compare results between two dates
--history                        # Show version history for query results
```

#### Examples

```bash
# Simple query
lightrag query "What is the landing fee?"

# Temporal query
lightrag query "What was the fee in Q1 2024?" --as-of 2024-03-31

# Latest version
lightrag query "What is the current fee?" --latest

# Compare versions
lightrag query "How did fees change?" --compare 2024-01-01 2024-06-01

# Stream response
lightrag query "Explain the contract terms" --stream

# Save to file
lightrag query "List all fees" --output fees.txt --format markdown

# With profiling
lightrag query "Complex query" --mode hybrid --profile --timing

# Switch working directory
lightrag query "What is the fee?" --working-dir ./contracts_rag

# List available graphs
lightrag query --list-graphs

# With MLflow tracing
lightrag query "What is the fee?" --trace --trace-name "fee-query"
```

### 3. `lightrag interactive` - Interactive Query Session

Start an interactive session for conversational querying.

#### Basic Usage

```bash
# Start interactive mode
lightrag interactive

# Start with specific mode and date
lightrag interactive --mode temporal --date 2024-06-01

# Start with working directory
lightrag interactive --working-dir ./my_rag
```

#### Options

```bash
--mode MODE, -m MODE             # Default query mode (default: hybrid)
--date DATE, -d DATE             # Default reference date for temporal mode
--working-dir DIR, -w DIR        # Working directory (can switch during session)
--list-graphs                    # List available working directories
--history-file FILE              # Command history file (default: ~/.lightrag_history)
--no-history                     # Disable command history
--trace                          # Enable MLflow tracing for session
--trace-name NAME                # Custom name for MLflow trace
```

#### Interactive Commands

Within the interactive session:

```
/mode <mode>                     # Change query mode
/date <YYYY-MM-DD>               # Set reference date
/latest                          # Set date to today
/stream                          # Toggle streaming mode
/save <file>                     # Save last response to file
/history                         # Show query history
/graph <dir>                     # Switch to different working directory
/graphs                          # List available working directories
/clear                           # Clear screen
/help                            # Show help
/quit, /exit                     # Exit interactive mode
```

#### Examples

```bash
# Start interactive session
lightrag interactive

# Interactive session with defaults and tracing
lightrag interactive --mode temporal --date 2024-01-01 --trace

# Session transcript:
# [hybrid] Query: What is the parking fee?
# Response: The parking fee is $200 per night...
#
# [hybrid] Query: /mode temporal
# ✓ Mode changed to: temporal
#
# [temporal] Query: /date 2024-01-01
# ✓ Reference date set to: 2024-01-01
#
# [temporal] Query: What was the parking fee?
# Response: In January 2024, the parking fee was $150 per night...
#
# [temporal] Query: /graph ./contracts_rag
# ✓ Switched to working directory: ./contracts_rag
#
# [temporal] Query: What are the contract terms?
# Response: The contract terms include...
#
# [temporal] Query: /quit
# Exiting interactive mode...
```

### 4. `lightrag info` - Show Graph Information

Display statistics and information about the knowledge graph.

#### Basic Usage

```bash
# Show basic info
lightrag info

# Show detailed statistics
lightrag info --detailed

# Show specific information
lightrag info --entities
lightrag info --documents
```

#### Options

```bash
--working-dir DIR, -w DIR        # Working directory (default: auto-detect)
--detailed, -d                   # Show detailed statistics
--entities                       # Show entity statistics
--documents                      # Show document statistics
--versions                       # Show version information
--storage                        # Show storage backend info
--format FORMAT                  # Output format: text, json, table (default: table)
```

#### Examples

```bash
# Basic info
lightrag info

# Output:
# Knowledge Graph Statistics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Working Directory:    ./rag_storage
# Total Documents:      4
# Total Entities:       87
# Versioned Entities:   23
# Total Relations:      156
# Sequence Range:       1-4
# Date Range:           2023-01-01 to 2025-12-31
# Storage Backend:      Neo4j + Milvus
# Last Updated:         2024-03-12 16:30:45
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Detailed statistics
lightrag info --detailed

# Entity breakdown
lightrag info --entities --format json
```

### 5. `lightrag config` - Configuration Management

Manage LightRAG configuration and settings.

#### Basic Usage

```bash
# Show current configuration
lightrag config show

# Set configuration value
lightrag config set working-dir ./my_rag

# Initialize new project
lightrag init ./my_project
```

#### Subcommands

```bash
lightrag config show                    # Show current configuration
lightrag config set KEY VALUE           # Set configuration value
lightrag config get KEY                 # Get configuration value
lightrag config list                    # List all configuration keys
lightrag config reset                   # Reset to defaults
lightrag config validate                # Validate configuration

lightrag init [DIR]                     # Initialize new project (alias for config init)
```

#### Configuration Keys

```bash
working-dir                    # Default working directory
input-dir                      # Default input directory
default-mode                   # Default query mode
chunk-size                     # Default chunk size
chunk-overlap                  # Default chunk overlap
llm-binding                    # LLM provider
embedding-binding              # Embedding provider
```

#### Examples

```bash
# Show configuration
lightrag config show

# Set default working directory
lightrag config set working-dir ./contracts_rag

# Set default query mode
lightrag config set default-mode temporal

# Initialize new project
lightrag init ./my_project
# Creates:
# - ./my_project/.env
# - ./my_project/inputs/
# - ./my_project/rag_storage/
# - ./my_project/README.md
```

## Smart Defaults & Auto-Detection

### Working Directory Detection

Priority order:
1. `--working-dir` flag
2. `LIGHTRAG_WORKING_DIR` environment variable
3. `.lightrag/config` file in current or parent directories
4. `./rag_storage` (default)

### Input Directory Detection

Priority order:
1. `--input` flag
2. `INPUT_DIR` environment variable
3. Auto-detect: `./inputs`, `./documents`, `./data`, `./docs`
4. Current directory as fallback

## MLflow Tracing Integration

### Overview

MLflow tracing provides observability for LightRAG operations, allowing you to track and analyze:
- Document ingestion performance
- Query execution paths
- LLM calls and token usage
- Embedding generation
- Graph operations

### Enabling Tracing

**Global Flag** (applies to all commands):
```bash
lightrag --trace build --input ./docs
lightrag --trace query "What is the fee?"
```

**Command-Specific Flag**:
```bash
lightrag build --input ./docs --trace
lightrag query "What is the fee?" --trace
lightrag interactive --trace
```

### Trace Naming

**Auto-Generated Names** (default):
```bash
lightrag build --trace
# Trace name: lightrag-build-20260312-164500

lightrag query "What is the fee?" --trace
# Trace name: lightrag-query-20260312-164530
```

**Custom Names**:
```bash
lightrag build --trace --trace-name "contract-ingestion-v1"
lightrag query "What is the fee?" --trace --trace-name "fee-lookup-test"
```

### Configuration

Set MLflow tracking URI via environment variable:
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
lightrag query "test" --trace
```

Or in `.env` file:
```bash
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=lightrag-production
```

### Trace Information Captured

**Build Command**:
- Document processing time per file
- Entity extraction metrics
- Embedding generation stats
- Graph storage operations
- Total tokens used
- Success/failure status

**Query Command**:
- Query processing time
- Retrieval phase timing
- LLM generation metrics
- Context size and tokens
- Cache hit/miss
- Response quality metrics

**Interactive Mode**:
- Session duration
- Number of queries
- Mode switches
- Graph switches
- Aggregate metrics

### Viewing Traces

**MLflow UI**:
```bash
# Start MLflow UI
mlflow ui --port 5000

# View traces at http://localhost:5000
```

**Programmatic Access**:
```python
import mlflow

# Get traces for specific run
client = mlflow.tracking.MlflowClient()
traces = client.search_traces(
    experiment_ids=["0"],
    filter_string="tags.command = 'lightrag-query'"
)
```

### Examples

**Build with Tracing**:
```bash
# Basic tracing
lightrag build --input ./contracts --trace

# With custom name
lightrag build --input ./contracts --trace --trace-name "contracts-v2-ingestion"

# View in MLflow UI
mlflow ui
```

**Query with Tracing**:
```bash
# Trace single query
lightrag query "What is the parking fee?" --trace

# Trace with custom name
lightrag query "What is the parking fee?" \
  --trace --trace-name "parking-fee-lookup" \
  --mode temporal --date 2024-06-01

# Compare traces for different dates
lightrag query "What is the fee?" --trace --trace-name "fee-2024-01" --date 2024-01-01
lightrag query "What is the fee?" --trace --trace-name "fee-2024-06" --date 2024-06-01
```

**Interactive Session with Tracing**:
```bash
# Start traced session
lightrag interactive --trace --trace-name "contract-analysis-session"

# All queries in session are traced
[hybrid] Query: What is the parking fee?
[hybrid] Query: What are the lease terms?
[hybrid] Query: /quit

# View session trace in MLflow UI
```

### Performance Impact

Tracing adds minimal overhead:
- ~5-10ms per operation
- Async logging (non-blocking)
- Configurable sampling rate

Disable tracing for production if not needed:
```bash
# No tracing (default)
lightrag query "test"

# Explicit disable
lightrag query "test" --no-trace
```

### Best Practices

1. **Use Custom Names for Important Operations**:
   ```bash
   lightrag build --trace --trace-name "production-ingestion-$(date +%Y%m%d)"
   ```

2. **Tag Traces with Metadata**:
   ```bash
   export MLFLOW_TAGS='{"environment":"production","version":"1.0"}'
   lightrag query "test" --trace
   ```

3. **Monitor Performance Trends**:
   - Track query latency over time
   - Identify slow operations
   - Optimize based on trace data

4. **Debug Issues**:
   - Enable tracing when investigating problems
   - Compare successful vs failed traces
   - Analyze LLM call patterns

### Query Mode Selection

Smart defaults based on context:
- If documents have versions → `temporal` mode
- If single document → `local` mode
- Otherwise → `hybrid` mode

### Date Handling

For temporal queries:
- No date specified → Use today's date
- `--latest` flag → Use today's date
- `--as-of DATE` → Use specified date
- Invalid date → Show error with format hint

## Error Handling & User Feedback

### Informative Error Messages

```bash
# Missing working directory
$ lightrag query "test"
Error: Working directory not found: ./rag_storage

Suggestions:
  1. Run 'lightrag build' to create a knowledge graph
  2. Specify directory: lightrag query "test" --working-dir ./path
  3. Check configuration: lightrag config show

# Invalid date format
$ lightrag query "test" --date 2024/01/01
Error: Invalid date format: 2024/01/01

Expected format: YYYY-MM-DD
Example: 2024-01-01

# No documents found
$ lightrag build --input ./empty
Error: No documents found in ./empty

Supported formats: .md, .txt, .pdf, .docx
Place documents in ./empty and try again

# Working directory not found for query
$ lightrag query "test" --working-dir ./missing
Error: Working directory not found: ./missing

Available graphs:
  - ./rag_storage (default)
  - ./contracts_rag
  - ./documents_rag

Use: lightrag query "test" --working-dir ./rag_storage
Or:  lightrag query "test" --list-graphs
```

### Progress Indicators

```bash
# Building graph
$ lightrag build
🔍 Scanning ./inputs... found 4 files

📋 Suggested order (please review):
  1. base-contract.pdf (detected: base document)
  2. amendment-q1.pdf (detected: 2024-Q1 date)
  3. amendment-q2.pdf (detected: 2024-Q2 date)
  4. update-2024.pdf (detected: 2024 date)

❓ Accept this order? [Y/n/edit]: Y

✓ Order confirmed:
  base-contract.pdf → v1
  amendment-q1.pdf → v2
  amendment-q2.pdf → v3
  update-2024.pdf → v4

🏗️  Building knowledge graph...
  [████████████████████████████████] 100% (4/4 files)

✅ Knowledge graph built successfully!
   - 4 documents ingested
   - 87 entities extracted
   - 156 relationships created
   - Working directory: ./rag_storage

Next: lightrag query "your question"
```

### Helpful Hints

```bash
# After successful build
Hint: Try 'lightrag query "What is the parking fee?"' to test your graph

# After query
Hint: Use 'lightrag interactive' for conversational querying

# When using old scripts
Note: You're using build_graph.py. Consider trying 'lightrag build' for a simpler experience.
```

## Migration from Old Scripts

### Compatibility Layer

Old scripts continue to work:
```bash
# Old way (still works)
python build_graph.py --input-dir ./docs
python query_graph.py --query "test" --mode temporal

# New way (recommended)
lightrag build --input ./docs
lightrag query "test" --mode temporal
```

### Migration Guide

```bash
# Old: build_graph.py
python build_graph.py --input-dir ./contracts --working-dir ./rag

# New: lightrag build
lightrag build --input ./contracts --working-dir ./rag

# Old: query_graph.py
python query_graph.py --query "What is the fee?" --mode temporal --date 2024-01-01

# New: lightrag query (temporal mode with date)
lightrag query "What is the fee?" --as-of 2024-01-01

# Old: query with different working directory
python query_graph.py --query "test" --working-dir ./contracts_rag

# New: query with different working directory
lightrag query "test" --working-dir ./contracts_rag

# Old: Interactive mode
python query_graph.py --interactive --mode temporal

# New: lightrag interactive
lightrag interactive --mode temporal
```

## Implementation Notes

### Module Structure

```
lightrag/
├── cli/
│   ├── __init__.py          # Main CLI entry point with argument parsing
│   ├── build.py             # Build subcommand implementation
│   ├── query.py             # Query subcommand implementation
│   ├── interactive.py       # Interactive mode implementation
│   ├── info.py              # Info subcommand implementation
│   ├── config.py            # Config management implementation
│   └── utils.py             # Shared utilities (auto-detection, formatting, etc.)
```

### Key Components

1. **Auto-Detection Logic** ([`cli/utils.py`](../lightrag/cli/utils.py))
   - Working directory detection
   - Input directory detection
   - File sequencing algorithms
   - Date extraction from filenames

2. **Configuration Management** ([`cli/config.py`](../lightrag/cli/config.py))
   - Load/save configuration
   - Environment variable handling
   - Default value resolution
   - Validation

3. **Progress Reporting** ([`cli/utils.py`](../lightrag/cli/utils.py))
   - Progress bars
   - Status indicators
   - Timing information
   - Error formatting

4. **Interactive Shell** ([`cli/interactive.py`](../lightrag/cli/interactive.py))
   - Command parsing
   - History management
   - Tab completion
   - Context switching

### Dependencies

New dependencies needed:
- `click` or `typer` - Modern CLI framework (recommend `typer` for type safety)
- `rich` - Beautiful terminal output (progress bars, tables, formatting)
- `prompt_toolkit` - Interactive shell features (history, completion)

### Entry Point Registration

Update [`pyproject.toml`](../pyproject.toml):

```toml
[project.scripts]
lightrag = "lightrag.cli:main"
lightrag-server = "lightrag.api.lightrag_server:main"
lightrag-gunicorn = "lightrag.api.run_with_gunicorn:main"
```

## Testing Strategy

### Unit Tests

```python
# Test auto-detection
def test_detect_working_dir()
def test_detect_input_dir()
def test_auto_sequence_files()

# Test command parsing
def test_build_command_parsing()
def test_query_command_parsing()

# Test configuration
def test_config_load_save()
def test_config_validation()
```

### Integration Tests

```bash
# Test complete workflows
test_build_and_query_workflow()
test_interactive_session()
test_config_management()
```

### User Acceptance Tests

```bash
# Test common user scenarios
test_first_time_user_experience()
test_advanced_user_workflow()
test_error_recovery()
```

## Documentation Updates

Files to update:
1. [`README.md`](../README.md) - Add CLI quick start
2. [`docs/GETTING_STARTED.md`](GETTING_STARTED.md) - Update with new CLI examples
3. [`docs/USER_GUIDE.md`](USER_GUIDE.md) - Add CLI reference section
4. Create [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) - Comprehensive CLI documentation
5. Create [`docs/MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) - Migration from old scripts

## Rollout Plan

### Phase 1: Core Implementation
- Implement main CLI entry point
- Implement build and query subcommands
- Add basic auto-detection
- Update pyproject.toml

### Phase 2: Enhanced Features
- Implement interactive mode
- Add info and config subcommands
- Enhance auto-detection logic
- Add progress indicators

### Phase 3: Polish & Documentation
- Comprehensive error handling
- Rich terminal output
- Complete documentation
- Migration guide

### Phase 4: Testing & Release
- Unit and integration tests
- User acceptance testing
- Beta release for feedback
- Final release

## Open Questions for Review

1. **CLI Framework**: Should we use `click`, `typer`, or `argparse`?
   - `typer` recommended for type safety and modern features
   - `click` is more mature and widely used
   - `argparse` is stdlib but less feature-rich

2. **Auto-Sequencing**: Should auto-sequencing be enabled by default?
   - Pro: Simplifies common case
   - Con: May surprise users who expect manual control
   - Proposal: Default to auto, allow `--no-auto-sequence` override

3. **Backward Compatibility**: Should we deprecate old scripts?
   - Proposal: Keep them for 2-3 releases with deprecation warnings
   - Eventually remove or make them thin wrappers around new CLI

4. **Configuration File**: Should we use `.lightrag/config` or `.env`?
   - Proposal: Support both, with `.lightrag/config` taking precedence
   - `.env` for environment-specific settings
   - `.lightrag/config` for project-specific settings

5. **Interactive Mode**: Should we use `prompt_toolkit` or simpler `input()`?
   - `prompt_toolkit` provides better UX (history, completion)
   - But adds dependency
   - Proposal: Use `prompt_toolkit` if available, fallback to `input()`

## Next Steps

Please review this design and provide feedback on:
1. Command structure and naming
2. Options and flags
3. Auto-detection behavior
4. Error handling approach
5. Any missing features or use cases

Once approved, we'll proceed with implementation following the rollout plan.