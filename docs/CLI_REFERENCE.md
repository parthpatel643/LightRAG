# LightRAG CLI Reference

Complete reference for the unified LightRAG command-line interface.

## Installation

```bash
# Install with CLI support
pip install -e .

# Or install from PyPI (when released)
pip install lightrag-hku
```

## Quick Start

```bash
# Initialize a new project
lightrag config init

# Build knowledge graph
lightrag build --files base.pdf amendment.pdf

# Query the graph
lightrag query "What is the parking fee?"

# Interactive mode
lightrag interactive
```

## Global Options

Available for all commands:

```bash
--working-dir PATH    # LightRAG working directory
--config FILE         # Load configuration from file
--verbose, -v         # Increase verbosity (-vv, -vvv)
--quiet, -q           # Suppress non-error output
--trace               # Enable MLflow tracing
--trace-name NAME     # Custom trace name
--help, -h            # Show help
--version             # Show version
```

## Commands

### `lightrag build`

Build knowledge graph from documents with interactive sequencing.

**Usage:**
```bash
lightrag build [OPTIONS]
```

**Options:**
```bash
--input DIR, -i DIR              # Input directory
--files FILE [FILE ...]          # Specific files (order = sequence)
--working-dir DIR, -w DIR        # Working directory
--suggest-order                  # Show suggested order
--chunk-size N                   # Chunk size in tokens (default: 2000)
--chunk-overlap N                # Chunk overlap (default: 200)
--profile                        # Enable profiling
--timing                         # Show timing breakdown
--force                          # Force rebuild
--dry-run                        # Preview without executing
--trace                          # Enable MLflow tracing
--trace-name NAME                # Custom trace name
```

**Examples:**
```bash
# Explicit file order (recommended)
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# Interactive with suggestions
lightrag build --input ./contracts

# With profiling
lightrag build --input ./docs --profile --timing

# Dry run
lightrag build --input ./docs --dry-run

# With MLflow tracing
lightrag build --files doc1.pdf doc2.pdf --trace --trace-name "ingestion-v1"
```

**Workflow:**
1. System scans for documents
2. Suggests order based on dates/versions/keywords
3. User reviews and confirms or modifies
4. Documents ingested sequentially with version numbers

### `lightrag query`

Query the knowledge graph with various modes.

**Usage:**
```bash
lightrag query [OPTIONS] "your question"
```

**Options:**
```bash
--query TEXT, -q TEXT            # Query string (required)
--mode MODE, -m MODE             # Query mode (default: hybrid)
--date DATE, -d DATE             # Reference date (YYYY-MM-DD)
--as-of DATE                     # Alias for --date
--latest                         # Use today's date (temporal mode)
--working-dir DIR, -w DIR        # Working directory
--list-graphs                    # List available graphs
--stream, -s                     # Stream response
--output FILE, -o FILE           # Save to file
--format FORMAT                  # Output format (text/json/markdown)
--profile                        # Enable profiling
--timing                         # Show timing breakdown
--no-cache                       # Disable cache
--trace                          # Enable MLflow tracing
--trace-name NAME                # Custom trace name
```

**Query Modes:**
- `local` - Single-hop graph traversal (fast)
- `global` - Multi-hop traversal (comprehensive)
- `hybrid` - Balanced combination (default)
- `temporal` - Time-aware with version filtering
- `naive` - Simple keyword matching
- `mix` - Mixed strategy
- `bypass` - Direct LLM query

**Examples:**
```bash
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

# Stream response
lightrag query "Explain the terms" --stream

# Save to file
lightrag query "List fees" --output fees.txt --format markdown

# With tracing
lightrag query "What changed?" --trace --trace-name "fee-comparison"
```

### `lightrag interactive`

Interactive query session for conversational querying.

**Usage:**
```bash
lightrag interactive [OPTIONS]
```

