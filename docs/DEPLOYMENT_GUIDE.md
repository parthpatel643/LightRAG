# LightRAG Deployment Guide

## Overview

This guide covers all deployment scenarios: local development, Docker, offline environments, and production setups.

---

## Quick Deployment Comparison

| Scenario | Best For | Setup Time | Complexity |
|----------|----------|-----------|-----------|
| **Local Development** | Testing, prototyping | 5 min | Low |
| **Docker** | Production, consistency | 10 min | Low |
| **Offline** | Restricted environments | 30 min | High |
| **Kubernetes** | Large scale | 1 hour | Very High |

---

## Local Development Setup

### Prerequisites

- Python 3.8+
- Bun (for frontend)
- 8GB RAM minimum
- 2GB disk space

### Installation

```bash
# Clone repository
git clone https://github.com/HKUDS/LightRAG.git
cd LightRAG

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode
pip install -e ".[api]"
```

### Configuration

Create `.env` file:

```bash
# LLM Configuration (OpenAI example)
LLM_BINDING=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_api_key

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small

# Server Configuration
HOST=0.0.0.0
PORT=9621

# Optional: Temporal Settings
LIGHTRAG_TEMPORAL_ENABLED=true
LIGHTRAG_SEQUENCE_FIRST=true
CHUNK_SIZE=2000
CHUNK_OVERLAP_SIZE=200
```

### Start Services

**Terminal 1: API Server**
```bash
lightrag-server
# Server runs at http://localhost:9621
```

**Terminal 2: Frontend (optional)**
```bash
cd lightrag_webui
bun install --frozen-lockfile
bun run dev
# Frontend runs at http://localhost:5173
```

### Verification

```bash
# Test API
curl http://localhost:9621/health

# Run tests
uv run test_prep.py
uv run demo_temporal_rag.py
```

---

## Docker Deployment

### Quick Start

```bash
# Clone and configure
git clone https://github.com/HKUDS/LightRAG.git
cd LightRAG

# Create .env file
cp .env.example .env
# Edit .env with your settings

# Start all services
docker-compose up -d

# Access services
# API: http://localhost:9621
# Frontend: http://localhost:3000
```

### Docker Services

```yaml
# docker-compose.yml includes:
# - lightrag-api (FastAPI backend)
# - lightrag-webui (React frontend)
# - lightrag-storage (Data persistence)
```

### Configuration

**Environment Variables in .env:**

```bash
# Server Configuration
HOST=0.0.0.0
PORT=9621

# LLM Configuration
LLM_BINDING=openai           # or ollama, anthropic, etc.
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small

# Storage Configuration
STORAGE_TYPE=networkx        # or neo4j, mongodb, etc.
RAG_STORAGE_DIR=/data/rag_storage

# Temporal Settings (optional)
LIGHTRAG_TEMPORAL_ENABLED=true
CHUNK_SIZE=2000
```

### Data Persistence

```bash
# Data stored in volumes
data/
├── rag_storage/    # Knowledge graphs
├── inputs/         # Upload location
└── outputs/        # Results

# Backup
docker-compose exec lightrag-api tar czf /backup/rag_backup.tar.gz /data

# Restore
docker-compose cp /backup/rag_backup.tar.gz lightrag-api:/
docker-compose exec lightrag-api tar xzf /rag_backup.tar.gz -C /
```

### Build Optimization

The Dockerfile uses BuildKit cache mounts for efficient rebuilds:

```bash
# Automatic cache management
# - Only downloads changed dependencies
# - Much faster rebuilds
# - No manual configuration needed

docker-compose build --no-cache  # Force full rebuild
docker-compose build              # Use cache
```

### Scaling

**For higher concurrency:**

```yaml
# docker-compose.yml
services:
  lightrag-api:
    environment:
      MAX_ASYNC: 8
      MAX_PARALLEL_INSERT: 4
```

**For multiple instances:**

```bash
# Start multiple API instances
docker-compose up -d --scale lightrag-api=3
# Use load balancer for routing
```

### Troubleshooting Docker

```bash
# Check logs
docker-compose logs lightrag-api

# Rebuild after changes
docker-compose down
docker-compose up --build

# Clean up
docker-compose down -v  # Remove volumes too
```

---

## Offline Deployment

### Challenge

Dynamic package installation fails without internet. Solution: Pre-install all dependencies.

### Three-Step Process

**Step 1: Download Packages (Online Machine)**

```bash
# Install offline extras
pip install lightrag-hku[offline]

# Download all packages
pip download lightrag-hku[offline] -d ./offline-packages

# Download tiktoken cache
lightrag-download-cache

# Create offline bundle
tar -czf lightrag-offline.tar.gz \
  ./offline-packages \
  ~/.tiktoken_cache
```

