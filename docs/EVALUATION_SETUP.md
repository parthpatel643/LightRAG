# Aviation Contracts RAGAS Evaluation Setup Guide

This guide explains how to set up and run RAGAS evaluation for your aviation contracts questions using your custom Azure OpenAI configuration.

## 📋 Prerequisites

1. **LightRAG API Server Running**
   ```bash
   lightrag-server
   ```
   The API should be accessible at `http://localhost:9621` (or your configured endpoint)

2. **Documents Indexed**
   - Ensure your aviation contract documents are already indexed in LightRAG
   - Use the WebUI or API to upload and process documents

3. **Python Dependencies**
   ```bash
   pip install -e ".[evaluation]"
   ```
   This installs: `ragas`, `datasets`, `langchain-openai`

## ⚙️ Environment Configuration

### Step 1: Configure Evaluation LLM (Azure OpenAI)

Add these variables to your `.env` file:

```bash
############################
### Evaluation Configuration
############################

### LLM Configuration for RAGAS Evaluation
# Use your existing Azure OpenAI setup
EVAL_LLM_MODEL=gpt-4.1
EVAL_LLM_BINDING_API_KEY=dummy_key
EVAL_LLM_BINDING_HOST=https://eur-sdr-int-pub.nestle.com/api/dv-exp-accelerator-openai-api/1/

### Embedding Configuration for RAGAS Evaluation
# Can use same or different endpoint
EVAL_EMBEDDING_MODEL=text-embedding-3-large
EVAL_EMBEDDING_BINDING_API_KEY=dummy_key
EVAL_EMBEDDING_BINDING_HOST=https://mars-llm-proxy-dev.ual.com/v2/unified

### Performance Tuning
# Number of concurrent test case evaluations (lower = fewer API rate limit issues)
EVAL_MAX_CONCURRENT=2

# Number of entities/relations retrieved per query
EVAL_QUERY_TOP_K=10

# LLM request retry and timeout settings
EVAL_LLM_MAX_RETRIES=5
EVAL_LLM_TIMEOUT=180
```

### Step 2: Verify Configuration

The evaluation script will automatically use your Azure OpenAI configuration from `lightrag/functions.py` if `EVAL_*` variables are not set. However, it's recommended to set them explicitly for evaluation to:
- Use different models for evaluation vs. production
- Avoid rate limiting on production endpoints
- Track evaluation costs separately

## 🚀 Running Evaluation

### Option 1: Using Helper Script (Recommended)

```bash
# Use defaults (aviation_contracts_questions.json, http://localhost:9621)
./run_aviation_evaluation.sh

# Custom dataset
./run_aviation_evaluation.sh path/to/custom_questions.json

# Custom dataset and endpoint
./run_aviation_evaluation.sh path/to/custom_questions.json http://your-server:9621
```

### Option 2: Direct Python Execution

```bash
# Use defaults
python lightrag/evaluation/eval_aviation_contracts.py

# Custom dataset
python lightrag/evaluation/eval_aviation_contracts.py --dataset path/to/questions.json

# Custom endpoint
python lightrag/evaluation/eval_aviation_contracts.py --ragendpoint http://localhost:9621

# Both custom
python lightrag/evaluation/eval_aviation_contracts.py -d questions.json -r http://localhost:9621
```

## 📊 Understanding Results

### Output Files

Results are saved to `lightrag/evaluation/results/`:

```
results/
├── aviation_results_20260305_120000.json  # Full results with all metrics
└── aviation_results_20260305_120000.csv   # Spreadsheet-friendly format
```

### Metrics Explained

| Metric | Description | Good Score |
|--------|-------------|------------|
| **Faithfulness** | Is the answer factually accurate based on retrieved context? | > 0.80 |
| **Answer Relevance** | Is the answer relevant to the user's question? | > 0.80 |
| **Context Recall** | Was all relevant information retrieved from documents? | > 0.80 |
| **Context Precision** | Is retrieved context clean without irrelevant noise? | > 0.80 |
| **RAGAS Score** | Overall quality metric (average of above) | > 0.80 |

### Score Interpretation

- **0.80-1.00**: ✅ Excellent (Production-ready)
- **0.60-0.80**: ⚠️ Good (Room for improvement)
- **0.40-0.60**: ❌ Poor (Needs optimization)
- **0.00-0.40**: 🔴 Critical (Major issues)

### Sample Output

```
========================================
📊 EVALUATION RESULTS SUMMARY
========================================
#    | Question                                           |  Faith | AnswRel | CtxRec | CtxPrec |  RAGAS | Status
---------------------------------------------------------------------------------------------------
1    | What is the price per event for Boeing 787 TUR... | 0.9500 |  0.9200 | 0.9800 |  0.9100 | 0.9400 |      ✓
2    | What is the price per event for Boeing 787 RON... | 0.9300 |  0.9100 | 0.9700 |  0.9000 | 0.9275 |      ✓
...

========================================
📈 BENCHMARK RESULTS (Average)
========================================
Average Faithfulness:      0.9250
Average Answer Relevance:  0.9050
Average Context Recall:    0.9650
Average Context Precision: 0.9000
Average RAGAS Score:       0.9238
```

