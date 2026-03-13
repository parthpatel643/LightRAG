import { useState, useMemo } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/Dialog'
import { useSettingsStore } from '@/stores/settings'
import { useTranslation } from 'react-i18next'
import { History, Search, Star, StarOff, Trash2, Copy, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { copyToClipboard } from '@/utils/clipboard'

interface QueryHistoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelectQuery: (query: string) => void
}

interface SavedQuery {
  query: string
  timestamp: number
  starred: boolean
  mode?: string
}

export function QueryHistoryDialog({ open, onOpenChange, onSelectQuery }: QueryHistoryDialogProps) {
  const { t } = useTranslation()
  const userPromptHistory = useSettingsStore.use.userPromptHistory()
  const setUserPromptHistory = useSettingsStore.use.setUserPromptHistory()
  
  const [searchTerm, setSearchTerm] = useState('')
  const [starredQueries, setStarredQueries] = useState<Set<string>>(new Set())
  const [filterStarred, setFilterStarred] = useState(false)

  // Convert history to saved queries format
  const savedQueries = useMemo<SavedQuery[]>(() => {
    return userPromptHistory.map((query, index) => ({
      query,
      timestamp: Date.now() - (userPromptHistory.length - index) * 60000, // Mock timestamps
      starred: starredQueries.has(query)
    }))
  }, [userPromptHistory, starredQueries])

  // Filter queries based on search and starred filter
  const filteredQueries = useMemo(() => {
    let filtered = savedQueries

    if (searchTerm) {
      filtered = filtered.filter(q =>
        q.query.toLowerCase().includes(searchTerm.toLowerCase())
      )
    }

    if (filterStarred) {
      filtered = filtered.filter(q => q.starred)
    }

    return filtered.sort((a, b) => {
      // Starred queries first
      if (a.starred && !b.starred) return -1
      if (!a.starred && b.starred) return 1
      // Then by timestamp (most recent first)
      return b.timestamp - a.timestamp
    })
  }, [savedQueries, searchTerm, filterStarred])

  const handleToggleStar = (query: string) => {
    setStarredQueries(prev => {
      const newSet = new Set(prev)
      if (newSet.has(query)) {
        newSet.delete(query)
      } else {
        newSet.add(query)
      }
      return newSet
    })
  }

  const handleDeleteQuery = (query: string) => {
    const newHistory = userPromptHistory.filter(q => q !== query)
    setUserPromptHistory(newHistory)
    toast.success('Query deleted from history')
  }

  const handleClearAll = () => {
    if (confirm('Are you sure you want to clear all query history?')) {
      setUserPromptHistory([])
      setStarredQueries(new Set())
      toast.success('Query history cleared')
    }
  }

  const handleCopyQuery = async (query: string) => {
    const success = await copyToClipboard(query)
    if (success) {
      toast.success('Query copied to clipboard')
    }
  }

  const handleSelectQuery = (query: string) => {
    onSelectQuery(query)
    onOpenChange(false)
    toast.success('Query loaded')
  }

  const formatTimestamp = (timestamp: number) => {
    const now = Date.now()
    const diff = now - timestamp
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    if (days < 7) return `${days}d ago`
    return new Date(timestamp).toLocaleDateString()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="h-5 w-5" />
            Query History
          </DialogTitle>
          <DialogDescription>
            View, search, and manage your query history. Star important queries for quick access.
          </DialogDescription>
        </DialogHeader>

        {/* Search and filters */}
        <div className="flex gap-2 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              type="search"
              placeholder="Search queries..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button
            variant={filterStarred ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilterStarred(!filterStarred)}
            className="flex items-center gap-2"
          >
            <Star className={cn('h-4 w-4', filterStarred && 'fill-current')} />
            Starred
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClearAll}
            disabled={userPromptHistory.length === 0}
            className="flex items-center gap-2 text-red-600 hover:text-red-700 dark:text-red-400"
          >
            <Trash2 className="h-4 w-4" />
            Clear All
          </Button>
        </div>

        {/* Query list */}
        <div className="flex-1 overflow-auto border rounded-md">
          {filteredQueries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-center">
              <History className="h-12 w-12 text-gray-300 dark:text-gray-600 mb-4" />
              <p className="text-gray-500 dark:text-gray-400 mb-2">
                {searchTerm || filterStarred ? 'No queries found' : 'No query history yet'}
              </p>
              <p className="text-sm text-gray-400 dark:text-gray-500">
                {searchTerm || filterStarred
                  ? 'Try adjusting your search or filters'
                  : 'Your query history will appear here'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {filteredQueries.map((item, index) => (
                <div
                  key={index}
                  className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group"
                >
                  <div className="flex items-start gap-3">
                    {/* Star button */}
                    <button
                      onClick={() => handleToggleStar(item.query)}
                      className="mt-1 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                      title={item.starred ? 'Unstar query' : 'Star query'}
                    >
                      {item.starred ? (
                        <Star className="h-4 w-4 text-yellow-500 fill-current" />
                      ) : (
                        <StarOff className="h-4 w-4 text-gray-400" />
                      )}
                    </button>

                    {/* Query content */}
                    <div className="flex-1 min-w-0">
                      <button
                        onClick={() => handleSelectQuery(item.query)}
                        className="text-left w-full group-hover:text-primary transition-colors"
                      >
                        <p className="text-sm font-medium break-words">
                          {item.query}
                        </p>
                      </button>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {formatTimestamp(item.timestamp)}
                      </p>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleCopyQuery(item.query)}
                        className="h-8 w-8"
                        title="Copy query"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteQuery(item.query)}
                        className="h-8 w-8 text-red-600 hover:text-red-700 dark:text-red-400"
                        title="Delete query"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer stats */}
        <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400 pt-2 border-t">
          <span>
            {filteredQueries.length} {filteredQueries.length === 1 ? 'query' : 'queries'}
            {searchTerm || filterStarred ? ' (filtered)' : ''}
          </span>
          <span>
            {starredQueries.size} starred
          </span>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default QueryHistoryDialog

// Made with Bob