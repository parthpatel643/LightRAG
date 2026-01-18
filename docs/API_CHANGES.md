# API Changes for Temporal Features

## Overview

This document describes the custom parameters added to LightRAG's FastAPI endpoints to support temporal querying and version-aware knowledge management. All endpoints maintain backward compatibility with non-temporal usage.

---

## API Base URL

**Local Development:**
```
http://localhost:8020
```

**Production (if deployed):**
```
https://your-domain.com/api
```

---

## Endpoint: `POST /upload`

Upload documents to the knowledge graph with sequence metadata.

### Request

**Endpoint:**
```
POST /upload
```

**Headers:**
```
Content-Type: multipart/form-data
```

**Parameters:**

| Parameter       | Type   | Required | Description                                                              |
|----------------|--------|----------|--------------------------------------------------------------------------|
| `file`         | File   | Yes      | The document file to upload (PDF, TXT, DOCX, etc.)                       |
| `sequence_map` | JSON   | No       | Mapping of filenames to sequence indices: `{"filename": index}`          |
| `working_dir`  | String | No       | Target directory for storing the knowledge graph (default: `./rag_storage`) |
| `doc_type`     | String | No       | Document type tag (e.g., "contract", "amendment", "policy")              |

### `sequence_map` Parameter Details

**Purpose:** Assign explicit sequence indices to documents to establish temporal ordering.

**Format:**
```json
{
  "contract_2023.pdf": 1,
  "amendment_2024_Q2.pdf": 2,
  "amendment_2024_Q4.pdf": 3,
  "latest_rates_2025.pdf": 4
}
```

**Behavior:**
- **If provided:** Uses the specified sequence indices
- **If omitted:** Auto-assigns sequential indices based on upload order
- **If partial:** Specified files get explicit indices, others auto-assigned

**Validation:**
- Indices must be positive integers
- Duplicates are rejected with HTTP 400 error
- Gaps in sequence are allowed (e.g., 1, 3, 7)

### Examples

#### Example 1: Single File Upload with Sequence

**cURL:**
```bash
curl -X POST "http://localhost:8020/upload" \
  -F "file=@contract_2023.pdf" \
  -F "sequence_map={\"contract_2023.pdf\": 1}" \
  -F "working_dir=data/output/contracts"
```

**Python (requests):**
```python
import requests

files = {"file": open("contract_2023.pdf", "rb")}
data = {
    "sequence_map": '{"contract_2023.pdf": 1}',
    "working_dir": "data/output/contracts"
}

response = requests.post("http://localhost:8020/upload", files=files, data=data)
print(response.json())
```

**Response:**
```json
{
  "status": "success",
  "filename": "contract_2023.pdf",
  "sequence_index": 1,
  "entities_created": 23,
  "relationships_created": 45,
  "working_dir": "data/output/contracts"
}
```

#### Example 2: Batch Upload with Sequence Map

**Python:**
```python
import requests

files = [
    ("file", open("contract_2023.pdf", "rb")),
    ("file", open("amendment_2024.pdf", "rb")),
]

sequence_map = {
    "contract_2023.pdf": 1,
    "amendment_2024.pdf": 2
}

data = {
    "sequence_map": json.dumps(sequence_map),
    "working_dir": "data/output/contracts"
}

response = requests.post("http://localhost:8020/upload", files=files, data=data)
```

#### Example 3: Upload Without Sequence (Auto-Assign)

**cURL:**
```bash
curl -X POST "http://localhost:8020/upload" \
  -F "file=@document.pdf" \
  -F "working_dir=data/output/general"
```

**Response:**
```json
{
  "status": "success",
  "filename": "document.pdf",
  "sequence_index": 1,
  "note": "Auto-assigned sequence index"
}
```

---

## Endpoint: `POST /query`

Query the knowledge graph with temporal filtering.

### Request

**Endpoint:**
```
POST /query
```

**Headers:**
```
Content-Type: application/json
```

**Body (JSON):**

| Parameter        | Type     | Required | Description                                                              |
|-----------------|----------|----------|--------------------------------------------------------------------------|
| `query`         | String   | Yes      | The natural language question                                            |
| `mode`          | Enum     | No       | Query mode (default: `"hybrid"`)                                         |
| `reference_date`| String   | No       | Temporal filter date in `YYYY-MM-DD` format                              |
| `working_dir`   | String   | No       | Directory containing the knowledge graph (default: `./rag_storage`)      |
| `top_k`         | Integer  | No       | Number of candidate results to retrieve (default: `20`)                  |

### `mode` Parameter Details

**Allowed Values:**

| Mode          | Description                                                                    |
|---------------|--------------------------------------------------------------------------------|
| `naive`       | Simple vector search without graph traversal (baseline)                        |
| `local`       | Single-hop graph retrieval (fast, entity-focused)                              |
| `global`      | Multi-hop graph traversal (comprehensive, slower)                              |
| `hybrid`      | Combines local and global search (balanced)                                    |
| `temporal`    | Version-aware retrieval with max-sequence filtering                            |

