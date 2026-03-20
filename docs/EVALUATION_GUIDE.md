# 🔬 LightRAG Evaluation Guide

Comprehensive guide to evaluating RAG quality using RAGAS metrics with full support for **temporal queries** and **workspace-specific evaluation**.

**Status**: ✅ **Production-Ready**  
**Latest Update**: March 2026

---

## Overview

LightRAG's evaluation framework provides automated RAG quality assessment using industry-standard RAGAS metrics. The system supports both standard and temporal evaluation modes, with workspace isolation for testing different document collections.

### Key Features

- **Temporal Evaluation**: Test versioned entity queries with reference dates
- **Workspace Isolation**: Each workspace maintains separate datasets and results
- **Standard RAGAS Metrics**: Faithfulness, Answer Relevancy, Context Recall, Context Precision
- **Semantic Equivalence**: LLM-based answer comparison for nuanced evaluation
- **Unified Configuration**: Uses same models as main LightRAG system
- **Flexible CLI**: Command-line interface for all evaluation scenarios

---

## Quick Start

### 1. Installation

Install evaluation dependencies:

```bash
# Install with evaluation support
pip install -e ".[evaluation]"

# Or install specific packages
pip install ragas datasets langchain-openai
```

### 2. Configuration

The evaluation system now uses the same configuration as your main LightRAG system. Simply ensure your `.env` file contains:

```bash
# Main LightRAG Configuration (Required)
LIGHTRAG_API_URL=http://localhost:9621
LLM_MODEL=gpt-4o-mini
LLM_BINDING_API_KEY=your_openai_api_key
LLM_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_API_KEY=your_openai_api_key
EMBEDDING_BINDING_HOST=https://api.openai.com/v1

# Optional: Performance Tuning
EVAL_MAX_CONCURRENT=2
EVAL_QUERY_TOP_K=10
EVAL_LLM_MAX_RETRIES=5
EVAL_LLM_TIMEOUT=180
```

### 3. Run Your First Evaluation

```bash
# Start LightRAG API server
lightrag-server

# Run semantic equivalence evaluation on a workspace
python -m lightrag.evaluation.semantic_equivalence_evaluator --workspace my_workspace

# Run full RAGAS evaluation
python -m lightrag.evaluation.temporal_evaluator --workspace my_workspace --reference-date 2024-01-15
```

---

## Directory Structure

```
LightRAG/
├── evaluation/                      # Project-root evaluation folder
│   ├── datasets/                    # Test datasets by workspace
│   │   ├── workspace_a/
│   │   │   └── evaluation_dataset.json
│   │   ├── workspace_b/
│   │   │   └── evaluation_dataset.json
│   │   └── ...
│   └── results/                     # Evaluation results by workspace
│       ├── workspace_a/
│       │   ├── semantic_eval_*.json
│       │   └── semantic_eval_*.csv
│       └── workspace_b/
│           └── ...
└── lightrag/
    └── evaluation/                  # Evaluation scripts
        ├── base_evaluator.py        # Base RAGAS evaluator
        ├── semantic_equivalence_evaluator.py
        ├── temporal_evaluator.py    # Temporal-specific evaluation
        └── __init__.py
```

---

## Dataset Format

### Standard Dataset Structure

```json
{
  "test_cases": [
    {
      "id": "test_001",
      "question": "What is the Boeing 787 TURN service rate?",
      "ground_truth": "$227.24 per event",
      "reference_date": "2024-01-15",
      "workspace": "aviation_contracts",
      "metadata": {
        "category": "pricing",
        "entity_type": "service_rate",
        "aircraft_type": "boeing_787"
      }
    }
  ]
}
```

### Temporal Dataset Features

```json
{
  "test_cases": [
    {
      "id": "temporal_001",
      "question": "What was the cabin cleaning rate in Q1 2024?",
      "ground_truth": "The cabin cleaning rate was $25.25 per hour for cleaning agents.",
      "reference_date": "2024-03-31",
      "workspace": "sea_cabin_cleaning",
      "metadata": {
        "category": "pricing",
        "entity_type": "hourly_rate",
        "position_type": "cleaning_agent",
        "service_type": "cabin_cleaning"
      }
    }
  ]
}
```