**Step 2: Transfer to Offline Machine**

```bash
# Copy offline bundle
scp lightrag-offline.tar.gz user@offline-server:/path/to/

# SSH to offline machine
ssh user@offline-server
```

**Step 3: Install Offline (Offline Machine)**

```bash
# Extract bundle
tar -xzf lightrag-offline.tar.gz

# Install packages
pip install --no-index \
  --find-links=./offline-packages \
  lightrag-hku[offline]

# Set up tiktoken cache
export TIKTOKEN_CACHE_DIR=~/.tiktoken_cache

# Verify installation
python -c "import lightrag; print('OK')"
```

### Dependency Groups

| Group | Contents | Use Case |
|-------|----------|----------|
| `api` | FastAPI + document processing | Basic server |
| `offline-storage` | DB drivers (Neo4j, MongoDB, etc.) | Storage backends |
| `offline-llm` | LLM providers (OpenAI, Anthropic, etc.) | LLM integrations |
| `offline` | All of above | Complete system |

### Verify Offline Installation

```bash
# Check all modules available
python -c "
import lightrag
import fastapi
import openai
print('✅ All dependencies installed')
"

# Test API without internet
lightrag-server
# Should start without errors
```

### Update in Offline Environment

To update in offline environment:

1. On online machine, download new packages
2. Transfer to offline machine
3. Reinstall: `pip install --no-index --find-links=...`

---

## LLM Backend Configuration

### OpenAI (Recommended)

```bash
# .env
LLM_BINDING=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

### Anthropic

```bash
# .env
LLM_BINDING=anthropic
LLM_MODEL=claude-opus-4
ANTHROPIC_API_KEY=...
```

### Ollama (Local LLM)

```bash
# Start Ollama
ollama pull mistral

# .env
LLM_BINDING=ollama
LLM_MODEL=mistral
LLM_BINDING_HOST=http://localhost:11434
```

### Azure OpenAI

```bash
# .env
LLM_BINDING=openai
LLM_MODEL=gpt-4
OPENAI_API_TYPE=azure
OPENAI_API_VERSION=2024-01-01
OPENAI_API_BASE=https://your-resource.openai.azure.com
OPENAI_API_KEY=...
```

---

## Storage Backend Configuration

### NetworkX (Default, In-Memory)

```bash
# .env
STORAGE_TYPE=networkx
# No additional configuration
```

### Neo4j (Graph Database)

```bash
# Start Neo4j (Docker)
docker run -e NEO4J_AUTH=neo4j/password -p 7687:7687 neo4j:latest

# .env
STORAGE_TYPE=neo4j
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### AWS Neptune (Managed Graph Database)

```bash
# Prerequisites:
# 1. Create Neptune cluster in AWS Console or via CloudFormation
# 2. Configure VPC security group to allow port 8182
# 3. Create IAM policy for Neptune access (if using IAM auth)
# 4. Ensure application can access Neptune VPC (VPN, Direct Connect, or EC2/Lambda in VPC)

# IAM Policy Example (attach to your EC2/Lambda role):
# {
#   "Version": "2012-10-17",
#   "Statement": [{
#     "Effect": "Allow",
#     "Action": "neptune-db:*",
#     "Resource": "arn:aws:neptune-db:region:account-id:cluster-id/*"
#   }]
# }

# .env
STORAGE_TYPE=neptune
NEPTUNE_ENDPOINT=your-cluster.region.neptune.amazonaws.com
NEPTUNE_PORT=8182
NEPTUNE_REGION=us-east-1
NEPTUNE_USE_IAM=true

# AWS Credentials (choose one):
# Option 1: AWS Profile
AWS_PROFILE=your-profile

# Option 2: Access Keys (not recommended for production)
# AWS_ACCESS_KEY_ID=your-key-id
# AWS_SECRET_ACCESS_KEY=your-secret-key

# Option 3: IAM Role (automatic for EC2, Lambda, ECS - recommended)

# Optional: OpenSearch integration for full-text search
# NEPTUNE_OPENSEARCH_ENDPOINT=https://search-domain.region.es.amazonaws.com

# Installation
pip install lightrag-hku[offline-storage]
```

**Important Neptune Notes:**
- Neptune clusters are VPC-only by default. Your application must have network access to the VPC.
- For local development, use AWS Client VPN or SSH tunnel through a bastion host.
- Neptune supports automatic backups and point-in-time recovery.
- IAM authentication is strongly recommended for production deployments.
- Neptune automatically scales read replicas based on load.

### MongoDB (Document Store)

```bash
# Start MongoDB (Docker)
docker run -p 27017:27017 mongo:latest

# .env
STORAGE_TYPE=mongodb
MONGODB_URI=mongodb://localhost:27017
```

