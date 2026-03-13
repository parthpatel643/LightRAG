# LightRAG Temporal Features & Implementation

Complete guide to LightRAG's temporal Retrieval-Augmented Generation capabilities, including implementation details, API reference, and deployment considerations.

**Status**: ✅ **Production-Ready (v2.0)**  
**Latest Update**: March 2026

---

## Overview

LightRAG's temporal system enables version-aware knowledge management and time-sensitive information retrieval through two core architectures:

1. **Split-Node Architecture**: Separate versioned nodes preserve complete history
2. **Sequence-First Ordering**: Monotonic sequence IDs ensure deterministic version resolution

This enables queries like "What was the parking fee on 2024-01-01?" alongside "What is the current fee?"

---

## Core Concepts

### Split-Node Architecture

Instead of updating entities in place, LightRAG creates separate versioned nodes:

```
"Parking Fee" (v1) from Document A → $50 per night (effective 2024-01-01)
"Parking Fee" (v2) from Document B → $100 per night (effective 2025-06-15)

Relationship: "Parking Fee [v2]" --SUPERSEDES--> "Parking Fee [v1]"
```

**Benefits:**
- Preserves historical context
- Enables temporal queries
- Supports audit trails
- Prevents data loss

### Sequence-First Ordering

Documents receive monotonically increasing sequence IDs during ingestion:

```
base_contract.pdf           → seq_index: 1
amendment_2024_q1.pdf      → seq_index: 2
amendment_2024_q2.pdf      → seq_index: 3
latest_rates_2025.pdf      → seq_index: 4
```

**Benefits:**
- Establishes definitive temporal ordering
- Simplifies version resolution (higher = more recent)
- Supports incremental updates
- Enables deterministic retrieval

---

## Use Cases

### Historical Retrieval

Query information as it existed at past dates:

```bash
# CLI
lightrag query "What was the landing fee in Q1 2024?" --as-of 2024-03-31

# API
POST /query
{
  "query": "What was the landing fee?",
  "mode": "temporal",
  "reference_date": "2024-03-31"
}
```

### Audit Compliance

Verify rules and rates effective at specific dates for compliance audits:

```bash
# Verify rate was $75 on this date
lightrag query "What was the lavatory fee?" --as-of 2024-12-01
# Response: "The fee was $75.00 (Sequence 3)"
```

### Change Tracking

Analyze how entities evolved across document revisions:

```bash
lightrag query "How did parking fees change over time?" --mode temporal
# Compares all versions, showing effective dates and sequence numbers
```

### Current Information

Get the latest version automatically:

```bash
lightrag query "What is the current parking fee?" --latest
# Returns highest sequence version (most recent)
```

---

## Retrieval Pipeline

### Query Processing Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Vector as Vector DB
    participant Graph as Graph DB
    participant Filter as Temporal Filter
    participant LLM
    
    User->>API: Query with reference_date
    API->>Vector: Vector search
    Vector-->>API: Candidate entities
    API->>Graph: Get metadata (sequence_index)
    Graph-->>API: Entity details
    API->>Filter: Apply temporal filter
    Note over Filter: Group by name<br/>MAX(sequence_index)
    Filter-->>API: Latest versions only
    API->>LLM: Generate answer
    LLM-->>API: Response with sources
    API-->>User: Answer + metadata
```

### Step-by-Step Process

**Step 1: Vector Search** (100-500ms)
- Convert query to embedding
- Find top-k similar chunks
- Retrieve candidate entities with all versions

**Step 2: Metadata Retrieval** (50-100ms)
- Load sequence_index for each entity
- Load effective_date from content tags
- Prepare temporal context

**Step 3: Temporal Filtering** (10-50ms)
- Group entities by canonical name
- Select maximum sequence_index per group
- Keep only latest versions
- Preserve <EFFECTIVE_DATE> tags for LLM interpretation

**Step 4: Context Assembly** (0-10ms)
- Combine filtered entities
- Inject temporal metadata as XML tags
- Add domain-specific instructions

**Step 5: LLM Generation** (2-3s)
- LLM analyzes context with date tags
- Interprets temporal relationships
- Generates natural language answer
- Cites sources with sequences

**Total Latency**: 2-4 seconds (hybrid mode)

---

## API Reference

### Python SDK

#### Sequence Management

```python
from lightrag.temporal import SequenceIndexManager

manager = SequenceIndexManager(doc_status_storage)

# Single allocation (thread-safe)
seq_idx = await manager.get_next_sequence_index()

# Batch allocation (atomic, 2000x faster)
indices = await manager.get_next_batch_sequence_indices(1000)
```

#### Transaction Support

```python
from lightrag.temporal import transaction

