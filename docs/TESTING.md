# Testing Structure Overview

## Quick Start

Run all offline tests:
```bash
python -m pytest tests/
```

Run integration tests (requires external services):
```bash
python -m pytest tests/ --run-integration
```

Run specific test file:
```bash
python -m pytest tests/test_versioning.py -v
```

## Test Organization

All tests are located in `/tests/` directory organized by functionality:

### Versioning & Temporal Features
- **[test_versioning.py](tests/test_versioning.py)** - Auto-versioning, temporal queries, soft tags

### Core Features
- **[test_chunking.py](tests/test_chunking.py)** - Document chunking
- **[test_extraction.py](tests/test_extraction.py)** - Entity/relationship extraction
- **[test_hierarchical_chunker.py](tests/test_hierarchical_chunker.py)** - Hierarchical chunking
- **[test_rerank_chunking.py](tests/test_rerank_chunking.py)** - Reranking
- **[test_overlap_validation.py](tests/test_overlap_validation.py)** - Overlap validation

### Backend & Storage
- **[test_graph_storage.py](tests/test_graph_storage.py)** - Graph storage operations
- **[test_postgres_*.py](tests/test_postgres_migration.py)** - PostgreSQL backend
- **[test_qdrant_migration.py](tests/test_qdrant_migration.py)** - Qdrant vector store
- **[test_neo4j_fulltext_index.py](tests/test_neo4j_fulltext_index.py)** - Neo4j graph DB

### Advanced Features
- **[test_lightrag_ollama_chat.py](tests/test_lightrag_ollama_chat.py)** - Ollama integration
- **[test_aquery_data_endpoint.py](tests/test_aquery_data_endpoint.py)** - Query API
- **[test_dimension_mismatch.py](tests/test_dimension_mismatch.py)** - Dimension validation
- **[test_no_model_suffix_safety.py](tests/test_no_model_suffix_safety.py)** - Model safety

### Concurrency & Isolation
- **[test_unified_lock_safety.py](tests/test_unified_lock_safety.py)** - Lock safety
- **[test_workspace_isolation.py](tests/test_workspace_isolation.py)** - Workspace isolation
- **[test_workspace_migration_isolation.py](tests/test_workspace_migration_isolation.py)** - Migration isolation

### Performance & Optimization
- **[test_write_json_optimization.py](tests/test_write_json_optimization.py)** - JSON write optimization
- **[test_token_auto_renewal.py](tests/test_token_auto_renewal.py)** - Token renewal
- **[test_postgres_retry_integration.py](tests/test_postgres_retry_integration.py)** - Retry logic

## Test Markers

Tests use pytest markers for fine-grained control:

```bash
# Only offline tests (default)
python -m pytest tests/ -m "not integration"

# Only integration tests  
python -m pytest tests/ -m integration

# Tests requiring database
python -m pytest tests/ -m requires_db

# Tests requiring API
python -m pytest tests/ -m requires_api
```

## Configuration

See [tests/TEST_CONSOLIDATION.md](tests/TEST_CONSOLIDATION.md) for:
- Detailed test consolidation changes
- Environment setup for integration tests
- Adding new tests
- Test running options
- CLI flags and environment variables

## WebUI Testing

### Graph Features Testing

**Edge Search & Chunks Display**

Test edge relationship search and chunks panel in the browser console:

```javascript
// Test edge search
const store = useGraphStore.getState()
const graph = store.sigmaGraph
console.log('Total edges:', graph.edges().length)

// Select first edge
if (graph.edges().length > 0) {
  const firstEdge = graph.edges()[0]
  store.setSelectedEdge(firstEdge)
  console.log('Edge selected:', firstEdge)
}

// Add test chunks
store.setEdgeChunks(firstEdge, [
  {
    reference_id: 'test-ref-1',
    file_path: '/documents/test.md',
    content: ['Test content for edge relationship'],
    score: 0.9
  }
])
```

**Feature Checklist:**
- [ ] Graph loads successfully
- [ ] Search bar shows both nodes and edges in results
- [ ] Can select edges from search results
- [ ] Selected edge is highlighted in the graph
- [ ] Properties panel appears when node/edge is selected
- [ ] ChunksPanel appears below PropertiesView when chunks are available
- [ ] Can expand/collapse chunks to view content
- [ ] Copy button works to copy chunk content

For detailed WebUI testing procedures, see [WEBUI_FEATURES.md](WEBUI_FEATURES.md).

## Recent Changes

**Test Consolidation (2026-01-20)**

✅ Consolidated all meaningful root-level tests into pytest framework
✅ Removed outdated demo scripts
✅ Created test_versioning.py with comprehensive versioning tests
✅ Added TEST_CONSOLIDATION.md migration guide

See [tests/TEST_CONSOLIDATION.md](tests/TEST_CONSOLIDATION.md) for complete details.

**Last Updated:** March 5, 2026