## 📝 Test Dataset Format

The evaluation uses `lightrag/evaluation/aviation_contracts_questions.json`:

```json
{
  "test_cases": [
    {
      "question": "What is the price per event for Boeing 787 TURN service?",
      "ground_truth": "$227.24",
      "project": "sea_cabin_cleaning"
    },
    {
      "question": "What is the incentive earned for TCI cabins?",
      "ground_truth": "PENDING - Answer not provided in source document",
      "project": "sea_cabin_cleaning"
    }
  ]
}
```

**Notes:**
- Questions with `"PENDING"` ground truth are skipped during evaluation
- 28 questions currently have pending ground truth answers
- 16 questions have validated ground truth answers

## 🔧 Troubleshooting

### Issue: "RAGAS dependencies not installed"

**Solution:**
```bash
pip install -e ".[evaluation]"
```

### Issue: "LightRAG API is not accessible"

**Solution:**
1. Start the LightRAG server:
   ```bash
   lightrag-server
   ```
2. Verify it's running:
   ```bash
   curl http://localhost:9621/health
   ```

### Issue: "No API key found for evaluation LLM"

**Solution:**
Set one of these environment variables in `.env`:
- `EVAL_LLM_BINDING_API_KEY` (recommended for evaluation)
- `LLM_BINDING_API_KEY` (fallback to production key)
- `OPENAI_API_KEY` (fallback to OpenAI official API)

### Issue: Rate Limiting / "LM returned 1 generations instead of 3"

**Solution:**
Reduce concurrency in `.env`:
```bash
EVAL_MAX_CONCURRENT=1  # Serial evaluation
EVAL_QUERY_TOP_K=5     # Fewer documents per query
```

### Issue: Context Precision returns NaN

**Cause:** Too many concurrent LLM calls or rate limiting

**Solution:**
1. Reduce `EVAL_MAX_CONCURRENT` to 1
2. Reduce `EVAL_QUERY_TOP_K` to 5
3. Increase `EVAL_LLM_MAX_RETRIES` to 10
4. Increase `EVAL_LLM_TIMEOUT` to 300

## 📈 Optimization Tips

### For Low Faithfulness Scores

1. **Improve Entity Extraction**
   - Review `ENTITY_TYPES` in `.env`
   - Increase `ENTITY_EXTRACT_MAX_GLEANING`

2. **Better Document Chunking**
   - Adjust `CHUNK_SIZE` (try 1500-2000)
   - Adjust `CHUNK_OVERLAP_SIZE` (try 150-200)

3. **Tune Retrieval**
   - Adjust `COSINE_THRESHOLD` (try 0.3-0.4)
   - Increase `TOP_K` (try 20-30)

### For Low Answer Relevance Scores

1. **Improve Prompt Engineering**
   - Review prompts in `lightrag/prompt.py`
   - Add domain-specific context

2. **Better Query Understanding**
   - Enable reranking: `RERANK_BY_DEFAULT=true`
   - Adjust `MIN_RERANK_SCORE`

### For Low Context Recall Scores

1. **Increase Retrieval Coverage**
   - Increase `TOP_K` to 30-40
   - Increase `CHUNK_TOP_K` to 30

2. **Improve Embedding Model**
   - Use larger embedding model
   - Increase `EMBEDDING_DIM`

### For Low Context Precision Scores

1. **Better Filtering**
   - Enable reranking
   - Increase `MIN_RERANK_SCORE` to 0.4-0.5

2. **Smaller, Focused Chunks**
   - Reduce `CHUNK_SIZE` to 1000-1500
   - Adjust `RELATED_CHUNK_NUMBER` to 3-5

## 🎯 Next Steps

1. **Run Initial Evaluation**
   ```bash
   ./run_aviation_evaluation.sh
   ```

2. **Review Results**
   - Check `lightrag/evaluation/results/` for detailed metrics
   - Identify low-scoring questions

3. **Update Pending Ground Truth**
   - Edit `aviation_contracts_questions.json`
   - Replace `"PENDING"` with actual answers from documents

4. **Iterate and Optimize**
   - Adjust configuration based on scores
   - Re-run evaluation to measure improvements

5. **Track Progress**
   - Keep historical results for comparison
   - Monitor score trends over time

## 📚 Additional Resources

- [RAGAS Documentation](https://docs.ragas.io/)
- [LightRAG Evaluation Guide](README_EVALUASTION_RAGAS.md)
- [Aviation Contracts Evaluation](README_AVIATION_CONTRACTS.md)
- [LightRAG API Reference](API_REFERENCE.md)

## 🤝 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review existing evaluation results
3. Consult the RAGAS documentation
4. Check LightRAG logs for errors