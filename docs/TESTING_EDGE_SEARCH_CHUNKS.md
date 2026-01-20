# Testing Edge Search & Chunks Display

## Browser Console Test Commands

Use these commands in your browser's DevTools console to test the new features:

### 1. Test Edge Search & Selection

```javascript
// Import the store
import { useGraphStore } from '@/stores/graph.ts'

// Get the current graph
const state = useGraphStore.getState()
const graph = state.sigmaGraph

// Check if edges exist
console.log('Total edges:', graph.edges().length)
console.log('Sample edges:', graph.edges().slice(0, 3).map(id => ({
  id,
  source: graph.getEdgeAttributes(id).source,
  target: graph.getEdgeAttributes(id).target,
  type: graph.getEdgeAttributes(id).type
})))

// Select the first edge (if available)
if (graph.edges().length > 0) {
  const firstEdgeId = graph.edges()[0]
  useGraphStore.getState().setSelectedEdge(firstEdgeId)
  console.log('Edge selected:', firstEdgeId)
}
```

### 2. Test Chunks Display

```javascript
import { useGraphStore } from '@/stores/graph.ts'

// Get a selected node/edge
const state = useGraphStore.getState()
const nodeId = state.selectedNode
const edgeId = state.selectedEdge

// Add test chunks for the selected node
if (nodeId) {
  useGraphStore.getState().setNodeChunks(nodeId, [
    {
      reference_id: 'test-1',
      file_path: '/path/to/document1.txt',
      content: ['This is test chunk content 1', 'More content here'],
      score: 0.95
    },
    {
      reference_id: 'test-2',
      file_path: '/path/to/document2.txt',
      content: ['This is test chunk content 2'],
      score: 0.87
    }
  ])
  console.log('Chunks added for node:', nodeId)
}

// Or add test chunks for selected edge
if (edgeId) {
  useGraphStore.getState().setEdgeChunks(edgeId, [
    {
      reference_id: 'edge-test-1',
      file_path: '/path/to/edge_doc.txt',
      content: ['Edge relationship chunk content'],
      score: 0.92
    }
  ])
  console.log('Chunks added for edge:', edgeId)
}
```

### 3. Monitor Console Logs

Open your browser's DevTools console and look for debug messages:

```
[GraphSearch] Edge selected: edge-id-123
[GraphViewer] Edge selected: edge-id-123
[ChunksPanel] Edge selected: edge-id-123, Chunks: [...]
```

These logs indicate that:
1. Edge was found and selected in search
2. GraphViewer properly routed the selection
3. ChunksPanel received the update

### 4. Test Search Results

```javascript
import { useGraphStore } from '@/stores/graph.ts'

// The search engine is created automatically
const searchEngine = useGraphStore.getState().searchEngine

if (searchEngine) {
  // Search for nodes
  console.log('Node search results for "person":', searchEngine.search('person').slice(0, 5))
  
  // Search for edges/relationships
  console.log('Edge search results for "has":', searchEngine.search('has').slice(0, 5))
  
  // Check what's in the search index
  console.log('Total documents in index:', searchEngine.documentCount)
}
```

## Feature Checklist

- [ ] Graph loads successfully
- [ ] Search bar shows both nodes and edges in results
- [ ] Can select edges from search results
- [ ] Selected edge is highlighted in the graph
- [ ] Properties panel appears when node/edge is selected
- [ ] ChunksPanel appears below PropertiesView when chunks are available
- [ ] Can expand/collapse chunks to view content
- [ ] Copy button works to copy chunk content
- [ ] PropertiesView shows edge properties (source, target, relationship type)

## Debugging Tips

### If edges aren't showing in search:
1. Check if graph has edges: `useGraphStore.getState().sigmaGraph.edges().length > 0`
2. Verify search engine was created: `useGraphStore.getState().searchEngine != null`
3. Check if edges are being indexed: Look for "Edge Search Index" in network requests

### If ChunksPanel doesn't show:
1. Verify chunks are stored: `useGraphStore.getState().nodeChunks` or `.edgeChunks`
2. Check if component is mounted: Look for `[ChunksPanel]` in console logs
3. Ensure property panel is visible: Check `useSettingsStore.getState().showPropertyPanel`

### If edge selection doesn't work:
1. Check that `graph.hasEdge(id)` returns true for selected edge
2. Verify store is updating: `useGraphStore.getState().selectedEdge`
3. Check browser console for error messages

## Example: Complete End-to-End Test

```javascript
// 1. Get the store and graph
const store = useGraphStore.getState()
const graph = store.sigmaGraph

// 2. Find first edge
const firstEdge = graph.edges()[0]
console.log('Testing with edge:', firstEdge)

// 3. Select the edge
store.setSelectedEdge(firstEdge)
console.log('Edge selected, selectedEdge is now:', store.selectedEdge)

// 4. Add test chunks
store.setEdgeChunks(firstEdge, [
  {
    reference_id: 'test-ref-1',
    file_path: '/documents/test.md',
    content: ['Test content for edge relationship'],
    score: 0.9
  }
])

// 5. Verify chunks are stored
console.log('Edge chunks:', store.edgeChunks[firstEdge])

// 6. Check PropertiesView is visible
console.log('Show property panel:', useSettingsStore.getState().showPropertyPanel)
```

## Next Steps

Once confirmed working in the browser console:
1. Integrate with actual query results to populate chunks
2. Handle references from backend API responses
3. Test with real graph data
4. Verify performance with large edge sets
