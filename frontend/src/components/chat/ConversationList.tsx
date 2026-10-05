import type { Conversation } from '@/types'
import { IconPlus, IconTrash } from '@/components/ui/Icons'

interface ConversationListProps {
  conversations: Conversation[]
  activeId: number | null
  onSelect: (id: number) => void
  onCreate: () => void
  onDelete: (id: number) => void
  disabled?: boolean
}

export default function ConversationList({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  disabled,
}: ConversationListProps) {
  return (
    <div className="w-56 shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] flex flex-col hidden md:flex">
      <div className="p-3 border-b border-[var(--border-primary)] flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
          Conversations
        </p>
        <button
          type="button"
          onClick={onCreate}
          disabled={disabled}
          className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-brand-500 hover:bg-brand-500/10 disabled:opacity-50"
          title="New conversation"
        >
          <IconPlus />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {conversations.length === 0 ? (
          <p className="text-xs text-[var(--text-tertiary)] px-2 py-4">
            No conversations yet. Send a message to start.
          </p>
        ) : (
          conversations.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center gap-1 rounded-lg px-2 py-2 cursor-pointer ${
                activeId === c.id
                  ? 'bg-brand-500/10 text-brand-500'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]'
              }`}
              onClick={() => onSelect(c.id)}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{c.title}</p>
                {c.use_knowledge && (
                  <p className="text-[10px] text-[var(--text-tertiary)]">Knowledge on</p>
                )}
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(c.id)
                }}
                className="opacity-0 group-hover:opacity-100 p-1 text-[var(--text-tertiary)] hover:text-[var(--color-error)]"
                title="Delete"
              >
                <IconTrash />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
