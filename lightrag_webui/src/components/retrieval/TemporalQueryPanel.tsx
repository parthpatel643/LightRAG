import { useCallback, useState } from 'react'
import { Calendar } from '@/components/ui/Calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/Popover'
import { Button } from '@/components/ui/Button'
import { CalendarIcon, Clock, Info } from 'lucide-react'
import { format } from 'date-fns'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/Tooltip'
import { Badge } from '@/components/ui/Badge'

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
  const [date, setDate] = useState<Date | undefined>(
    referenceDate ? new Date(referenceDate) : undefined
  )

  const handleDateSelect = useCallback((selectedDate: Date | undefined) => {
    setDate(selectedDate)
    if (selectedDate) {
      // Format date as YYYY-MM-DD
      const formattedDate = format(selectedDate, 'yyyy-MM-dd')
      onReferenceDateChange(formattedDate)
    } else {
      onReferenceDateChange(undefined)
    }
  }, [onReferenceDateChange])

  const handleClearDate = useCallback(() => {
    setDate(undefined)
    onReferenceDateChange(undefined)
  }, [onReferenceDateChange])

  const handleToday = useCallback(() => {
    const today = new Date()
    setDate(today)
    onReferenceDateChange(format(today, 'yyyy-MM-dd'))
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
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn(
                'w-full justify-start text-left font-normal',
                !date && 'text-muted-foreground'
              )}
              size="sm"
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {date ? (
                format(date, 'PPP')
              ) : (
                <span>{t('retrievePanel.temporal.selectDate', 'Select reference date')}</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={date}
              onSelect={handleDateSelect}
              initialFocus
              disabled={(date) => date > new Date()}
            />
            <div className="flex gap-2 p-3 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={handleToday}
                className="flex-1"
              >
                {t('retrievePanel.temporal.today', 'Today')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearDate}
                className="flex-1"
              >
                {t('retrievePanel.temporal.clear', 'Clear')}
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {date && (
        <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-300">
          <Badge variant="secondary" className="text-xs">
            {t('retrievePanel.temporal.activeDate', 'Active')}: {format(date, 'yyyy-MM-dd')}
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


