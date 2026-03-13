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

---

**Last Updated:** March 5, 2026

---

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
flowchart TB
    subgraph Clients["Client Layer"]
        WebUI[Web UI]
        MobileApp[Mobile App]
        API_Client[API Clients]
    end
    
    subgraph LoadBalancer["Load Balancing"]
        LB[Load Balancer<br/>Nginx/HAProxy]
    end
    
    subgraph APILayer["LightRAG API Layer (Kubernetes Pods)"]
        API1[API Pod 1<br/>lightrag-server]
        API2[API Pod 2<br/>lightrag-server]
        API3[API Pod 3<br/>lightrag-server]
    end
    
    subgraph CacheLayer["Caching Layer"]
        Redis[(Redis Cache<br/>Query Results)]
    end
    
    subgraph StorageLayer["Storage Layer"]
        GraphDB[(Graph Storage<br/>Neo4j/NetworkX)]
        VectorDB[(Vector Storage<br/>Milvus/Qdrant)]
        KVDB[(KV Storage<br/>MongoDB/PostgreSQL)]
    end
    
    subgraph LLMLayer["LLM Services"]
        LLM[LLM Provider<br/>OpenAI/Azure/Ollama]
        Embedding[Embedding Service<br/>text-embedding-3]
    end
    
    WebUI --> LB
    MobileApp --> LB
    API_Client --> LB
    
    LB --> API1
    LB --> API2
    LB --> API3
    
    API1 --> Redis
    API2 --> Redis
    API3 --> Redis
    
    API1 --> GraphDB
    API1 --> VectorDB
    API1 --> KVDB
    
    API2 --> GraphDB
    API2 --> VectorDB
    API2 --> KVDB
    
    API3 --> GraphDB
    API3 --> VectorDB
    API3 --> KVDB
    
    API1 -.->|LLM Requests| LLM
    API2 -.->|LLM Requests| LLM
    API3 -.->|LLM Requests| LLM
    
    API1 -.->|Embedding Requests| Embedding
    API2 -.->|Embedding Requests| Embedding
    API3 -.->|Embedding Requests| Embedding
    
    style LoadBalancer fill:#e1f5ff
    style APILayer fill:#fff4e1
    style CacheLayer fill:#f0e1ff
    style StorageLayer fill:#e1ffe1
    style LLMLayer fill:#ffe1e1
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

---

## Production Deployment Checklist

### Pre-Deployment Verification

#### Infrastructure Setup

- [ ] **Core Services Provisioned**
  - [ ] Database cluster running (Neptune/Neo4j/MongoDB)
  - [ ] Vector database live (Milvus/Qdrant)
  - [ ] Cache layer active (Redis/Memcached)
  - [ ] Load balancer configured
  - [ ] Backup storage available

- [ ] **Network Configuration**
  - [ ] VPC and subnets configured
  - [ ] Security groups allow required traffic
  - [ ] NAT gateway for private subnets
  - [ ] DNS records updated
  - [ ] SSL/TLS certificates installed

- [ ] **IAM and Authentication**
  - [ ] Database access credentials secured
  - [ ] API authentication configured
  - [ ] Service accounts created
  - [ ] Secrets manager integration complete
  - [ ] Cross-account access configured (if multi-account)

#### Application Configuration

- [ ] **Environment Setup**
  - [ ] `.env.production` template filled out
  - [ ] All placeholder values replaced
  - [ ] Database endpoints verified
  - [ ] API keys validated
  - [ ] SSL certificates configured
  - [ ] Concurrency limits set appropriately

- [ ] **Security Configuration**
  - [ ] Default admin password changed
  - [ ] API keys are strong and rotated
  - [ ] CORS origins restricted
  - [ ] Rate limiting enabled
  - [ ] Request validation enabled
  - [ ] Audit logging configured

- [ ] **Storage Backend**
  - [ ] Connection strings verified
  - [ ] Connection pooling configured
  - [ ] Backup scheduling enabled
  - [ ] Replication configured
  - [ ] Disaster recovery tested

#### Application Testing

- [ ] **Functionality Tests**
  - [ ] Document ingestion works
  - [ ] Query execution works
  - [ ] All query modes functional (local, global, hybrid, temporal)
  - [ ] Multi-user concurrent access tested
  - [ ] Error handling verified

- [ ] **Performance Tests**
  - [ ] Baseline latency measured
  - [ ] Load test with target concurrency completed
  - [ ] Cache hit rates verified
  - [ ] Database query performance acceptable
  - [ ] Memory usage stable

- [ ] **Integration Tests**
  - [ ] LLM API endpoints reachable
  - [ ] Embedding service functional
  - [ ] Database backups work
  - [ ] API health checks pass
  - [ ] Monitoring alerts configured

#### Monitoring & Observability

- [ ] **Metrics & Logging**
  - [ ] Application logs shipping to CloudWatch/ELK
  - [ ] Database query logs enabled
  - [ ] Error tracking configured (Sentry/DataDog)
  - [ ] Performance metrics collected
  - [ ] Distributed tracing enabled (optional)

- [ ] **Alerting**
  - [ ] High latency alert configured (>2s)
  - [ ] Error rate alert configured (>1%)
  - [ ] Database connection pool alert
  - [ ] Disk space alert
  - [ ] Memory usage alert
  - [ ] On-call rotation configured

#### Backup & Recovery

- [ ] **Backup Configuration**
  - [ ] Daily backups scheduled
  - [ ] Backup retention policy set (minimum 7 days)
  - [ ] Backup encryption enabled
  - [ ] Backup verification automated
  - [ ] Recovery procedure documented

