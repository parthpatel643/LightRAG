# LightRAG API Reference

Complete REST API documentation for LightRAG temporal RAG system.

---

## Base URL

**Local Development:**
```
http://localhost:9621
```

**Production:**
```
https://your-domain.com
```

---

## Authentication

### API Key (Optional, if enabled)

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:9621/query
```

Set `API_KEY_REQUIRED=true` in .env to enable.

---

## Endpoints

### Health Check

#### `GET /health`

Check server and system status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "temporal_enabled": true,
  "graph_backend": "NetworkX"
}
```

---

### Statistics

#### `GET /stats`

Get knowledge graph statistics.

**Query Parameters:**
- `working_dir` (optional): Target graph directory

**Response:**
```json
{
  "working_dir": "rag_storage",
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

---

### Upload Documents

#### `POST /upload`

Upload files and optionally assign sequence metadata.

**Headers:**
```
Content-Type: multipart/form-data
```

**Body Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | Yes | PDF, TXT, DOCX, etc. |
| `sequence_index` | Integer | No | Document sequence (1, 2, 3...) |
| `effective_date` | String | No | Date in YYYY-MM-DD format |
| `doc_type` | String | No | base, amendment, supplement, etc. |
| `working_dir` | String | No | Storage directory (default: `./rag_storage`) |

**Example:**

```bash
curl -X POST "http://localhost:9621/upload" \
  -F "file=@contract.pdf" \
  -F "sequence_index=1" \
  -F "effective_date=2023-01-01" \
  -F "doc_type=base" \
  -F "working_dir=rag_storage"
```

**Response:**
```json
{
  "status": "success",
  "filename": "contract.pdf",
  "sequence_index": 1,
  "entities_created": 23,
  "relationships_created": 45,
  "working_dir": "rag_storage"
}
```

**Error Responses:**

```json
{
  "error": "Invalid sequence_map format",
  "detail": "Expected JSON object with string keys and integer values",
  "example": "{\"file.pdf\": 1}"
}
```

---

### Query Knowledge Graph

#### `POST /query`

Query the knowledge graph with optional temporal filtering.

**Headers:**
```
Content-Type: application/json
```

**Request Body:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | String | Yes | - | Natural language question |
| `mode` | Enum | No | hybrid | Query mode (local, global, hybrid, temporal) |
| `reference_date` | String | No | null | Date in YYYY-MM-DD format for temporal queries |
| `working_dir` | String | No | `./rag_storage` | Storage directory |
| `top_k` | Integer | No | 20 | Number of candidates to retrieve |

**Query Modes:**

| Mode | Speed | Coverage | Use Case |
|------|-------|----------|----------|
| `local` | Fast | Single-hop | Entity-specific |
| `global` | Slow | Multi-hop | Comprehensive |
| `hybrid` | Balanced | Mixed | Recommended default |
| `temporal` | Fast+ | Versioned | Time-aware queries |

**Example 1: Basic Query**

```bash
curl -X POST "http://localhost:9621/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the parking fee?",
    "mode": "hybrid"
  }'
```

**Example 2: Temporal Query**

```bash
curl -X POST "http://localhost:9621/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What was the parking fee?",
    "mode": "temporal",
    "reference_date": "2024-06-01"
  }'
```

**Response:**
```json
{
  "answer": "The parking fee is $100 per night (Sequence 2, Effective 2025-06-15).",
  "mode": "temporal",
  "reference_date": "2024-06-01",
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

---

### List Entities

#### `GET /entities`

List all entities in the knowledge graph.

**Query Parameters:**
- `working_dir` (optional): Storage directory
- `search` (optional): Filter by name pattern
- `limit` (optional): Max results (default: 100)

**Example:**

```bash
curl "http://localhost:9621/entities?working_dir=rag_storage&search=parking"
```

**Response:**
```json
{
  "entities": [
    {
      "id": "parking-fee-v1",
      "name": "Parking Fee [v1]",
      "sequence_index": 1,
      "effective_date": "2023-01-01",
      "doc_type": "base"
    },
    {
      "id": "parking-fee-v2",
      "name": "Parking Fee [v2]",
      "sequence_index": 2,
      "effective_date": "2024-06-15",
      "doc_type": "amendment"
    }
  ],
  "count": 2
}
```

---

### Delete Knowledge Graph

#### `DELETE /graph`

Delete an entire knowledge graph.

**Query Parameters:**
- `working_dir` (required): Directory to delete

**Example:**

```bash
curl -X DELETE "http://localhost:9621/graph?working_dir=rag_storage"
```

**Response:**
```json
{
  "status": "deleted",
  "working_dir": "rag_storage",
  "entities_removed": 87,
  "relationships_removed": 142
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Query completed |
| 400 | Bad Request | Invalid parameter |
| 404 | Not Found | Directory doesn't exist |
| 500 | Server Error | LLM unavailable |
| 429 | Too Many Requests | Rate limit exceeded |

### Error Response Format

```json
{
  "error": "Invalid mode parameter",
  "detail": "Mode must be one of: local, global, hybrid, temporal",
  "provided": "invalid_mode",
  "suggestion": "Use mode=hybrid for balanced retrieval"
}
```

### Common Errors

**400: Invalid sequence_map**
```json
{
  "error": "Invalid sequence_map format",
  "detail": "Expected JSON with string keys and integer values"
}
```

**400: Invalid reference_date**
```json
{
  "error": "Invalid reference_date format",
  "detail": "Date must be in YYYY-MM-DD format"
}
```

**404: Working directory not found**
```json
{
  "error": "Working directory not found",
  "path": "rag_storage",
  "suggestion": "Ensure documents are uploaded or use correct path"
}
```

---

## Rate Limiting

**Default Limits:**
- Upload: 10 requests/minute
- Query: 60 requests/minute
- Graph: 2 requests/minute

**Response Headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1640995200
```

When rate limit exceeded:
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 30
}
```

---

## Data Formats

### Sequence Map Format

```json
{
  "base_contract.pdf": 1,
  "amendment_2024_q2.pdf": 2,
  "amendment_2024_q4.pdf": 3,
  "latest_rates.pdf": 4
}
```

**Rules:**
- String keys (filenames)
- Integer values (sequence numbers)
- Values must be unique
- Gaps allowed (1, 3, 7 OK)

### Entity Format

```json
{
  "id": "unique-entity-id",
  "name": "Entity Name [v2]",
  "sequence_index": 2,
  "effective_date": "2024-06-15",
  "doc_type": "amendment",
  "content": "Entity description...",
  "metadata": {
    "source_file": "amendment.pdf",
    "similarity_score": 0.91
  }
}
```

### Response Format

All responses follow this structure:

```json
{
  "status": "success|error",
  "data": { /* endpoint-specific */ },
  "metadata": {
    "timestamp": "2025-01-19T12:34:56Z",
    "request_id": "req-123456"
  }
}
```

---

## Pagination

Endpoints with large result sets support pagination:

```bash
curl "http://localhost:9621/entities?limit=50&offset=100"
```

**Parameters:**
- `limit`: Results per page (default: 100, max: 1000)
- `offset`: Number of results to skip (default: 0)

**Response includes:**
```json
{
  "data": [...],
  "pagination": {
    "total": 1234,
    "limit": 50,
    "offset": 100,
    "has_more": true
  }
}
```

---

## SDK Support

### Python SDK

```python
from lightrag.client import LightRAGClient

