import MessageList from './MessageList'
import ChatInput from './ChatInput'
import ConversationList from './ConversationList'
import { useChat } from '@/hooks/useChat'

export default function ChatArea() {
  const {
    conversations,
    activeConversationId,
    setActiveConversationId,
    messages,
    isStreaming,
    loading,
    error,
    knowledgeBases,
    useKnowledge,
    selectedKbIds,
    sendMessage,
    startNewConversation,
    removeConversation,
    persistKnowledgeSettings,
  } = useChat()

  function toggleKb(id: number) {
    // Empty selection means "all KBs". First click narrows to one KB.
    if (selectedKbIds.length === 0) {
      void persistKnowledgeSettings(true, [id])
      return
    }
    if (selectedKbIds.includes(id)) {
      const next = selectedKbIds.filter((x) => x !== id)
      void persistKnowledgeSettings(true, next)
      return
    }
    void persistKnowledgeSettings(true, [...selectedKbIds, id])
  }

  return (
    <div className="flex-1 flex min-w-0 bg-[var(--bg-primary)]">
      <ConversationList
        conversations={conversations}
        activeId={activeConversationId}
        onSelect={setActiveConversationId}
        onCreate={() => void startNewConversation()}
        onDelete={(id) => void removeConversation(id)}
        disabled={isStreaming || loading}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <div className="border-b border-[var(--border-primary)] px-4 py-2 flex flex-wrap items-center gap-3 bg-[var(--bg-secondary)]">
          <label className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={useKnowledge}
              onChange={(e) => void persistKnowledgeSettings(e.target.checked, selectedKbIds)}
              disabled={isStreaming}
              className="rounded border-[var(--border-primary)]"
            />
            Use knowledge
          </label>
          {useKnowledge && (
            <div className="flex flex-wrap items-center gap-2">
              {knowledgeBases.length === 0 ? (
                <span className="text-xs text-[var(--text-tertiary)]">No knowledge bases</span>
              ) : (
                knowledgeBases.map((kb) => (
                  <label
                    key={kb.id}
                    className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)] px-2 py-1 rounded-md border border-[var(--border-primary)]"
                  >
                    <input
                      type="checkbox"
                      checked={selectedKbIds.length === 0 || selectedKbIds.includes(kb.id)}
                      onChange={() => toggleKb(kb.id)}
                      disabled={isStreaming}
                    />
                    {kb.name}
                  </label>
                ))
              )}
              {selectedKbIds.length === 0 && knowledgeBases.length > 0 && (
                <span className="text-[10px] text-[var(--text-tertiary)]">All knowledge bases</span>
              )}
            </div>
          )}
        </div>

        {error && (
          <p className="mx-4 mt-2 text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-tertiary)]">
            Loading conversations...
          </div>
        ) : (
          <MessageList messages={messages} isStreaming={isStreaming} onQuickAsk={sendMessage} />
        )}
        <ChatInput onSend={sendMessage} disabled={isStreaming || loading} />
      </div>
    </div>
  )
}
