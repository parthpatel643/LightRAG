# LightRAG Web UI Temporal Parity Implementation Plan

**Status**: Planning Complete - Ready for Implementation  
**Date**: March 12, 2026  
**Goal**: Bring full parity between CLI temporal features and Web UI

---

## Executive Summary

This document outlines the complete implementation plan to bring the LightRAG Web UI to feature parity with the temporal CLI implementation demonstrated in [`demo_temporal_rag.py`](../demo_temporal_rag.py).

### Current State Analysis

#### ✅ What Exists
- **Backend**: Complete temporal logic implementation (27/27 issues resolved)
  - Distributed locking for sequence indices
  - ACID transaction support
  - Timezone-aware date handling
  - Temporal filtering by date and sequence
- **Frontend Components**: Built but not integrated
  - [`TemporalQueryPanel.tsx`](../lightrag_webui/src/components/retrieval/TemporalQueryPanel.tsx) - Date picker for temporal queries
  - [`WorkspaceSwitcher.tsx`](../lightrag_webui/src/components/WorkspaceSwitcher.tsx) - Workspace management UI
- **Data Preparation**: [`data_prep.py`](../data_prep.py) - ContractSequencer for document ordering

#### ❌ What's Missing
1. **Integration**: Existing components not connected to pages
2. **Backend APIs**: No REST endpoints for temporal features
3. **Batch Upload**: No UI for mass document upload with sequencing
4. **Sequence Management**: No UI to view/reorder document sequences
5. **Temporal Query**: UI exists but not connected to backend
6. **Workspace API**: No backend support for workspace switching

---

## Required Features (from demo_temporal_rag.py)

### 1. Mass Upload with Document Sequencing
**CLI Behavior**:
```python
# Create sample contracts
temp_dir, files = create_sample_contracts()

# Define order
order = ["Base.md", "Amendment1.md", "Amendment2.md"]

# Initialize sequencer
sequencer = ContractSequencer(files, order)

# Prepare for ingestion with metadata
sequenced_docs = sequencer.prepare_for_ingestion()
```

**Web UI Requirements**:
- Upload multiple files at once
- Define temporal order (drag-and-drop or manual ordering)
- Assign sequence indices automatically
- Extract/inject effective dates
- Preview sequencing before upload
- Batch insert with metadata

### 2. Temporal Query Interface
**CLI Behavior**:
```python
result = await rag.aquery(
    query,
    param=QueryParam(
        mode="temporal",
        only_need_context=False,
        reference_date="2023-01-01"
    )
)
```

**Web UI Requirements**:
- Date picker for reference date (✅ component exists)
- Temporal mode selection
- Visual indicator when temporal mode active
- Pass `reference_date` to backend
- Display temporal context in results

### 3. Workspace Selection
**CLI Behavior**:
```python
rag = LightRAG(
    working_dir=str(rag_dir),
    llm_model_func=gpt_4o_mini_complete,
    # ... other config
)
```

**Web UI Requirements**:
- Select from multiple workspaces (✅ component exists)
- Create new workspaces with custom directories
- Switch between workspaces dynamically
- Persist workspace configurations
- Backend API to update working directory

### 4. Sequence Management
**CLI Behavior**:
- Documents have `sequence_index` in metadata
- Queries can filter by sequence index
- Version tracking: `Entity [v1]`, `Entity [v2]`, etc.

**Web UI Requirements**:
- Display sequence index in document table
- Reorder documents (change sequence)
- Filter/sort by sequence index
- Visual timeline of document versions
- Edit sequence metadata

---

## Implementation Architecture

### Phase 1: Backend API Development

#### 1.1 Workspace Management API
**File**: `lightrag/api/routers/workspace_routes.py` (NEW)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/workspace", tags=["workspace"])

class WorkspaceConfig(BaseModel):
    name: str
    working_dir: str
    input_dir: str
    description: str | None = None

