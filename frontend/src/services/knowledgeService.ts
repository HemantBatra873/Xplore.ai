import api from './api'
import type { Document, KnowledgeBase, KnowledgeQueryResult } from '@/types'

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await api.get<KnowledgeBase[]>('/knowledge-bases/')
  return response.data
}

export async function createKnowledgeBase(payload: {
  name: string
  description?: string | null
}): Promise<KnowledgeBase> {
  const response = await api.post<KnowledgeBase>('/knowledge-bases/', payload)
  return response.data
}

export async function updateKnowledgeBase(
  id: number,
  payload: { name?: string; description?: string | null },
): Promise<KnowledgeBase> {
  const response = await api.patch<KnowledgeBase>(`/knowledge-bases/${id}`, payload)
  return response.data
}

export async function deleteKnowledgeBase(id: number): Promise<void> {
  await api.delete(`/knowledge-bases/${id}`)
}

export async function listKnowledgeBaseDocuments(knowledgeBaseId: number): Promise<Document[]> {
  const response = await api.get<Document[]>(`/knowledge-bases/${knowledgeBaseId}/documents`)
  return response.data
}

export async function uploadKnowledgeBaseDocument(
  knowledgeBaseId: number,
  file: File,
): Promise<Document> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post<Document>(
    `/knowledge-bases/${knowledgeBaseId}/documents/upload`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return response.data
}

export async function deleteKnowledgeBaseDocument(
  knowledgeBaseId: number,
  documentId: number,
): Promise<void> {
  await api.delete(`/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`)
}

export async function queryKnowledgeBase(
  knowledgeBaseId: number,
  query: string,
  topK = 3,
): Promise<KnowledgeQueryResult> {
  const response = await api.post<KnowledgeQueryResult>(
    `/knowledge-bases/${knowledgeBaseId}/query`,
    { query, top_k: topK },
  )
  return response.data
}
