import { FC, useCallback, useEffect } from 'react'
import {
  GraphSearchInputProps,
  GraphSearchContextProviderProps
} from '@react-sigma/graph-search'
import { AsyncSearch } from '@/components/ui/AsyncSearch'
import { searchResultLimit } from '@/lib/constants'
import { useGraphStore } from '@/stores/graph'
import MiniSearch from 'minisearch'
import { useTranslation } from 'react-i18next'

// Message item identifier for search results
export const messageId = '__message_item'

// Search result option item interface
export interface OptionItem {
  id: string
  type: 'nodes' | 'edges' | 'message'
  message?: string
}

const NodeOption = ({ id }: { id: string }) => {
  const graph = useGraphStore.use.sigmaGraph()

  // Early return if no graph or node doesn't exist
  if (!graph?.hasNode(id)) {
    return null
  }

  // Safely get node attributes with fallbacks
  const label = graph.getNodeAttribute(id, 'label') || id
  const color = graph.getNodeAttribute(id, 'color') || '#666'
  const size = graph.getNodeAttribute(id, 'size') || 4

  // Custom node display component that doesn't rely on @react-sigma/graph-search
  return (
    <div className="flex items-center gap-2 p-2 text-sm">
      <div
        className="rounded-full flex-shrink-0"
        style={{
          width: Math.max(8, Math.min(size * 2, 16)),
          height: Math.max(8, Math.min(size * 2, 16)),
          backgroundColor: color
        }}
      />
      <span className="truncate">{label}</span>
    </div>
  )
}

const EdgeOption = ({ id }: { id: string }) => {
  const graph = useGraphStore.use.sigmaGraph()

  // Early return if no graph or edge doesn't exist
  if (!graph?.hasEdge(id)) {
    return null
  }

  // Safely get edge attributes
  const edgeData = graph.getEdgeAttributes(id)
  const source = edgeData.source || ''
  const target = edgeData.target || ''
  const label = edgeData.label || edgeData.type || 'Relationship'
  const sourceLabel = source && graph.hasNode(source) ? 
    (graph.getNodeAttribute(source, 'label') || source) : source
  const targetLabel = target && graph.hasNode(target) ? 
    (graph.getNodeAttribute(target, 'label') || target) : target
  const color = edgeData.color || '#999'

  // Edge display component showing source -> relation -> target
  return (
    <div className="flex items-center gap-2 p-2 text-sm max-w-md">
      <div className="flex items-center gap-1 overflow-hidden">
        <span className="truncate text-xs opacity-75">{sourceLabel}</span>
        <span className="flex-shrink-0 mx-1 font-semibold text-xs px-1 py-0.5 rounded" style={{ backgroundColor: color, color: 'white' }}>
          {label}
        </span>
        <span className="truncate text-xs opacity-75">{targetLabel}</span>
      </div>
    </div>
  )
}

function OptionComponent(item: OptionItem) {
  return (
    <div>
      {item.type === 'nodes' && <NodeOption id={item.id} />}
      {item.type === 'edges' && <EdgeOption id={item.id} />}
      {item.type === 'message' && <div>{item.message}</div>}
    </div>
  )
}


/**
 * Component thats display the search input.
 */
