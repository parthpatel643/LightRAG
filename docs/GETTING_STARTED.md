# LightRAG Getting Started Guide

## Quick Overview

LightRAG is a temporal Retrieval-Augmented Generation system that maintains version history of entities across document revisions. It enables time-aware queries, automatic versioning, and chronologically accurate information retrieval.

### What Can You Do?

- **Upload Documents** → System automatically sequences and versions them
- **Query with Dates** → Retrieve information as it existed at any point in time
- **Track Changes** → See how entities evolved across document revisions
- **Audit Compliance** → Verify rules and rates effective at specific dates

---

## Installation

### Prerequisites
- Python 3.8+
- Bun (for frontend development)
- Docker (optional, for containerized deployment)

### Quick Install (End Users)

```bash
# Install from PyPI with API server
pip install lightrag-hku[api]

# Start the API server
lightrag-server
# Server runs at http://localhost:9621
```

### Development Install

```bash
# Clone repository
git clone https://github.com/HKUDS/LightRAG.git
cd LightRAG

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e ".[api]"

# Build frontend (optional, for development)
cd lightrag_webui
bun install --frozen-lockfile
bun run dev
# Frontend runs at http://localhost:5173
```

---

## Five-Minute Setup

### Step 1: Prepare Your Documents

Organize your documents in chronological order:
```
documents/
├── base_contract.pdf        # Original document
├── amendment_2024_q2.pdf    # First revision
└── amendment_2024_q4.pdf    # Latest revision
```

### Step 2: Configure Environment

Create `.env` file:
```bash
# LLM Configuration
LLM_BINDING=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key_here

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small

# Server Configuration
HOST=0.0.0.0
PORT=9621
```

### Step 3: Start LightRAG

**Option A: Web Interface**
```bash
# Terminal 1: Start API
lightrag-server

# Terminal 2: Start Frontend (development)
cd lightrag_webui
bun run dev

# Open http://localhost:5173
```

**Option B: Command Line**
```bash
# Query directly
python query_graph.py \
  --query "What are the current rates?" \
  --mode temporal \
  --date 2025-01-01
```

### Step 4: Upload Documents

**Via Web UI:**
1. Open http://localhost:5173
2. Go to "Documents" tab
3. Click "Staging Area"
4. Drag and drop PDFs
5. Reorder chronologically (earliest first)
6. Click "Upload All"

**Via API:**
```bash
curl -X POST "http://localhost:9621/upload" \
  -F "file=@base_contract.pdf" \
  -F "sequence_index=1" \
  -F "effective_date=2023-01-01"
```

**Via Python:**
```python
from lightrag import LightRAG, QueryParam

rag = LightRAG(working_dir="./rag_storage")
await rag.initialize_storages()

# Insert document with metadata
await rag.ainsert(
    input=document_content,
    metadata={
        "sequence_index": 1,
        "effective_date": "2023-01-01",
        "doc_type": "base"
    }
)
```

### Step 5: Run Your First Query

**Via Web UI:**
1. Go to "Query" tab
2. Select mode: "Temporal"
3. Set reference date (e.g., 2024-06-01)
4. Type your question
5. View results with citations

**Via API:**
```bash
curl -X POST "http://localhost:9621/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the parking fee?",
    "mode": "temporal",
    "reference_date": "2024-06-01"
  }'
```

**Via Python:**
```python
result = await rag.aquery(
    "What is the parking fee?",
    param=QueryParam(
        mode="temporal",
        reference_date="2024-06-01"
    )
)
print(result)
```

---

## Common Tasks

### Upload Multiple Versioned Documents

**Web UI (Recommended):**
1. Click "Staging Area" in Documents tab
2. Add files (order = sequence)
3. Set effective dates for each
4. Sequence numbers auto-assign (1, 2, 3...)
5. Upload

**CLI:**
```bash
python build_graph.py \
  --input-dir ./contracts \
  --mode temporal
```

### Query Historical Information

```python
# Query as of specific date
result = await rag.aquery(
    "What was the fee in Q1 2024?",
    param=QueryParam(
        mode="temporal",
        reference_date="2024-03-31"  # Q1 2024
    )
)
```

### Compare Versions

```python
result = await rag.aquery(
    "How did the fee change over time?",
    param=QueryParam(
        mode="temporal",
        reference_date="2025-01-01"  # Latest version
    )
)
```

### View System Statistics

```bash
python query_graph.py --stats
```

Example output:
```
Total Entities: 87
Versioned Entities: 23
Sequence Range: 1-4
Effective Date Range: 2023-01-01 to 2025-12-31
```

### Performance Profiling

Monitor LightRAG performance during ingestion and querying:

**Query with timing breakdown:**
```bash
python query_graph.py --query "Your question" --timing
```

**Profile with detailed statistics:**
```bash
python query_graph.py --query "Your question" --profile
```

**Profile ingestion:**
```bash
python build_graph.py --profile --timing
```

For detailed profiling workflows, see [PROFILING_GUIDE.md](PROFILING_GUIDE.md) and [PROFILING_QUICK_REFERENCE.md](PROFILING_QUICK_REFERENCE.md).

---

## Testing Your Installation

```bash
# Test data sequencing
uv run test_prep.py

# Test entity versioning
uv run test_ingest.py

# Test temporal queries
uv run test_temporal.py

# Test complete workflow
uv run demo_temporal_rag.py
```

All tests should pass with ✅ indicators.

---

## Next Steps

After getting started:

1. **Learn the System** → Read [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Master Queries** → See [RETRIEVAL_LOGIC.md](RETRIEVAL_LOGIC.md)
3. **Explore API** → Check [API_REFERENCE.md](API_REFERENCE.md)
4. **Deploy Production** → See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
5. **Advanced Topics** → Review [ADVANCED_GUIDE.md](ADVANCED_GUIDE.md)

---

## Troubleshooting

### "Module not found" error
```bash
# Reinstall dependencies
pip install -e ".[api]"
```

### Versioned entities not being created
- Check `sequence_index > 0` in metadata
- Verify LLM is following versioning prompt
- See [ARCHITECTURE.md - Versioned Entity Extraction](ARCHITECTURE.md#2-versioned-entity-extraction)

### Temporal queries returning unexpected results
- Confirm `reference_date` format is YYYY-MM-DD
- Check `<EFFECTIVE_DATE>` tags in content
- See [RETRIEVAL_LOGIC.md - Edge Cases](RETRIEVAL_LOGIC.md#handling-edge-cases)

### Docker container won't start
```bash
# Check configuration
cat .env

# Rebuild
docker-compose down
docker-compose up --build
```

---

## Getting Help

- **Concepts** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **How-To** → [USER_GUIDE.md](USER_GUIDE.md)
- **API** → [API_REFERENCE.md](API_REFERENCE.md)
- **Deployment** → [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Main Repo** → [GitHub](https://github.com/HKUDS/LightRAG)

---

**Ready to get started? Run:** `lightrag-server`
