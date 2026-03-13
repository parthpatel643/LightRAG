# Temporal RAG Web UI User Guide

## Overview

The LightRAG Web UI now supports full temporal RAG capabilities, bringing parity with the CLI implementation. This guide covers all temporal features available through the web interface.

## Features

### 1. Workspace Management

**Location:** Site Header (top navigation bar)

**Purpose:** Manage multiple isolated working directories for different projects or document collections.

**How to Use:**
1. Click the workspace dropdown in the header
2. Select an existing workspace or click "New" to create one
3. Configure:
   - **Workspace Name**: Unique identifier (e.g., "aviation-contracts")
   - **Working Directory**: Where RAG data is stored (e.g., `./rag_storage/aviation`)
   - **Input Directory**: Where source documents are located (e.g., `./inputs/aviation`)
   - **Description**: Optional description for the workspace

**Benefits:**
- Isolate different document collections
- Switch between projects without data mixing
- Organize documents by domain or time period

---

### 2. Batch Upload with Document Sequencing

**Location:** Documents tab → "Batch Upload & Sequence" button

**Purpose:** Upload multiple documents and arrange them in chronological order with effective dates for temporal queries.

**Workflow:**

#### Step 1: Upload Files
- Drag and drop files or click to select
- Supported formats: TXT, PDF, DOC, DOCX, MD
- Add multiple files at once
- Remove unwanted files before proceeding