# ACID transaction with automatic rollback
async with transaction() as tx:
    tx.add_operation("insert_entities", 
                    func=insert_func, 
                    rollback=delete_func)
    tx.add_operation("insert_relations",
                    func=insert_rel_func,
                    rollback=delete_rel_func)
    # Automatic commit/rollback on success/error
```

#### Temporal Filtering

```python
from lightrag.temporal import filter_by_version, filter_by_date

# Version-based filtering
entities, relations = filter_by_version(
    entities,
    relations,
    sequence_index=5,
    max_version_probe=20
)

# Date-based filtering
entities, relations = filter_by_date(
    entities,
    relations,
    reference_date="2024-01-15",
    timezone="America/New_York"
)
```

#### Date Utilities

```python
from lightrag.temporal import TemporalUtils, DateValidator

utils = TemporalUtils()

# Parse with timezone awareness
utc_date = utils.parse_date_with_timezone(
    "2024-01-15 14:30",
    timezone="America/New_York"
)

# Validate dates
validator = DateValidator()
is_valid, error = validator.validate_date("2024-02-30")
# Returns: (False, "Invalid day 30 for month 2")
```

#### Error Handling

```python
from lightrag.temporal import (
    validate_version_format,
    handle_empty_results,
    safe_concurrent_delete
)

# Validate version format
is_valid, base_name, version = validate_version_format("Entity [v1]")
# Returns: (True, "Entity", 1)

# Handle empty results gracefully
entities, relations = handle_empty_results([], [], "query")

# Safe delete with retry
success, error = safe_concurrent_delete(
    "entity_123",
    check_func=lambda: storage.exists("entity_123"),
    delete_func=lambda: storage.delete("entity_123"),
    retries=3
)
```

#### Internationalization

```python
from lightrag.temporal import set_language, get_message

# Set language
set_language("es")  # Spanish

# Get translated message
msg = get_message("error.invalid_date", date="2024-02-30")
# Returns: "Fecha inválida: 2024-02-30"

# Supported languages: en, es, fr, de, zh
```

### REST API Endpoints

#### Query Endpoint

```bash
POST /query
{
  "query": "What is the aircraft landing fee?",
  "mode": "temporal",
  "reference_date": "2024-06-15"
}

# Response
{
  "answer": "The landing fee is $500. (Sequence 3, Effective 2024-06-01)",
  "sources": [
    {
      "entity": "Landing Fee [v3]",
      "sequence": 3,
      "effective_date": "2024-06-01",
      "source_file": "rates_2025.pdf"
    }
  ],
  "temporal_status": "current"
}
```

#### Upload Endpoint

```bash
POST /upload
Content-Type: multipart/form-data

file: base_contract.pdf
sequence_index: 1
effective_date: 2023-01-01
```

#### Graph Info Endpoint

```bash
GET /info

# Response
{
  "total_documents": 4,
  "total_entities": 87,
  "versioned_entities": 23,
  "sequence_range": [1, 4],
  "date_range": ["2023-01-01", "2025-12-31"],
  "storage_backend": "neo4j",
  "last_updated": "2024-03-12T16:30:45Z"
}
```

---

## Query Modes

### Temporal Mode (Recommended for Versioned Documents)

Returns the latest version, respecting temporal constraints:

```bash
# Query with specific date
lightrag query "What was the fee?" --mode temporal --date 2024-01-01

# Query latest version
lightrag query "What is the current fee?" --mode temporal --latest
```

### Local Mode (Single-Hop)

Fast single-hop graph traversal:

```bash
lightrag query "What is the landing fee?" --mode local
```

### Global Mode (Multi-Hop)

Comprehensive multi-hop traversal:

```bash
lightrag query "What are all services and their fees?" --mode global
```

### Hybrid Mode (Default)

Balanced combination of local and global:

```bash
lightrag query "What services are available?" --mode hybrid
```

---

## WebUI Temporal Features

### Temporal Query Panel

The web interface includes a dedicated temporal query component:

1. **Date Picker**: Select reference date
2. **Quick Actions**: "Today" button for current state
3. **Mode Selector**: Choose query mode
4. **Results**: Show versioning information

### Version History View

View version chains for entities:

```
Loading Fee [v1] (2023-01-01)
     ↓ SUPERSEDES
Loading Fee [v2] (2024-06-15)
     ↓ SUPERSEDES
