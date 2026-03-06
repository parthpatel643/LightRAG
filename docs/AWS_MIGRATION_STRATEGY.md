# AWS Database Migration Strategy

**Document Version:** 1.0  
**Last Updated:** 2026-03-05  
**Target:** Production Migration from JSON/NetworkX to AWS Services

---

## Table of Contents

1. [Migration Overview](#migration-overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Migration Phases](#migration-phases)
4. [Data Migration Scripts](#data-migration-scripts)
5. [Parallel Run Strategy](#parallel-run-strategy)
6. [Validation & Testing](#validation--testing)
7. [Rollback Procedures](#rollback-procedures)
8. [Post-Migration Tasks](#post-migration-tasks)

---

## Migration Overview

### Current Architecture (Source)
```
┌─────────────────────────────────┐
│   JSON File Storage             │
│   - JsonKVStorage               │
│   - JsonDocStatusStorage        │
│   - NetworkXStorage (in-memory) │
│   - NanoVectorDBStorage         │
└─────────────────────────────────┘
```

### Target Architecture (AWS)
```
┌─────────────────────────────────┐
│   AWS Managed Services          │
│   - DocumentDB (KV/DocStatus)   │
│   - Neptune (Graph)             │
│   - Milvus (Vectors)            │
│   - Redis (Cache)               │
└─────────────────────────────────┘
```

### Migration Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| **Phase 1: Preparation** | 1 week | Setup AWS services, test connections |
| **Phase 2: Data Export** | 2-3 days | Export existing data to intermediate format |
| **Phase 3: Data Import** | 3-5 days | Import data to AWS services |
| **Phase 4: Parallel Run** | 1-2 weeks | Run both systems in parallel |
| **Phase 5: Cutover** | 1 day | Switch to AWS, decommission old system |
| **Phase 6: Monitoring** | 2 weeks | Monitor and optimize |

**Total Duration:** 4-6 weeks

---

## Pre-Migration Checklist

### 1. AWS Infrastructure Setup

```bash
# ✅ Verify all AWS services are provisioned
aws neptune describe-db-clusters --db-cluster-identifier lightrag-neptune-cluster
aws docdb describe-db-clusters --db-cluster-identifier lightrag-docdb-cluster
aws elasticache describe-cache-clusters --cache-cluster-id lightrag-redis

# ✅ Verify network connectivity
nc -zv lightrag-neptune-cluster.cluster-xxxxx.us-east-1.neptune.amazonaws.com 8182
nc -zv lightrag-docdb.cluster-xxxxx.us-east-1.docdb.amazonaws.com 27017
nc -zv lightrag-milvus.us-east-1.elb.amazonaws.com 19530
```

### 2. Backup Current Data

```bash
# Create backup directory
mkdir -p /backup/lightrag-migration-$(date +%Y%m%d)
cd /backup/lightrag-migration-$(date +%Y%m%d)

# Backup JSON storage
cp -r /path/to/rag_storage/kv_store_*.json ./
cp -r /path/to/rag_storage/doc_status_*.json ./
cp -r /path/to/rag_storage/vdb_*.json ./

# Create tarball
tar -czf lightrag-backup-$(date +%Y%m%d-%H%M%S).tar.gz *.json

# Upload to S3
aws s3 cp lightrag-backup-*.tar.gz s3://lightrag-backups/pre-migration/
```

### 3. Document Current State

```bash
# Count entities and relationships
python3 << EOF
import json
import glob

# Count KV entries
kv_files = glob.glob('/path/to/rag_storage/kv_store_*.json')
total_kv = sum(len(json.load(open(f))) for f in kv_files)
print(f"Total KV entries: {total_kv}")

# Count documents
doc_files = glob.glob('/path/to/rag_storage/doc_status_*.json')
total_docs = sum(len(json.load(open(f))) for f in doc_files)
print(f"Total documents: {total_docs}")

# Count vectors
vdb_files = glob.glob('/path/to/rag_storage/vdb_*.json')
total_vectors = sum(len(json.load(open(f))) for f in vdb_files)
print(f"Total vectors: {total_vectors}")
EOF
```

---

## Migration Phases

### Phase 1: Preparation (Week 1)

#### 1.1 Setup AWS Services

```bash
# Run infrastructure setup scripts
cd k8s-deploy/databases
./00-config.sh
./01-prepare.sh
./02-install-database.sh

# Verify services are running
kubectl get pods -n lightrag-databases
```

#### 1.2 Configure Connection Strings

```bash
# Update .env with AWS endpoints
cat >> .env << 'EOF'
# AWS Migration Configuration
MIGRATION_MODE=parallel
MIGRATION_SOURCE_STORAGE=json
MIGRATION_TARGET_STORAGE=aws

# Source (current)
SOURCE_WORKING_DIR=/path/to/rag_storage

# Target (AWS)
NEPTUNE_ENDPOINT=lightrag-neptune-cluster.cluster-xxxxx.us-east-1.neptune.amazonaws.com
MONGO_URI=mongodb://admin:password@lightrag-docdb.cluster-xxxxx.us-east-1.docdb.amazonaws.com:27017/
MILVUS_URI=http://lightrag-milvus.us-east-1.elb.amazonaws.com:19530
EOF
```

#### 1.3 Test Connections

```python
# test_aws_connections.py
import asyncio
import os
from lightrag.kg.neptune_impl import NeptuneGraphStorage
from lightrag.kg.mongo_impl import MongoKVStorage
from lightrag.kg.milvus_impl import MilvusVectorDBStorage

async def test_connections():
    """Test all AWS service connections"""
    
    # Test Neptune
    try:
        neptune = NeptuneGraphStorage(namespace="test", workspace="test", global_config={}, embedding_func=None)
        await neptune.initialize()
        print("✅ Neptune connection successful")
        await neptune.finalize()
    except Exception as e:
        print(f"❌ Neptune connection failed: {e}")
    
    # Test DocumentDB
    try:
        mongo = MongoKVStorage(namespace="test", workspace="test", global_config={}, embedding_func=None)
        await mongo.initialize()
        print("✅ DocumentDB connection successful")
        await mongo.finalize()
    except Exception as e:
        print(f"❌ DocumentDB connection failed: {e}")
    
    # Test Milvus
    try:
        milvus = MilvusVectorDBStorage(namespace="test", workspace="test", global_config={}, embedding_func=None)
        await milvus.initialize()
        print("✅ Milvus connection successful")
        await milvus.finalize()
    except Exception as e:
        print(f"❌ Milvus connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connections())
```

### Phase 2: Data Export (Days 1-3)

#### 2.1 Export KV Store

```python
# export_kv_store.py
import json
import glob
from pathlib import Path

def export_kv_store(source_dir: str, output_file: str):
    """Export all KV store data to single JSON file"""
    
    kv_data = {}
    kv_files = glob.glob(f"{source_dir}/kv_store_*.json")
    
    for file_path in kv_files:
        namespace = Path(file_path).stem.replace("kv_store_", "")
        with open(file_path, 'r') as f:
            kv_data[namespace] = json.load(f)
    
    with open(output_file, 'w') as f:
        json.dump(kv_data, f, indent=2)
    
    print(f"Exported {len(kv_data)} namespaces to {output_file}")
    return kv_data

if __name__ == "__main__":
    export_kv_store(
        source_dir="/path/to/rag_storage",
        output_file="/backup/kv_store_export.json"
    )
```

#### 2.2 Export Document Status

```python
# export_doc_status.py
import json
import glob
from pathlib import Path

def export_doc_status(source_dir: str, output_file: str):
    """Export all document status data"""
    
    doc_data = {}
    doc_files = glob.glob(f"{source_dir}/doc_status_*.json")
    
    for file_path in doc_files:
        namespace = Path(file_path).stem.replace("doc_status_", "")
        with open(file_path, 'r') as f:
            doc_data[namespace] = json.load(f)
    
    with open(output_file, 'w') as f:
        json.dump(doc_data, f, indent=2)
    
    print(f"Exported {len(doc_data)} namespaces to {output_file}")
    return doc_data

if __name__ == "__main__":
    export_doc_status(
        source_dir="/path/to/rag_storage",
        output_file="/backup/doc_status_export.json"
    )
```

#### 2.3 Export Graph Data

```python
# export_graph_data.py
import json
import pickle
from pathlib import Path

def export_graph_data(source_dir: str, output_file: str):
    """Export NetworkX graph to JSON format"""
    
    # Load NetworkX graph (if pickled)
    graph_file = Path(source_dir) / "graph_storage.pkl"
    
    if graph_file.exists():
        with open(graph_file, 'rb') as f:
            graph = pickle.load(f)
        
        # Convert to JSON-serializable format
        graph_data = {
            "nodes": [
                {
                    "id": node,
                    "properties": data
                }
                for node, data in graph.nodes(data=True)
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "properties": data
                }
                for u, v, data in graph.edges(data=True)
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(graph_data, f, indent=2)
        
        print(f"Exported {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges")
        return graph_data
    else:
        print("No graph storage file found")
        return None

if __name__ == "__main__":
    export_graph_data(
        source_dir="/path/to/rag_storage",
        output_file="/backup/graph_export.json"
    )
```

#### 2.4 Export Vector Data

```python
# export_vector_data.py
import json
import glob
import numpy as np
from pathlib import Path

def export_vector_data(source_dir: str, output_dir: str):
    """Export vector embeddings"""
    
    vdb_files = glob.glob(f"{source_dir}/vdb_*.json")
    
    for file_path in vdb_files:
        namespace = Path(file_path).stem.replace("vdb_", "")
        
        with open(file_path, 'r') as f:
            vdb_data = json.load(f)
        
        # Export to separate file per namespace
        output_file = f"{output_dir}/vectors_{namespace}.json"
        with open(output_file, 'w') as f:
            json.dump(vdb_data, f, indent=2)
        
        print(f"Exported {len(vdb_data)} vectors for namespace {namespace}")

if __name__ == "__main__":
    export_vector_data(
        source_dir="/path/to/rag_storage",
        output_dir="/backup/vectors"
    )
```

### Phase 3: Data Import (Days 4-8)

#### 3.1 Import to DocumentDB

```python
# import_to_documentdb.py
import asyncio
import json
from lightrag.kg.mongo_impl import MongoKVStorage, MongoDocStatusStorage

async def import_kv_store(export_file: str):
    """Import KV store data to DocumentDB"""
    
    with open(export_file, 'r') as f:
        kv_data = json.load(f)
    
    for namespace, data in kv_data.items():
        storage = MongoKVStorage(
            namespace=namespace,
            workspace="production",
            global_config={},
            embedding_func=None
        )
        
        await storage.initialize()
        
        # Batch insert
        batch_size = 100
        items = list(data.items())
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            for key, value in batch:
                await storage.upsert({key: value})
        
        print(f"Imported {len(data)} items for namespace {namespace}")
        await storage.finalize()

async def import_doc_status(export_file: str):
    """Import document status to DocumentDB"""
    
    with open(export_file, 'r') as f:
        doc_data = json.load(f)
    
    for namespace, data in doc_data.items():
        storage = MongoDocStatusStorage(
            namespace=namespace,
            workspace="production",
            global_config={},
            embedding_func=None
        )
        
        await storage.initialize()
        
        # Import documents
        for doc_id, status in data.items():
            await storage.upsert_doc_status(doc_id, status)
        
        print(f"Imported {len(data)} documents for namespace {namespace}")
        await storage.finalize()

if __name__ == "__main__":
    asyncio.run(import_kv_store("/backup/kv_store_export.json"))
    asyncio.run(import_doc_status("/backup/doc_status_export.json"))
```

#### 3.2 Import to Neptune

```python
# import_to_neptune.py
import asyncio
import json
from lightrag.kg.neptune_impl import NeptuneGraphStorage

async def import_graph_data(export_file: str):
    """Import graph data to Neptune"""
    
    with open(export_file, 'r') as f:
        graph_data = json.load(f)
    
    storage = NeptuneGraphStorage(
        namespace="production",
        workspace="production",
        global_config={},
        embedding_func=None
    )
    
    await storage.initialize()
    
    # Import nodes in batches
    batch_size = 100
    nodes = graph_data['nodes']
    
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]
        
        # Build batch Gremlin query
        query = "g"
        for node in batch:
            query += f".addV('entity').property('id', '{node['id']}')"
            for key, value in node['properties'].items():
                query += f".property('{key}', '{value}')"
        
        await storage._submit_query(query)
        print(f"Imported nodes {i} to {i + len(batch)}")
    
    # Import edges in batches
    edges = graph_data['edges']
    
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        
        query = "g"
        for edge in batch:
            query += f".V().has('id', '{edge['source']}').addE('relates_to').to(V().has('id', '{edge['target']}'))"
            for key, value in edge['properties'].items():
                query += f".property('{key}', '{value}')"
        
        await storage._submit_query(query)
        print(f"Imported edges {i} to {i + len(batch)}")
    
    await storage.finalize()
    print(f"Import complete: {len(nodes)} nodes, {len(edges)} edges")

if __name__ == "__main__":
    asyncio.run(import_graph_data("/backup/graph_export.json"))
```

#### 3.3 Import to Milvus

```python
# import_to_milvus.py
import asyncio
import json
import glob
import numpy as np
from lightrag.kg.milvus_impl import MilvusVectorDBStorage

async def import_vector_data(export_dir: str):
    """Import vector embeddings to Milvus"""
    
    vector_files = glob.glob(f"{export_dir}/vectors_*.json")
    
    for file_path in vector_files:
        namespace = file_path.split('vectors_')[1].replace('.json', '')
        
        with open(file_path, 'r') as f:
            vector_data = json.load(f)
        
        storage = MilvusVectorDBStorage(
            namespace=namespace,
            workspace="production",
            global_config={},
            embedding_func=None
        )
        
        await storage.initialize()
        
        # Batch insert vectors
        batch_size = 100
        items = list(vector_data.items())
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            ids = [item[0] for item in batch]
            vectors = [np.array(item[1]['vector']) for item in batch]
            metadata = [item[1].get('metadata', {}) for item in batch]
            
            await storage.upsert(ids, vectors, metadata)
            print(f"Imported vectors {i} to {i + len(batch)} for namespace {namespace}")
        
        await storage.finalize()

if __name__ == "__main__":
    asyncio.run(import_vector_data("/backup/vectors"))
```

### Phase 4: Parallel Run (Weeks 3-4)

#### 4.1 Dual-Write Configuration

```python
# Enable parallel writes to both systems
MIGRATION_MODE=parallel
MIGRATION_WRITE_TO_BOTH=true
MIGRATION_READ_FROM=json  # or 'aws' for testing
```

#### 4.2 Validation Script

```python
# validate_migration.py
import asyncio
import json

async def validate_data_consistency():
    """Compare data between JSON and AWS storage"""
    
    # Compare KV store
    json_kv = load_json_kv_store()
    aws_kv = await load_aws_kv_store()
    
    kv_diff = compare_dicts(json_kv, aws_kv)
    print(f"KV Store differences: {len(kv_diff)}")
    
    # Compare document status
    json_docs = load_json_doc_status()
    aws_docs = await load_aws_doc_status()
    
    doc_diff = compare_dicts(json_docs, aws_docs)
    print(f"Document status differences: {len(doc_diff)}")
    
    # Compare graph
    json_graph = load_json_graph()
    aws_graph = await load_aws_graph()
    
    graph_diff = compare_graphs(json_graph, aws_graph)
    print(f"Graph differences: {graph_diff}")
    
    # Compare vectors
    json_vectors = load_json_vectors()
    aws_vectors = await load_aws_vectors()
    
    vector_diff = compare_vectors(json_vectors, aws_vectors)
    print(f"Vector differences: {vector_diff}")
    
    return {
        "kv_diff": kv_diff,
        "doc_diff": doc_diff,
        "graph_diff": graph_diff,
        "vector_diff": vector_diff
    }

if __name__ == "__main__":
    results = asyncio.run(validate_data_consistency())
    
    with open("/backup/validation_results.json", 'w') as f:
        json.dump(results, f, indent=2)
```

### Phase 5: Cutover (Day 1)

#### 5.1 Pre-Cutover Checklist

```bash
# ✅ Verify data consistency
python validate_migration.py

# ✅ Run performance tests
python benchmark_aws_performance.py

# ✅ Verify monitoring is active
aws cloudwatch describe-alarms --alarm-names lightrag-*

# ✅ Create final backup
./backup_current_state.sh

# ✅ Notify stakeholders
echo "Migration cutover scheduled for $(date)"
```

#### 5.2 Cutover Steps

```bash
# 1. Stop writes to JSON storage
# Update .env
MIGRATION_MODE=readonly
MIGRATION_READ_FROM=json

# 2. Final data sync
python sync_final_changes.py

# 3. Switch to AWS
# Update .env
LIGHTRAG_KV_STORAGE=MongoKVStorage
LIGHTRAG_DOC_STATUS_STORAGE=MongoDocStatusStorage
LIGHTRAG_GRAPH_STORAGE=NeptuneGraphStorage
LIGHTRAG_VECTOR_STORAGE=MilvusVectorDBStorage

# 4. Restart services
systemctl restart lightrag-api

# 5. Verify health
curl http://localhost:9621/health

# 6. Run smoke tests
python smoke_tests.py
```

---

## Rollback Procedures

### Immediate Rollback (< 1 hour)

```bash
# 1. Stop services
systemctl stop lightrag-api

# 2. Revert .env configuration
cp .env.backup .env

# 3. Restart with JSON storage
systemctl start lightrag-api

# 4. Verify functionality
curl http://localhost:9621/health
```

### Partial Rollback (1-24 hours)

```bash
# Rollback specific component
# Example: Rollback graph storage only

# Update .env
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
# Keep other AWS services

# Restart
systemctl restart lightrag-api
```

### Full Rollback (> 24 hours)

```bash
# 1. Restore from backup
cd /backup/lightrag-migration-YYYYMMDD
tar -xzf lightrag-backup-*.tar.gz -C /path/to/rag_storage/

# 2. Revert all configuration
cp .env.pre-migration .env

# 3. Restart services
systemctl restart lightrag-api

# 4. Verify data integrity
python verify_json_storage.py
```

---

## Post-Migration Tasks

### Week 1: Monitoring

```bash
# Monitor CloudWatch metrics daily
aws cloudwatch get-metric-statistics \
  --namespace LightRAG/Production \
  --metric-name QueryLatency \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum

# Check error rates
aws logs tail /aws/lightrag/api --follow --filter-pattern "ERROR"
```

### Week 2: Optimization

```bash
# Analyze slow queries
python analyze_slow_queries.py

# Optimize indexes
python optimize_neptune_indexes.py
python optimize_milvus_indexes.py

# Tune connection pools
# Adjust based on metrics
NEPTUNE_MAX_CONNECTIONS=150  # if needed
MONGO_MAX_POOL_SIZE=150
```

### Week 3-4: Decommission

```bash
# Archive JSON storage
tar -czf json-storage-archive-$(date +%Y%m%d).tar.gz /path/to/rag_storage/
aws s3 cp json-storage-archive-*.tar.gz s3://lightrag-archives/

# Remove old storage (after 30 days)
# rm -rf /path/to/rag_storage/*.json
```

---

## Migration Scripts Summary

| Script | Purpose | Duration |
|--------|---------|----------|
| `test_aws_connections.py` | Verify AWS connectivity | 1 min |
| `export_kv_store.py` | Export KV data | 10-30 min |
| `export_doc_status.py` | Export document status | 5-15 min |
| `export_graph_data.py` | Export graph | 30-60 min |
| `export_vector_data.py` | Export vectors | 1-3 hours |
| `import_to_documentdb.py` | Import to DocumentDB | 1-2 hours |
| `import_to_neptune.py` | Import to Neptune | 2-4 hours |
| `import_to_milvus.py` | Import to Milvus | 1-3 hours |
| `validate_migration.py` | Validate consistency | 30-60 min |
| `benchmark_aws_performance.py` | Performance testing | 1-2 hours |

---

## Success Criteria

- ✅ 100% data migrated (verified by validation script)
- ✅ Query response time < 500ms (p95)
- ✅ Zero data loss
- ✅ All health checks passing
- ✅ CloudWatch monitoring active
- ✅ Rollback procedures tested
- ✅ Documentation complete
- ✅ Team trained on new system

---

## Support & Troubleshooting

### Common Issues

**Issue:** Connection timeout to Neptune
**Solution:** Check security groups, verify IAM permissions

**Issue:** DocumentDB authentication failure
**Solution:** Verify TLS certificate, check connection string

**Issue:** Milvus index creation slow
**Solution:** Increase `MILVUS_HNSW_EF_CONSTRUCTION`, use smaller batches

**Issue:** Data inconsistency detected
**Solution:** Re-run import for affected namespace, verify source data

---

**Document Status:** ✅ Complete  
**Next Document:** `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`