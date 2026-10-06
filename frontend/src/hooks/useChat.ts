import { useState, useCallback, useEffect } from 'react'
import type { Agent, Conversation, KnowledgeBase, Message, CitationSource, ToolCall } from '@/types'
import {
  listConversations,
  createConversation,
  getConversation,
  updateConversation,
  deleteConversation,
  streamMessage,
} from '@/services/conversationService'
import { listKnowledgeBases } from '@/services/knowledgeService'
import { listAgents } from '@/services/agentService'

function generateId() {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function normalizeToolCalls(raw: unknown): ToolCall[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined
  return raw.map((item) => {
    const row = item as Record<string, unknown>
    let args: Record<string, string> = {}
    const argumentsRaw = row.arguments
    if (typeof argumentsRaw === 'string') {
      try {
        args = JSON.parse(argumentsRaw) as Record<string, string>
      } catch {
        args = { raw: argumentsRaw }
      }
    } else if (argumentsRaw && typeof argumentsRaw === 'object') {
      args = Object.fromEntries(
        Object.entries(argumentsRaw as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
      )
    }
    return {
      name: String(row.name || 'tool'),
      arguments: args,
      result: row.result != null ? String(row.result) : undefined,
    }
  })
}

function toUiMessage(msg: {
  id: number
  role: string
  content: string
  citations?: CitationSource[]
  tool_calls?: unknown
  created_at: string
}): Message {
  return {
    id: String(msg.id),
    serverId: msg.id,
    role: msg.role as Message['role'],
    content: msg.content,
    citations: msg.citations || [],
    tool_calls: normalizeToolCalls(msg.tool_calls),
    timestamp: new Date(msg.created_at).getTime(),
  }
}

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [useKnowledge, setUseKnowledge] = useState(false)
  const [selectedKbIds, setSelectedKbIds] = useState<number[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)

  const refreshConversations = useCallback(async () => {
    try {
      const data = await listConversations()
      setConversations(data)
      return data
    } catch {
      setError('Failed to load conversations')
      return []
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const [convs, kbs, agentRows] = await Promise.all([
          listConversations(),
          listKnowledgeBases(),
          listAgents(),
        ])
        if (cancelled) return
        setConversations(convs)
        setKnowledgeBases(kbs)
        setAgents(agentRows.filter((a) => a.is_enabled))
        if (convs.length > 0) {
          setActiveConversationId(convs[0].id)
        }
      } catch {
        if (!cancelled) setError('Failed to load chat')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (activeConversationId == null) {
      setMessages([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const detail = await getConversation(activeConversationId)
        if (cancelled) return
        setMessages(detail.messages.map(toUiMessage))
        setUseKnowledge(detail.use_knowledge)
        setSelectedKbIds(detail.knowledge_base_ids || [])
        setSelectedAgentId(detail.agent_id ?? null)
      } catch {
        if (!cancelled) setError('Failed to load conversation')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeConversationId])

  const ensureConversation = useCallback(async (): Promise<number> => {
    if (activeConversationId != null) return activeConversationId
    const created = await createConversation({
      title: 'New conversation',
      use_knowledge: useKnowledge,
      knowledge_base_ids: selectedKbIds.length ? selectedKbIds : undefined,
      agent_id: selectedAgentId ?? undefined,
    })
    setConversations((prev) => [created, ...prev])
    setActiveConversationId(created.id)
    return created.id
  }, [activeConversationId, useKnowledge, selectedKbIds, selectedAgentId])

  const startNewConversation = useCallback(async () => {
    setError('')
    try {
      const created = await createConversation({
        title: 'New conversation',
        use_knowledge: useKnowledge,
        knowledge_base_ids: selectedKbIds.length ? selectedKbIds : undefined,
        agent_id: selectedAgentId ?? undefined,
      })
      setConversations((prev) => [created, ...prev])
      setActiveConversationId(created.id)
      setMessages([])
    } catch {
      setError('Failed to create conversation')
    }
  }, [useKnowledge, selectedKbIds, selectedAgentId])

  const removeConversation = useCallback(
    async (id: number) => {
      setError('')
      try {
        await deleteConversation(id)
        const remaining = await refreshConversations()
        if (activeConversationId === id) {
          setActiveConversationId(remaining[0]?.id ?? null)
          if (!remaining.length) setMessages([])
        }
      } catch {
        setError('Failed to delete conversation')
      }
    },
    [activeConversationId, refreshConversations],
  )

  const persistKnowledgeSettings = useCallback(
    async (nextUse: boolean, nextIds: number[]) => {
      setUseKnowledge(nextUse)
      setSelectedKbIds(nextIds)
      if (activeConversationId == null) return
      try {
        const updated = await updateConversation(activeConversationId, {
          use_knowledge: nextUse,
          knowledge_base_ids: nextIds,
        })
        setConversations((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)),
        )
      } catch {
        setError('Failed to update knowledge settings')
      }
    },
    [activeConversationId],
  )

  const persistAgentSelection = useCallback(
    async (agentId: number | null) => {
      setSelectedAgentId(agentId)
      if (activeConversationId == null) return
      try {
        const updated = await updateConversation(activeConversationId, {
          agent_id: agentId,
        })
        setConversations((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)),
        )
      } catch {
        setError('Failed to update agent selection')
      }
    },
    [activeConversationId],
  )

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isStreaming) return
      setError('')

      const userMessage: Message = {
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: Date.now(),
      }
      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        citations: [],
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, userMessage, assistantMessage])
      setIsStreaming(true)

      try {
        const conversationId = await ensureConversation()
        const generator = streamMessage(conversationId, content.trim(), {
          use_knowledge: useKnowledge,
          knowledge_base_ids: useKnowledge && selectedKbIds.length ? selectedKbIds : undefined,
          agent_id: selectedAgentId ?? undefined,
        })

        let fullContent = ''
        let reasoningContent = ''
        let sources: CitationSource[] = []
        let toolCalls: ToolCall[] | undefined
        let hasError = false

        for await (const chunk of generator) {
          if (chunk.error) {
            hasError = true
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.id === assistantMessage.id) {
                updated[updated.length - 1] = { ...last, content: `Error: ${chunk.error}` }
              }
              return updated
            })
            break
          }
          if (chunk.sources?.length) sources = chunk.sources
          if (chunk.tool_calls) toolCalls = normalizeToolCalls(chunk.tool_calls)
          if (chunk.reasoning) reasoningContent += chunk.reasoning
          if (chunk.content) fullContent += chunk.content

          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.id === assistantMessage.id) {
              updated[updated.length - 1] = {
                ...last,
                content: fullContent,
                reasoning: reasoningContent || undefined,
                citations: sources,
                tool_calls: toolCalls,
                serverId: chunk.assistant_message_id ?? last.serverId,
              }
            }
            return updated
          })
        }

        if (hasError || !fullContent) {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.id === assistantMessage.id && !fullContent) {
              updated.pop()
            }
            return updated
          })
          if (!hasError) setError('The assistant did not return a response.')
        }

        await refreshConversations()
      } catch {
        setError('Failed to send message')
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last?.id === assistantMessage.id) updated.pop()
          return updated
        })
      } finally {
        setIsStreaming(false)
      }
    },
    [
      isStreaming,
      ensureConversation,
      useKnowledge,
      selectedKbIds,
      selectedAgentId,
      refreshConversations,
    ],
  )

  return {
    conversations,
    activeConversationId,
    setActiveConversationId,
    messages,
    isStreaming,
    loading,
    error,
    knowledgeBases,
    agents,
    useKnowledge,
    selectedKbIds,
    selectedAgentId,
    sendMessage,
    startNewConversation,
    removeConversation,
    persistKnowledgeSettings,
    persistAgentSelection,
  }
}