client = LightRAGClient(base_url="http://localhost:9621")

# Upload
result = client.upload(
    file_path="contract.pdf",
    sequence_index=1,
    working_dir="rag_storage"
)

# Query
result = client.query(
    query="What is the fee?",
    mode="temporal",
    reference_date="2025-01-01"
)

print(result.answer)
```

### JavaScript/TypeScript SDK

```typescript
import { LightRAGClient } from '@lightrag/sdk';

const client = new LightRAGClient({
  baseUrl: 'http://localhost:9621'
});

// Upload
await client.upload({
  file: fileBlob,
  sequenceIndex: 1,
  workingDir: 'rag_storage'
});

// Query
const result = await client.query({
  query: 'What is the fee?',
  mode: 'temporal',
  referenceDate: '2025-01-01'
});

console.log(result.answer);
```

---

## WebSocket Support (Beta)

Real-time streaming queries:

```javascript
const ws = new WebSocket('ws://localhost:9621/ws/query');

ws.onopen = () => {
  ws.send(JSON.stringify({
    query: "What is the fee?",
    mode: "temporal"
  }));
};

ws.onmessage = (event) => {
  const chunk = JSON.parse(event.data);
  console.log(chunk.text); // Stream response chunks
};
```

---

## Batch Operations

### Batch Upload

```bash
# Upload multiple files with sequences
for i in {1..3}; do
  curl -X POST "http://localhost:9621/upload" \
    -F "file=@doc_$i.pdf" \
    -F "sequence_index=$i"
done
```

### Batch Query

```python
queries = [
  {"query": "What is the fee?", "reference_date": "2024-01-01"},
  {"query": "What is the fee?", "reference_date": "2024-06-01"},
  {"query": "What is the fee?", "reference_date": "2025-01-01"},
]

results = [client.query(**q) for q in queries]
```

---

## OpenAPI/Swagger

**Swagger UI:**
```
http://localhost:9621/docs
```

**ReDoc:**
```
http://localhost:9621/redoc
```

**OpenAPI JSON:**
```
http://localhost:9621/openapi.json
```

---

## Migration from Non-Temporal API

### Backward Compatibility

Existing non-temporal queries still work:

```bash
# Old API (still supported)
curl -X POST "http://localhost:9621/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the fee?", "mode": "hybrid"}'

# Returns results without temporal filtering
```

### Gradual Adoption

1. **Start with uploads:**
   ```bash
   -F "sequence_index=1" -F "effective_date=2024-01-01"
   ```

2. **Test temporal queries:**
   ```bash
   -d '{"query": "...", "mode": "temporal"}'
   ```

3. **Add reference dates:**
   ```bash
   -d '{"query": "...", "mode": "temporal", "reference_date": "2024-06-01"}'
   ```

---

## Performance Tips

1. **Batch uploads** - Multiple documents in one request
2. **Cache results** - Same query+date = cached response
3. **Use local mode** - Faster for specific entities
4. **Pagination** - Limit results with `top_k` parameter
5. **Connection pooling** - Keep-alive for multiple requests

---

## Support & Resources

- **Python Examples** → `/examples/lightrag_*.py`
- **CLI Tools** → `python query_graph.py --help`
- **GitHub** → https://github.com/HKUDS/LightRAG
- **Issues** → https://github.com/HKUDS/LightRAG/issues

---

**API Version:** 1.0.0
**Last Updated:** March 5, 2026
**Status:** Production Ready