---

## Evaluation Types

### 1. Semantic Equivalence Evaluation

Fast LLM-based evaluation comparing RAG answers to ground truth:

```bash
python -m lightrag.evaluation.semantic_equivalence_evaluator \
  --workspace my_workspace \
  --reference-date 2024-01-15
```

**Features:**
- Uses existing `llm_model_func` for consistency
- Generates semantic equivalence scores (0-10)
- Fast evaluation suitable for development cycles
- Outputs both JSON and CSV results

### 2. Full RAGAS Evaluation

Comprehensive evaluation using multiple RAGAS metrics:

```bash
python -m lightrag.evaluation.temporal_evaluator \
  --workspace my_workspace \
  --reference-date 2024-01-15
```

**Metrics Evaluated:**
- **Faithfulness**: Answer accuracy based on retrieved context
- **Answer Relevancy**: Answer relevance to the question
- **Context Recall**: Completeness of retrieved information
- **Context Precision**: Quality of retrieved context

### 3. Cross-Workspace Comparison

Evaluate multiple workspaces for comparative analysis:

```bash
# Evaluate all workspaces with temporal mode
python -m lightrag.evaluation.temporal_evaluator --all-workspaces --reference-date 2024-01-15
```

---

## Metrics Reference

### Standard RAGAS Metrics

| Metric | Description | Target Score | Interpretation |
|--------|-------------|--------------|----------------|
| **Faithfulness** | Answer accuracy vs. retrieved context | > 0.80 | Higher = more factually accurate |
| **Answer Relevancy** | Answer relevance to question | > 0.80 | Higher = more relevant response |
| **Context Recall** | Completeness of information retrieval | > 0.80 | Higher = less information missed |
| **Context Precision** | Signal-to-noise ratio in context | > 0.80 | Higher = cleaner, more focused context |

### Semantic Equivalence Scoring

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| **9-10** | Semantically identical | ✅ Excellent |
| **7-8** | Very similar, minor differences | ✅ Good |
| **5-6** | Partially correct, some issues | ⚠️ Review needed |
| **3-4** | Significant differences | ❌ Investigation required |
| **0-2** | Completely different/incorrect | ❌ Major issues |

---

## Programmatic Usage

### Semantic Equivalence Evaluator

```python
import asyncio
from lightrag.evaluation.semantic_equivalence_evaluator import SemanticEquivalenceEvaluator

async def run_semantic_eval():
    evaluator = SemanticEquivalenceEvaluator(
        workspace="my_workspace",
        default_reference_date="2024-01-15"
    )
    results = await evaluator.run()
    
    # Access results
    avg_score = results['aggregate_stats']['avg_semantic_score']
    print(f"Average Semantic Score: {avg_score:.2f}")
    
    return results

# Run evaluation
results = asyncio.run(run_semantic_eval())
```

### Temporal RAGAS Evaluator

```python
import asyncio
from lightrag.evaluation.temporal_evaluator import TemporalRAGEvaluator

async def run_temporal_eval():
    evaluator = TemporalRAGEvaluator(
        workspace="contracts_2024",
        default_reference_date="2024-01-15",
        track_versions=True
    )
    results = await evaluator.run()
    
    # Access RAGAS metrics
    ragas_score = results['benchmark_stats']['average_metrics']['ragas_score']
    faithfulness = results['benchmark_stats']['average_metrics']['faithfulness']
    
    print(f"RAGAS Score: {ragas_score:.3f}")
    print(f"Faithfulness: {faithfulness:.3f}")
    
    return results

# Run evaluation
results = asyncio.run(run_temporal_eval())
```

---

## Creating Custom Datasets

### 1. Create Dataset Directory

```bash
mkdir -p evaluation/datasets/my_custom_workspace
```

