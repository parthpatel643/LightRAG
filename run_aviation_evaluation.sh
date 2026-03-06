#!/bin/bash
#
# Aviation Contracts RAGAS Evaluation Helper Script
#
# This script runs the RAGAS evaluation for aviation contract questions
# with proper environment configuration.
#
# Usage:
#   ./run_aviation_evaluation.sh                    # Use defaults
#   ./run_aviation_evaluation.sh custom_data.json   # Custom dataset
#   ./run_aviation_evaluation.sh custom_data.json http://localhost:9621  # Custom dataset and endpoint
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Aviation Contracts RAGAS Evaluation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Please create .env file with required configuration:${NC}"
    echo ""
    echo "  # LLM Configuration for Evaluation"
    echo "  EVAL_LLM_MODEL=gpt-4.1"
    echo "  EVAL_LLM_BINDING_API_KEY=your_api_key"
    echo "  EVAL_LLM_BINDING_HOST=https://your-endpoint.com/v1"
    echo ""
    echo "  # Embedding Configuration for Evaluation"
    echo "  EVAL_EMBEDDING_MODEL=text-embedding-3-large"
    echo "  EVAL_EMBEDDING_BINDING_API_KEY=your_api_key"
    echo "  EVAL_EMBEDDING_BINDING_HOST=https://your-endpoint.com/v1"
    echo ""
    echo "  # Performance Tuning"
    echo "  EVAL_MAX_CONCURRENT=2"
    echo "  EVAL_QUERY_TOP_K=10"
    echo "  EVAL_LLM_MAX_RETRIES=5"
    echo "  EVAL_LLM_TIMEOUT=180"
    echo ""
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    echo "Please install Python 3.10 or higher"
    exit 1
fi

# Check if required packages are installed
echo -e "${BLUE}Checking dependencies...${NC}"
if ! python3 -c "import ragas" 2>/dev/null; then
    echo -e "${YELLOW}RAGAS not installed. Installing evaluation dependencies...${NC}"
    pip install -e ".[evaluation]"
fi

# Check if LightRAG API is running
LIGHTRAG_API_URL="${2:-${LIGHTRAG_API_URL:-http://localhost:9621}}"
echo -e "${BLUE}Checking LightRAG API at ${LIGHTRAG_API_URL}...${NC}"

if curl -s -f "${LIGHTRAG_API_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ LightRAG API is running${NC}"
else
    echo -e "${RED}Error: LightRAG API is not accessible at ${LIGHTRAG_API_URL}${NC}"
    echo -e "${YELLOW}Please start the LightRAG server:${NC}"
    echo "  lightrag-server"
    echo ""
    echo -e "${YELLOW}Or specify a different endpoint:${NC}"
    echo "  ./run_aviation_evaluation.sh dataset.json http://your-server:9621"
    echo ""
    exit 1
fi

# Prepare arguments
DATASET="${1:-lightrag/evaluation/aviation_contracts_questions.json}"
ARGS=()

if [ -n "$DATASET" ]; then
    ARGS+=("--dataset" "$DATASET")
fi

if [ -n "$2" ]; then
    ARGS+=("--ragendpoint" "$2")
fi

# Run evaluation
echo ""
echo -e "${BLUE}Starting evaluation...${NC}"
echo -e "${BLUE}Dataset: ${DATASET}${NC}"
echo -e "${BLUE}Endpoint: ${LIGHTRAG_API_URL}${NC}"
echo ""

python3 lightrag/evaluation/eval_aviation_contracts.py "${ARGS[@]}"

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Evaluation completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Results saved to: lightrag/evaluation/results/${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Evaluation failed${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    exit 1
fi