**Options:**
```bash
--mode MODE, -m MODE             # Default query mode
--date DATE, -d DATE             # Default reference date
--working-dir DIR, -w DIR        # Working directory
--trace                          # Enable MLflow tracing
--trace-name NAME                # Custom trace name
```

**Interactive Commands:**
```
/mode <mode>                     # Change query mode
/date <YYYY-MM-DD>               # Set reference date
/latest                          # Set date to today
/graph <dir>                     # Switch working directory
/graphs                          # List available graphs
/help                            # Show help
/quit, /exit                     # Exit
```

**Examples:**
```bash
# Start interactive mode
lightrag interactive

# With temporal mode
lightrag interactive --mode temporal --date 2024-01-01

# With specific graph
lightrag interactive --working-dir ./contracts_rag

# With tracing
lightrag interactive --trace --trace-name "analysis-session"
```

**Session Example:**
```
[hybrid] Query: What is the parking fee?
Response: The parking fee is $200 per night...

[hybrid] Query: /mode temporal
✓ Mode changed to: temporal

[temporal] Query: /date 2024-01-01
✓ Reference date set to: 2024-01-01

[temporal] Query: What was the parking fee?
Response: In January 2024, the parking fee was $150 per night...

[temporal] Query: /graph ./contracts_rag
✓ Switched to working directory: ./contracts_rag

[temporal] Query: /quit
Exiting interactive mode...
```

### `lightrag info`

Show knowledge graph statistics and information.

**Usage:**
```bash
lightrag info [OPTIONS]
```

**Options:**
```bash
--working-dir DIR, -w DIR        # Working directory
--detailed, -d                   # Show detailed statistics
--entities                       # Show entity statistics
--documents                      # Show document statistics
--format FORMAT                  # Output format (text/json/table)
```

**Examples:**
```bash
# Basic info
lightrag info

# Detailed statistics
lightrag info --detailed

# JSON output
lightrag info --format json

# Specific graph
lightrag info --working-dir ./contracts_rag
```

**Output:**
```
═══════════════════════════════════════════════════════
       Knowledge Graph Statistics
═══════════════════════════════════════════════════════

Working Directory    ./rag_storage
Total Documents      4
Total Entities       87
Total Relations      156
Storage Backend      JSON (default)

═══════════════════════════════════════════════════════
```

### `lightrag config`

Manage LightRAG configuration.

**Subcommands:**
```bash
lightrag config show             # Show current configuration
lightrag config set KEY VALUE    # Set configuration value
lightrag config get KEY          # Get configuration value
lightrag config list             # List available keys
lightrag config reset            # Reset to defaults
lightrag config validate         # Validate configuration
lightrag config init [DIR]       # Initialize new project
```

**Configuration Keys:**
- `working-dir` - Default working directory
- `input-dir` - Default input directory
- `default-mode` - Default query mode
- `chunk-size` - Default chunk size
- `chunk-overlap` - Default chunk overlap
- `llm-binding` - LLM provider
- `embedding-binding` - Embedding provider

**Examples:**
```bash
# Show configuration
lightrag config show

# Set working directory
lightrag config set working-dir ./my_rag

# Set default mode
lightrag config set default-mode temporal

# Initialize new project
lightrag config init ./my_project

# Validate configuration
lightrag config validate
```

## MLflow Tracing

Enable observability for LightRAG operations.

**Configuration:**
```bash
# Set tracking URI
export MLFLOW_TRACKING_URI=http://localhost:5000

# Or in .env
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=lightrag-production
```

**Usage:**
```bash
# Enable tracing globally
lightrag --trace build --input ./docs

# Enable per-command
lightrag build --trace --trace-name "ingestion-v1"
lightrag query "test" --trace --trace-name "fee-lookup"

# View traces
mlflow ui --port 5000
# Open http://localhost:5000
```

**Captured Metrics:**
- Document processing time
- Entity extraction stats
- Query execution time
- LLM call metrics
- Token usage
- Cache hit/miss rates

