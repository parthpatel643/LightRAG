# 🔬 LightRAG RAGAS Evaluation Framework

This evaluation framework provides comprehensive RAG quality assessment using RAGAS metrics, with full support for **temporal queries** and **workspace-specific evaluation**.

## 🌟 Key Features

- **Temporal Mode Evaluation**: Evaluate versioned entity queries with reference dates
- **Workspace Isolation**: Each workspace can have its own evaluation datasets and results
- **Standard RAGAS Metrics**: Faithfulness, Answer Relevancy, Context Recall, Context Precision
- **Temporal Metrics**: Version Accuracy, Temporal Precision, Sequence Consistency
- **Cross-Workspace Comparison**: Evaluate and compare results across multiple workspaces
- **Flexible CLI**: Command-line interface for all evaluation scenarios

## 📦 Installation

```bash
# Install evaluation dependencies
pip install -e ".[evaluation]"

# Or install specific packages
pip install ragas datasets langchain-openai
```

## 🚀 Quick Start

### 1. Configure Environment

Add to your `.env` file:

```bash
# Required: Evaluation LLM (uses same as LightRAG if not set)
EVAL_LLM_MODEL=gpt-4o-mini
EVAL_LLM_BINDING_API_KEY=your_api_key

# Required: Evaluation Embeddings
EVAL_EMBEDDING_MODEL=text-embedding-3-large

# Optional: Temporal evaluation settings
EVAL_DEFAULT_REFERENCE_DATE=2024-01-01
EVAL_WORKSPACE=default

# Optional: Performance tuning
EVAL_MAX_CONCURRENT=2
EVAL_QUERY_TOP_K=10
```

### 2. Run Evaluation

```bash
# Standard evaluation (mix mode)
python -m lightrag.evaluation.eval_workspace

# Temporal evaluation
python -m lightrag.evaluation.eval_workspace --mode temporal

# Specific workspace
python -m lightrag.evaluation.eval_workspace --workspace my_project --mode temporal

# With reference date
python -m lightrag.evaluation.eval_workspace --mode temporal --reference-date 2024-01-15

# List available workspaces
python -m lightrag.evaluation.eval_workspace --list-workspaces

# Evaluate all workspaces
python -m lightrag.evaluation.eval_workspace --all-workspaces
```

## 📁 Directory Structure

```
lightrag/evaluation/
├── __init__.py                      # Package init with lazy imports
├── base_evaluator.py                # Base evaluator class with workspace support
├── temporal_evaluator.py            # Temporal-specific evaluation
├── eval_workspace.py                # Main CLI for workspace evaluation
├── eval_rag_quality.py              # Legacy standard evaluator
├── datasets/                        # Workspace-specific datasets
│   ├── default/
│   │   └── evaluation_dataset.json  # Default workspace dataset
│   ├── temporal/
│   │   └── evaluation_dataset.json  # Temporal evaluation dataset
│   └── {workspace_name}/            # Custom workspace datasets
│       └── evaluation_dataset.json
├── results/                         # Evaluation results
│   ├── default/
│   │   ├── results_20240115_103022.json
│   │   └── results_20240115_103022.csv
│   ├── {workspace_name}/
│   └── aggregate/                   # Cross-workspace aggregates
│       └── aggregate_temporal_20240115.json
└── README_TEMPORAL_EVALUATION.md    # This file
```

## 📊 Dataset Format

### Standard Dataset

```json
{
  "workspace": "my_workspace",
  "test_cases": [
    {
      "question": "What is the Boeing 787 TURN service rate?",
      "ground_truth": "$227.24 per event",
      "project": "aviation_contracts"
    }
  ]
}
```

### Temporal Dataset

```json
{
  "workspace": "contracts_2024",
  "evaluation_type": "temporal",
  "test_cases": [
    {
      "id": "tc_001",
      "question": "What is the current Boeing 787 TURN service rate?",
      "ground_truth": "The Boeing 787 TURN service rate is $227.24 per event.",
      "reference_date": "2024-01-15",
      "expected_version": 3,
      "metadata": {
        "category": "pricing",
        "entity_type": "service_rate"
      }
    }
  ]
}
```

## 📈 Metrics

### Standard RAGAS Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Faithfulness** | Is the answer factually accurate based on context? | > 0.80 |
| **Answer Relevancy** | Is the answer relevant to the question? | > 0.80 |
| **Context Recall** | Was all relevant information retrieved? | > 0.80 |
| **Context Precision** | Is retrieved context clean without noise? | > 0.80 |

