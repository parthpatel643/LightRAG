import { useEffect, useState } from 'react'
import { useGraphStore } from '@/stores/graph'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, Copy, ExternalLink } from 'lucide-react'
import Button from '@/components/ui/Button'
import { toast } from 'sonner'
import Text from '@/components/ui/Text'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import useTheme from '@/hooks/useTheme'

interface ChunkReference {
  reference_id: string
  file_path: string
  content?: string[]
  score?: number
}

/**
 * Component that displays chunks/references for selected graph elements.
 * This component stores chunks related to nodes and edges in the graph store.
 */
const ChunksPanel = () => {
  const { t } = useTranslation()
  const { theme } = useTheme()
  const selectedNode = useGraphStore.use.selectedNode()
  const selectedEdge = useGraphStore.use.selectedEdge()
  const [chunks, setChunks] = useState<ChunkReference[]>([])
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set())

  // Get chunks from graph store if available
  const nodeChunks = useGraphStore.use.nodeChunks()
  const edgeChunks = useGraphStore.use.edgeChunks()

  useEffect(() => {
    if (selectedNode) {
      // Get chunks for the selected node
      const nodeChunkList = nodeChunks[selectedNode] || []
      setChunks(nodeChunkList)
      console.debug('[ChunksPanel] Node selected:', selectedNode, 'Chunks:', nodeChunkList)
    } else if (selectedEdge) {
      // Get chunks for the selected edge
      const edgeChunkList = edgeChunks[selectedEdge] || []
      setChunks(edgeChunkList)
      console.debug('[ChunksPanel] Edge selected:', selectedEdge, 'Chunks:', edgeChunkList)
    } else {
      setChunks([])
      console.debug('[ChunksPanel] No selection')
    }
  }, [selectedNode, selectedEdge, nodeChunks, edgeChunks])

  const toggleChunkExpand = (chunkId: string) => {
    const newExpanded = new Set(expandedChunks)
    if (newExpanded.has(chunkId)) {
      newExpanded.delete(chunkId)
    } else {
      newExpanded.add(chunkId)
    }
    setExpandedChunks(newExpanded)
  }

  const copyChunkContent = (content: string[]) => {
    const text = content.join('\n\n')
    navigator.clipboard.writeText(text)
    toast.success(t('graphPanel.chunks.copied', 'Chunk content copied to clipboard'))
  }

  if (chunks.length === 0) {
    return null
  }

  return (
    <div className="bg-background/80 max-w-2xl rounded-lg border-2 p-3 text-xs backdrop-blur-lg">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-bold tracking-wide text-blue-700">
          {t('graphPanel.chunks.title', 'Chunks / References')}
        </h3>
        <span className="text-xs text-primary/60 bg-primary/10 px-2 py-1 rounded">
          {chunks.length}
        </span>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {chunks.map((chunk, index) => {
          const isExpanded = expandedChunks.has(chunk.reference_id)
          const hasContent = chunk.content && chunk.content.length > 0

          return (
            <div
              key={`${chunk.reference_id}-${index}`}
              className="border border-primary/20 rounded-lg p-2 bg-primary/5 hover:bg-primary/10 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {hasContent && (
                      <button
                        onClick={() => toggleChunkExpand(chunk.reference_id)}
                        className="flex-shrink-0 text-primary/60 hover:text-primary transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </button>
                    )}
                    <div className="flex-1 min-w-0">
                      <Text
                        className="text-xs font-medium truncate text-primary"
                        text={chunk.file_path}
                        tooltip={chunk.file_path}
                      />
                      {chunk.score !== undefined && (
                        <span className="text-xs text-primary/50 ml-1">
                          (score: {(chunk.score * 100).toFixed(1)}%)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  {hasContent && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-5 w-5 border border-gray-300 hover:bg-gray-200 dark:border-gray-600 dark:hover:bg-gray-700"
                      onClick={() => copyChunkContent(chunk.content!)}
                      tooltip={t('graphPanel.chunks.copy', 'Copy content')}
                    >
                      <Copy className="h-3 w-3 text-gray-700 dark:text-gray-300" />
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-5 w-5 border border-gray-300 hover:bg-gray-200 dark:border-gray-600 dark:hover:bg-gray-700"
                    tooltip={t('graphPanel.chunks.openFile', 'Open file')}
                  >
                    <ExternalLink className="h-3 w-3 text-gray-700 dark:text-gray-300" />
                  </Button>
                </div>
              </div>

              {/* Expanded content - rendered as markdown */}
              {isExpanded && hasContent && (
                <div className="mt-2 pl-6 border-l border-primary/30 text-xs text-primary/70 prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-code:px-1 prose-code:py-0.5 prose-code:bg-primary/10 prose-code:rounded prose-pre:bg-primary/5 prose-pre:text-xs">
                  {chunk.content?.map((text, idx) => (
                    <div key={idx} className="py-1">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          code: ({ node, inline, className, children, ...props }: any) => {
                            const match = /language-(\w+)/.exec(className || '')
                            return !inline && match ? (
                              <SyntaxHighlighter
                                style={theme === 'dark' ? oneDark : oneLight}
                                language={match[1]}
                                PreTag="div"
                                className="text-xs rounded"
                                {...props}
                              >
                                {String(children).replace(/\n$/, '')}
                              </SyntaxHighlighter>
                            ) : (
                              <code className="bg-primary/10 px-1 py-0.5 rounded text-xs font-mono" {...props}>
                                {children}
                              </code>
                            )
                          },
                          h1: ({ children }: any) => <h1 className="text-sm font-bold mt-2 mb-1">{children}</h1>,
                          h2: ({ children }: any) => <h2 className="text-xs font-bold mt-2 mb-1">{children}</h2>,
                          h3: ({ children }: any) => <h3 className="text-xs font-semibold mt-1 mb-1">{children}</h3>,
                          p: ({ children }: any) => <p className="my-1 text-xs leading-relaxed">{children}</p>,
                          ul: ({ children }: any) => <ul className="list-disc pl-4 my-1">{children}</ul>,
                          ol: ({ children }: any) => <ol className="list-decimal pl-4 my-1">{children}</ol>,
                          li: ({ children }: any) => <li className="my-0.5 text-xs">{children}</li>,
                          a: ({ href, children }: any) => (
                            <a href={href} className="text-primary hover:underline" target="_blank" rel="noopener noreferrer">
                              {children}
                            </a>
                          ),
                          blockquote: ({ children }: any) => (
                            <blockquote className="border-l-2 border-primary/30 pl-2 italic text-xs my-1">
                              {children}
                            </blockquote>
                          ),
                        }}
                      >
                        {text}
                      </ReactMarkdown>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default ChunksPanel
