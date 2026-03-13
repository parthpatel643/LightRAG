# Temporal RAG API Reference

## Overview

This document describes the REST API endpoints for temporal RAG features in LightRAG.

## Base URL

```
http://localhost:9621/api
```

---

## Workspace Management

### Switch Workspace

Switch to a different workspace configuration.

**Endpoint:** `POST /workspace/switch`

**Request Body:**
```json
{
  "name": "string",
  "working_dir": "string",
  "input_dir": "string",
  "description": "string (optional)"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Workspace switched successfully",
  "workspace": {
    "name": "aviation-contracts",
    "working_dir": "./rag_storage/aviation",
    "input_dir": "./inputs/aviation",
    "description": "Aviation contract documents"
  }
}
```

**Status Codes:**
- `200 OK`: Workspace switched successfully
- `400 Bad Request`: Invalid workspace configuration
- `500 Internal Server Error`: Server error

**Example:**
```bash
curl -X POST http://localhost:9621/api/workspace/switch \
  -H "Content-Type: application/json" \
  -d '{
    "name": "aviation-contracts",
    "working_dir": "./rag_storage/aviation",
    "input_dir": "./inputs/aviation",
    "description": "Aviation contract documents"
  }'
```

---

### Get Current Workspace

Retrieve the current workspace configuration.

**Endpoint:** `GET /workspace/current`

**Response:**
```json
{
  "name": "aviation-contracts",
  "working_dir": "./rag_storage/aviation",
  "input_dir": "./inputs/aviation",
  "description": "Aviation contract documents"
}
```

**Status Codes:**
- `200 OK`: Workspace retrieved successfully
- `500 Internal Server Error`: Server error

**Example:**
```bash
curl http://localhost:9621/api/workspace/current
```

---

### List Workspaces

List all available workspaces.

**Endpoint:** `GET /workspace/list`

**Response:**
```json
[
  {
    "name": "default",
    "working_dir": "./rag_storage",
    "input_dir": "./inputs",
    "description": "Default workspace"
  },
  {
    "name": "aviation-contracts",
    "working_dir": "./rag_storage/aviation",
    "input_dir": "./inputs/aviation",
    "description": "Aviation contract documents"
  }
]
```

**Status Codes:**
- `200 OK`: Workspaces retrieved successfully
- `500 Internal Server Error`: Server error

**Example:**
```bash
curl http://localhost:9621/api/workspace/list
```

---

## Document Sequencing

### Batch Upload with Sequencing

Upload multiple documents with sequence information and effective dates.

**Endpoint:** `POST /documents/batch-upload-sequenced`

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `files`: Array of file uploads
- `order`: JSON array of filenames in sequence order
- `metadata`: JSON object with metadata for each file

