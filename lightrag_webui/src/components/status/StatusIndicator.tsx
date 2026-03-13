import { cn } from '@/lib/utils'
import { useBackendState } from '@/stores/state'
import { useEffect, useState } from 'react'
import StatusDialog from './StatusDialog'
import { useTranslation } from 'react-i18next'

const StatusIndicator = () => {
  const { t } = useTranslation()
  const health = useBackendState.use.health()
  const lastCheckTime = useBackendState.use.lastCheckTime()
  const status = useBackendState.use.status()
  const [animate, setAnimate] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)

  // listen to health change
  useEffect(() => {
    setAnimate(true)
    const timer = setTimeout(() => setAnimate(false), 300)
    return () => clearTimeout(timer)
  }, [lastCheckTime])

  return (
    <>
      {/* Header indicator - more prominent when disconnected */}
      <div
        className={cn(
          "flex items-center gap-2 cursor-pointer transition-all duration-300 px-2 py-1 rounded-md",
          !health && "bg-red-50 dark:bg-red-900/20 animate-pulse"
        )}
        onClick={() => setDialogOpen(true)}
        title={health ? t('graphPanel.statusIndicator.connected') : t('graphPanel.statusIndicator.disconnected')}
      >
        <div
          className={cn(
            'h-2 w-2 rounded-full transition-all duration-300',
            health ? 'bg-green-500' : 'bg-red-500',
            animate && 'scale-125',
            !health && 'shadow-[0_0_8px_rgba(239,68,68,0.6)]'
          )}
        />
        {!health && (
          <span className="text-red-600 dark:text-red-400 text-xs font-medium">
            {t('graphPanel.statusIndicator.disconnected')}
          </span>
        )}
      </div>

      <StatusDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        status={status}
      />
    </>
  )
}

export default StatusIndicator
