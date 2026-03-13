import { AlertTriangle, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import Button from './Button'

interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
  className?: string
  persistent?: boolean
}

export function ErrorBanner({ message, onDismiss, className, persistent = false }: ErrorBannerProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 text-red-900 dark:text-red-200',
        className
      )}
      role="alert"
    >
      <AlertTriangle className="h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
      <div className="flex-1 text-sm font-medium">
        {message}
      </div>
      {!persistent && onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          onClick={onDismiss}
          className="h-6 w-6 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}

export default ErrorBanner

// Made with Bob
