import { useCallback, useEffect, useRef, useState } from 'react'
import { useSettingsStore } from '@/stores/settings'
import { useQuerySettingsStore } from '@/stores/querySettings'
import { useWebuiRetrievalHistoryStore } from '@/stores/webuiRetrievalHistory'
import { useWorkspaceStore } from '@/stores/workspace'
import QuerySettings from '@/components/retrieval/QuerySettings'
import QueryHistoryDialog from '@/components/retrieval/QueryHistoryDialog'
import MessageList from '@/features/retrieval/MessageList'
import QueryComposer from '@/features/retrieval/QueryComposer'
import { useQuerySession } from '@/features/retrieval/useQuerySession'
import Button from '@/components/ui/Button'
import { HistoryIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { prepareQueryInput, SUPPORTED_QUERY_MODES } from '@/features/retrieval/queryInput'

/**
 * The ADMIN query page: composes the shared query session, message list and
 * composer with the QuerySettings sidebar and the `/mode` prefix override.
 * Its history storage is the admin entry's own store; the settings snapshot
 * is passed through unmodified (including the `only_need_*` debug switches —
 * those are clamped only on the workspace page).
 */
export default function RetrievalView() {
  const { t } = useTranslation()
  // Get current tab to determine if this tab is active (for performance optimization)
  const currentTab = useSettingsStore.use.currentTab()
  const isRetrievalTabActive = currentTab === 'retrieval'

  const [showHistoryDialog, setShowHistoryDialog] = useState(false)

  const getQuerySettingsSnapshot = useCallback(
    () => useQuerySettingsStore.getState().querySettings,
    []
  )

  const onUserPromptUsed = useCallback((prompt: string) => {
    useSettingsStore.getState().addUserPromptToHistory(prompt)
  }, [])

  const session = useQuerySession({
    historyStore: useWebuiRetrievalHistoryStore,
    getQuerySettingsSnapshot,
    onUserPromptUsed
  })

  // Reset the conversation when the active workspace changes, so answers from
  // the previous workspace's knowledge base are not shown against the new one.
  const currentWorkspace = useWorkspaceStore.use.currentWorkspace()
  const previousWorkspaceRef = useRef(currentWorkspace)
  const { clearMessages } = session
  useEffect(() => {
    if (previousWorkspaceRef.current === currentWorkspace) return
    previousWorkspaceRef.current = currentWorkspace
    clearMessages()
  }, [currentWorkspace, clearMessages])

  // The composer owns its draft state, so the history picker fills it through
  // the native value setter + input event, which React's onChange picks up.
  const handleSelectHistoryQuery = useCallback((query: string) => {
    const el = document.getElementById('query-input') as
      | HTMLInputElement
      | HTMLTextAreaElement
      | null
    if (!el) return
    const proto =
      el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(el, query)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.focus()
  }, [])

  // A leading `/mode ` prefix overrides the query mode for this one request.
  // The workspace entry uses the same shared preparation contract.
  const handleSend = useCallback(
    (input: string): string | null => {
      const prepared = prepareQueryInput(input, getQuerySettingsSnapshot().mode)
      if (!prepared.ok) {
        return t(`retrievePanel.retrieval.${prepared.error}`, {
          modes: SUPPORTED_QUERY_MODES.join(', ')
        })
      }

      // The displayed user message keeps the original input (prefix and all);
      // the request carries the stripped query — same as before extraction.
      void session.submitQuery(prepared.query, {
        modeOverride: prepared.modeOverride,
        displayedInput: input
      })
      return null
    },
    [getQuerySettingsSnapshot, session, t]
  )

  // Match DocumentManager's 24px content padding plus its 8px inner-card
  // margin. The resulting 32px clearance also stays above StatusIndicator.
  return (
    <div className="flex size-full gap-2 overflow-hidden px-2 pb-8">
      <div className="flex grow flex-col gap-4">
        <MessageList
          messages={session.messages}
          isLoading={session.isLoading}
          queryProgress={session.queryProgress}
          isActive={isRetrievalTabActive}
          emptyState={
            <div className="text-muted-foreground text-lg">
              {t('retrievePanel.retrieval.startPrompt')}
            </div>
          }
        />
        <div className="flex shrink-0 items-center gap-2">
          <div className="min-w-0 flex-1">
            <QueryComposer
              isLoading={session.isLoading}
              stopDisabled={session.stopDisabled}
              onSend={handleSend}
              onStop={session.handleStop}
              onClear={session.clearMessages}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => setShowHistoryDialog(true)}
            disabled={session.isLoading}
            size="sm"
            className="min-h-11"
            tooltip="View query history"
          >
            <HistoryIcon />
          </Button>
        </div>
      </div>
      <QuerySettings />
      <QueryHistoryDialog
        open={showHistoryDialog}
        onOpenChange={setShowHistoryDialog}
        onSelectQuery={handleSelectHistoryQuery}
      />
    </div>
  )
}
