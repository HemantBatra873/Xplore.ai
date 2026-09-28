import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { getCurrentUser, updateLLMConfig, changePassword } from '@/services/userService'
import type { HealthStatus } from '@/types'
import api from '@/services/api'

const PROVIDERS = [
  { value: '', label: 'Use global configuration' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'custom', label: 'Custom' },
]

export default function SettingsPage() {
  const navigate = useNavigate()
  const { user, setUser } = useAuth()

  const [provider, setProvider] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [modelName, setModelName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmMessage, setLlmMessage] = useState('')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwSaving, setPwSaving] = useState(false)
  const [pwMessage, setPwMessage] = useState('')

  const [health, setHealth] = useState<HealthStatus | null>(null)

  useEffect(() => {
    getCurrentUser().then((u) => setUser(u)).catch(() => {})
    api.get<HealthStatus>('/health').then((r) => setHealth(r.data)).catch(() => {})
  }, [setUser])

  useEffect(() => {
    if (user) {
      setProvider(user.llm_provider || '')
      setBaseUrl(user.llm_base_url || '')
      setModelName(user.llm_model_name || '')
    }
  }, [user])

  async function handleLLMConfig(e: FormEvent) {
    e.preventDefault()
    setLlmMessage('')
    setLlmSaving(true)
    try {
      const updated = await updateLLMConfig({
        provider: provider || undefined,
        base_url: baseUrl || undefined,
        model_name: modelName || undefined,
        api_key: apiKey || undefined,
      })
      setUser(updated)
      setApiKey('')
      setLlmMessage('LLM configuration saved')
    } catch {
      setLlmMessage('Save failed. Please try again.')
    } finally {
      setLlmSaving(false)
    }
  }

  async function handleClearLLMConfig() {
    setLlmMessage('')
    setLlmSaving(true)
    try {
      const updated = await updateLLMConfig({
        provider: '',
        base_url: '',
        model_name: '',
        api_key: '',
      })
      setUser(updated)
      setProvider('')
      setBaseUrl('')
      setModelName('')
      setApiKey('')
      setLlmMessage('Personal LLM configuration cleared. Using the global configuration')
    } catch {
      setLlmMessage('Clear failed. Please try again.')
    } finally {
      setLlmSaving(false)
    }
  }

  async function handlePassword(e: FormEvent) {
    e.preventDefault()
    setPwMessage('')
    if (newPassword !== confirmPassword) {
      setPwMessage('The new passwords do not match')
      return
    }
    if (newPassword.length < 6) {
      setPwMessage('New password must be at least 6 characters')
      return
    }
    setPwSaving(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPwMessage('Password changed successfully')
    } catch {
      setPwMessage('Update failed. Check the current password.')
    } finally {
      setPwSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="h-14 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] flex items-center px-6 gap-4">
        <button onClick={() => navigate('/chat')} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
          ← Back
        </button>
        <h1 className="text-sm font-semibold text-[var(--text-primary)]">Settings</h1>
      </header>

      <div className="max-w-xl mx-auto p-6 space-y-8">
        <section>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">System status</h2>
          <div className="grid grid-cols-3 gap-3">
            <StatusCard label="Database" status={health?.dependencies.database.status} />
            <StatusCard label="Redis" status={health?.dependencies.redis.status} />
            <StatusCard label="Ollama" status={health?.dependencies.ollama.status} />
          </div>
          {health?.dependencies.ollama.status !== 'up' && (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              Ollama is not running, so RAG document embedding is unavailable. Run <code className="px-1 py-0.5 rounded bg-[var(--bg-tertiary)] font-mono">make up-full</code> to start the full stack.
            </p>
          )}
        </section>

        <hr className="border-[var(--border-primary)]" />

        <section>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-1">LLM configuration</h2>
          <p className="text-xs text-[var(--text-tertiary)] mb-4">
            When configured, your personal LLM key takes precedence over the global key.
          </p>

          <form onSubmit={handleLLMConfig} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Provider</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Base URL</label>
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Model name</label>
              <input
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="gpt-4o-mini"
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                API key {user?.has_custom_llm_key ? <span className="text-[var(--color-success)]">(configured)</span> : <span className="text-[var(--text-tertiary)]">(not configured)</span>}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] font-mono focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            {llmMessage && (
              <p className={`text-sm ${llmMessage.includes('Success') ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}`}>
                {llmMessage}
              </p>
            )}

            <div className="flex items-center gap-3">
              <button type="submit" disabled={llmSaving} className="px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 disabled:opacity-50 transition-colors">
                {llmSaving ? 'Saving...' : 'Save configuration'}
              </button>
              {user?.has_custom_llm_key && (
                <button type="button" disabled={llmSaving} onClick={handleClearLLMConfig} className="px-4 py-2 rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--color-error)] hover:border-[var(--color-error)] disabled:opacity-50 transition-colors">
                  Clear personal configuration
                </button>
              )}
            </div>
          </form>
        </section>

        <hr className="border-[var(--border-primary)]" />

        <section>
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Change password</h2>

          <form onSubmit={handlePassword} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Current password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">New password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Confirm new password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
              />
            </div>

            {pwMessage && (
              <p className={`text-sm ${pwMessage.includes('Success') ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}`}>
                {pwMessage}
              </p>
            )}

            <button type="submit" disabled={pwSaving} className="px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 disabled:opacity-50 transition-colors">
              {pwSaving ? 'Updating...' : 'Change password'}
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}

function StatusCard({ label, status }: { label: string; status?: string }) {
  const isUp = status === 'up'
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]">
      <span className={`w-2 h-2 rounded-full ${isUp ? 'bg-emerald-500' : 'bg-red-400'}`} />
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span className={`text-xs ml-auto ${isUp ? 'text-emerald-500' : 'text-red-400'}`}>
        {isUp ? 'UP' : 'DOWN'}
      </span>
    </div>
  )
}