### Temporal Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Version Accuracy** | Correct entity version retrieved? | > 0.95 |
| **Temporal Precision** | All entities valid for reference date? | > 0.90 |
| **Sequence Consistency** | Versions properly ordered by sequence? | > 0.95 |

## 🔧 Programmatic Usage

### Standard Evaluation

```python
import asyncio
from lightrag.evaluation import StandardRAGEvaluator

async def main():
    evaluator = StandardRAGEvaluator(
        workspace="my_workspace",
        query_mode="mix"
    )
    results = await evaluator.run()
    print(f"Average RAGAS Score: {results['benchmark_stats']['average_metrics']['ragas_score']}")

asyncio.run(main())
```

### Temporal Evaluation

```python
import asyncio
from lightrag.evaluation import TemporalRAGEvaluator

async def main():
    evaluator = TemporalRAGEvaluator(
        workspace="contracts_2024",
        default_reference_date="2024-01-15",
        track_versions=True
    )
    results = await evaluator.run()
    
    # Access temporal metrics
    temporal = results['benchmark_stats']['temporal_metrics']
    print(f"Version Accuracy: {temporal['avg_version_accuracy']}")

asyncio.run(main())
```

### Cross-Workspace Evaluation

```python
import asyncio
from lightrag.evaluation.temporal_evaluator import WorkspaceEvaluator

async def main():
    evaluator = WorkspaceEvaluator(
        workspaces=["workspace_a", "workspace_b"],
        mode="temporal"
    )
    all_results = await evaluator.evaluate_all_workspaces(
        reference_date="2024-01-15"
    )
    
    for workspace, results in all_results.items():
        score = results['benchmark_stats']['average_metrics']['ragas_score']
        print(f"{workspace}: {score}")

asyncio.run(main())
```

## 🎯 CLI Reference

### eval_workspace

```bash
python -m lightrag.evaluation.eval_workspace [OPTIONS]

Options:
  -w, --workspace TEXT        Workspace name (default: default)
  -m, --mode TEXT             Query mode: naive, local, global, hybrid, mix, temporal, bypass
  -d, --dataset TEXT          Custom dataset path
  -r, --ragendpoint TEXT      LightRAG API endpoint URL
  --reference-date TEXT       Reference date for temporal queries (YYYY-MM-DD)
  --all-workspaces            Evaluate all discovered workspaces
  --list-workspaces           List available workspaces and exit
  --help                      Show help message
```

### temporal_evaluator

```bash
python -m lightrag.evaluation.temporal_evaluator [OPTIONS]

Options:
  -w, --workspace TEXT        Workspace name (default: default)
  -d, --dataset TEXT          Custom dataset path
  -r, --ragendpoint TEXT      LightRAG API endpoint URL
  --reference-date TEXT       Reference date for temporal queries
  --all-workspaces            Evaluate all workspaces with temporal mode
```

## 📋 Creating Custom Datasets

1. Create a workspace directory:
   ```bash
   mkdir -p lightrag/evaluation/datasets/my_workspace
   ```

2. Create `evaluation_dataset.json`:
   ```json
   {
     "workspace": "my_workspace",
     "evaluation_type": "temporal",
     "description": "My custom evaluation dataset",
     "test_cases": [
       {
         "question": "Your test question?",
         "ground_truth": "Expected answer",
         "reference_date": "2024-01-01",
         "expected_version": 1
       }
     ]
   }
   ```

3. Run evaluation:
   ```bash
   python -m lightrag.evaluation.eval_workspace -w my_workspace -m temporal
   ```

## 🔍 Troubleshooting

### RAGAS Dependencies Not Found

```bash
pip install -e ".[evaluation]"
```

### LightRAG API Connection Error

Ensure LightRAG server is running:
```bash
lightrag-server
# or
uvicorn lightrag.api.lightrag_server:app --reload
```

### No Test Cases Found

Check that your dataset file exists and has valid JSON:
```bash
python -c "import json; json.load(open('lightrag/evaluation/datasets/my_workspace/evaluation_dataset.json'))"
```

## 📚 Related Documentation

- [TEMPORAL_API_REFERENCE.md](../../docs/TEMPORAL_API_REFERENCE.md) - Temporal API documentation
- [TEMPORAL_RAGAS_EVALUATION.md](../../docs/TEMPORAL_RAGAS_EVALUATION.md) - Detailed evaluation design
- [EVALUATION_SETUP.md](../../docs/EVALUATION_SETUP.md) - General evaluation setup
