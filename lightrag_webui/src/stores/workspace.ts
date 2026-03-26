import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { createSelectors } from '@/lib/utils'

interface WorkspaceState {
  currentWorkspace: string | null
  isSwitching: boolean
  setCurrentWorkspace: (workspace: string | null) => void
  setIsSwitching: (switching: boolean) => void
}

const useWorkspaceStoreBase = create<WorkspaceState>()(
  persist(
    (set) => ({
      currentWorkspace: null,
      isSwitching: true,  // Start as true to block initial data fetches until workspace is synced
      setCurrentWorkspace: (workspace) => set({ currentWorkspace: workspace }),
      setIsSwitching: (switching) => set({ isSwitching: switching })
    }),
    {
      name: 'lightrag-workspace',
      version: 1,
      storage: createJSONStorage(() => localStorage)
    }
  )
)

export const useWorkspaceStore = createSelectors(useWorkspaceStoreBase)
