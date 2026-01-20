# Knowledge Graph Enhancement - Edge Relationships & Chunks Display

## Overview
Successfully implemented two new features for the knowledge graph visualization:
1. **Edge Relationship Search** - Users can now search for and display edge relationships in the graph
2. **Chunks Display Panel** - A new panel displays text chunks/references associated with selected nodes or edges

## Changes Made

### 1. Enhanced GraphSearch Component
**File**: [lightrag_webui/src/components/graph/GraphSearch.tsx](lightrag_webui/src/components/graph/GraphSearch.tsx)

**Changes**:
- Added `EdgeOption` component to display edge relationships with source → relation → target format
- Extended MiniSearch to index both nodes and edges with labels and relationship types
- Updated search engine to include edges in search results (50% nodes, 50% edges when showing defaults)
- Implemented middle-content matching for edges (matching by relationship type)
- Enhanced `loadOptions` to return both node and edge search results
- Updated onChange/onFocus handlers to distinguish between node and edge selections
- Removed unused `EdgeById` import

**Key Features**:
- Visual edge display showing: `SourceNode - RelationType - TargetNode`
- Edges colored by their relationship type
- Full-text search with fuzzy matching and prefix matching for edge relationships
- Seamless integration with existing node search

### 2. New ChunksPanel Component
**File**: [lightrag_webui/src/components/graph/ChunksPanel.tsx](lightrag_webui/src/components/graph/ChunksPanel.tsx)

**Features**:
- Displays chunks/references associated with selected nodes or edges
- Expandable chunk view with full content display
- Copy-to-clipboard functionality for chunk content
- Truncated display with hover tooltips for long paths/content
- Score display for ranked references
- File path navigation support (placeholder for opening files)
- Responsive layout with scrollable content area

**UI Elements**:
- Chunk count badge
- Collapsible sections for each chunk
- Copy and external link action buttons
- Multi-line content display with proper formatting

### 3. Updated Graph Store
**File**: [lightrag_webui/src/stores/graph.ts](lightrag_webui/src/stores/graph.ts)

**New State Properties**:
```typescript
nodeChunks: Record<string, Array<{
  reference_id: string
  file_path: string
  content?: string[]
  score?: number
}>>
edgeChunks: Record<string, Array<{
  reference_id: string
  file_path: string
  content?: string[]
  score?: number
}>>
```

**New Methods**:
- `setNodeChunks(nodeId, chunks)` - Store chunks for a node
- `setEdgeChunks(edgeId, chunks)` - Store chunks for an edge
- `clearNodeChunks(nodeId?)` - Clear chunks for specific node or all nodes
- `clearEdgeChunks(edgeId?)` - Clear chunks for specific edge or all edges

### 4. Enhanced GraphViewer Integration
**File**: [lightrag_webui/src/features/GraphViewer.tsx](lightrag_webui/src/features/GraphViewer.tsx)

**Changes**:
- Imported `ChunksPanel` component
- Updated `onSearchFocus` handler to support edge selections
- Updated `onSearchSelect` handler to support edge selections
- Integrated ChunksPanel next to PropertiesView in the property panel
- Both panels now display in a flex column layout in the top-right corner

**Behavior**:
- Node selection clears edge selection and vice versa
- Both panels show together when property panel is enabled
- ChunksPanel automatically hides when no chunks are available for selection

## Technical Details

### Search Architecture
- **MiniSearch Configuration**:
  - Fields indexed: `label`, `type`
  - Boost weights: `label: 2`, `type: 1`
  - Search options: `prefix: true, fuzzy: 0.2`
  
- **Edge Search Index**:
  - Format: `{id, label: "source - relation - target", type: "relationship_type", entityType: "edge"}`
  - Supports fuzzy matching on both relationship type and full edge description

### Component Hierarchy
```
GraphViewer
├── GraphSearch (enhanced with edges)
├── GraphControl
├── FocusOnNode
├── GraphLabels
└── PropertiesView Panel
    ├── PropertiesView (existing)
    └── ChunksPanel (new)
```

## Usage

### Searching for Edges
1. Open the graph
2. Use the search bar to find relationship types (e.g., "owns", "manages", "related_to")
3. Results show both matching nodes and edges
4. Click on an edge to select it and view its properties

### Viewing Chunks
1. Select a node or edge in the graph
2. If chunks are available (populated via `setNodeChunks` or `setEdgeChunks`), they appear in the ChunksPanel
3. Click the chevron to expand/collapse individual chunks
4. Use the copy button to copy chunk content to clipboard
5. Use the external link button to open the source file

## API Integration Points

### Backend Expected API Changes
To fully utilize the chunks display:
1. Query responses should populate `references` array with actual chunk data
2. Backend can call `useGraphStore.getState().setNodeChunks(nodeId, references)` after query completion
3. Optional: Implement edge-specific reference retrieval

### Example Usage in Query Component
```typescript
// After receiving query response
if (response.references) {
  response.references.forEach(ref => {
    useGraphStore.getState().setNodeChunks(selectedNodeId, response.references)
  })
}
```

## Testing Recommendations

1. **Edge Search**:
   - Search for relationship types (should find matching edges)
   - Verify edge visual format shows source, relation, and target
   - Test fuzzy matching (e.g., "own" finds "owns", "owned_by")
   - Test prefix matching (e.g., "rel" finds "related_to", "relationship")

2. **Chunks Display**:
   - Populate chunks using store methods
   - Verify expand/collapse functionality
   - Test copy-to-clipboard feature
   - Verify responsive layout with long content

3. **Integration**:
   - Ensure node/edge selection clears other type
   - Verify panels display together correctly
   - Check theme compatibility (dark/light mode)

## Files Modified
1. `lightrag_webui/src/components/graph/GraphSearch.tsx` - Edge search implementation
2. `lightrag_webui/src/components/graph/ChunksPanel.tsx` - New component
3. `lightrag_webui/src/stores/graph.ts` - Chunk storage state
4. `lightrag_webui/src/features/GraphViewer.tsx` - Integration and edge selection

## Build Status
✅ Build successful - all TypeScript types validated, no errors or warnings