**Request Example:**
```bash
curl -X POST http://localhost:9621/api/documents/batch-upload-sequenced \
  -F "files=@contract_v1.pdf" \
  -F "files=@amendment_1.pdf" \
  -F "files=@amendment_2.pdf" \
  -F 'order=["contract_v1.pdf","amendment_1.pdf","amendment_2.pdf"]' \
  -F 'metadata={
    "contract_v1.pdf": {
      "effective_date": "2022-01-15",
      "sequence_index": 0
    },
    "amendment_1.pdf": {
      "effective_date": "2022-06-20",
      "sequence_index": 1
    },
    "amendment_2.pdf": {
      "effective_date": "2023-03-10",
      "sequence_index": 2
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "message": "Documents uploaded and sequenced successfully",
  "documents": [
    {
      "id": "doc_001",
      "filename": "contract_v1.pdf",
      "sequence_index": 0,
      "effective_date": "2022-01-15",
      "status": "pending"
    },
    {
      "id": "doc_002",
      "filename": "amendment_1.pdf",
      "sequence_index": 1,
      "effective_date": "2022-06-20",
      "status": "pending"
    },
    {
      "id": "doc_003",
      "filename": "amendment_2.pdf",
      "sequence_index": 2,
      "effective_date": "2023-03-10",
      "status": "pending"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Documents uploaded successfully
- `400 Bad Request`: Invalid request (missing files, invalid metadata)
- `500 Internal Server Error`: Server error

---

### Get Document Sequences

Retrieve all documents with their sequence information.

**Endpoint:** `GET /documents/sequences`

**Response:**
```json
{
  "documents": [
    {
      "id": "doc_001",
      "filename": "contract_v1.pdf",
      "sequence_index": 0,
      "effective_date": "2022-01-15",
      "status": "processed"
    },
    {
      "id": "doc_002",
      "filename": "amendment_1.pdf",
      "sequence_index": 1,
      "effective_date": "2022-06-20",
      "status": "processed"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Sequences retrieved successfully
- `500 Internal Server Error`: Server error

**Example:**
```bash
curl http://localhost:9621/api/documents/sequences
```

---

### Update Document Sequence

Update the sequence index and effective date for a document.

**Endpoint:** `PUT /documents/{doc_id}/sequence`

**Path Parameters:**
- `doc_id`: Document ID

**Request Body:**
```json
{
  "sequence_index": 5,
  "effective_date": "2023-09-15"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Document sequence updated successfully",
  "document": {
    "id": "doc_001",
    "sequence_index": 5,
    "effective_date": "2023-09-15"
  }
}
```

**Status Codes:**
- `200 OK`: Sequence updated successfully
- `404 Not Found`: Document not found
- `400 Bad Request`: Invalid sequence data
- `500 Internal Server Error`: Server error

**Example:**
```bash
curl -X PUT http://localhost:9621/api/documents/doc_001/sequence \
  -H "Content-Type: application/json" \
  -d '{
    "sequence_index": 5,
    "effective_date": "2023-09-15"
  }'
```

---

## Temporal Queries

### Query with Reference Date

Execute a query with temporal filtering based on a reference date.

**Endpoint:** `POST /query`

**Request Body:**
```json
{
  "query": "string",
  "mode": "temporal|hybrid|local|global|naive",
  "reference_date": "YYYY-MM-DD (optional)",
  "top_k": 40,
  "chunk_top_k": 20,
  "max_entity_tokens": 6000,
  "max_relation_tokens": 8000,
  "max_total_tokens": 30000,
  "only_need_context": false,
  "only_need_prompt": false,
  "stream": true,
  "history_turns": 0,
  "enable_rerank": true,
  "hl_keywords": [],
  "ll_keywords": [],
  "include_references": true,
  "include_chunk_content": false
}
```

**Response (Non-streaming):**
```json
{
  "response": "Based on documents effective before 2023-01-01...",
  "context": {
    "entities": [...],
    "relationships": [...],
    "chunks": [...]
  },
  "metadata": {
    "reference_date": "2022-12-31",
    "documents_considered": 3,
    "query_time_ms": 1250
  }
}
```

**Response (Streaming):**
```
data: {"type": "chunk", "content": "Based on "}
data: {"type": "chunk", "content": "documents "}
data: {"type": "chunk", "content": "effective "}
...
data: {"type": "done", "metadata": {...}}
```

**Status Codes:**
- `200 OK`: Query executed successfully
- `400 Bad Request`: Invalid query parameters
- `500 Internal Server Error`: Server error

**Example:**
```bash
# Non-streaming
curl -X POST http://localhost:9621/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What were the payment terms?",
    "mode": "temporal",
    "reference_date": "2022-12-31",
    "top_k": 40,
    "stream": false
  }'

# Streaming
curl -X POST http://localhost:9621/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What were the payment terms?",
    "mode": "temporal",
    "reference_date": "2022-12-31",
    "stream": true
  }' \
  --no-buffer
```

---

## Query Modes

### Temporal Mode

Specifically designed for time-based queries with reference dates.

**Features:**
- Filters documents by effective date
- Considers document sequence
- Optimized for historical analysis

**Best For:**
- Point-in-time queries
- Historical comparisons
- Version tracking

### Hybrid Mode with Reference Date

Combines local and global search with temporal filtering.

**Features:**
- Uses both entity and chunk-based retrieval
- Applies reference date filter
- Balanced approach

**Best For:**
- General queries with time constraints
- Complex questions requiring multiple sources
- When you need both precision and recall

---

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "status_code": 400
}
```

**Common Error Codes:**
- `400 Bad Request`: Invalid input parameters
- `401 Unauthorized`: Authentication required
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server-side error

---

## Rate Limiting

API endpoints are subject to rate limiting:
- **Default:** 100 requests per minute per IP
- **Burst:** Up to 20 requests in 1 second

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1678901234
```

---

## Authentication

If authentication is enabled, include the API key in the header:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:9621/api/query
```

Or use the `X-API-Key` header:

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  http://localhost:9621/api/query
```

---

## WebSocket Support

For real-time streaming queries, use WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:9621/ws/query');

ws.onopen = () => {
  ws.send(JSON.stringify({
    query: "What were the payment terms?",
    mode: "temporal",
    reference_date: "2022-12-31"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

---

## SDK Examples

### Python

```python
import requests

# Switch workspace
response = requests.post(
    'http://localhost:9621/api/workspace/switch',
    json={
        'name': 'aviation-contracts',
        'working_dir': './rag_storage/aviation',
        'input_dir': './inputs/aviation'
    }
)

# Temporal query
response = requests.post(
    'http://localhost:9621/api/query',
    json={
        'query': 'What were the payment terms?',
        'mode': 'temporal',
        'reference_date': '2022-12-31',
        'stream': False
    }
)
result = response.json()
```

### JavaScript/TypeScript

```typescript
// Switch workspace
const response = await fetch('http://localhost:9621/api/workspace/switch', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'aviation-contracts',
    working_dir: './rag_storage/aviation',
    input_dir: './inputs/aviation'
  })
});

// Temporal query
const queryResponse = await fetch('http://localhost:9621/api/query', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'What were the payment terms?',
    mode: 'temporal',
    reference_date: '2022-12-31',
    stream: false
  })
});
const result = await queryResponse.json();
```

---

## Related Documentation

- [User Guide](TEMPORAL_WEB_UI_GUIDE.md)
- [Implementation Details](TEMPORAL_COMPLETE_IMPLEMENTATION.md)
- [CLI Reference](CLI_REFERENCE.md)

---

**Last Updated:** 2026-03-12  
**API Version:** 1.0.0