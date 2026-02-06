# AWS DocumentDB and Neptune Storage Implementation

This document summarizes the implementation of AWS DocumentDB and Neptune storage backends for LightRAG.

## Implementation Overview

### 1. DocumentDB Implementation (`lightrag/kg/documentdb_impl.py`)

AWS DocumentDB is fully MongoDB-compatible, so the implementation provides convenience wrappers that:
- Map `DOCUMENTDB_*` environment variables to `MONGO_*` variables
- Use the existing MongoDB storage implementations
- Allow users to explicitly use DocumentDB with clear environment variable names

**Classes:**
- `DocumentDBKVStorage` - Key-value storage (alias for MongoKVStorage)
- `DocumentDBDocStatusStorage` - Document status storage (alias for MongoDocStatusStorage)
- `DocumentDBVectorDBStorage` - Vector storage (alias for MongoVectorDBStorage)

**Environment Variables:**
```bash
DOCUMENTDB_ENDPOINT=your-cluster.us-east-1.docdb.amazonaws.com
DOCUMENTDB_PORT=27017
DOCUMENTDB_DATABASE=LightRAG
DOCUMENTDB_USERNAME=your-username
DOCUMENTDB_PASSWORD=your-password
DOCUMENTDB_SSL=true
DOCUMENTDB_WORKSPACE=optional-workspace-name  # Optional
```

### 2. Neptune Implementation (`lightrag/kg/neptune_impl.py`)

AWS Neptune graph database implementation using Gremlin (Apache TinkerPop) API.

**Class:**
- `NeptuneGraphStorage` - Graph storage using Gremlin traversals

**Features:**
- Workspace isolation using ID prefixes
- Asynchronous operations with asyncio
- Support for all BaseGraphStorage abstract methods
- Batch operations for better performance

**Environment Variables:**
```bash
NEPTUNE_ENDPOINT=your-cluster.us-east-1.neptune.amazonaws.com
NEPTUNE_PORT=8182
NEPTUNE_USE_SSL=true
NEPTUNE_IAM_AUTH=false
NEPTUNE_WORKSPACE=optional-workspace-name  # Optional
```

## Registry Updates

Updated `lightrag/kg/__init__.py` to register new storage implementations:

1. **STORAGE_IMPLEMENTATIONS**: Added DocumentDB and Neptune classes to appropriate storage types
2. **STORAGE_ENV_REQUIREMENTS**: Added environment variable requirements for each implementation
3. **STORAGES**: Added module mappings for new implementations

## Dependency Updates

Added `gremlinpython>=3.7.0,<4.0.0` to `pyproject.toml` in the `offline-storage` optional dependencies.

## Configuration Files

### `.env.example`
Added complete DocumentDB and Neptune configuration examples with all available options.

### `config.ini.example`
Added DocumentDB and Neptune sections with configuration parameters.

## Usage Examples

### Using DocumentDB

```python
from lightrag import LightRAG

# Initialize with DocumentDB storage
rag = LightRAG(
    working_dir="./rag_storage",
    kv_storage="DocumentDBKVStorage",
    vector_storage="DocumentDBVectorDBStorage",
    graph_storage="MongoGraphStorage",  # Can also use MongoDB for graph
    doc_status_storage="DocumentDBDocStatusStorage",
)
```

### Using Neptune

```python
from lightrag import LightRAG

# Initialize with Neptune graph storage
rag = LightRAG(
    working_dir="./rag_storage",
    kv_storage="MongoKVStorage",  # Use MongoDB for KV
    vector_storage="MongoVectorDBStorage",  # Use MongoDB for vectors
    graph_storage="NeptuneGraphStorage",  # Use Neptune for graph
    doc_status_storage="MongoDocStatusStorage",  # Use MongoDB for doc status
)
```

### Full AWS Stack

```python
from lightrag import LightRAG

# Use DocumentDB for KV/Vector/DocStatus and Neptune for Graph
rag = LightRAG(
    working_dir="./rag_storage",
    kv_storage="DocumentDBKVStorage",
    vector_storage="DocumentDBVectorDBStorage",
    graph_storage="NeptuneGraphStorage",
    doc_status_storage="DocumentDBDocStatusStorage",
)
```

## Migration Path

For users migrating from local storage to AWS:

1. **Export existing data** using the JSON/NetworkX implementations
2. **Set up AWS resources**:
   - Create DocumentDB cluster
   - Create Neptune cluster
   - Configure security groups and VPC
3. **Update environment variables** to point to AWS resources
4. **Import data** into DocumentDB and Neptune
5. **Update storage configuration** in LightRAG initialization

## Testing

Test the implementations with:

```bash
# Set environment variables
export DOCUMENTDB_ENDPOINT=your-cluster.docdb.amazonaws.com
export DOCUMENTDB_PORT=27017
export DOCUMENTDB_DATABASE=LightRAG
export DOCUMENTDB_USERNAME=your-username
export DOCUMENTDB_PASSWORD=your-password
export DOCUMENTDB_SSL=true

export NEPTUNE_ENDPOINT=your-cluster.neptune.amazonaws.com
export NEPTUNE_PORT=8182
export NEPTUNE_USE_SSL=true

# Run tests
python -m pytest tests/ --run-integration
```

## Implementation Notes

### DocumentDB
- DocumentDB is 100% MongoDB-compatible, so we reuse MongoDB implementations
- Environment variable mapping happens at module load time
- SSL/TLS is enabled by default for security
- Connection pooling is configured for optimal performance

### Neptune
- Uses Gremlin Python client for graph traversals
- Implements workspace isolation via ID prefixes
- All operations are wrapped with asyncio.to_thread() since Gremlin client is synchronous
- Supports both vertex (node) and edge operations
- Implements all required BaseGraphStorage abstract methods

## Limitations

### DocumentDB
- Vector search capabilities may differ from MongoDB Atlas
- Some advanced MongoDB features may not be available
- Ensure your DocumentDB version supports required features

### Neptune
- Gremlin client is synchronous, so operations use asyncio.to_thread()
- No built-in fuzzy search - uses contains() or exact match
- IAM authentication not yet implemented (can be added)
- Large graph operations may require optimization

## Future Enhancements

1. **Migration Tools**: Create automated migration scripts from JSON/NetworkX to DocumentDB/Neptune
2. **Performance Optimization**: Implement Neptune-specific bulk operations
3. **IAM Authentication**: Add support for Neptune IAM authentication
4. **Monitoring**: Add CloudWatch metrics integration
5. **Caching**: Implement query result caching for frequently accessed data
6. **Backup/Restore**: Add utilities for backup and restore operations

## Related Files

- Implementation: `lightrag/kg/documentdb_impl.py`, `lightrag/kg/neptune_impl.py`
- Registry: `lightrag/kg/__init__.py`
- Dependencies: `pyproject.toml`
- Configuration: `env.example`, `config.ini.example`
- Documentation: `plan.md` (migration plan)