@router.post("/switch")
async def switch_workspace(config: WorkspaceConfig):
    """Switch to a different workspace configuration."""
    # Update LightRAG instance with new working_dir
    # Return success/failure
    pass

@router.get("/current")
async def get_current_workspace():
    """Get current workspace configuration."""
    pass

@router.get("/list")
async def list_workspaces():
    """List all available workspaces."""
    pass
```

#### 1.2 Temporal Query Support
**File**: `lightrag/api/routers/query_routes.py` (MODIFY)

```python
class QueryRequest(BaseModel):
    query: str
    mode: QueryMode = "hybrid"
    reference_date: str | None = None  # ADD THIS
    # ... other fields

@router.post("/query")
async def query_text(request: QueryRequest):
    # Pass reference_date to QueryParam
    param = QueryParam(
        mode=request.mode,
        reference_date=request.reference_date,
        # ... other params
    )
    result = await rag.aquery(request.query, param=param)
    return result
```

#### 1.3 Document Sequencing API
**File**: `lightrag/api/routers/document_routes.py` (MODIFY)

```python
class DocumentSequenceRequest(BaseModel):
    documents: List[Dict[str, Any]]  # [{file_path, sequence_index, metadata}]

@router.post("/sequence")
async def sequence_documents(request: DocumentSequenceRequest):
    """Set sequence indices for multiple documents."""
    # Update doc_status with sequence_index
    # Return updated documents
    pass

@router.post("/batch-upload-sequenced")
async def batch_upload_sequenced(
    files: List[UploadFile],
    order: List[str],  # Ordered list of filenames
    metadata: Dict[str, Any] = {}
):
    """Upload multiple files with automatic sequencing."""
    # Use ContractSequencer logic
    # Inject soft tags for dates
    # Insert with sequence metadata
    pass
```

#### 1.4 Enhanced Document Status
**File**: `lightrag/api/routers/document_routes.py` (MODIFY)

```python
class DocStatusResponse(BaseModel):
    id: str
    file_path: str
    status: DocStatus
    sequence_index: int | None = None  # ADD THIS
    doc_type: str | None = None        # ADD THIS
    effective_date: str | None = None  # ADD THIS
    metadata: Dict[str, Any] = {}
```

---

### Phase 2: Frontend Component Integration

#### 2.1 Integrate TemporalQueryPanel
**File**: `lightrag_webui/src/features/RetrievalTesting.tsx` (MODIFY)

```tsx
import TemporalQueryPanel from '@/components/retrieval/TemporalQueryPanel'

export default function RetrievalTesting() {
  const [referenceDate, setReferenceDate] = useState<string | undefined>()
  const [queryMode, setQueryMode] = useState<QueryMode>('hybrid')

  // Add TemporalQueryPanel after query mode selector
  return (
    <div>
      {/* Query mode selector */}
      <QuerySettings 
        mode={queryMode}
        onModeChange={setQueryMode}
      />
      
      {/* Temporal query panel */}
      <TemporalQueryPanel
        referenceDate={referenceDate}
        onReferenceDateChange={setReferenceDate}
        isTemporalMode={queryMode === 'temporal'}
      />
      
      {/* Query input and results */}
    </div>
  )
}
```

#### 2.2 Integrate WorkspaceSwitcher
**File**: `lightrag_webui/src/features/SiteHeader.tsx` (MODIFY)

```tsx
import WorkspaceSwitcher from '@/components/WorkspaceSwitcher'

export default function SiteHeader() {
  const handleWorkspaceChange = async (workspace: WorkspaceConfig) => {
    // Call backend API to switch workspace
    await switchWorkspace(workspace)
    // Refresh document list
    // Show success toast
  }

  return (
    <header>
      {/* Logo and navigation */}
      
      <WorkspaceSwitcher
        currentWorkspace={currentWorkspace}
        onWorkspaceChange={handleWorkspaceChange}
        className="ml-auto mr-4"
      />
      
      {/* User menu */}
    </header>
  )
}
```

#### 2.3 Create DocumentSequencer Component
**File**: `lightrag_webui/src/components/documents/DocumentSequencer.tsx` (NEW)

```tsx
interface DocumentSequencerProps {
  files: File[]
  onSequenceComplete: (sequencedFiles: SequencedFile[]) => void
}

