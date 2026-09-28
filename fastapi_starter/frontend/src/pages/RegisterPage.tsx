import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { register, login, getCurrentUser } from '@/services/authService'

export default function RegisterPage() {
  const navigate = useNavigate()
  const { login: authLogin } = useAuth()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(username, email, password)
      const { access_token } = await login(email, password)
      authLogin(access_token, { id: 0, username, email, full_name: null, is_active: true, is_superuser: false, has_custom_llm_key: false, llm_provider: null, llm_base_url: null, llm_model_name: null })
      const user = await getCurrentUser()
      authLogin(access_token, user)
      navigate('/chat', { replace: true })
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosErr.response?.status === 409 || axiosErr.response?.status === 400) {
          setError('That email is already registered')
        } else if (axiosErr.response?.data?.detail) {
          setError(axiosErr.response.data.detail)
        } else {
          setError('Registration failed. Please try again.')
        }
      } else {
        setError('Unable to connect to the server')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight">
            Xplore.ai
          </h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-1">
            Create an account to get started
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] p-6">
          <div className="flex mb-6 border-b border-[var(--border-primary)]">
            <Link
              to="/auth/login"
              className="flex-1 pb-3 text-sm font-medium text-center text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Sign in
            </Link>
            <Link
              to="/auth/register"
              className="flex-1 pb-3 text-sm font-medium text-center text-brand-500 border-b-2 border-brand-500"
            >
              Create account
            </Link>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="your_name"
                required
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-colors"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={6}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-colors"
              />
            </div>

            {error && (
              <p className="text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>
        </div>

        <p className="text-center mt-6 text-xs text-[var(--text-tertiary)]">
          Xplore.ai v0.1.0
        </p>
      </div>
    </div>
  )
}