**Default:** `hybrid`

### `reference_date` Parameter Details

**Purpose:** Retrieve information as it existed on a specific date.

**Format:** `YYYY-MM-DD` (ISO 8601)

**Behavior:**
- **With `mode=temporal`:**
  - Filters entities to those with `effective_date <= reference_date`
  - Selects max sequence among valid candidates
  
- **Without `mode=temporal`:**
  - Parameter ignored (warning logged)

- **If omitted in temporal mode:**
  - Returns absolute latest version (highest sequence)

**Validation:**
- Must be a valid date
- Can be in the past or future
- Timezone is ignored (date-only comparison)

### Examples

#### Example 1: Basic Temporal Query

**Request:**
```json
POST /query
{
  "query": "What is the parking fee for Boeing 787?",
  "mode": "temporal",
  "working_dir": "data/output/contracts"
}
```

**Response:**
```json
{
  "answer": "The parking fee for Boeing 787 aircraft is $100 per night (Sequence 2, Effective 2025-06-15).",
  "mode": "temporal",
  "sources": [
    {
      "entity_name": "Parking Fee [v2]",
      "sequence_index": 2,
      "effective_date": "2025-06-15",
      "source_file": "amendment_2024.pdf",
      "similarity_score": 0.91
    }
  ],
  "metadata": {
    "total_candidates": 5,
    "filtered_results": 1,
    "query_time_ms": 234
  }
}
```

#### Example 2: Temporal Query with Reference Date

**Request:**
```json
POST /query
{
  "query": "What was the lavatory service fee?",
  "mode": "temporal",
  "reference_date": "2024-12-31",
  "working_dir": "data/output/contracts"
}
```

**Response:**
```json
{
  "answer": "As of December 31, 2024, the lavatory service fee was $75 per service (Sequence 3, Effective 2024-12-01).",
  "mode": "temporal",
  "reference_date": "2024-12-31",
  "sources": [
    {
      "entity_name": "Lavatory Service Fee [v3]",
      "sequence_index": 3,
      "effective_date": "2024-12-01",
      "source_file": "rates_2025.pdf"
    }
  ],
  "temporal_status": "valid",
  "note": "A newer version (v4) exists with effective date 2025-06-15."
}
```

#### Example 3: Complex Multi-Entity Temporal Query

**Request:**
```json
POST /query
{
  "query": "What are the latest rates for Boeing 787 flights that remain overnight and undergo cabin cleaning with lavatory service?",
  "mode": "temporal",
  "reference_date": "2025-01-15",
  "working_dir": "data/output/contracts",
  "top_k": 30
}
```

**Response:**
```json
{
  "answer": "For Boeing 787 aircraft with overnight stays requiring cabin cleaning and lavatory service:\n\n- Parking Fee: $100 per night (Seq 2)\n- Cabin Cleaning: $500 per service (Seq 3)\n- Lavatory Service: $75 per service (Seq 3)\n\nTotal estimated cost: $675 per overnight stay.",
  "mode": "temporal",
  "reference_date": "2025-01-15",
  "sources": [
    {
      "entity_name": "Parking Fee [v2]",
      "sequence_index": 2,
      "effective_date": "2025-06-15",
      "temporal_status": "future"
    },
    {
      "entity_name": "Cabin Cleaning Fee [v3]",
      "sequence_index": 3,
      "effective_date": "2024-12-01",
      "temporal_status": "valid"
    },
    {
      "entity_name": "Lavatory Service Fee [v3]",
      "sequence_index": 3,
      "effective_date": "2024-12-01",
      "temporal_status": "valid"
    }
  ],
  "warnings": [
    "Parking Fee has a future effective date. Current rate may differ."
  ]
}
```

#### Example 4: Non-Temporal Query (Baseline)

**Request:**
```json
POST /query
{
  "query": "What is the parking fee?",
  "mode": "hybrid",
  "working_dir": "data/output/contracts"
}
```

**Response:**
```json
{
  "answer": "The parking fee is mentioned in multiple documents with varying amounts ($50, $75, $100).",
  "mode": "hybrid",
  "sources": [
    {"entity_name": "Parking Fee [v1]", "content": "$50..."},
    {"entity_name": "Parking Fee [v2]", "content": "$100..."}
  ],
  "note": "Multiple versions found. Use mode=temporal for version-aware results."
}
```

---

## Error Responses

### 400 Bad Request

**Scenario 1: Invalid sequence_map**
```json
{
  "error": "Invalid sequence_map format",
  "detail": "Expected JSON object with string keys and integer values",
  "example": "{\"file.pdf\": 1}"
}
```

