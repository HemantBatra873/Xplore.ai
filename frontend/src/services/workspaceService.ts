import api from './api'
import type { Workspace, WorkspaceCreate } from '@/types'

export async function listWorkspaces(): Promise<Workspace[]> {
  const response = await api.get<Workspace[]>('/workspaces/')
  return response.data
}

export async function getWorkspace(workspaceId: number): Promise<Workspace> {
  const response = await api.get<Workspace>(`/workspaces/${workspaceId}`)
  return response.data
}

export async function createWorkspace(payload: WorkspaceCreate): Promise<Workspace> {
  const response = await api.post<Workspace>('/workspaces/', payload)
  return response.data
}