#### Step 2: Arrange Order
- Drag documents to reorder them chronologically
- Use up/down arrows for fine-tuning
- Documents are numbered sequentially (#1, #2, #3...)
- Order represents temporal progression

#### Step 3: Set Effective Dates
- Assign an effective date to each document
- Dates enable temporal queries (e.g., "What was known on 2023-06-15?")
- All documents must have dates to proceed

#### Step 4: Review & Confirm
- Review the complete sequence
- Check document names, dates, and order
- Click "Upload Documents" to process

**Example Use Case:**
```
Aviation Contract Amendments:
#1: contract_v1.pdf → 2022-01-15
#2: amendment_1.pdf → 2022-06-20
#3: amendment_2.pdf → 2023-03-10
#4: amendment_3.pdf → 2023-09-05
```

---

### 3. Temporal Queries

**Location:** Retrieval tab → Temporal Query Panel

**Purpose:** Query the knowledge base as it existed at a specific point in time.

**How to Use:**

1. **Enable Temporal Mode:**
   - Toggle "Enable Temporal Query" switch
   - The reference date picker appears

2. **Select Reference Date:**
   - Choose a date using the calendar picker
   - Only documents with effective dates ≤ reference date are considered

3. **Run Query:**
   - Enter your question
   - Select query mode (local, global, hybrid, naive, or **temporal**)
   - Click "Send" or press Enter

**Query Modes:**
- **Temporal Mode**: Specifically designed for time-based queries
- **Hybrid Mode**: Can also use reference dates for filtering
- **Other Modes**: Work with temporal filtering when reference date is set

**Example Queries:**
```
Reference Date: 2022-12-31
Query: "What were the payment terms in the original contract?"
→ Returns information only from documents effective before 2023-01-01

Reference Date: 2023-06-30
Query: "What changes were made to the delivery schedule?"
→ Includes amendments up to June 2023

Reference Date: 2023-12-31
Query: "What is the current status of all amendments?"
→ Includes all documents up to end of 2023
```

---

### 4. Document Sequence Display

**Location:** Documents tab → Document table

**Purpose:** View sequence indices for uploaded documents.

**Features:**
- **Sequence Column**: Shows sequence index as a numbered badge
- **Visual Indicator**: Green circular badge with sequence number
- **Sorting**: Documents can be sorted by sequence
- **Filtering**: Filter by status while maintaining sequence visibility

**Interpretation:**
- Documents with sequence indices are part of a temporal collection
- Lower numbers = earlier in the sequence
- Missing sequence index ("-") = document not part of a sequence

---

## Complete Workflow Example

### Scenario: Managing Aviation Contract History

**Step 1: Create Workspace**
```
Name: aviation-contracts
Working Dir: ./rag_storage/aviation
Input Dir: ./inputs/aviation
Description: Historical aviation contract documents
```

**Step 2: Batch Upload Documents**
```
Upload Order:
1. base_contract.pdf (2020-01-15)
2. amendment_safety.pdf (2020-08-20)
3. amendment_pricing.pdf (2021-03-10)
4. amendment_scope.pdf (2021-11-05)
5. amendment_terms.pdf (2022-06-15)
```

**Step 3: Verify Upload**
- Check Documents tab
- Confirm all documents show sequence indices (0-4)
- Verify effective dates in metadata

**Step 4: Temporal Queries**

Query 1 - Original Contract:
```
Reference Date: 2020-07-31
Query: "What are the safety requirements?"
Result: Only base contract is considered
```

Query 2 - After Safety Amendment:
```
Reference Date: 2020-12-31
Query: "What are the safety requirements?"
Result: Base contract + safety amendment
```

Query 3 - Current State:
```
Reference Date: 2023-01-01
Query: "What are all the current terms?"
Result: All documents included
```

---

## API Integration

All temporal features are backed by REST API endpoints:

### Workspace Management
```bash
# Switch workspace
POST /workspace/switch
{
  "name": "aviation-contracts",
  "working_dir": "./rag_storage/aviation",
  "input_dir": "./inputs/aviation"
}

# Get current workspace
GET /workspace/current

# List workspaces
GET /workspace/list
```

### Document Sequencing
```bash
# Batch upload with sequencing
POST /documents/batch-upload-sequenced
Content-Type: multipart/form-data

files: [file1, file2, file3]
order: ["file1.pdf", "file2.pdf", "file3.pdf"]
metadata: {
  "file1.pdf": {"effective_date": "2022-01-15", "sequence_index": 0},
  "file2.pdf": {"effective_date": "2022-06-20", "sequence_index": 1},
  "file3.pdf": {"effective_date": "2023-03-10", "sequence_index": 2}
}

# Get document sequences
GET /documents/sequences

# Update sequence
PUT /documents/{doc_id}/sequence
{
  "sequence_index": 5,
  "effective_date": "2023-09-15"
}
```

### Temporal Queries
```bash
# Query with reference date
POST /query
{
  "query": "What were the payment terms?",
  "mode": "temporal",
  "reference_date": "2022-12-31",
  "top_k": 40
}
```

---

## Best Practices

### 1. Document Organization
- Use consistent naming conventions (e.g., `contract_v1.pdf`, `amendment_1.pdf`)
- Include dates in filenames when possible
- Group related documents in the same workspace

### 2. Effective Dates
- Use the date when the document became effective, not creation date
- For amendments, use the amendment effective date
- Be consistent with date formats (YYYY-MM-DD recommended)

### 3. Sequence Ordering
- Order documents chronologically by effective date
- Maintain logical progression (base → amendments → revisions)
- Use sequence indices to track document versions

### 4. Temporal Queries
- Start with broad date ranges, then narrow down
- Use specific dates for point-in-time analysis
- Compare results across different reference dates

### 5. Workspace Management
- Create separate workspaces for different projects
- Use descriptive names and descriptions
- Regularly backup workspace data

---

## Troubleshooting

### Issue: Documents not appearing in temporal queries
**Solution:**
- Verify documents have effective dates in metadata
- Check reference date is after document effective dates
- Ensure documents are fully processed (status = "processed")

### Issue: Sequence indices not showing
**Solution:**
- Documents must be uploaded via "Batch Upload & Sequence"
- Check metadata contains `sequence_index` field
- Refresh the document list

### Issue: Workspace switch not working
**Solution:**
- Verify directories exist and are accessible
- Check backend logs for permission errors
- Ensure workspace configuration is valid

### Issue: Drag-and-drop not working in sequencer
**Solution:**
- Try using up/down arrow buttons instead
- Ensure browser supports HTML5 drag-and-drop
- Check for JavaScript errors in console

---

## Advanced Features

### Custom Metadata
Add custom metadata during batch upload:
```json
{
  "document.pdf": {
    "effective_date": "2023-01-15",
    "sequence_index": 0,
    "version": "1.0",
    "author": "Legal Team",
    "category": "contract"
  }
}
```

### Temporal Mode Query Parameters
```json
{
  "query": "What changed?",
  "mode": "temporal",
  "reference_date": "2023-06-30",
  "top_k": 40,
  "chunk_top_k": 20,
  "max_entity_tokens": 6000,
  "enable_rerank": true
}
```

### Workspace Environment Variables
Backend respects these environment variables:
```bash
LIGHTRAG_WORKING_DIR=/path/to/rag_storage
LIGHTRAG_INPUT_DIR=/path/to/inputs
```

---

## Keyboard Shortcuts

- **Ctrl/Cmd + Enter**: Send query
- **Esc**: Close dialogs
- **Tab**: Navigate form fields
- **Arrow Keys**: Navigate document list in sequencer

---

## Related Documentation

- [Temporal Implementation Guide](TEMPORAL_COMPLETE_IMPLEMENTATION.md)
- [API Reference](CLI_REFERENCE.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)

---

## Support

For issues or questions:
1. Check the [GitHub Issues](https://github.com/HKUDS/LightRAG/issues)
2. Review [Documentation](../docs/)
3. Join community discussions

---

**Last Updated:** 2026-03-12  
**Version:** 1.0.0