- [ ] **Disaster Recovery**
  - [ ] Failover procedure documented
  - [ ] RTO/RPO requirements met
  - [ ] Backup restoration tested
  - [ ] Geographic redundancy configured (if needed)

### Rollback Procedure

If deployment encounters issues:

**Step 1: Immediate Rollback**
```bash
# Switch load balancer to previous version
# Database: Point to previous snapshot
# Environment: Roll back .env file

# Restart services with previous configuration
docker-compose down
docker-compose up -d --detach
```

**Step 2: Validate Rollback**
```bash
# Test API health
curl http://localhost:9621/health

# Run smoke tests
python test_queries.py

# Monitor error rates
# Should return to baseline within 5 minutes
```

**Step 3: Incident Review**
- Document what failed
- Update deployment checklist
- Schedule post-mortem
- Update runbooks

---

## Performance Profiling & Optimization

### Quick Reference Commands

```bash
# Profile document ingestion
python build_graph.py --profile --timing

# Profile query execution
python query_graph.py --query "test" --profile --timing

# Profile specific modes
python query_graph.py --query "test" --mode hybrid --profile

# Temporal query profiling
python query_graph.py --query "What changed?" --mode temporal --date 2024-01-01 --profile

# Full profiling with stats
python build_graph.py --profile --timing > profiling_results.txt
```

### Profiling Guide

#### Document Ingestion Profiling

Profile the `build_graph.py` script to identify bottlenecks in the data pipeline:

```bash
# Basic profiling
python build_graph.py --profile --timing

# Output shows breakdown by phase:
# - File loading: 0.2s
# - Text chunking: 1.5s
# - Entity extraction: 12.3s (LLM bottleneck)
# - Relationship extraction: 8.7s (LLM call)
# - Version detection: 0.3s
# - Graph storage: 0.8s
# - Vector indexing: 2.1s
# Total: 25.9s

# Profile with specific documents
python build_graph.py -i ./inputs --files doc1.pdf doc2.pdf --profile
```

#### Query Profiling

Profile the `query_graph.py` script to measure query performance:

```bash
# Basic query profiling
python query_graph.py --query "What is the fee?" --profile --timing

# Output breakdown:
# - Entity extraction: 1.2s (LLM call)
# - Vector search: 0.15s
# - Graph traversal: 0.3s
# - Context ranking: 0.4s
# - LLM generation: 2.1s
# Total: 4.15s

# Profile specific modes
python query_graph.py --query "test" --mode hybrid --profile
python query_graph.py --query "test" --mode temporal --date 2024-01-01 --profile
python query_graph.py --query "test" --mode global --profile

# Profile with reranking
python query_graph.py --query "test" --reranker true --profile
```

#### Identifying Bottlenecks

**LLM Call Bottleneck** (40-60% of time)
- Issue: Entity/relationship extraction takes longest
- Solution: Use smaller, faster models for extraction; use larger models for generation
- Configuration: Set different models for extraction vs. generation
- Expected gain: 30-50% overall reduction

**Vector Search Bottleneck** (5-15% of time)
- Issue: NanoVectorDB uses linear search O(n)
- Solution: Migrate to vector DB with HNSW indexing (Milvus, Qdrant, Weaviate)
- Configuration: `LIGHTRAG_VECTOR_STORAGE=MilvusVectorStorage`
- Expected gain: 80-90% reduction for large datasets

**Graph Traversal Bottleneck** (10-20% of time)
- Issue: NetworkX operations and Neo4j queries not optimized
- Solution: Implement graph caching, use read replicas, optimize query patterns
- Configuration: Enable query result caching
- Expected gain: 60-75% reduction with caching

**Memory Usage**
- Issue: All data kept in memory for NetworkX storage
- Solution: Migrate to persistent storage (Neo4j, MongoDB)
- Monitor: Track memory growth over time
- Expected: 10-100x capacity increase

#### Performance Optimization Checklist

After profiling, apply these optimizations:

```bash
# 1. Enable caching for LLM calls
ENABLE_LLM_CACHE=true
LLM_CACHE_TTL=3600

# 2. Use dedicated extraction model
EXTRACTER_LLM_BINDING=openai
EXTRACTER_LLM_MODEL=gpt-4o-mini  # Faster, cheaper

# 3. Increase concurrency
MAX_ASYNC=8
MAX_PARALLEL_INSERT=4

# 4. Switch to production storage
LIGHTRAG_VECTOR_STORAGE=MilvusVectorDBStorage
LIGHTRAG_GRAPH_STORAGE=NeptuneGraphStorage

# 5. Enable reranking
ENABLE_RERANKER=true
RERANK_BINDING=jinaai
RERANK_MODEL=jina-reranker-v1

# 6. Optimize chunking
CHUNK_SIZE=2000
CHUNK_OVERLAP_SIZE=200
```

#### Benchmark Results

Expected improvements from optimization:

| Metric | Baseline | Optimized | Gain |
|--------|----------|-----------|------|
| Ingestion (per doc) | 25-30s | 10-12s | 55-60% |
| Query latency | 4-6s | 1.5-2s | 60-65% |
| Concurrent users | 10-15 | 50+ | 5x |
| Vector search | O(n), 100-500ms | O(log n), 10-50ms | 90x |
| LLM cache hits | 0% | 30-50% | 70-90% reduction |

---

## Support & References

- **Installation Issues** → [GETTING_STARTED.md](GETTING_STARTED.md)
- **CLI Usage** → [CLI Reference](CLI_REFERENCE.md)
- **Architecture** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Details** → [API_REFERENCE.md](API_REFERENCE.md)
- **GitHub Issues** → [Report bug](https://github.com/HKUDS/LightRAG/issues)

---

**Successfully deployed? Check [USER_GUIDE.md](USER_GUIDE.md) for usage instructions.**
