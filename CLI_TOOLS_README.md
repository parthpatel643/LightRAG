# Temporal RAG CLI Tools

Two command-line scripts for building and querying temporal knowledge graphs with LightRAG.

## Scripts Overview

### 1. `build_graph.py` - Data Ingestion

Ingests versioned documents into LightRAG, creating a temporal knowledge graph with version-aware entity extraction.

**Key Features:**
- Automatic sequence assignment based on file order
- Optional ContractSequencer integration for metadata extraction
- Date extraction from filenames or content
- Document type inference
- Batch processing of directories

### 2. `query_graph.py` - Query Interface

Query the knowledge graph with support for temporal mode, enabling chronologically accurate retrieval.

**Key Features:**
- Multiple query modes (local, global, hybrid, temporal, etc.)
- Reference date support for temporal queries
- Interactive query mode for exploration
- Streaming response support
- Command-line or interactive usage

---

## Installation & Setup

### Prerequisites
```bash
# Ensure LightRAG is installed
pip install -e .

# Set environment variables
export OPENAI_API_KEY="your-api-key-here"
export LIGHTRAG_LLM_MODEL="gpt-4o-mini"
```

### Verify Installation
```bash
# Both scripts should be executable
python build_graph.py --help
python query_graph.py --help
```

---

## Usage Examples

### Basic Workflow

#### Step 1: Ingest Documents
```bash
# Ingest all markdown files in a directory
python build_graph.py --input-dir ./test_temporal_ingest

# Ingest specific files in order
python build_graph.py --files Base_Contract.md Amendment_1.md
```

#### Step 2: Query the Graph
```bash
# Query with temporal mode (historical state)
python query_graph.py --query "What is the service fee?" --mode temporal --date 2023-06-01

# Query with temporal mode (current state)
python query_graph.py --query "What is the service fee?" --mode temporal --date 2024-06-01

# Compare results to see version differences!
```

---

## Detailed Usage

### build_graph.py

#### Ingest Directory (Auto-Sequence)
```bash
# Process all .md and .txt files in directory
python build_graph.py --input-dir ./contracts --working-dir ./rag_storage
```

Files are automatically sequenced based on alphabetical order. The script:
- Assigns `sequence_index` = 1, 2, 3...
- Extracts effective dates from filenames (e.g., `Contract_2023-01-01.md`)
- Infers document types (base, amendment, supplement, etc.)

#### Ingest Specific Files
```bash
# Specify exact order
python build_graph.py --files Base.md Amend1.md Amend2.md --working-dir ./rag_storage
```

#### Use ContractSequencer (Advanced)
```bash
# Automatic metadata extraction from content
python build_graph.py --input-dir ./contracts --use-sequencer
```

Requires `data_prep.py` with ContractSequencer class.

#### Options
```
--input-dir DIR         Directory containing documents
--files FILE [FILE...]  Specific files to ingest (in order)
--working-dir DIR       LightRAG working directory (default: ./rag_storage)
--use-sequencer         Use ContractSequencer for metadata extraction
--no-sequence           Disable automatic sequence assignment
--model MODEL           LLM model: gpt-4o-mini (default) or gpt-4o
```

---

### query_graph.py

#### Single Query (Temporal Mode)
```bash
# Query as of specific date
python query_graph.py \
  --query "What are the monthly costs?" \
  --mode temporal \
  --date 2023-06-01 \
  --working-dir ./rag_storage
```

#### Interactive Mode
```bash
# Start interactive session
python query_graph.py --interactive --mode temporal --date 2024-01-01
```

**Interactive Commands:**
```
/mode <mode>       - Change query mode (local, global, hybrid, temporal, etc.)
/date <YYYY-MM-DD> - Set reference date for temporal mode
/help              - Show help
/quit or /exit     - Exit
```

**Example Session:**
```
[temporal] Query: What is the parking fee?
Response: The parking fee is $120 per space with 75 spaces allocated...

[temporal] Query: /date 2023-06-01
✓ Reference date set to: 2023-06-01

[temporal] Query: What is the parking fee?
Response: The parking fee is $100 per space with 50 spaces allocated...
```

#### Hybrid Mode (No Temporal Filtering)
```bash
# Returns information from all versions
python query_graph.py --query "What are all the service fees mentioned?" --mode hybrid
```

#### Stream Response
```bash
# Stream output token by token
python query_graph.py \
  --query "Summarize the contract" \
  --mode temporal \
  --date 2024-06-01 \
  --stream
```

#### Options
```
--query TEXT          Query string
--mode MODE           Query mode: local, global, hybrid, temporal (default: hybrid)
--date YYYY-MM-DD     Reference date for temporal mode
--stream              Stream the response
--interactive         Enter interactive mode
--working-dir DIR     LightRAG working directory (default: ./rag_storage)
--model MODEL         LLM model: gpt-4o-mini (default) or gpt-4o
```

---

## Complete Example Workflow

### Setup Test Data
```bash
# Create test directory
mkdir -p test_temporal_ingest

# Create Base Contract (v1)
cat > test_temporal_ingest/Base_Contract.md << 'EOF'
# Commercial Lease Agreement
**Effective Date:** 2023-01-01

## Service Fee
Monthly service fee: **$1,000**

## Parking Fee
Parking: **$100** per space, **50 spaces** allocated
Total parking: $5,000/month
EOF

# Create Amendment (v2)
cat > test_temporal_ingest/Amendment_1.md << 'EOF'
# Amendment to Lease Agreement
**Effective Date:** 2024-01-01

## Changes
- Service fee increased to **$1,500**/month
- Parking increased to **75 spaces** at **$120**/space
- Total parking: $9,000/month
EOF
```

### Ingest Documents
```bash
python build_graph.py --input-dir ./test_temporal_ingest --working-dir ./demo_rag
```

