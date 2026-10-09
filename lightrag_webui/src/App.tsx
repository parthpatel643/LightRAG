import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import ThemeProvider from '@/components/ThemeProvider'
import TabVisibilityProvider from '@/contexts/TabVisibilityProvider'
import ApiKeyAlert from '@/components/ApiKeyAlert'
import ErrorBanner from '@/components/ui/ErrorBanner'
import KeyboardShortcutsDialog from '@/components/KeyboardShortcutsDialog'
import { SiteInfo } from '@/lib/constants'
import { entryHomeHref } from '@/lib/pathPrefix'
import { useBackendState, useAuthStore } from '@/stores/state'
import { useSettingsStore } from '@/stores/settings'
import { getAuthStatus } from '@/api/lightrag'
import {
  activateLoginIdentityFromToken,
  useIdentityEpochStore
} from '@/lib/loginIdentity'
import {
  markVersionCheckedFromLogin,
  wasVersionCheckedThisPageLoad
} from '@/lib/versionCheckCache'
import SiteHeader from '@/features/SiteHeader'
import { InvalidApiKeyError, RequireApiKeError } from '@/api/lightrag'
import { ZapIcon } from 'lucide-react'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useTranslation } from 'react-i18next'

import GraphViewer from '@/features/GraphViewer'
import DocumentManager from '@/features/DocumentManager'
import RetrievalView from '@/features/RetrievalView'

import { Tabs, TabsContent } from '@/components/ui/Tabs'
import ErrorBoundary from '@/components/ErrorBoundary'
import usePageRestoreGeneration from '@/hooks/usePageRestoreGeneration'