### 2. Create Evaluation Dataset

Create `evaluation/datasets/my_custom_workspace/evaluation_dataset.json`:

```json
{
  "test_cases": [
    {
      "id": "custom_001",
      "question": "What is the service fee?",
      "ground_truth": "The service fee is $50 per transaction.",
      "reference_date": "2024-01-01",
      "workspace": "my_custom_workspace",
      "metadata": {
        "category": "pricing",
        "entity_type": "transaction_fee"
      }
    }
  ]
}
```

### 3. Run Custom Evaluation

```bash
python -m lightrag.evaluation.semantic_equivalence_evaluator \
  --workspace my_custom_workspace \
  --reference-date 2024-01-01
```

---

## CLI Reference

### Semantic Equivalence Evaluator

```bash
python -m lightrag.evaluation.semantic_equivalence_evaluator [OPTIONS]

Options:
  -w, --workspace TEXT        Workspace name
  -d, --dataset TEXT          Custom dataset path
  -r, --rag-endpoint TEXT     LightRAG API endpoint URL
  --reference-date TEXT       Reference date for temporal queries (YYYY-MM-DD)
  --enable-rerank             Enable reranking in queries
  --help                      Show help message
```

### Temporal RAGAS Evaluator

```bash
python -m lightrag.evaluation.temporal_evaluator [OPTIONS]

Options:
  -w, --workspace TEXT        Workspace name
  -d, --dataset TEXT          Custom dataset path
  -r, --rag-endpoint TEXT     LightRAG API endpoint URL
  --reference-date TEXT       Reference date for temporal queries
  --track-versions            Enable version tracking in results
  --all-workspaces            Evaluate all available workspaces
  --help                      Show help message
```

---

## Best Practices

### Dataset Design

1. **Diverse Question Types**: Include factual, analytical, and comparative questions
2. **Temporal Coverage**: Test different reference dates for temporal workspaces
3. **Ground Truth Quality**: Ensure ground truth answers are accurate and complete
4. **Metadata Consistency**: Use consistent category and entity_type values

### Evaluation Strategy

1. **Start with Semantic Equivalence**: Fast feedback during development
2. **Regular RAGAS Evaluation**: Comprehensive assessment before releases
3. **Cross-Workspace Testing**: Compare performance across different document sets
4. **Temporal Validation**: Test with multiple reference dates for temporal accuracy

### Performance Optimization

1. **Concurrent Limits**: Use `EVAL_MAX_CONCURRENT=2` to balance speed vs. API limits
2. **Timeout Settings**: Adjust `EVAL_LLM_TIMEOUT` based on model response times
3. **Retry Configuration**: Set `EVAL_LLM_MAX_RETRIES` for reliable evaluation runs

---

## Troubleshooting

### Common Issues

**RAGAS Dependencies Not Found**
```bash
pip install -e ".[evaluation]"
```

**LightRAG API Connection Error**
```bash
# Ensure API server is running
lightrag-server

# Verify endpoint in .env
echo $LIGHTRAG_API_URL
```

**No Test Cases Found**
```bash
# Verify dataset file exists
ls evaluation/datasets/my_workspace/evaluation_dataset.json

# Validate JSON format
python -c "import json; json.load(open('evaluation/datasets/my_workspace/evaluation_dataset.json'))"
```

**Model Configuration Errors**
```bash
# Verify main LightRAG environment variables are set
echo $LLM_MODEL $LLM_BINDING_API_KEY $EMBEDDING_MODEL $EMBEDDING_API_KEY
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
export LOG_LEVEL=DEBUG
python -m lightrag.evaluation.semantic_equivalence_evaluator --workspace my_workspace
```

---

## Related Documentation

- [Temporal Features Guide](TEMPORAL.md) - Temporal query capabilities
- [Getting Started](GETTING_STARTED.md) - Initial setup and configuration
- [API Reference](CLI_REFERENCE.md) - Complete CLI and API documentation
- [Architecture Overview](ARCHITECTURE.md) - System architecture and design