export default function DocumentSequencer({ files, onSequenceComplete }: DocumentSequencerProps) {
  const [orderedFiles, setOrderedFiles] = useState<File[]>(files)
  
  // Drag-and-drop reordering
  const handleDragEnd = (result: DropResult) => {
    // Reorder files
    // Update sequence indices
  }
  
  return (
    <DragDropContext onDragEnd={handleDragEnd}>
      <Droppable droppableId="documents">
        {(provided) => (
          <div {...provided.droppableProps} ref={provided.innerRef}>
            {orderedFiles.map((file, index) => (
              <Draggable key={file.name} draggableId={file.name} index={index}>
                {(provided) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.draggableProps}
                    {...provided.dragHandleProps}
                  >
                    <DocumentSequenceItem
                      file={file}
                      sequenceIndex={index + 1}
                    />
                  </div>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>
  )
}
```

#### 2.4 Update DocumentManager
**File**: `lightrag_webui/src/features/DocumentManager.tsx` (MODIFY)

```tsx
// Add sequence index column to table
<TableHead>Sequence</TableHead>

// Display sequence index
<TableCell>
  {doc.sequence_index ? (
    <Badge variant="outline">#{doc.sequence_index}</Badge>
  ) : (
    <span className="text-muted-foreground">-</span>
  )}
</TableCell>

// Add reorder button
<Button
  variant="ghost"
  size="sm"
  onClick={() => openReorderDialog(selectedDocs)}
>
  <ArrowUpDown className="h-4 w-4 mr-2" />
  Reorder
</Button>
```

#### 2.5 Create Batch Upload Dialog
**File**: `lightrag_webui/src/components/documents/BatchUploadDialog.tsx` (NEW)

```tsx
export default function BatchUploadDialog() {
  const [files, setFiles] = useState<File[]>([])
  const [step, setStep] = useState<'upload' | 'sequence' | 'confirm'>('upload')
  
  const handleFilesSelected = (selectedFiles: File[]) => {
    setFiles(selectedFiles)
    setStep('sequence')
  }
  
  const handleSequenceComplete = async (sequencedFiles: SequencedFile[]) => {
    setStep('confirm')
  }
  
  const handleUpload = async () => {
    // Call batch upload API with sequenced files
    await batchUploadSequenced(sequencedFiles)
  }
  
  return (
    <Dialog>
      {step === 'upload' && <FileUploadStep onFilesSelected={handleFilesSelected} />}
      {step === 'sequence' && <DocumentSequencer files={files} onSequenceComplete={handleSequenceComplete} />}
      {step === 'confirm' && <ConfirmUploadStep sequencedFiles={sequencedFiles} onUpload={handleUpload} />}
    </Dialog>
  )
}
```

---

### Phase 3: API Client Functions

#### 3.1 Workspace API Client
**File**: `lightrag_webui/src/api/lightrag.ts` (MODIFY)

```typescript
export interface WorkspaceConfig {
  name: string
  working_dir: string
  input_dir: string
  description?: string
}

export async function switchWorkspace(config: WorkspaceConfig): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/workspace/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  })
  if (!response.ok) throw new Error('Failed to switch workspace')
}

export async function getCurrentWorkspace(): Promise<WorkspaceConfig> {
  const response = await fetch(`${API_BASE_URL}/workspace/current`)
  if (!response.ok) throw new Error('Failed to get current workspace')
  return response.json()
}
```

#### 3.2 Temporal Query Client
**File**: `lightrag_webui/src/api/lightrag.ts` (MODIFY)

```typescript
export interface QueryRequest {
  query: string
  mode: QueryMode
  reference_date?: string  // ADD THIS
  // ... other fields
}

export async function queryText(request: QueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  })
  if (!response.ok) throw new Error('Query failed')
  return response.json()
}
```

#### 3.3 Document Sequencing Client
**File**: `lightrag_webui/src/api/lightrag.ts` (MODIFY)

```typescript
export interface SequencedDocument {
  file: File
  sequence_index: number
  metadata?: Record<string, any>
}

