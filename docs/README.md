# LightRAG Documentation

Welcome to LightRAG documentation. This folder contains comprehensive guides for understanding, deploying, and using LightRAG's temporal RAG capabilities.

## Documentation Structure (Consolidated)

### Quick Start
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Five-minute setup guide
  - Prerequisites and installation
  - Quick setup in 5 steps
  - Common tasks (upload, query, version)
  - Testing procedures
  - Troubleshooting basics

### Core Concepts
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, principles, and data flow
  - Split-Node architecture
  - Sequence-First approach
  - Integration points
  - Configuration options

- **[RETRIEVAL_LOGIC.md](RETRIEVAL_LOGIC.md)** - Temporal filtering algorithm
  - Max-Sequence algorithm
  - Vector search → Filtering → Generation pipeline
  - Edge case handling
  - Performance considerations

### User Guides
- **[USER_GUIDE.md](USER_GUIDE.md)** - Complete user workflow (consolidated)
  - All 4 workflow phases (Prepare → Upload → Build → Query)
  - All upload options (Web UI, API, SDK, CLI)
  - Query modes: Local, Global, Hybrid, Temporal
  - Response formatting: Quantitative vs Qualitative
  - Best practices and advanced usage
  - Performance tuning and troubleshooting

### Deployment & Setup
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - All deployment options (consolidated)
  - Local development setup
  - Docker/Docker Compose deployment
  - Offline deployment
  - Kubernetes deployment with Helm
  - LLM backend configuration (OpenAI, Anthropic, Ollama, Azure)
  - Storage backend configuration (NetworkX, Neo4j, MongoDB, PostgreSQL)
  - Production architecture
  - Performance tuning by deployment scenario

### API & Integration
- **[API_REFERENCE.md](API_REFERENCE.md)** - Complete API endpoints and specifications (consolidated)
  - All endpoints: `/upload`, `/query`, `/health`, `/stats`, `/entities`, `/graph`
  - Request/response schemas with examples
  - Error handling and rate limiting
  - Batch operations and pagination
  - WebSocket support
  - SDK support (Python, JavaScript)
  - Migration from non-temporal API

### Advanced Topics
- **[PROFILING_GUIDE.md](PROFILING_GUIDE.md)** - Performance analysis and profiling
  - cProfile-based function profiling
  - Timing breakdown analysis
  - Memory profiling utilities
  - Query and ingestion profiling examples
  - Best practices for performance optimization

- **[PROFILING_QUICK_REFERENCE.md](PROFILING_QUICK_REFERENCE.md)** - Quick profiling reference
  - One-liner commands for common tasks
  - Using profiling decorators and context managers
  - Interpreting profiling output
  - Pro tips and troubleshooting

- **[LightRAG_concurrent_explain.md](LightRAG_concurrent_explain.md)** - Concurrency strategy
  - Document-level control
  - Chunk-level control
  - Graph-level control
  - LLM-level prioritization
  - Performance recommendations

- **[UV_LOCK_GUIDE.md](UV_LOCK_GUIDE.md)** - Dependency management
  - uv.lock file format
  - When it updates
  - Common workflows
  - Git practices

- **[Algorithm.md](Algorithm.md)** - External resource references
  - Indexing flowchart
  - Retrieval and querying flowchart

## Quick Navigation

### By Use Case

**I want to...**

- **Get started quickly** → Start with [GETTING_STARTED.md](GETTING_STARTED.md)
- **Use LightRAG (all features)** → See [USER_GUIDE.md](USER_GUIDE.md)
- **Deploy LightRAG** → Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Understand the architecture** → Read [ARCHITECTURE.md](ARCHITECTURE.md)
- **Integrate via API** → Check [API_REFERENCE.md](API_REFERENCE.md)
- **Profile and optimize performance** → See [PROFILING_GUIDE.md](PROFILING_GUIDE.md) and [PROFILING_QUICK_REFERENCE.md](PROFILING_QUICK_REFERENCE.md)
- **Optimize concurrency** → Review [LightRAG_concurrent_explain.md](LightRAG_concurrent_explain.md)
- **Manage dependencies** → See [UV_LOCK_GUIDE.md](UV_LOCK_GUIDE.md)

### By Role

**New User / Evaluator**
1. [GETTING_STARTED.md](GETTING_STARTED.md) - Five-minute setup
2. [USER_GUIDE.md](USER_GUIDE.md) - Learn all features
3. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deploy to your environment

**System Architect**
1. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
2. [RETRIEVAL_LOGIC.md](RETRIEVAL_LOGIC.md) - Algorithm details
3. [PROFILING_GUIDE.md](PROFILING_GUIDE.md) - Performance optimization
4. [LightRAG_concurrent_explain.md](LightRAG_concurrent_explain.md) - Concurrency tuning

**DevOps / Platform Engineer**
1. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deployment setup
2. [PROFILING_GUIDE.md](PROFILING_GUIDE.md) - Performance monitoring
3. [ARCHITECTURE.md](ARCHITECTURE.md) - System understanding
4. [UV_LOCK_GUIDE.md](UV_LOCK_GUIDE.md) - Dependency management

**Application Developer**
1. [USER_GUIDE.md](USER_GUIDE.md) - Getting started
2. [API_CHANGES.md](API_CHANGES.md) - API integration
3. [temporal_guide.md](temporal_guide.md) - Feature overview

