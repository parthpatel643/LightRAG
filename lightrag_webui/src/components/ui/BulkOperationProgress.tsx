import { Loader2 } from 'lucide-react'

interface BulkOperationProgressProps {
  isActive: boolean
  message: string
  count?: number
}

export default function BulkOperationProgress({ isActive, message, count }: BulkOperationProgressProps) {
  if (!isActive) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-4 min-w-[300px] max-w-md">
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-blue-600 dark:text-blue-400" />
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {message}
          </p>
          {count !== undefined && count > 0 && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Processing {count} {count === 1 ? 'item' : 'items'}...
            </p>
          )}
        </div>
      </div>
      
      {/* Indeterminate progress bar */}
      <div className="mt-3 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className="h-full bg-blue-600 dark:bg-blue-400 rounded-full animate-progress-indeterminate" />
      </div>
    </div>
  )
}

// Made with Bob
