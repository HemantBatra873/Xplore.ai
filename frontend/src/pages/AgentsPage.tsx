import { useCallback, useEffect, useState, type FormEvent } from 'react'
import ChatLayout from '@/components/layout/ChatLayout'
import type { Agent, KnowledgeBase, ToolInfo } from '@/types'
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  listTools,
} from '@/services/agentService'
import { listKnowledgeBases } from '@/services/knowledgeService'
import { IconPlus, IconTrash, IconRefresh } from '@/components/ui/Icons'

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful assistant for Xplore.ai.')
  const [enabledTools, setEnabledTools] = useState<string[]>([])
  const [kbIds, setKbIds] = useState<number[]>([])
  const [isEnabled, setIsEnabled] = useState(true)
  const [creating, setCreating] = useState(false)

  const selected = agents.find((a) => a.id === selectedId) ?? null

  const load = useCallback(async () => {
    setError('')
    try {
      const [agentRows, toolRows, kbRows] = await Promise.all([
        listAgents(),
        listTools(),
        listKnowledgeBases(),
      ])
      setAgents(agentRows)
      setTools(toolRows)
      setKnowledgeBases(kbRows)
      setSelectedId((current) => {
        if (current != null && agentRows.some((a) => a.id === current)) return current
        return agentRows[0]?.id ?? null
      })
    } catch {
      setError('Failed to load agents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!selected) {
      setName('')
      setDescription('')
      setSystemPrompt('You are a helpful assistant for Xplore.ai.')
      setEnabledTools([])
      setKbIds([])
      setIsEnabled(true)
      return
    }
    setName(selected.name)
    setDescription(selected.description || '')
    setSystemPrompt(selected.system_prompt)
    setEnabledTools(selected.enabled_tools || [])
    setKbIds(selected.knowledge_base_ids || [])
    setIsEnabled(selected.is_enabled)
  }, [selected])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim() || 'New agent'
    setCreating(true)
    setError('')
    try {
      const agent = await createAgent({
        name: trimmed,
        description: description || null,
        system_prompt: systemPrompt,
        enabled_tools: enabledTools,
        knowledge_base_ids: kbIds,
        is_enabled: true,
      })
      await load()
      setSelectedId(agent.id)
    } catch {
      setError('Failed to create agent')
    } finally {
      setCreating(false)
    }
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      await updateAgent(selected.id, {
        name: name.trim(),
        description: description || null,
        system_prompt: systemPrompt,
        enabled_tools: enabledTools,
        knowledge_base_ids: kbIds,
        is_enabled: isEnabled,
      })
      await load()
    } catch {
      setError('Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number, agentName: string) {
    if (!window.confirm(`Delete agent "${agentName}"? Conversations will keep working without it.`)) {
      return
    }
    setError('')
    try {
      await deleteAgent(id)
      await load()
    } catch {
      setError('Failed to delete agent')
    }
  }

  function toggleTool(toolName: string) {
    setEnabledTools((prev) =>
      prev.includes(toolName) ? prev.filter((t) => t !== toolName) : [...prev, toolName],
    )
  }

  function toggleKb(id: number) {
    setKbIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  return (
    <ChatLayout>
    <div className="h-full flex flex-col bg-[var(--bg-primary)] flex-1 min-w-0">
      <div className="border-b border-[var(--border-primary)] px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Agents</h1>
          <p className="text-sm text-[var(--text-tertiary)]">
            Configure system prompts, knowledge bases, and tools for conversations
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
        >
          <IconRefresh />
        </button>
      </div>

      {error && (
        <p className="mx-6 mt-3 text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-tertiary)]">
          Loading agents...
        </div>
      ) : (
        <div className="flex-1 flex min-h-0">
          <aside className="w-64 border-r border-[var(--border-primary)] p-3 space-y-2 overflow-y-auto">
            <button
              type="button"
              onClick={() => {
                setSelectedId(null)
                setName('New agent')
                setDescription('')
                setSystemPrompt('You are a helpful assistant for Xplore.ai.')
                setEnabledTools([])
                setKbIds([])
                setIsEnabled(true)
              }}
              className="w-full flex items-center justify-center gap-2 h-9 rounded-lg border border-dashed border-[var(--border-primary)] text-sm text-[var(--text-secondary)] hover:border-brand-500 hover:text-brand-500"
            >
              <IconPlus /> New agent
            </button>
            {agents.map((agent) => (
              <div
                key={agent.id}
                className={`group flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer ${
                  selectedId === agent.id
                    ? 'bg-brand-500/10 text-brand-500'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]'
                }`}
                onClick={() => setSelectedId(agent.id)}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{agent.name}</p>
                  <p className="text-[10px] text-[var(--text-tertiary)]">
                    {agent.is_enabled ? 'Enabled' : 'Disabled'} · {agent.enabled_tools.length} tools
                  </p>
                </div>
                <button
                  type="button"
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-[var(--color-error)]"
                  onClick={(e) => {
                    e.stopPropagation()
                    void handleDelete(agent.id, agent.name)
                  }}
                >
                  <IconTrash />
                </button>
              </div>
            ))}
          </aside>

          <form
            onSubmit={selected ? handleSave : handleCreate}
            className="flex-1 overflow-y-auto p-6 space-y-4 max-w-3xl"
          >
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                Description
              </span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                System prompt
              </span>
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={6}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
                required
              />
            </label>

            {selected && (
              <label className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={(e) => setIsEnabled(e.target.checked)}
                />
                Enabled
              </label>
            )}

            <div>
              <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase mb-2">
                Knowledge bases
              </p>
              <div className="flex flex-wrap gap-2">
                {knowledgeBases.length === 0 ? (
                  <p className="text-sm text-[var(--text-tertiary)]">No knowledge bases</p>
                ) : (
                  knowledgeBases.map((kb) => (
                    <label
                      key={kb.id}
                      className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-[var(--border-primary)]"
                    >
                      <input
                        type="checkbox"
                        checked={kbIds.includes(kb.id)}
                        onChange={() => toggleKb(kb.id)}
                      />
                      {kb.name}
                    </label>
                  ))
                )}
              </div>
            </div>

            <div>
              <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase mb-2">Tools</p>
              <div className="space-y-2">
                {tools.map((tool) => (
                  <label
                    key={tool.name}
                    className="flex items-start gap-2 rounded-lg border border-[var(--border-primary)] p-3"
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={enabledTools.includes(tool.name)}
                      onChange={() => toggleTool(tool.name)}
                    />
                    <span>
                      <span className="text-sm text-[var(--text-primary)] font-medium">
                        {tool.name}
                      </span>
                      <span className="block text-xs text-[var(--text-tertiary)]">
                        {tool.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={saving || creating}
              className="h-9 px-4 rounded-lg bg-brand-500 text-white text-sm font-medium disabled:opacity-50"
            >
              {selected ? (saving ? 'Saving...' : 'Save agent') : creating ? 'Creating...' : 'Create agent'}
            </button>
          </form>
        </div>
      )}
    </div>
    </ChatLayout>
  )
}