**End User**
1. [USER_GUIDE.md](USER_GUIDE.md) - Start here
2. [FrontendBuildGuide.md](FrontendBuildGuide.md) - Frontend setup

## Key Features

### Temporal RAG
- **Version History:** Maintains separate entity versions across document revisions
- **Sequence-First:** Simple sequence indices for deterministic ordering
- **Soft Tagging:** Effective dates embedded in content for LLM interpretation
- **Audit Trails:** Complete history with SUPERSEDES relationships
- **Time-Travel Queries:** Retrieve information as it existed at any point

### Architectural Innovations
- **Split-Node Strategy:** Each version is a separate entity node
- **Soft Tagging:** Temporal context via XML tags in content
- **Sequence-First Logic:** Primary ordering by insertion sequence
- **Content-Centric:** All temporal information in content, not metadata
- **LLM-Interpreted Dates:** Soft dates (not hard filters) for flexibility

### Performance Optimizations
- **Hierarchical Chunking:** Smart YAML block optimization (21% reduction)
- **Vector Search:** Efficient similarity matching on versioned entities
- **Caching:** Reference-date-aware cache keys
- **Concurrent Processing:** Layered concurrency control at document/chunk/LLM levels

## System Capabilities

| Capability | Status | Reference |
|-----------|--------|-----------|
| Document Sequencing | ✅ | [temporal_guide.md](temporal_guide.md#1-data-sequencing-module) |
| Versioned Entities | ✅ | [temporal_guide.md](temporal_guide.md#2-versioned-entity-extraction) |
| Temporal Queries | ✅ | [temporal_guide.md](temporal_guide.md#3-temporal-query-mode) |
| Web UI Staging | ✅ | [temporal_guide.md](temporal_guide.md#4-frontend-staging-area) |
| Domain Personas | ✅ | [temporal_guide.md](temporal_guide.md#5-persona-alignment) |
| Soft Tagging | ✅ | [temporal_guide.md](temporal_guide.md#6-sequence-first-logic-with-soft-tagging) |
| Airline Specialization | ✅ | [temporal_guide.md](temporal_guide.md#7-airline-domain-specialization) |
| Hierarchical Chunking | ✅ | [temporal_guide.md](temporal_guide.md#8-hierarchical-markdown-yaml-chunking) |

## Testing

All components include comprehensive test suites:

```bash
# Unit tests
uv run test_prep.py              # Data sequencing
uv run test_ingest.py            # Entity versioning
uv run test_temporal.py          # Temporal queries
uv run test_temporal_persona.py  # Response formatting
uv run test_soft_tags.py         # Soft tagging

# Integration test
uv run demo_temporal_rag.py      # End-to-end demonstration

# Chunking tests
python -m pytest tests/test_hierarchical_chunker.py -v
```

## Configuration

### Environment Variables

```bash
# Temporal Settings
LIGHTRAG_TEMPORAL_ENABLED=true
LIGHTRAG_SEQUENCE_FIRST=true

# Chunking
CHUNK_SIZE=2000
CHUNK_OVERLAP_SIZE=200

# LLM Concurrency
MAX_ASYNC=4
MAX_PARALLEL_INSERT=2
```

### Configuration File

See `config.ini` for persistent settings:

```ini
[temporal]
enabled = true
sequence_first = true
track_effective_dates = true
max_versions_per_entity = 10
```

## Troubleshooting

### Common Issues

**Q: Versioned entities not being created**
- Check `sequence_index` in metadata (must be > 0)
- Verify LLM follows versioning prompt instructions
- See [temporal_guide.md - Entity Versioning](temporal_guide.md#2-versioned-entity-extraction)

**Q: Temporal queries returning unexpected results**
- Confirm `reference_date` format (YYYY-MM-DD)
- Check `<EFFECTIVE_DATE>` tags in entity content
- Review [RETRIEVAL_LOGIC.md](RETRIEVAL_LOGIC.md) edge cases

**Q: Docker container not starting**
- Verify `.env` configuration
- Check Docker resource limits
- See [DockerDeployment.md](DockerDeployment.md)

**Q: Offline deployment missing packages**
- Run `lightrag-download-cache`
- Use `pip download` with offline extras
- See [OfflineDeployment.md](OfflineDeployment.md)

## Performance Tuning

### For Large Datasets
- Increase `CHUNK_SIZE` to 3000-4000 tokens
- Set `MAX_ASYNC` based on LLM concurrency capacity
- Use hierarchical chunking for structured documents
- See [LightRAG_concurrent_explain.md](LightRAG_concurrent_explain.md)

### For Real-Time Queries
- Enable caching (cache keys include `reference_date`)
- Use `hybrid` mode instead of `temporal` if date filtering not needed
- Pre-optimize chunks with hierarchical chunking
- See [ARCHITECTURE.md - Scalability](ARCHITECTURE.md#4-scalability)

## Contributing

When adding documentation:
1. Follow the structure above
2. Use mermaid diagrams for workflows
3. Include code examples
4. Link to related docs
5. Update this README if adding new sections

## Resources

- **Main Repository:** [LightRAG on GitHub](https://github.com/HKUDS/LightRAG)
- **Main README:** [../README.md](../README.md)
- **CLI Tools:** [../CLI_TOOLS_README.md](../CLI_TOOLS_README.md)
- **Examples:** [../examples/](../examples/)

## Version

Documentation updated for LightRAG v1.0.0+

**Last Updated:** January 19, 2026
