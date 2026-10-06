import api from './api'
import type { Agent, ToolInfo } from '@/types'

export async function listAgents(): Promise<Agent[]> {
  const response = await api.get<Agent[]>('/agents/')
  return response.data
}

export async function createAgent(payload: {
  name: string
  description?: string | null
  system_prompt?: string
  provider?: string | null
  model_name?: string | null
  is_enabled?: boolean
  knowledge_base_ids?: number[]
  enabled_tools?: string[]
}): Promise<Agent> {
  const response = await api.post<Agent>('/agents/', payload)
  return response.data
}

export async function updateAgent(
  id: number,
  payload: {
    name?: string
    description?: string | null
    system_prompt?: string
    provider?: string | null
    model_name?: string | null
    is_enabled?: boolean
    knowledge_base_ids?: number[]
    enabled_tools?: string[]
  },
): Promise<Agent> {
  const response = await api.put<Agent>(`/agents/${id}`, payload)
  return response.data
}

export async function deleteAgent(id: number): Promise<void> {
  await api.delete(`/agents/${id}`)
}

export async function listTools(): Promise<ToolInfo[]> {
  const response = await api.get<ToolInfo[]>('/agents/tools')
  return response.data
}
