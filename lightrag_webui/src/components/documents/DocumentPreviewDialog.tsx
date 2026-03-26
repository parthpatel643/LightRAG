import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/Dialog'
import { DocStatusResponse } from '@/api/lightrag'
import { useTranslation } from 'react-i18next'
import { FileText, Calendar, Hash, FileType, Layers } from 'lucide-react'
import { cn } from '@/lib/utils'

interface DocumentPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  document: DocStatusResponse | null
}

export function DocumentPreviewDialog({ open, onOpenChange, document }: DocumentPreviewDialogProps) {
  const { t } = useTranslation()

  if (!document) return null

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleString()
    } catch {
      return dateString
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'processed':
        return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20'
      case 'processing':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20'
      case 'pending':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
      case 'preprocessed':
        return 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20'
      case 'failed':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20'
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/20'
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Document Preview
          </DialogTitle>
          <DialogDescription>
            View document details and content
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-auto space-y-4">
          {/* Document Metadata */}
          <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 dark:bg-gray-900/40 rounded-lg">
            <div className="space-y-3">
              <div className="flex items-start gap-2">
                <Hash className="h-4 w-4 mt-1 text-gray-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Document ID</p>
                  <p className="text-sm font-mono break-all">{document.id}</p>
                </div>
              </div>

              {document.file_path && (
                <div className="flex items-start gap-2">
                  <FileType className="h-4 w-4 mt-1 text-gray-500" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">File Path</p>
                    <p className="text-sm break-all">{document.file_path}</p>
                  </div>
                </div>
              )}

              <div className="flex items-start gap-2">
                <Layers className="h-4 w-4 mt-1 text-gray-500" />
                <div className="flex-1">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Status</p>
                  <span className={cn(
                    'inline-flex items-center px-2 py-1 rounded-md text-xs font-medium',
                    getStatusColor(document.status)
                  )}>
                    {document.status}
                  </span>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-start gap-2">
                <Calendar className="h-4 w-4 mt-1 text-gray-500" />
                <div className="flex-1">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Created</p>
                  <p className="text-sm">{formatDate(document.created_at)}</p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <Calendar className="h-4 w-4 mt-1 text-gray-500" />
                <div className="flex-1">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Updated</p>
                  <p className="text-sm">{formatDate(document.updated_at)}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Length</p>
                  <p className="text-sm font-medium">{document.content_length?.toLocaleString() || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Chunks</p>
                  <p className="text-sm font-medium">{document.chunks_count || 'N/A'}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Document Summary */}
          {document.content_summary && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Summary</h3>
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {document.content_summary}
                </p>
              </div>
            </div>
          )}

          {/* Metadata */}
          {document.metadata && Object.keys(document.metadata).length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Metadata</h3>
              <div className="p-3 bg-gray-50 dark:bg-gray-900/40 rounded-lg border border-gray-200 dark:border-gray-700">
                <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono">
                  {JSON.stringify(document.metadata, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* No content message */}
          {!document.content_summary && (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No summary available for this document</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default DocumentPreviewDialog

// Made with Bob