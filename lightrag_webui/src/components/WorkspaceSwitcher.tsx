import { useCallback, useEffect, useState } from 'react'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from '@/components/ui/Select'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import { FolderOpen, Plus, Settings2, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/Tooltip'

export interface WorkspaceConfig {
  name: string
  workingDir: string
  inputDir: string
  description?: string
}

interface WorkspaceSwitcherProps {
  currentWorkspace?: string
  onWorkspaceChange: (workspace: WorkspaceConfig) => void
  className?: string
}

export default function WorkspaceSwitcher({
  currentWorkspace,
  onWorkspaceChange,
  className
}: WorkspaceSwitcherProps) {
  const { t } = useTranslation()
  const [workspaces, setWorkspaces] = useState<WorkspaceConfig[]>([])
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>(currentWorkspace || 'default')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  // New workspace form state
  const [newWorkspace, setNewWorkspace] = useState<WorkspaceConfig>({
    name: '',
    workingDir: '',
    inputDir: '',
    description: ''
  })

  // Load workspaces from localStorage on mount
  useEffect(() => {
    const loadWorkspaces = () => {
      try {
        const stored = localStorage.getItem('lightrag_workspaces')
        if (stored) {
          const parsed = JSON.parse(stored) as WorkspaceConfig[]
          setWorkspaces(parsed)
        } else {
          // Initialize with default workspace
          const defaultWorkspace: WorkspaceConfig = {
            name: 'default',
            workingDir: './rag_storage',
            inputDir: './inputs',
            description: 'Default workspace'
          }
          setWorkspaces([defaultWorkspace])
          localStorage.setItem('lightrag_workspaces', JSON.stringify([defaultWorkspace]))
        }
      } catch (error) {
        console.error('Error loading workspaces:', error)
        toast.error(t('workspace.loadError', 'Failed to load workspaces'))
      }
    }

    loadWorkspaces()
  }, [t])

  // Save workspaces to localStorage
  const saveWorkspaces = useCallback((updatedWorkspaces: WorkspaceConfig[]) => {
    try {
      localStorage.setItem('lightrag_workspaces', JSON.stringify(updatedWorkspaces))
      setWorkspaces(updatedWorkspaces)
    } catch (error) {
      console.error('Error saving workspaces:', error)
      toast.error(t('workspace.saveError', 'Failed to save workspaces'))
    }
  }, [t])

  // Handle workspace selection
  const handleWorkspaceSelect = useCallback((workspaceName: string) => {
    const workspace = workspaces.find(w => w.name === workspaceName)
    if (workspace) {
      setSelectedWorkspace(workspaceName)
      onWorkspaceChange(workspace)
      toast.success(
        t('workspace.switched', 'Switched to workspace: {{name}}', { name: workspaceName })
      )
    }
  }, [workspaces, onWorkspaceChange, t])

  // Handle new workspace creation
  const handleCreateWorkspace = useCallback(async () => {
    // Validation
    if (!newWorkspace.name.trim()) {
      toast.error(t('workspace.nameRequired', 'Workspace name is required'))
      return
    }

    if (!newWorkspace.workingDir.trim()) {
      toast.error(t('workspace.workingDirRequired', 'Working directory is required'))
      return
    }

    if (!newWorkspace.inputDir.trim()) {
      toast.error(t('workspace.inputDirRequired', 'Input directory is required'))
      return
    }

    // Check for duplicate names
    if (workspaces.some(w => w.name === newWorkspace.name)) {
      toast.error(t('workspace.duplicateName', 'Workspace name already exists'))
      return
    }

    setIsLoading(true)

    try {
      // Add new workspace
      const updatedWorkspaces = [...workspaces, newWorkspace]
      saveWorkspaces(updatedWorkspaces)

      // Switch to new workspace
      handleWorkspaceSelect(newWorkspace.name)

      // Reset form and close dialog
      setNewWorkspace({
        name: '',
        workingDir: '',
        inputDir: '',
        description: ''
      })
      setIsDialogOpen(false)

      toast.success(
        t('workspace.created', 'Workspace created: {{name}}', { name: newWorkspace.name })
      )
    } catch (error) {
      console.error('Error creating workspace:', error)
      toast.error(t('workspace.createError', 'Failed to create workspace'))
    } finally {
      setIsLoading(false)
    }
  }, [newWorkspace, workspaces, saveWorkspaces, handleWorkspaceSelect, t])

  // Handle workspace deletion
  const handleDeleteWorkspace = useCallback((workspaceName: string) => {
    if (workspaceName === 'default') {
      toast.error(t('workspace.cannotDeleteDefault', 'Cannot delete default workspace'))
      return
    }

    const updatedWorkspaces = workspaces.filter(w => w.name !== workspaceName)
    saveWorkspaces(updatedWorkspaces)

    // If deleted workspace was selected, switch to default
    if (selectedWorkspace === workspaceName) {
      handleWorkspaceSelect('default')
    }

    toast.success(
      t('workspace.deleted', 'Workspace deleted: {{name}}', { name: workspaceName })
    )
  }, [workspaces, selectedWorkspace, saveWorkspaces, handleWorkspaceSelect, t])

  return (
    <div className={`flex items-center gap-2 ${className || ''}`}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2">
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
              <Select value={selectedWorkspace} onValueChange={handleWorkspaceSelect}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder={t('workspace.select', 'Select workspace')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>{t('workspace.available', 'Available Workspaces')}</SelectLabel>
                    {workspaces.map((workspace) => (
                      <SelectItem key={workspace.name} value={workspace.name}>
                        <div className="flex flex-col">
                          <span className="font-medium">{workspace.name}</span>
                          {workspace.description && (
                            <span className="text-xs text-muted-foreground">
                              {workspace.description}
                            </span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <div className="text-xs">
              <p className="font-medium">{t('workspace.current', 'Current Workspace')}</p>
              <p className="text-muted-foreground">
                {workspaces.find(w => w.name === selectedWorkspace)?.workingDir || 'N/A'}
              </p>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-1" />
            {t('workspace.new', 'New')}
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>{t('workspace.createTitle', 'Create New Workspace')}</DialogTitle>
            <DialogDescription>
              {t('workspace.createDescription', 
                'Configure a new workspace with custom working and input directories.'
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="workspace-name" className="text-sm font-medium">
                {t('workspace.name', 'Workspace Name')} *
              </label>
              <Input
                id="workspace-name"
                placeholder="e.g., aviation-contracts"
                value={newWorkspace.name}
                onChange={(e) => setNewWorkspace({ ...newWorkspace, name: e.target.value })}
              />
            </div>

            <div className="grid gap-2">
              <label htmlFor="working-dir" className="text-sm font-medium">
                {t('workspace.workingDir', 'Working Directory')} *
              </label>
              <Input
                id="working-dir"
                placeholder="e.g., ./rag_storage/aviation"
                value={newWorkspace.workingDir}
                onChange={(e) => setNewWorkspace({ ...newWorkspace, workingDir: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                {t('workspace.workingDirHelp', 'Directory where RAG data will be stored')}
              </p>
            </div>

            <div className="grid gap-2">
              <label htmlFor="input-dir" className="text-sm font-medium">
                {t('workspace.inputDir', 'Input Directory')} *
              </label>
              <Input
                id="input-dir"
                placeholder="e.g., ./inputs/aviation"
                value={newWorkspace.inputDir}
                onChange={(e) => setNewWorkspace({ ...newWorkspace, inputDir: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                {t('workspace.inputDirHelp', 'Directory where source documents are located')}
              </p>
            </div>

            <div className="grid gap-2">
              <label htmlFor="description" className="text-sm font-medium">
                {t('workspace.description', 'Description')} ({t('workspace.optional', 'optional')})
              </label>
              <Input
                id="description"
                placeholder={t('workspace.descriptionPlaceholder', 'Brief description of this workspace')}
                value={newWorkspace.description}
                onChange={(e) => setNewWorkspace({ ...newWorkspace, description: e.target.value })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDialogOpen(false)}
              disabled={isLoading}
            >
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button onClick={handleCreateWorkspace} disabled={isLoading}>
              {isLoading ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  {t('workspace.creating', 'Creating...')}
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  {t('workspace.create', 'Create Workspace')}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                const workspace = workspaces.find(w => w.name === selectedWorkspace)
                if (workspace) {
                  onWorkspaceChange(workspace)
                  toast.success(t('workspace.refreshed', 'Workspace refreshed'))
                }
              }}
            >
              <Settings2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{t('workspace.refresh', 'Refresh workspace configuration')}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  )
}