function App() {
  const { i18n } = useTranslation()
  const message = useBackendState.use.message()
  const health = useBackendState.use.health()
  const enableHealthCheck = useSettingsStore.use.enableHealthCheck()
  const currentTab = useSettingsStore.use.currentTab()
  const [apiKeyAlertOpen, setApiKeyAlertOpen] = useState(false)
  const [initializing, setInitializing] = useState(true) // Add initializing state
  const [showShortcutsDialog, setShowShortcutsDialog] = useState(false)
  // Bumped by the cross-tab identity watch: remounting the retrieval view
  // drops the live session state that belonged to the previous identity.
  const identityEpoch = useIdentityEpochStore((s) => s.epoch)
  const versionCheckRef = useRef(false); // Prevent duplicate calls in Vite dev mode
  const healthCheckInitializedRef = useRef(false); // Prevent duplicate health checks in Vite dev mode
  const pageRestoreGeneration = usePageRestoreGeneration()

  // RTL Support: Set HTML dir attribute based on language
  useEffect(() => {
    const rtlLanguages = ['ar', 'he', 'fa', 'ur']
    const isRTL = rtlLanguages.includes(i18n.language)
    document.documentElement.dir = isRTL ? 'rtl' : 'ltr'
  }, [i18n.language])

  const handleApiKeyAlertOpenChange = useCallback((open: boolean) => {
    setApiKeyAlertOpen(open)
    if (!open) {
      useBackendState.getState().clear()
    }
  }, [])

  // Track component mount status with useRef
  const isMountedRef = useRef(true);

  // Set up React mount/unmount status tracking. Do not treat beforeunload as
  // an unmount: a BFCache navigation fires it without destroying this React
  // tree, and the restored page would otherwise keep this ref false forever.
  useEffect(() => {
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Health check - can be disabled
  useEffect(() => {
    // Health check function
    const performHealthCheck = async () => {
      try {
        // Only perform health check if component is still mounted
        if (isMountedRef.current) {
          await useBackendState.getState().check();
        }
      } catch (error) {
        console.error('Health check error:', error);
      }
    };

    // Set health check function in the store
    useBackendState.getState().setHealthCheckFunction(performHealthCheck);

    if (!enableHealthCheck || apiKeyAlertOpen) {
      useBackendState.getState().clearHealthCheckTimer();
      // With periodic checks disabled the header still needs to know whether
      // the backend serves /docs. Resolve that capability alone (RFC #3671) —
      // never through `check()`, whose failure path would latch `health: false`
      // and stop the document list polling with no timer left to recover it.
      if (!enableHealthCheck && !apiKeyAlertOpen) {
        useBackendState.getState().probeApiDocsCapability();
      }
      return;
    }

    // On first mount or when enableHealthCheck becomes true and apiKeyAlertOpen is false,
    // perform an immediate health check and start the timer
    if (!healthCheckInitializedRef.current) {
      healthCheckInitializedRef.current = true;
    }

    // Start/reset the health check timer using the store
    useBackendState.getState().resetHealthCheckTimer();

    // Component unmount cleanup
    return () => {
      useBackendState.getState().clearHealthCheckTimer();
    };
  }, [enableHealthCheck, apiKeyAlertOpen, pageRestoreGeneration]);

  // Version check - independent and executed only once
  useEffect(() => {
    const checkVersion = async () => {
      // Prevent duplicate calls in Vite dev mode
      if (versionCheckRef.current) return;
      versionCheckRef.current = true;

      // Skip only the request the login page just made in THIS page load: a
      // reload must reconcile again, since the server's auth mode can have
      // changed under a still-valid stored token (see versionCheckCache).
      if (wasVersionCheckedThisPageLoad()) {
        setInitializing(false); // Skip initialization if already checked
        return;
      }

      try {
        setInitializing(true); // Start initialization

        // Get version info
        const token = localStorage.getItem('LIGHTRAG-API-TOKEN');
        const status = await getAuthStatus();

        // If auth is not configured and a new token is returned, use the new token.
        // A fresh guest activation is an identity transition: clear the previous
        // identity's histories when it differs (same rule as the login page).
        if (!status.auth_configured && status.access_token) {
          activateLoginIdentityFromToken(status.access_token)
          useAuthStore.getState().login(
            status.access_token, // Use the new token
            true, // Guest mode
            status.core_version,
            status.api_version,
            status.webui_title || null,
            status.webui_description || null
          );
        } else if (token && (status.core_version || status.api_version || status.webui_title || status.webui_description)) {
          // Otherwise use the old token (if it exists)
          const isGuestMode = status.auth_mode === 'disabled' || useAuthStore.getState().isGuestMode;
          useAuthStore.getState().login(
            token,
            isGuestMode,
            status.core_version,
            status.api_version,
            status.webui_title || null,
            status.webui_description || null
          );
        }

        // Set flag to indicate version info has been checked
        markVersionCheckedFromLogin();
      } catch (error) {
        console.error('Failed to get version info:', error);
      } finally {
        // Ensure initializing is set to false even if there's an error
        setInitializing(false);
      }
    };

    // Execute version check
    checkVersion();
  }, []); // Empty dependency array ensures it only runs once on mount

  const handleTabChange = useCallback(
    (tab: string) => useSettingsStore.getState().setCurrentTab(tab as any),
    []
  )

  // React to backend message changes during render rather than via useEffect
  // (avoids cascading renders flagged by react-hooks/set-state-in-effect)
  const [previousMessage, setPreviousMessage] = useState(message)
  if (message !== previousMessage) {
    setPreviousMessage(message)
    if (message && (message.includes(InvalidApiKeyError) || message.includes(RequireApiKeError))) {
      setApiKeyAlertOpen(true)
    }
  }

  // Show error banner when backend is disconnected. Derived directly during
  // render rather than via useEffect+setState (avoids cascading renders
  // flagged by react-hooks/set-state-in-effect).
  const showErrorBanner = enableHealthCheck && !health && !initializing

  // Keyboard shortcuts
  const shortcuts = useMemo(() => [
    {
      key: '1',
      ctrlKey: true,
      action: () => useSettingsStore.getState().setCurrentTab('documents'),
      description: 'Go to Documents tab'
    },
    {
      key: '2',
      ctrlKey: true,
      action: () => useSettingsStore.getState().setCurrentTab('knowledge-graph'),
      description: 'Go to Knowledge Graph tab'
    },
    {
      key: '3',
      ctrlKey: true,
      action: () => useSettingsStore.getState().setCurrentTab('retrieval'),
      description: 'Go to Retrieval tab'
    },
    {
      key: '/',
      ctrlKey: true,
      action: () => {
        // Focus on search input if available
        const searchInput = document.querySelector('input[type="search"]') as HTMLInputElement
        if (searchInput) {
          searchInput.focus()
        }
      },
      description: 'Focus search'
    },
    {
      key: 'k',
      ctrlKey: true,
      action: () => {
        // Focus on query input in retrieval tab
        const queryInput = document.querySelector('#query-input') as HTMLInputElement
        if (queryInput) {
          queryInput.focus()
        }
      },
      description: 'Focus query input'
    },
    {
      key: '?',
      shiftKey: true,
      action: () => setShowShortcutsDialog(true),
      description: 'Show keyboard shortcuts'
    }
  ], [])

  useKeyboardShortcuts(shortcuts, !initializing)

  return (
    <ThemeProvider>
      <TabVisibilityProvider>
        {initializing ? (
          // Loading state while initializing with simplified header
          <div className="flex h-screen w-screen flex-col">
            {/* Simplified header during initialization - matches SiteHeader structure */}
            <header className="border-border/40 bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50 flex h-10 w-full border-b px-4 backdrop-blur">
              <div className="min-w-[200px] w-auto flex items-center">
                {/* Document-relative brand link — resolves to this entry's own
                    root (see SiteHeader / entryHomeHref). */}
                <a href={entryHomeHref(window.location.pathname)} className="flex items-center gap-2">
                  <ZapIcon className="size-4 text-emerald-400" aria-hidden="true" />
                  <span className="font-bold md:inline-block">{SiteInfo.name}</span>
                </a>
              </div>

              {/* Empty middle section to maintain layout */}
              <div className="flex h-10 flex-1 items-center justify-center">
              </div>

              {/* Empty right section to maintain layout */}
              <nav className="w-[200px] flex items-center justify-end">
              </nav>
            </header>

            {/* Loading indicator in content area */}
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto"></div>
                <p>Initializing...</p>
              </div>
            </div>
          </div>
        ) : (
          // Main content after initialization
          <main className="flex h-screen w-screen overflow-hidden">
            <Tabs
              defaultValue={currentTab}
              className="!m-0 flex grow flex-col !p-0 overflow-hidden"
              onValueChange={handleTabChange}
            >
              <SiteHeader />
              {showErrorBanner && (
                <ErrorBanner
                  message="Backend connection lost. Some features may not work properly. Check your connection and refresh the page."
                  persistent={true}
                  className="flex-shrink-0"
                />
              )}
              <div className="relative grow">
                <TabsContent value="documents" className="absolute top-0 right-0 bottom-0 left-0 overflow-auto">
                  <ErrorBoundary>
                    <DocumentManager />
                  </ErrorBoundary>
                </TabsContent>
                <TabsContent value="knowledge-graph" className="absolute top-0 right-0 bottom-0 left-0 overflow-hidden">
                  <ErrorBoundary>
                    <GraphViewer />
                  </ErrorBoundary>
                </TabsContent>
                <TabsContent value="retrieval" className="absolute top-0 right-0 bottom-0 left-0 overflow-hidden">
                  <ErrorBoundary>
                    <RetrievalView key={identityEpoch} />
                  </ErrorBoundary>
                </TabsContent>
              </div>
            </Tabs>
            <ApiKeyAlert open={apiKeyAlertOpen} onOpenChange={handleApiKeyAlertOpenChange} />
            <KeyboardShortcutsDialog open={showShortcutsDialog} onOpenChange={setShowShortcutsDialog} />
          </main>
        )}
      </TabVisibilityProvider>
    </ThemeProvider>
  )
}

export default App
