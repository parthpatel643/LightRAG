import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { createSelectors } from '@/lib/utils'

interface WorkspaceState {
  currentWorkspace: string | null
  setCurrentWorkspace: (workspace: string | null) => void
}

const useWorkspaceStoreBase = create<WorkspaceState>()(
  persist(
    (set) => ({
      currentWorkspace: null,
      setCurrentWorkspace: (workspace) => set({ currentWorkspace: workspace })
    }),
    {
      name: 'lightrag-workspace',
      version: 1,
      storage: createJSONStorage(() => localStorage)
    }
  )
)

export const useWorkspaceStore = createSelectors(useWorkspaceStoreBase)
