import api from './api'
import type { Integration, IntegrationTool } from '@/types'

export async function listIntegrationTypes(): Promise<string[]> {
  const response = await api.get<{ types: string[] }>('/integrations/types')
  return response.data.types
}

export async function listIntegrations(): Promise<Integration[]> {
  const response = await api.get<Integration[]>('/integrations/')
  return response.data
}

export async function createIntegration(payload: {
  type: string
  name: string
  description?: string | null
  config?: Record<string, unknown>
  credentials?: Record<string, unknown> | null
  is_enabled?: boolean
}): Promise<Integration> {
  const response = await api.post<Integration>('/integrations/', payload)
  return response.data
}

export async function updateIntegration(
  id: number,
  payload: {
    name?: string
    description?: string | null
    config?: Record<string, unknown>
    credentials?: Record<string, unknown> | null
    is_enabled?: boolean
  },
): Promise<Integration> {
  const response = await api.put<Integration>(`/integrations/${id}`, payload)
  return response.data
}

export async function deleteIntegration(id: number): Promise<void> {
  await api.delete(`/integrations/${id}`)
}

export async function connectIntegration(id: number): Promise<Integration> {
  const response = await api.post<Integration>(`/integrations/${id}/connect`)
  return response.data
}

export async function refreshIntegrationTools(id: number): Promise<Integration> {
  const response = await api.post<Integration>(`/integrations/${id}/refresh-tools`)
  return response.data
}

export async function listIntegrationTools(id: number): Promise<IntegrationTool[]> {
  const response = await api.get<IntegrationTool[]>(`/integrations/${id}/tools`)
  return response.data
}