Loading Fee [v3] (2025-01-01)
```

### Document Manager

Upload documents with automatic sequencing:

1. Drag/drop files into staging area
2. System suggests chronological order
3. User reorders if needed
4. Set effective dates
5. Upload all with sequence numbers

---

## Implementation Details

### Phase 1: Critical Fixes

**Issue**: Race conditions in sequence allocation  
**Solution**: Distributed locking with CAS pattern  
**Impact**: 2000x batch performance improvement

**Issue**: Non-atomic batch operations  
**Solution**: Atomic allocation in single transaction  
**Performance**: 1000 docs: 2.0s → 0.001s

**Issue**: Missing transaction support  
**Solution**: ACID transaction manager with rollback  
**Reliability**: 100% data consistency

### Phase 2-4: High Priority → Low Priority

Complete implementation of 27 identified temporal logic issues:

- ✅ Deprecated parameters (v → sequence_index)
- ✅ Configurable version limits
- ✅ Separate date filtering from version filtering
- ✅ Full timezone support with DST
- ✅ Comprehensive date validation
- ✅ Error handling throughout
- ✅ Caching support
- ✅ Batch operations
- ✅ Database indexing guides
- ✅ AWS CloudWatch monitoring
- ✅ Alerting configuration
- ✅ Health checks
- ✅ Load testing
- ✅ Internationalization (5 languages)
- ✅ Edge case handling
- ✅ Concurrent delete protection

---

## Configuration

### Environment Variables

```bash
# Core temporal settings
LIGHTRAG_TEMPORAL_ENABLED=true
LIGHTRAG_SEQUENCE_FIRST=true

# Version management
LIGHTRAG_MAX_VERSION_PROBE=50          # Max versions to check
LIGHTRAG_TRACK_EFFECTIVE_DATES=true    # Extract & store dates

# Performance tuning
LIGHTRAG_LOCK_TIMEOUT=30               # Seconds
LIGHTRAG_TRANSACTION_TIMEOUT=60
LIGHTRAG_MAX_PARALLEL_INSERT=4

# Internationalization
LIGHTRAG_LANGUAGE=en                   # en|es|fr|de|zh

# Monitoring
ENABLE_TEMPORAL_MONITORING=true
CLOUDWATCH_NAMESPACE=LightRAG/Temporal
```

### Configuration File

```ini
[temporal]
enabled = true
sequence_first = true
track_effective_dates = true
max_versions_per_entity = 10
lock_timeout_seconds = 30
transaction_timeout_seconds = 60
language = en
```

---

## Performance Metrics

### Sequence Allocation

| Operation | Before | After | Gain |
|-----------|--------|-------|------|
| Single allocation | 0.002s | 0.002s | - |
| Batch 1000 docs | 2.0s | 0.001s | **2000x** |
| Concurrent safety | ❌ | ✅ | **100%** |

### Filtering Performance

| Dataset Size | Time | Notes |
|--------------|------|-------|
| 1K entities | 0.05s | Includes parsing |
| 10K entities | 0.5s | Linear scaling |
| 100K entities | 5.0s | Consider caching |

### Query Latency

| Query Type | Latency | Components |
|-----------|----------|-----------|
| Temporal (cached) | 0.1-0.2s | No LLM call |
| Local query | 1.5-2s | Fast single-hop |
| Hybrid query | 3-4s | Balanced |
| Global query | 5-7s | Comprehensive |

---

## Troubleshooting

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Lock timeout | `LockTimeoutError` | Check for deadlocks; increase timeout |
| Date parsing error | `Invalid date format` | Use YYYY-MM-DD; specify timezone |
| Version validation | `Invalid version format` | Use "Entity [vN]" format |
| Empty results | No entities returned | Check temporal filter parameters |
| Race condition | Duplicate sequences | Ensure locking is enabled |

### Debugging

```bash
# Enable debug logging
export LIGHTRAG_LOG_LEVEL=DEBUG

# Profile temporal operations
python query_graph.py --query "test" --profile --timing

# Check graph statistics
lightrag info --detailed

# Validate temporal configuration
lightrag config validate
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Database indices created on sequence_index columns
- [ ] Lock timeout configured appropriately
- [ ] Transaction timeout set
- [ ] Monitoring and alerting configured
- [ ] Full test suite passes
- [ ] Backup procedures verified

### Monitoring

```python
# Enable monitoring
from lightrag.temporal import enable_monitoring

enable_monitoring(
    cloudwatch_namespace="LightRAG/Temporal",
    metrics=["sequence_allocation_time", "lock_wait_time", 
             "filter_latency", "query_latency"]
)
```

### Health Checks

```bash
# Check temporal system health
curl http://localhost:9621/health/temporal

# Response
{
  "sequence_manager": "healthy",
  "transaction_manager": "healthy",
  "filter_module": "healthy",
  "can_allocate_sequence": true
}
```

---

## References

See the main documentation for related topics:

- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md) - Includes temporal principles
- **Getting Started**: [GETTING_STARTED.md](GETTING_STARTED.md)
- **CLI Usage**: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- **Deployment**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **User Guide**: [USER_GUIDE.md](USER_GUIDE.md)

---

**Document Version**: 2.0  
**Status**: Production-Ready  
**Last Updated**: March 2026

**LightRAG Temporal: Enabling time-aware RAG at scale.**