Output:
```
Found 2 files in test_temporal_ingest
Files to ingest (2):
  1. Amendment_1.md
  2. Base_Contract.md

Initializing LightRAG (working_dir: demo_rag)...
✅ LightRAG initialized

Ingesting: Amendment_1.md (sequence 1/2)
  Metadata: sequence=1, date=2024-01-01, type=amendment
Ingesting: Base_Contract.md (sequence 2/2)
  Metadata: sequence=2, date=2023-01-01, type=base

✅ All documents ingested successfully!
```

### Query Historical State (v1)
```bash
python query_graph.py \
  --query "What are the monthly costs for service and parking?" \
  --mode temporal \
  --date 2023-06-01 \
  --working-dir ./demo_rag
```

Expected Response:
```
The monthly costs are:
- Service fee: $1,000
- Parking: $5,000 (50 spaces at $100 each)
- Total: $6,000/month
```

### Query Current State (v2)
```bash
python query_graph.py \
  --query "What are the monthly costs for service and parking?" \
  --mode temporal \
  --date 2024-06-01 \
  --working-dir ./demo_rag
```

Expected Response:
```
The monthly costs are:
- Service fee: $1,500
- Parking: $9,000 (75 spaces at $120 each)
- Total: $10,500/month
```

### Query Evolution
```bash
python query_graph.py \
  --query "How did the monthly costs change over time?" \
  --mode temporal \
  --date 2024-06-01 \
  --working-dir ./demo_rag
```

Expected Response:
```
The monthly costs increased from $6,000 to $10,500:
- Service fee increased from $1,000 to $1,500 (+50%)
- Parking increased from $5,000 to $9,000 (+80%)
- Changes effective 2024-01-01
```

---

## Query Modes Explained

| Mode | Description | When to Use |
|------|-------------|-------------|
| **temporal** | Filters entities by reference date, returns version-specific data | Historical queries, compliance, audit trails |
| **hybrid** | Combines local + global retrieval (no temporal filtering) | General queries, may include multi-version data |
| **local** | Context-dependent local information | Specific detail queries |
| **global** | Global knowledge across documents | Broad summary queries |
| **naive** | Basic search without advanced techniques | Simple lookups |
| **mix** | Integrates knowledge graph + vector retrieval | Balanced retrieval |

---

## Tips & Best Practices

### File Naming for Auto-Sequencing
Include dates in filenames for automatic extraction:
```
Contract_2023-01-01.md
Amendment_2024-01-01.md
Supplement_2024-06-15.md
```

### Document Order Matters
When using `--files`, specify files in chronological order:
```bash
# ✅ Correct order
python build_graph.py --files Base.md Amend1.md Amend2.md

# ❌ Wrong order (will assign incorrect sequence)
python build_graph.py --files Amend2.md Base.md Amend1.md
```

### Temporal Mode Best Practices
- Use specific dates: `2023-06-01` not `2023-06`
- Date format must be `YYYY-MM-DD`
- Choose dates between version effective dates for testing
- Use boundary dates (exact effective dates) to verify filtering logic

### Interactive Mode Efficiency
- Start in temporal mode with a date
- Use `/mode` to switch modes and compare results
- Use `/date` to time-travel through versions
- Perfect for exploration and testing

---

## Troubleshooting

### "Working directory not found"
```bash
# Make sure you ran build_graph.py first
python build_graph.py --input-dir ./contracts
```

### "No .md or .txt files found"
```bash
# Check directory path
ls ./test_temporal_ingest

# Use absolute path if needed
python build_graph.py --input-dir /full/path/to/contracts
```

### "ImportError: data_prep.py not found"
```bash
# Don't use --use-sequencer flag, or ensure data_prep.py exists
python build_graph.py --input-dir ./contracts  # Without --use-sequencer
```

### Temporal queries return unexpected versions
- Verify effective dates in documents
- Check sequence indices assigned during ingestion
- Use `--date` exactly as `YYYY-MM-DD`
- Review entity names in knowledge graph (should have `[v1]`, `[v2]` suffixes)

---

## Advanced Usage

### Custom Working Directory
```bash
# Use separate graphs for different projects
python build_graph.py --input-dir ./project_a --working-dir ./rag_project_a
python build_graph.py --input-dir ./project_b --working-dir ./rag_project_b

python query_graph.py --query "..." --working-dir ./rag_project_a
```

### Different LLM Models
```bash
# Use GPT-4o for better quality (slower, more expensive)
python build_graph.py --input-dir ./contracts --model gpt-4o
python query_graph.py --query "..." --model gpt-4o
```

### Combine with Other Tools
```bash
# Export results
python query_graph.py --query "Summarize contract" --mode temporal --date 2024-01-01 > summary.txt

# Pipe to other scripts
python query_graph.py --interactive | tee query_session.log
```

---

## Related Files

- `build_graph.py` - Data ingestion script (this file)
- `query_graph.py` - Query interface script
- `data_prep.py` - ContractSequencer for metadata extraction (optional)
- `test_temporal.py` - Automated test suite for temporal mode
- `PROGRESS.md` - Development progress and architecture notes
- `SPRINT4_TEST_PLAN.md` - Comprehensive testing guide

---

## See Also

- [PROGRESS.md](PROGRESS.md) - Full system documentation
- [SPRINT4_SUMMARY.md](SPRINT4_SUMMARY.md) - Sprint 4 implementation details
- [SPRINT4_TEST_PLAN.md](SPRINT4_TEST_PLAN.md) - Testing strategies

---

**Quick Start:**
```bash
# 1. Ingest
python build_graph.py --input-dir ./test_temporal_ingest

# 2. Query
python query_graph.py --interactive --mode temporal

# 3. Explore!
```