export async function batchUploadSequenced(
  documents: SequencedDocument[]
): Promise<void> {
  const formData = new FormData()
  
  documents.forEach((doc, index) => {
    formData.append('files', doc.file)
  })
  
  formData.append('order', JSON.stringify(documents.map(d => d.file.name)))
  formData.append('metadata', JSON.stringify(documents.map(d => d.metadata || {})))
  
  const response = await fetch(`${API_BASE_URL}/documents/batch-upload-sequenced`, {
    method: 'POST',
    body: formData
  })
  
  if (!response.ok) throw new Error('Batch upload failed')
}

export async function updateDocumentSequence(
  documentId: string,
  sequenceIndex: number
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/sequence`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sequence_index: sequenceIndex })
  })
  
  if (!response.ok) throw new Error('Failed to update sequence')
}
```

---

## Implementation Sequence

### Sprint 1: Backend Foundation (Days 1-3)
1. ✅ Create workspace management API endpoints
2. ✅ Add temporal query support to query endpoint
3. ✅ Create document sequencing API endpoint
4. ✅ Add sequence index to document status responses
5. ✅ Test all endpoints with Postman/curl

### Sprint 2: Frontend Integration (Days 4-6)
1. ✅ Integrate TemporalQueryPanel into RetrievalTesting
2. ✅ Integrate WorkspaceSwitcher into SiteHeader
3. ✅ Add API client functions for new endpoints
4. ✅ Connect temporal query UI to backend
5. ✅ Connect workspace switcher to backend
6. ✅ Test basic temporal queries and workspace switching

### Sprint 3: Batch Upload & Sequencing (Days 7-10)
1. ✅ Create DocumentSequencer component
2. ✅ Create BatchUploadDialog component
3. ✅ Implement drag-and-drop reordering
4. ✅ Add sequence index display to DocumentManager
5. ✅ Create batch upload API endpoint
6. ✅ Test complete batch upload workflow

### Sprint 4: Polish & Documentation (Days 11-12)
1. ✅ Add loading states and error handling
2. ✅ Create user guide for temporal features
3. ✅ Update API documentation
4. ✅ Add tooltips and help text
5. ✅ End-to-end testing
6. ✅ Performance optimization

---

## Technical Specifications

### Data Models

#### Document with Sequence
```typescript
interface DocumentWithSequence {
  id: string
  file_path: string
  status: DocStatus
  sequence_index: number | null
  doc_type: 'base' | 'amendment' | 'supplement' | 'unknown'
  effective_date: string | null
  metadata: {
    source: string
    date: string
    [key: string]: any
  }
}
```

#### Temporal Query Request
```typescript
interface TemporalQueryRequest {
  query: string
  mode: 'temporal'
  reference_date: string  // YYYY-MM-DD format
  only_need_context: boolean
  top_k: number
}
```

#### Workspace Configuration
```typescript
interface WorkspaceConfig {
  name: string
  working_dir: string
  input_dir: string
  description?: string
  created_at?: string
  last_used?: string
}
```

### API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/workspace/switch` | Switch to different workspace |
| GET | `/workspace/current` | Get current workspace config |
| GET | `/workspace/list` | List all workspaces |
| POST | `/query` | Query with temporal support |
| POST | `/documents/batch-upload-sequenced` | Upload multiple files with sequence |
| POST | `/documents/sequence` | Set sequence indices |
| PATCH | `/documents/{id}/sequence` | Update single document sequence |
| GET | `/documents` | Get documents (includes sequence_index) |

---

## Testing Strategy

### Unit Tests
- Backend API endpoints (pytest)
- Frontend components (Vitest)
- API client functions (Vitest)

### Integration Tests
1. **Temporal Query Flow**
   - Select temporal mode
   - Pick reference date
   - Submit query
   - Verify results filtered by date

2. **Workspace Switching Flow**
   - Create new workspace
   - Switch to workspace
   - Verify working directory changed
   - Upload document to new workspace
   - Verify isolation

3. **Batch Upload Flow**
   - Select multiple files
   - Reorder files
   - Set sequence indices
   - Upload batch
   - Verify sequence in database
   - Query with temporal filter

### End-to-End Tests
- Complete temporal RAG workflow (like demo_temporal_rag.py)
- Multi-workspace document management
- Temporal queries across document versions

---

## Success Criteria

### Feature Parity Checklist
- [ ] ✅ Mass upload multiple documents
- [ ] ✅ Define document sequence order
- [ ] ✅ Temporal queries with reference date
- [ ] ✅ Workspace selection and switching
- [ ] ✅ Display sequence indices in UI
- [ ] ✅ Reorder document sequences
- [ ] ✅ All features work end-to-end
- [ ] ✅ Documentation complete
- [ ] ✅ Tests passing

### Performance Targets
- Batch upload: < 5s for 10 documents
- Workspace switch: < 2s
- Temporal query: < 3s (same as hybrid)
- Sequence reorder: < 1s

### User Experience Goals
- Intuitive drag-and-drop sequencing
- Clear visual feedback for temporal mode
- Smooth workspace transitions
- Helpful tooltips and guidance
- Error messages with recovery suggestions

---

## Dependencies

### Backend
- FastAPI (existing)
- LightRAG core (existing)
- data_prep.py (existing)
- Temporal logic modules (existing)

### Frontend
- React 19 (existing)
- TypeScript (existing)
- shadcn/ui components (existing)
- react-beautiful-dnd (NEW - for drag-and-drop)
- date-fns (existing)

### Installation
```bash
# Frontend
cd lightrag_webui
bun add react-beautiful-dnd @types/react-beautiful-dnd

# Backend (no new dependencies needed)
```

---

## Migration Guide

### For Existing Users

1. **Update Backend**
   ```bash
   git pull
   pip install -e .
   ```

2. **Update Frontend**
   ```bash
   cd lightrag_webui
   bun install
   bun run build
   ```

3. **Configure Workspaces**
   - Default workspace created automatically
   - Create additional workspaces via UI
   - Or configure in localStorage

4. **Use Temporal Features**
   - Select "temporal" mode in query settings
   - Pick reference date
   - Upload documents with sequence order
   - Query historical versions

---

## Future Enhancements

### Phase 2 Features (Post-Parity)
1. **Visual Timeline**
   - Interactive timeline showing document versions
   - Click to jump to specific date
   - Highlight changes between versions

2. **Advanced Sequencing**
   - Auto-detect document order from dates
   - Suggest sequence based on content analysis
   - Bulk sequence operations

3. **Workspace Templates**
   - Pre-configured workspace templates
   - Import/export workspace configs
   - Shared workspaces for teams

4. **Temporal Analytics**
   - Version comparison view
   - Change tracking visualization
   - Entity evolution graphs

---

## References

- [Temporal Complete Implementation](./TEMPORAL_COMPLETE_IMPLEMENTATION.md)
- [Web UI Features Guide](./WEBUI_FEATURES.md)
- [Demo Temporal RAG](../demo_temporal_rag.py)
- [Data Prep Module](../data_prep.py)
- [API Reference](./API_REFERENCE.md)

---

**Document Version**: 1.0  
**Last Updated**: March 12, 2026  
**Status**: Ready for Implementation  
**Estimated Effort**: 12 days (2 sprints)