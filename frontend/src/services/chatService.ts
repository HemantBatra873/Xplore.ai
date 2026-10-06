import api, { buildAuthFetchHeaders } from './api'

export interface ChatRequest {
  message: string
  stream: boolean
}

export async function sendChatMessage(message: string): Promise<string> {
  const response = await api.post<{ reply: string }>('/chat/', {
    message,
    stream: false,
  })
  return response.data.reply
}

export async function* streamChatMessage(message: string): AsyncGenerator<{
  reasoning?: string
  content?: string
  error?: string
}> {
  const useMock = import.meta.env.VITE_USE_MOCK === 'true'
  if (useMock) {
    yield { content: 'This is a streamed mock response. You can continue exploring the chat flow offline.' }
    return
  }

  const baseUrl = import.meta.env.VITE_API_BASE || '/api/v1'
  const url = `${baseUrl}/chat/`

  const response = await fetch(url, {
    method: 'POST',
    headers: buildAuthFetchHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message, stream: true }),
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
      errorMsg = err.detail || errorMsg
    } catch {
      // Keep default error message when body is not JSON
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
          const parsed = JSON.parse(data)
          yield parsed
        } catch {
          // Ignore malformed SSE JSON chunks
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
