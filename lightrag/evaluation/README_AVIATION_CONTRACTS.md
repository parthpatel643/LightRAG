# RAGAS Evaluation Datasets

This directory contains RAGAS evaluation datasets for testing aviation service contract RAG queries.

## Dataset Files

### 1. `sample_dataset.json` (8 questions)
Contains questions with confirmed ground truth answers. Ready for immediate evaluation.

**Categories:**
- SEA Cabin Cleaning (7 questions)
- SEA VBC & Wheelchair (1 question)

**All questions have validated answers.**

### 2. `aviation_contracts_complete.json` (24 questions)
Contains all questions including those pending ground truth answers.

**Categories:**
- SEA Cabin Cleaning (10 questions)
- SEA VBC & Wheelchair (2 questions)
- LGA Cabin Cleaning (4 questions)
- YYZ Ground Handling (3 questions)
- YYZ Security Handling (3 questions)
- YYZ Wheelchair (2 questions)

**Note:** Questions marked with `"PENDING - Answer not provided in source document"` need ground truth answers to be updated before evaluation.

### 3. `sample_dataset_lightrag_demo.json` (6 questions)
Original demo questions about LightRAG framework. Requires indexing files from `sample_documents/` folder.

## How to Use

### Step 1: Prepare Your LightRAG Instance

Make sure you have indexed the relevant aviation service contract documents into LightRAG:

```bash
# Example: Index your documents
python build_graph.py --input ./inputs/aviation_contracts
```

### Step 2: Start the LightRAG API Server

```bash
# Make sure you have the API dependencies installed
pip install -e ".[api]"

# Start the server
lightrag-server
# Or for development:
uvicorn lightrag.api.lightrag_server:app --reload --port 9621
```

### Step 3: Run RAGAS Evaluation

#### Option A: Using the ready dataset (8 questions)

```bash
python lightrag/evaluation/eval_rag_quality.py \
  --dataset lightrag/evaluation/sample_dataset.json \
  --ragendpoint http://localhost:9621

# Or simply (uses sample_dataset.json by default):
python lightrag/evaluation/eval_rag_quality.py
```

#### Option B: Using the complete dataset (24 questions)

**First, update the ground truth answers in `aviation_contracts_complete.json` for questions marked as PENDING.**

Then run:

```bash
python lightrag/evaluation/eval_rag_quality.py \
  --dataset lightrag/evaluation/aviation_contracts_complete.json \
  --ragendpoint http://localhost:9621
```

### Step 4: View Results

Results are automatically saved to `lightrag/evaluation/results/`:

```
results/
├── results_YYYYMMDD_HHMMSS.json     # Detailed metrics
└── results_YYYYMMDD_HHMMSS.csv      # CSV for spreadsheet analysis
```

## Understanding RAGAS Metrics

| Metric | What It Measures | Target Score |
|--------|------------------|--------------|
| **Faithfulness** | Is the answer factually accurate based on retrieved context? | > 0.80 |
| **Answer Relevance** | Is the answer relevant to the user's question? | > 0.80 |
| **Context Recall** | Was all relevant information retrieved from documents? | > 0.80 |
| **Context Precision** | Is retrieved context clean without irrelevant noise? | > 0.80 |
| **Overall RAGAS Score** | Average of all metrics | > 0.80 |

## Quick Reference

**Minimal command (uses default sample_dataset.json):**
```bash
python lightrag/evaluation/eval_rag_quality.py
```

**With specific dataset:**
```bash
python lightrag/evaluation/eval_rag_quality.py \
  -d lightrag/evaluation/aviation_contracts_complete.json
```

**With custom endpoint:**
```bash
python lightrag/evaluation/eval_rag_quality.py \
  -d lightrag/evaluation/sample_dataset.json \
  -r http://localhost:9621
```

**Help:**
```bash
python lightrag/evaluation/eval_rag_quality.py --help
```

## Environment Configuration

Make sure your `.env` file has the necessary RAGAS evaluation settings:

```bash
# RAGAS evaluation models
EVAL_LLM_BINDING=openai
EVAL_LLM_MODEL=gpt-4o-mini
EVAL_EMBED_MODEL=text-embedding-3-small

# Or use custom OpenAI-compatible endpoint
# EVAL_LLM_BINDING_HOST=http://localhost:8000/v1
```

## Updating Ground Truth Answers

To update pending answers in `aviation_contracts_complete.json`:

1. Open the file: `lightrag/evaluation/aviation_contracts_complete.json`
2. Find questions with `"PENDING - Answer not provided in source document"`
3. Replace with the correct ground truth answer from your source documents
4. Save and re-run evaluation

Example:
```json
{
  "question": "What are the latest discount rates applicable to United?",
  "ground_truth": "10% discount for bookings over 1000 wheelchairs per quarter",
  "project": "sea_vbc_wheelchair"
}
```

## Troubleshooting

### RAGAS dependencies not installed
```bash
pip install ragas datasets langfuse
# Or:
pip install -e ".[evaluation]"
```

### API server not responding
Make sure the server is running:
```bash
curl http://localhost:9621/health
```

### Low scores
- Verify documents are properly indexed in LightRAG
- Check that ground truth answers match the source documents
- Try different query modes (hybrid, mix, etc.)
- Adjust retrieval parameters (top_k, chunk_top_k)

## Related Documentation

- [LightRAG Evaluation Framework](README_EVALUASTION_RAGAS.md)
- [API Reference](../../docs/API_REFERENCE.md)
- [Deployment Guide](../../docs/DEPLOYMENT_GUIDE.md)
