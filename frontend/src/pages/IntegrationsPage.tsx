import { useCallback, useEffect, useState, type FormEvent } from 'react'
import ChatLayout from '@/components/layout/ChatLayout'
import type { Integration, IntegrationTool } from '@/types'
import {
  listIntegrations,
  createIntegration,
  updateIntegration,
  deleteIntegration,
  connectIntegration,
  refreshIntegrationTools,
  listIntegrationTools,
  listIntegrationTypes,
} from '@/services/integrationService'
import { IconPlus, IconTrash, IconRefresh } from '@/components/ui/Icons'

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [types, setTypes] = useState<string[]>(['mcp', 'github'])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [tools, setTools] = useState<IntegrationTool[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [type, setType] = useState('github')
  const [endpoint, setEndpoint] = useState('')
  const [allowPrivate, setAllowPrivate] = useState(false)
  const [credentialValue, setCredentialValue] = useState('')
  const [isEnabled, setIsEnabled] = useState(true)
  const [creating, setCreating] = useState(false)

  const selected = integrations.find((i) => i.id === selectedId) ?? null

  const load = useCallback(async () => {
    setError('')
    try {
      const [rows, typeRows] = await Promise.all([listIntegrations(), listIntegrationTypes()])
      setIntegrations(rows)
      if (typeRows.length) setTypes(typeRows)
      setSelectedId((current) => {
        if (current != null && rows.some((r) => r.id === current)) return current
        return rows[0]?.id ?? null
      })
    } catch {
      setError('Failed to load integrations')
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
      setType('github')
      setEndpoint('')
      setAllowPrivate(false)
      setCredentialValue('')
      setIsEnabled(true)
      setTools([])
      return
    }
    setName(selected.name)
    setDescription(selected.description || '')
    setType(selected.type)
    setEndpoint(String(selected.config?.endpoint || ''))
    setAllowPrivate(Boolean(selected.config?.allow_private))
    setCredentialValue('')
    setIsEnabled(selected.is_enabled)
    void listIntegrationTools(selected.id)
      .then(setTools)
      .catch(() => setTools([]))
  }, [selected])

  function buildConfig(): Record<string, unknown> {
    if (type === 'mcp') {
      return { endpoint: endpoint.trim(), transport: 'http', allow_private: allowPrivate }
    }
    return {}
  }

  function buildCredentials(): Record<string, unknown> | null {
    const value = credentialValue.trim()
    if (!value) return null
    if (type === 'github') return { access_token: value }
    if (type === 'mcp') return { bearer_token: value }
    return { token: value }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setCreating(true)
    setError('')
    try {
      const credentials = buildCredentials()
      const created = await createIntegration({
        type,
        name: name.trim() || `${type} integration`,
        description: description || null,
        config: buildConfig(),
        credentials,
        is_enabled: true,
      })
      setCredentialValue('')
      await load()
      setSelectedId(created.id)
    } catch {
      setError('Failed to create integration. Check configuration and credentials.')
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
      const credentials = buildCredentials()
      await updateIntegration(selected.id, {
        name: name.trim(),
        description: description || null,
        config: buildConfig(),
        ...(credentials ? { credentials } : {}),
        is_enabled: isEnabled,
      })
      setCredentialValue('')
      await load()
    } catch {
      setError('Failed to save integration')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number, integrationName: string) {
    if (!window.confirm(`Delete integration "${integrationName}"? Discovered tools will be removed.`)) {
      return
    }
    setError('')
    try {
      await deleteIntegration(id)
      await load()
    } catch {
      setError('Failed to delete integration')
    }
  }

  async function handleConnect() {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      await connectIntegration(selected.id)
      await load()
      setTools(await listIntegrationTools(selected.id))
    } catch {
      setError('Connect/discover failed. Check endpoint, credentials, and server availability.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRefresh() {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      await refreshIntegrationTools(selected.id)
      await load()
      setTools(await listIntegrationTools(selected.id))
    } catch {
      setError('Tool refresh failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <ChatLayout>
      <div className="h-full flex flex-col bg-[var(--bg-primary)] flex-1 min-w-0">
        <div className="border-b border-[var(--border-primary)] px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-[var(--text-primary)]">Integrations</h1>
            <p className="text-sm text-[var(--text-tertiary)]">
              Connect MCP servers and GitHub. Credentials are never shown after save.
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
            Loading integrations...
          </div>
        ) : (
          <div className="flex-1 flex min-h-0">
            <aside className="w-64 border-r border-[var(--border-primary)] p-3 space-y-2 overflow-y-auto">
              <button
                type="button"
                onClick={() => {
                  setSelectedId(null)
                  setName('')
                  setDescription('')
                  setType('github')
                  setEndpoint('')
                  setAllowPrivate(false)
                  setCredentialValue('')
                  setIsEnabled(true)
                  setTools([])
                }}
                className="w-full flex items-center justify-center gap-2 h-9 rounded-lg border border-dashed border-[var(--border-primary)] text-sm text-[var(--text-secondary)] hover:border-brand-500 hover:text-brand-500"
              >
                <IconPlus /> New integration
              </button>
              {integrations.map((item) => (
                <div
                  key={item.id}
                  className={`group flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer ${
                    selectedId === item.id
                      ? 'bg-brand-500/10 text-brand-500'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]'
                  }`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{item.name}</p>
                    <p className="text-[10px] text-[var(--text-tertiary)]">
                      {item.type} · {item.tool_count} tools ·{' '}
                      {item.is_enabled ? 'Enabled' : 'Disabled'}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="opacity-0 group-hover:opacity-100 p-1 hover:text-[var(--color-error)]"
                    onClick={(e) => {
                      e.stopPropagation()
                      void handleDelete(item.id, item.name)
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
                <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                  Type
                </span>
                <select
                  value={type}
                  disabled={Boolean(selected)}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
                >
                  {types.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block space-y-1">
                <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                  Name
                </span>
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

              {type === 'mcp' && (
                <>
                  <label className="block space-y-1">
                    <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                      MCP endpoint (HTTPS)
                    </span>
                    <input
                      value={endpoint}
                      onChange={(e) => setEndpoint(e.target.value)}
                      placeholder="https://example.com/mcp"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
                      required={!selected}
                    />
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                    <input
                      type="checkbox"
                      checked={allowPrivate}
                      onChange={(e) => setAllowPrivate(e.target.checked)}
                    />
                    Allow private/local hosts (trusted MCP only)
                  </label>
                </>
              )}

              <label className="block space-y-1">
                <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">
                  {type === 'github' ? 'GitHub access token' : 'Bearer token (optional)'}
                </span>
                <input
                  type="password"
                  value={credentialValue}
                  onChange={(e) => setCredentialValue(e.target.value)}
                  placeholder={
                    selected?.has_credentials
                      ? 'Credentials saved — leave blank to keep'
                      : 'Enter secret (never displayed after save)'
                  }
                  className="w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-sm"
                  autoComplete="off"
                />
                {selected?.has_credentials && (
                  <span className="text-xs text-[var(--text-tertiary)]">
                    Credentials are stored encrypted and never returned by the API.
                  </span>
                )}
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

              {selected?.last_error && (
                <p className="text-xs text-[var(--color-error)]">Last error: {selected.last_error}</p>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={saving || creating}
                  className="h-9 px-4 rounded-lg bg-brand-500 text-white text-sm font-medium disabled:opacity-50"
                >
                  {selected
                    ? saving
                      ? 'Saving...'
                      : 'Save integration'
                    : creating
                      ? 'Creating...'
                      : 'Create integration'}
                </button>
                {selected && (
                  <>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleConnect()}
                      className="h-9 px-4 rounded-lg border border-[var(--border-primary)] text-sm disabled:opacity-50"
                    >
                      Connect & discover
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleRefresh()}
                      className="h-9 px-4 rounded-lg border border-[var(--border-primary)] text-sm disabled:opacity-50"
                    >
                      Refresh tools
                    </button>
                  </>
                )}
              </div>

              {selected && (
                <div>
                  <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase mb-2">
                    Discovered tools (usable in Agents)
                  </p>
                  {tools.length === 0 ? (
                    <p className="text-sm text-[var(--text-tertiary)]">
                      No tools yet. Use Connect & discover after saving credentials.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {tools.map((tool) => (
                        <li
                          key={tool.id}
                          className="rounded-lg border border-[var(--border-primary)] p-3"
                        >
                          <p className="text-sm font-medium text-[var(--text-primary)]">
                            {tool.registry_name}
                          </p>
                          <p className="text-xs text-[var(--text-tertiary)]">{tool.description}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </form>
          </div>
        )}
      </div>
    </ChatLayout>
  )
}
