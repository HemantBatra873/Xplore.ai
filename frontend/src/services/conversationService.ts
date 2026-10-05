import api, { buildAuthFetchHeaders } from './api'
import type {
  Conversation,
  ConversationDetail,
  ConversationMessage,
  CitationSource,
} from '@/types'

export async function listConversations(): Promise<Conversation[]> {
  const response = await api.get<Conversation[]>('/conversations/')
  return response.data
}

export async function createConversation(payload: {
  title?: string
  use_knowledge?: boolean
  knowledge_base_ids?: number[]
}): Promise<Conversation> {
  const response = await api.post<Conversation>('/conversations/', payload)
  return response.data
}

export async function getConversation(id: number): Promise<ConversationDetail> {
  const response = await api.get<ConversationDetail>(`/conversations/${id}`)
  return response.data
}

export async function updateConversation(
  id: number,
  payload: {
    title?: string
    use_knowledge?: boolean
    knowledge_base_ids?: number[] | null
  },
): Promise<Conversation> {
  const response = await api.patch<Conversation>(`/conversations/${id}`, payload)
  return response.data
}

export async function deleteConversation(id: number): Promise<void> {
  await api.delete(`/conversations/${id}`)
}

export async function listMessages(conversationId: number): Promise<ConversationMessage[]> {
  const response = await api.get<ConversationMessage[]>(
    `/conversations/${conversationId}/messages`,
  )
  return response.data
}

export async function sendMessage(
  conversationId: number,
  content: string,
  options?: {
    use_knowledge?: boolean
    knowledge_base_ids?: number[]
    top_k?: number
  },
): Promise<{
  user_message: ConversationMessage
  assistant_message: ConversationMessage
  sources: CitationSource[]
}> {
  const response = await api.post(`/conversations/${conversationId}/messages`, {
    content,
    ...options,
  })
  return response.data
}

export async function* streamMessage(
  conversationId: number,
  content: string,
  options?: {
    use_knowledge?: boolean
    knowledge_base_ids?: number[]
    top_k?: number
  },
): AsyncGenerator<{
  content?: string
  reasoning?: string
  error?: string
  sources?: CitationSource[]
  user_message_id?: number
  assistant_message_id?: number
}> {
  const useMock = import.meta.env.VITE_USE_MOCK === 'true'
  if (useMock) {
    yield { content: 'This is a streamed mock response from a persistent conversation.' }
    yield {
      sources: [
        {
          chunk_id: 1,
          document_id: 1,
          knowledge_base_id: 1,
          knowledge_base_name: 'Product docs',
          filename: 'Getting Started.md',
          chunk_index: 0,
          excerpt: 'Mock citation excerpt for offline development.',
          score: 0.9,
        },
      ],
      assistant_message_id: Date.now(),
    }
    return
  }

  const baseUrl = import.meta.env.VITE_API_BASE || '/api/v1'
  const url = `${baseUrl}/conversations/${conversationId}/messages/stream`

  const response = await fetch(url, {
    method: 'POST',
    headers: buildAuthFetchHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, ...options }),
  })

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('xplore_token')
      localStorage.removeItem('xplore_user')
      window.location.href = '/auth/login'
      yield { error: 'Your session has expired. Please sign in again.' }
      return
    }
    let errorMsg = 'Request failed'
    try {
      const err = await response.json()
      errorMsg = err.msg || err.detail || errorMsg
    } catch {
      /* ignore */
    }
    yield { error: errorMsg }
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    yield { error: 'Unable to read the response stream' }
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const data = trimmed.slice(6)
        if (data === '[DONE]') return
        try {
          yield JSON.parse(data)
        } catch {
          /* ignore partial JSON */
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