### PostgreSQL

```bash
# Start PostgreSQL (Docker)
docker run -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:latest

# .env
STORAGE_TYPE=postgres
POSTGRES_URI=postgresql://user:password@localhost:5432/lightrag
```

---

## Production Deployment

### Recommended Architecture

```mermaid
graph TD
    Client["Client Applications"]
    LB["Load Balancer"]
    API1["API Pod 1"]
    API2["API Pod 2"]
    API3["API Pod 3"]
    Cache["Redis Cache"]
    DB["Neo4j/PostgreSQL"]
    
    Client --> LB
    LB --> API1
    LB --> API2
    LB --> API3
    API1 --> Cache
    API2 --> Cache
    API3 --> Cache
    Cache --> DB
```

### Environment Variables

```bash
# High availability
MAX_ASYNC=8
MAX_PARALLEL_INSERT=4

# Caching
CACHE_BACKEND=redis
REDIS_URL=redis://redis-server:6379

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
CORS_ORIGINS=https://yourdomain.com
API_KEY_REQUIRED=true
```

### Database Backup

```bash
# Neo4j backup
neo4j-admin backup --database=neo4j --to=/backups/neo4j

# PostgreSQL backup
pg_dump -U user lightrag > backup.sql

# Restore
psql -U user lightrag < backup.sql
```

### Monitoring

```bash
# Health check endpoint
curl http://localhost:9621/health

# Metrics
curl http://localhost:9621/metrics  # Prometheus format

# Logs
tail -f /var/log/lightrag/server.log
```

### Security Checklist

- ✅ Use HTTPS/TLS for all connections
- ✅ Enable API authentication
- ✅ Restrict CORS origins
- ✅ Use strong LLM API keys
- ✅ Enable database encryption
- ✅ Set up audit logging
- ✅ Regular security updates
- ✅ Rate limiting enabled

---

## Kubernetes Deployment

### Helm Chart Installation

```bash
# Add LightRAG helm repository
helm repo add lightrag https://charts.lightrag.io
helm repo update

# Install
helm install lightrag lightrag/lightrag \
  --set llm.model=gpt-4o \
  --set llm.apiKey=$OPENAI_API_KEY \
  --set replicas=3
```

### Custom Deployment

```yaml
# lightrag-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lightrag-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: lightrag
        image: lightrag:latest
        env:
        - name: LLM_MODEL
          value: gpt-4o
        - name: MAX_ASYNC
          value: "8"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
---
apiVersion: v1
kind: Service
metadata:
  name: lightrag-service
spec:
  type: LoadBalancer
  ports:
  - port: 9621
```

---

## Troubleshooting Deployments

### API won't start

```bash
# Check logs
docker logs lightrag-api
# or
kubectl logs deployment/lightrag-api

# Common issues:
# - Missing .env file
# - Invalid LLM API key
# - Port already in use
```

### High memory usage

```bash
# Reduce concurrency
MAX_ASYNC=2
MAX_PARALLEL_INSERT=1

# Reduce chunk size
CHUNK_SIZE=1024

# Enable document-level caching
CACHE_BACKEND=redis
```

### Slow queries

```bash
# Check if using temporal mode unnecessarily
# Prefer local/hybrid over global

# Increase chunk size for large documents
CHUNK_SIZE=3000

# Use indexing on frequently queried entities
# Enable caching
```

---

## Performance Tuning

### For Production (High Load)

```bash
# .env
MAX_ASYNC=8                 # Increase concurrency
MAX_PARALLEL_INSERT=4       # Multiple documents
CACHE_BACKEND=redis         # Distributed cache
STORAGE_TYPE=neo4j          # Production DB
CHUNK_SIZE=2000             # Optimize for typical docs
```

### For Development (Low Resources)

```bash
# .env
MAX_ASYNC=2                 # Lower concurrency
MAX_PARALLEL_INSERT=1       # Single document
CACHE_BACKEND=memory        # In-memory cache
STORAGE_TYPE=networkx       # In-memory graph
CHUNK_SIZE=1024             # Smaller chunks
```

### Monitoring Performance

```bash
# Request latency
curl -w "Time: %{time_total}s\n" http://localhost:9621/health

# Database stats
python query_graph.py --stats

# Memory usage
ps aux | grep lightrag-server
```

---

## Support & References

- **Installation Issues** → [GETTING_STARTED.md](GETTING_STARTED.md)
- **Configuration** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Details** → [API_REFERENCE.md](API_REFERENCE.md)
- **GitHub Issues** → [Report bug](https://github.com/HKUDS/LightRAG/issues)

---

**Successfully deployed? Check [USER_GUIDE.md](USER_GUIDE.md) for usage instructions.**
