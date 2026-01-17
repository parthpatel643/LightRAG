## Sprint 2: Versioned Entity Extraction

### Overview
Sprint 2 modifies LightRAG's entity extraction pipeline to support **temporal versioning** of entities. Instead of merging entities with the same name across different document versions, the system now creates separate versioned entities (e.g., `Parking Fee [v1]`, `Parking Fee [v2]`).

### What Was Modified

#### 1. **Data Schema Extensions** (`lightrag/base.py`)
Added temporal metadata fields to `TextChunkSchema`:
```python
class TextChunkSchema(TypedDict):
    tokens: int
    content: str
    full_doc_id: str
    chunk_order_index: int
    # New temporal metadata fields
    sequence_index: int      # Version number (1, 2, 3...)
    effective_date: str      # Document effective date
    doc_type: str           # Document type (base, amendment, etc.)
```

#### 2. **Insert API Updates** (`lightrag/lightrag.py`)
Updated `insert()` and `ainsert()` signatures to accept metadata:
```python
def insert(
    self,
    input: str | list[str],
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
    metadata: dict | list[dict] | None = None,  # NEW
) -> str:
```

**Metadata format:**
```python
metadata = {
    "sequence_index": 1,
    "effective_date": "2023-01-01",
    "doc_type": "base"
}
```

#### 3. **Metadata Propagation**
- Metadata flows from `insert()` → `apipeline_enqueue_documents()` → `full_docs` storage → document chunks
- Each chunk now carries temporal metadata from its source document

#### 4. **Versioned Entity Extraction** (`lightrag/operate.py`)
Modified `extract_entities()` to inject versioning instructions into the LLM prompt:

```python
# Extract metadata from chunk
sequence_index = chunk_dp.get("sequence_index", 0)

# Inject versioning instruction
versioning_instruction = f"""
**CRITICAL VERSIONING INSTRUCTION:**
You MUST append ' [v{sequence_index}]' to EVERY entity name you extract.
"""

# Add to system prompt
entity_extraction_system_prompt = PROMPTS["entity_extraction_system_prompt"].format(**context_base) + versioning_instruction
```

This instructs the LLM to append version suffixes to all extracted entity names.

### Files Created

1. **`test_ingest.py`** - Validation script that:
   - Creates two contract versions
   - Inserts them with different `sequence_index` values
   - Verifies that separate versioned entities are created
   - Tests querying across versions

2. **`demo_temporal_rag.py`** - Complete demo combining Sprint 1 & 2:
   - Uses `ContractSequencer` to prepare data (Sprint 1)
   - Inserts versioned documents into LightRAG (Sprint 2)
   - Demonstrates temporal queries

### Usage Example

```python
from lightrag import LightRAG
from data_prep import ContractSequencer

# Sprint 1: Sequence your documents
sequencer = ContractSequencer(
    files=["Base.md", "Amendment1.md"],
    order=["Base.md", "Amendment1.md"]
)
sequenced_docs = sequencer.prepare_for_ingestion()

# Sprint 2: Insert with metadata
rag = LightRAG(working_dir="./rag_storage")

for doc in sequenced_docs:
    await rag.ainsert(
        input=doc["content"],
        file_paths=doc["metadata"]["source"],
        metadata=doc["metadata"]  # Contains sequence_index, date, type
    )
```

### Expected Behavior

**Before Sprint 2:**
- "Parking Fee" mentioned in Base.md → Entity: `Parking Fee`
- "Parking Fee" mentioned in Amendment1.md → Entity: `Parking Fee` (merged)
- Result: Single entity with combined information

**After Sprint 2:**
- "Parking Fee" in Base.md (sequence=1) → Entity: `Parking Fee [v1]`
- "Parking Fee" in Amendment1.md (sequence=2) → Entity: `Parking Fee [v2]`
- Result: Two distinct entities, each with version-specific information

### Testing

Run the test script:
```bash
uv run test_ingest.py
```

Run the complete demo:
```bash
uv run demo_temporal_rag.py
```

### Key Benefits

1. **Temporal Awareness**: The knowledge graph now preserves the evolution of entities over time
2. **Version-Specific Queries**: Can ask "What was X in version 1?" or "How did X change?"
3. **No Information Loss**: Each version maintains its own context and relationships
4. **Audit Trail**: The `effective_date` and `doc_type` metadata provide temporal context

### Integration with Sprint 1

Sprint 2 seamlessly integrates with Sprint 1's `ContractSequencer`:
- Sprint 1 output provides the exact metadata format Sprint 2 expects
- `sequence_index` from Sprint 1 drives the versioning in Sprint 2
- Combined workflow enables end-to-end temporal document processing

### Next Steps (Future Sprints)

Potential enhancements:
- **Temporal Query Language**: Specialized query syntax for version-specific retrieval
- **Version Comparison**: Automatic diff between entity versions
- **Temporal Aggregation**: Roll-up queries across all versions
- **Supersession Logic**: Mark which entities supersede others
- **Time-Travel Queries**: "What was the state as of date X?"

### Limitations & Considerations

1. **LLM Compliance**: The versioning depends on the LLM following the prompt instructions to append `[vN]` suffixes
2. **Storage Overhead**: Each version creates a separate entity, increasing storage requirements
3. **Query Complexity**: Users need to be aware of versioning when formulating queries
4. **Cache Impact**: Versioning instructions modify prompts, which may affect LLM response caching

### Troubleshooting

If versioned entities aren't appearing:
1. Check LightRAG logs for entity extraction output
2. Verify metadata is being passed correctly in the `insert()` call
3. Ensure `sequence_index > 0` (versioning only applies when index is set)
4. Inspect `full_docs` storage to confirm metadata persistence
5. Review LLM responses to see if version suffixes are present

---

**Sprint 2 Status**: ✅ Complete

This implementation provides the foundation for temporal knowledge graph operations in LightRAG.
