import { useCallback } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { Clock, Info, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/Tooltip'
import Badge from '@/components/ui/Badge'

interface TemporalQueryPanelProps {
  referenceDate: string | undefined
  onReferenceDateChange: (date: string | undefined) => void
  isTemporalMode: boolean
}

export default function TemporalQueryPanel({
  referenceDate,
  onReferenceDateChange,
  isTemporalMode
}: TemporalQueryPanelProps) {
  const { t } = useTranslation()

  const handleDateChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    onReferenceDateChange(value || undefined)
  }, [onReferenceDateChange])

  const handleClearDate = useCallback(() => {
    onReferenceDateChange(undefined)
  }, [onReferenceDateChange])

  const handleToday = useCallback(() => {
    const today = new Date().toISOString().split('T')[0]
    onReferenceDateChange(today)
  }, [onReferenceDateChange])

  if (!isTemporalMode) {
    return null
  }

  return (
    <div className="flex flex-col gap-2 p-3 border rounded-lg bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
          {t('retrievePanel.temporal.title', 'Temporal Query Mode')}
        </span>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3 w-3 text-blue-600 dark:text-blue-400 cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-xs">
              <p className="text-xs">
                {t('retrievePanel.temporal.tooltip', 
                  'Temporal mode retrieves information as it existed on a specific date. ' +
                  'This is useful for querying historical versions of documents and tracking changes over time.'
                )}
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex items-center gap-2">
        <Input
          type="date"
          value={referenceDate || ''}
          onChange={handleDateChange}
          max={new Date().toISOString().split('T')[0]}
          className="flex-1"
          placeholder={t('retrievePanel.temporal.selectDate', 'Select reference date')}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handleToday}
          title={t('retrievePanel.temporal.today', 'Today')}
        >
          {t('retrievePanel.temporal.today', 'Today')}
        </Button>
        {referenceDate && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearDate}
            title={t('retrievePanel.temporal.clear', 'Clear')}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {referenceDate && (
        <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-300">
          <Badge variant="secondary" className="text-xs">
            {t('retrievePanel.temporal.activeDate', 'Active')}: {referenceDate}
          </Badge>
        </div>
      )}

      <div className="text-xs text-blue-600 dark:text-blue-400">
        <p>
          {t('retrievePanel.temporal.description',
            'Queries will retrieve entity and relation versions as they existed on the selected date.'
          )}
        </p>
      </div>
    </div>
  )
}

// Made with Bob
