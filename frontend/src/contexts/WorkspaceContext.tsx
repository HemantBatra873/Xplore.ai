import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'
import type { Workspace } from '@/types'
import { useAuth } from '@/contexts/AuthContext'
import * as workspaceService from '@/services/workspaceService'

export const WORKSPACE_STORAGE_KEY = 'xplore_workspace'

export function clearWorkspaceStorage(): void {
  localStorage.removeItem(WORKSPACE_STORAGE_KEY)
}

interface WorkspaceContextType {
  currentWorkspace: Workspace | null
  workspaces: Workspace[]
  loading: boolean
  error: string | null
  setCurrentWorkspace: (workspace: Workspace | null) => void
  refreshWorkspaces: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceContextType | null>(null)

function readStoredWorkspaceId(): number | null {
  const raw = localStorage.getItem(WORKSPACE_STORAGE_KEY)
  if (!raw) return null
  const id = Number.parseInt(raw, 10)
  return Number.isFinite(id) ? id : null
}

function persistWorkspaceId(id: number | null): void {
  if (id == null) {
    clearWorkspaceStorage()
    return
  }
  localStorage.setItem(WORKSPACE_STORAGE_KEY, String(id))
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState<number | null>(() =>
    readStoredWorkspaceId(),
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setCurrentWorkspace = useCallback((workspace: Workspace | null) => {
    const id = workspace?.id ?? null
    setCurrentWorkspaceId(id)
    persistWorkspaceId(id)
  }, [])

  const refreshWorkspaces = useCallback(async () => {
    if (!isAuthenticated) {
      setWorkspaces([])
      setCurrentWorkspace(null)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const list = await workspaceService.listWorkspaces()
      setWorkspaces(list)

      const storedId = readStoredWorkspaceId()
      const match = storedId != null ? list.find((w) => w.id === storedId) : undefined
      if (match) {
        setCurrentWorkspaceId(match.id)
        persistWorkspaceId(match.id)
      } else if (list.length > 0) {
        setCurrentWorkspaceId(list[0].id)
        persistWorkspaceId(list[0].id)
      } else {
        setCurrentWorkspaceId(null)
        clearWorkspaceStorage()
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load workspaces'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) {
      setWorkspaces([])
      setCurrentWorkspaceId(null)
      clearWorkspaceStorage()
      setError(null)
      setLoading(false)
      return
    }
    void refreshWorkspaces()
  }, [isAuthenticated, refreshWorkspaces])

  const currentWorkspace = useMemo(() => {
    if (currentWorkspaceId == null) return null
    return workspaces.find((w) => w.id === currentWorkspaceId) ?? null
  }, [workspaces, currentWorkspaceId])

  return (
    <WorkspaceContext.Provider
      value={{
        currentWorkspace,
        workspaces,
        loading,
        error,
        setCurrentWorkspace,
        refreshWorkspaces,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider')
  }
  return context
}