**Scenario 2: Invalid mode**
```json
{
  "error": "Invalid mode parameter",
  "detail": "Mode must be one of: naive, local, global, hybrid, temporal",
  "provided": "invalid_mode"
}
```

**Scenario 3: Invalid reference_date**
```json
{
  "error": "Invalid reference_date format",
  "detail": "Date must be in YYYY-MM-DD format",
  "provided": "2025/01/01"
}
```

### 404 Not Found

**Scenario: Working directory doesn't exist**
```json
{
  "error": "Working directory not found",
  "path": "data/output/nonexistent",
  "suggestion": "Verify the working_dir path or upload documents first"
}
```

### 500 Internal Server Error

**Scenario: Graph construction failed**
```json
{
  "error": "Graph construction failed",
  "detail": "LLM service unavailable",
  "retry": true
}
```

---

## Additional Endpoints

### `GET /health`

Check API server status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "temporal_enabled": true,
  "graph_backend": "NetworkX"
}
```

### `GET /stats`

Get statistics about the knowledge graph.

**Query Parameters:**
- `working_dir` (optional): Target graph directory

**Response:**
```json
{
  "working_dir": "data/output/contracts",
  "total_entities": 87,
  "versioned_entities": 23,
  "total_relationships": 142,
  "sequence_range": {
    "min": 1,
    "max": 4
  },
  "effective_date_range": {
    "earliest": "2023-01-01",
    "latest": "2025-12-31"
  }
}
```

### `DELETE /graph`

Delete a knowledge graph.

**Query Parameters:**
- `working_dir` (required): Directory to delete

**Response:**
```json
{
  "status": "deleted",
  "working_dir": "data/output/contracts",
  "entities_removed": 87,
  "relationships_removed": 142
}
```

---

## Rate Limiting

**Default Limits:**
- Upload: 10 requests/minute
- Query: 60 requests/minute

**Headers (returned in responses):**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1640995200
```

---

## Authentication (If Enabled)

**API Key Header:**
```
Authorization: Bearer YOUR_API_KEY
```

**Example:**
```bash
curl -X POST "http://localhost:8020/query" \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the fee?", "mode": "temporal"}'
```

---

## WebSocket Support (Future)

**Planned for v2.0:**
- Real-time query streaming
- Live graph update notifications
- Multi-turn conversational queries

**Endpoint (upcoming):**
```
ws://localhost:8020/ws/query
```

---

## SDK Support

### Python SDK

```python
from lightrag.client import LightRAGClient

client = LightRAGClient(base_url="http://localhost:8020")

# Upload with sequence
client.upload(
    file_path="contract.pdf",
    sequence_index=1,
    working_dir="data/output/contracts"
)

# Temporal query
result = client.query(
    query="What is the fee?",
    mode="temporal",
    reference_date="2025-01-01",
    working_dir="data/output/contracts"
)

print(result.answer)
print(result.sources)
```

### JavaScript SDK

```javascript
import { LightRAGClient } from '@lightrag/sdk';

const client = new LightRAGClient({ baseUrl: 'http://localhost:8020' });

// Upload
await client.upload({
  file: fileBlob,
  sequenceMap: { 'contract.pdf': 1 },
  workingDir: 'data/output/contracts'
});

// Query
const result = await client.query({
  query: 'What is the fee?',
  mode: 'temporal',
  referenceDate: '2025-01-01',
  workingDir: 'data/output/contracts'
});

console.log(result.answer);
```

---

## Migration from Non-Temporal API

### Backward Compatibility

**Existing queries work without changes:**
```json
// Old API (still works)
POST /query
{
  "query": "What is the fee?",
  "mode": "hybrid"
}

// Response: Standard hybrid search (no temporal filtering)
```

### Gradual Adoption

1. **Start uploading with sequences:**
   ```json
   POST /upload
   {
     "file": "...",
     "sequence_map": {"file.pdf": 1}
   }
   ```

2. **Test with temporal queries:**
   ```json
   POST /query
   {
     "query": "...",
     "mode": "temporal"
   }
   ```

3. **Add reference dates when needed:**
   ```json
   POST /query
   {
     "query": "...",
     "mode": "temporal",
     "reference_date": "2025-01-01"
   }
   ```

---

## OpenAPI Specification

**Swagger UI:**
```
http://localhost:8020/docs
```

**ReDoc:**
```
http://localhost:8020/redoc
```

**Download OpenAPI JSON:**
```
http://localhost:8020/openapi.json
```

---

## Next Steps

- **Understand the architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Learn retrieval logic**: See [RETRIEVAL_LOGIC.md](RETRIEVAL_LOGIC.md)
- **User guide**: See [USER_GUIDE.md](USER_GUIDE.md)
- **API server source**: See [lightrag/api/lightrag_server.py](../lightrag/api/lightrag_server.py)

---

**API versioning follows semantic versioning. Breaking changes will increment the major version.**