export const GraphSearchInput = ({
  onChange,
  onFocus,
  value
}: {
  onChange: GraphSearchInputProps['onChange']
  onFocus?: GraphSearchInputProps['onFocus']
  value?: GraphSearchInputProps['value']
}) => {
  const { t } = useTranslation()
  const graph = useGraphStore.use.sigmaGraph()
  const searchEngine = useGraphStore.use.searchEngine()

  // Reset search engine when graph changes
  useEffect(() => {
    if (graph) {
      useGraphStore.getState().resetSearchEngine()
    }
  }, [graph]);

  // Create search engine when needed
  useEffect(() => {
    // Skip if no graph, empty graph, or search engine already exists
    if (!graph || graph.nodes().length === 0 || searchEngine) {
      console.debug('[GraphSearch] Skipping search engine creation:', {
        hasGraph: !!graph,
        graphNodesCount: graph?.nodes().length || 0,
        hasSearchEngine: !!searchEngine
      })
      return
    }

    console.debug('[GraphSearch] Creating search engine with', graph.nodes().length, 'nodes and', graph.edges().length, 'edges')

    // Create new search engine
    const newSearchEngine = new MiniSearch({
      idField: 'id',
      fields: ['label', 'type'],
      searchOptions: {
        prefix: true,
        fuzzy: 0.2,
        boost: {
          label: 2,
          type: 1
        }
      }
    })

    // Add nodes to search engine with safety checks
    const nodeDocuments = graph.nodes()
      .filter(id => graph.hasNode(id)) // Ensure node exists before accessing attributes
      .map((id: string) => ({
        id: id,
        label: graph.getNodeAttribute(id, 'label'),
        type: 'node',
        entityType: 'node'
      }))

    console.debug('[GraphSearch] Adding', nodeDocuments.length, 'nodes to search engine')
    if (nodeDocuments.length > 0) {
      newSearchEngine.addAll(nodeDocuments)
    }

    // Add edges to search engine with safety checks
    const edgeDocuments = graph.edges()
      .filter(id => graph.hasEdge(id))
      .map((id: string) => {
        const edgeData = graph.getEdgeAttributes(id)
        const sourceLabel = edgeData.source && graph.hasNode(edgeData.source) ? 
          graph.getNodeAttribute(edgeData.source, 'label') : edgeData.source
        const targetLabel = edgeData.target && graph.hasNode(edgeData.target) ? 
          graph.getNodeAttribute(edgeData.target, 'label') : edgeData.target
        const label = `${sourceLabel} - ${edgeData.label || edgeData.type || 'link'} - ${targetLabel}`
        
        return {
          id: id,
          label: label,
          type: edgeData.label || edgeData.type || 'relationship',
          entityType: 'edge'
        }
      })

    console.debug('[GraphSearch] Adding', edgeDocuments.length, 'edges to search engine', { sampleEdges: edgeDocuments.slice(0, 3) })
    if (edgeDocuments.length > 0) {
      newSearchEngine.addAll(edgeDocuments)
    }

    // Update search engine in store
    useGraphStore.getState().setSearchEngine(newSearchEngine)
    console.debug('[GraphSearch] Search engine created successfully')
  }, [graph, searchEngine])

  /**
   * Loading the options while the user is typing.
   */
  const loadOptions = useCallback(
    async (query?: string): Promise<OptionItem[]> => {
      if (onFocus) onFocus(null)

      // Safety checks to prevent crashes
      if (!graph || !searchEngine) {
        console.debug('[GraphSearch] loadOptions: Missing graph or searchEngine', { hasGraph: !!graph, hasSearchEngine: !!searchEngine })
        return []
      }

      // Verify graph has nodes before proceeding
      if (graph.nodes().length === 0) {
        console.debug('[GraphSearch] loadOptions: Graph has no nodes')
        return []
      }

      // If no query, return some nodes and edges for user to select
      if (!query) {
        const nodeIds = graph.nodes()
          .filter(id => graph.hasNode(id))
          .slice(0, Math.floor(searchResultLimit / 2))
        
        const edgeIds = graph.edges()
          .filter(id => graph.hasEdge(id))
          .slice(0, Math.floor(searchResultLimit / 2))

        const results: OptionItem[] = [
          ...nodeIds.map(id => ({ id, type: 'nodes' as const })),
          ...edgeIds.map(id => ({ id, type: 'edges' as const }))
        ]
        
        console.debug('[GraphSearch] loadOptions: No query, returning defaults:', { nodes: nodeIds.length, edges: edgeIds.length })
        return results.slice(0, searchResultLimit)
      }

      // If has query, search nodes and edges and verify they still exist
      let result: OptionItem[] = searchEngine.search(query)
        .filter((r: { id: string, entityType?: string }) => {
          if (r.entityType === 'edge') {
            return graph.hasEdge(r.id)
          }
          return graph.hasNode(r.id)
        })
        .map((r: { id: string, entityType?: string }) => {
          const type = r.entityType === 'edge' ? 'edges' : 'nodes'
          return {
            id: r.id,
            type: type as 'nodes' | 'edges'
          }
        })

      console.debug('[GraphSearch] loadOptions: Search results for query "' + query + '":', { totalResults: result.length, sampleResults: result.slice(0, 3) })

      // Add middle-content matching if results are few
      // This enables matching content in the middle of text, not just from the beginning
      if (result.length < 5) {
        // Get already matched IDs to avoid duplicates
        const matchedIds = new Set(result.map(item => item.id))

        // Perform middle-content matching on all nodes with safety checks
        const middleMatchResults = graph.nodes()
          .filter(id => {
            // Skip already matched nodes
            if (matchedIds.has(id)) return false

            // Ensure node exists before accessing attributes
            if (!graph.hasNode(id)) return false

            // Get node label safely
            const label = graph.getNodeAttribute(id, 'label')
            // Match if label contains query string but doesn't start with it
            return label &&
                   typeof label === 'string' &&
                   !label.toLowerCase().startsWith(query.toLowerCase()) &&
                   label.toLowerCase().includes(query.toLowerCase())
          })
          .map(id => ({
            id,
            type: 'nodes' as const
          }))

        // Also match edges in the middle
        const middleEdgeMatchResults = graph.edges()
          .filter(id => {
            // Skip already matched edges
            if (matchedIds.has(id)) return false

            // Ensure edge exists
            if (!graph.hasEdge(id)) return false

            // Get edge label
            const edgeData = graph.getEdgeAttributes(id)
            const label = edgeData.label || edgeData.type || ''
            
            return label &&
                   typeof label === 'string' &&
                   !label.toLowerCase().startsWith(query.toLowerCase()) &&
                   label.toLowerCase().includes(query.toLowerCase())
          })
          .map(id => ({
            id,
            type: 'edges' as const
          }))

        // Merge results
        result = [...result, ...middleMatchResults, ...middleEdgeMatchResults]
      }

      // prettier-ignore
      return result.length <= searchResultLimit
        ? result
        : [
          ...result.slice(0, searchResultLimit),
          {
            type: 'message',
            id: messageId,
            message: t('graphPanel.search.message', { count: result.length - searchResultLimit })
          }
        ]
    },
    [graph, searchEngine, onFocus, t]
  )

  return (
    <AsyncSearch
      className="bg-background/60 w-24 rounded-xl border-1 opacity-60 backdrop-blur-lg transition-all hover:w-fit hover:opacity-100 w-full"
      fetcher={loadOptions}
      renderOption={OptionComponent}
      getOptionValue={(item) => item.id}
      value={value && value.type !== 'message' ? value.id : null}
      onChange={(id) => {
        if (id !== messageId) {
          // Determine if this is a node or edge
          if (graph && graph.hasEdge(id)) {
            console.debug('[GraphSearch] Edge selected:', id)
            onChange(id ? { id, type: 'edges' } : null)
          } else {
            console.debug('[GraphSearch] Node selected:', id)
            onChange(id ? { id, type: 'nodes' } : null)
          }
        }
      }}
      onFocus={(id) => {
        if (id !== messageId && onFocus) {
          // Determine if this is a node or edge
          if (graph && graph.hasEdge(id)) {
            onFocus(id ? { id, type: 'edges' } : null)
          } else {
            onFocus(id ? { id, type: 'nodes' } : null)
          }
        }
      }}
      ariaLabel={t('graphPanel.search.placeholder')}
      placeholder={t('graphPanel.search.placeholder')}
      noResultsMessage={t('graphPanel.search.placeholder')}
    />
  )
}

/**
 * Component that display the search.
 */
const GraphSearch: FC<GraphSearchInputProps & GraphSearchContextProviderProps> = ({ ...props }) => {
  return <GraphSearchInput {...props} />
}

export default GraphSearch