## Environment Variables

```bash
# LLM Configuration
LLM_BINDING=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small

# Directories
INPUT_DIR=./inputs
WORKING_DIR=./rag_storage
LIGHTRAG_WORKING_DIR=./rag_storage

# Chunking
CHUNK_SIZE=2000
CHUNK_OVERLAP_SIZE=200

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=lightrag
```

## Common Workflows

### First-Time Setup

```bash
# 1. Initialize project
lightrag config init ./my_project
cd my_project

# 2. Configure API keys in .env
nano .env

# 3. Add documents to inputs/
cp ~/documents/*.pdf ./inputs/

# 4. Build graph
lightrag build

# 5. Query
lightrag query "What is the main topic?"
```

### Multiple Knowledge Graphs

```bash
# Build separate graphs
lightrag build --files contract1.pdf --working-dir ./contract1_rag
lightrag build --files contract2.pdf --working-dir ./contract2_rag

# Query different graphs
lightrag query "What is the fee?" --working-dir ./contract1_rag
lightrag query "What is the fee?" --working-dir ./contract2_rag

# Or use interactive mode
lightrag interactive
[hybrid] Query: /graph ./contract2_rag
[hybrid] Query: What is the fee?
```

### Temporal Analysis

```bash
# Build with versioned documents
lightrag build --files base.pdf amendment-q1.pdf amendment-q2.pdf

# Query at different dates
lightrag query "What was the fee?" --as-of 2024-01-01
lightrag query "What was the fee?" --as-of 2024-06-01
lightrag query "What is the current fee?" --latest

# Interactive temporal analysis
lightrag interactive --mode temporal
[temporal] Query: /date 2024-01-01
[temporal] Query: What was the fee?
[temporal] Query: /date 2024-06-01
[temporal] Query: What was the fee?
```

### Production Deployment

```bash
# Enable tracing
export MLFLOW_TRACKING_URI=http://mlflow.example.com

# Build with profiling
lightrag build --input ./docs --profile --timing --trace

# Query with monitoring
lightrag query "test" --trace --trace-name "prod-query-$(date +%s)"

# Monitor in MLflow UI
mlflow ui --host 0.0.0.0 --port 5000
```

## Troubleshooting

### Working Directory Not Found

```bash
$ lightrag query "test"
Error: Working directory not found: ./rag_storage

# Solutions:
lightrag build                              # Create graph
lightrag query "test" --working-dir ./path  # Specify directory
lightrag query --list-graphs                # List available
```

### No Documents Found

```bash
$ lightrag build --input ./empty
Error: No documents found in ./empty

# Solutions:
# 1. Add documents to directory
cp ~/docs/*.pdf ./empty/

# 2. Check supported formats
# Supported: .md, .txt, .pdf, .docx
```

### Invalid Date Format

```bash
$ lightrag query "test" --date 2024/01/01
Error: Invalid date format: 2024/01/01

# Correct format: YYYY-MM-DD
lightrag query "test" --date 2024-01-01
```

## Tips & Best Practices

1. **Use Explicit File Order**: Specify files with `--files` for predictable sequencing
2. **Enable Tracing**: Use `--trace` for production monitoring
3. **Save Important Queries**: Use `--output` to save responses
4. **Interactive for Exploration**: Use interactive mode for iterative analysis
5. **Validate Configuration**: Run `lightrag config validate` after changes
6. **Check Statistics**: Use `lightrag info` to verify graph state
7. **Use Dry Run**: Test with `--dry-run` before actual ingestion

## See Also

- [Getting Started Guide](GETTING_STARTED.md)
- [User Guide](USER_GUIDE.md)
- [CLI Design Specification](CLI_DESIGN.md)
- [API Reference](API_REFERENCE.md)
- [Profiling Guide](PROFILING_GUIDE.md)

---

**Last Updated:** March 12, 2026