import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { useTheme } from '@/contexts/ThemeContext'
import { IconSun, IconMoon, IconSearch, IconUser, IconLogout, IconSettings, IconMenu } from '@/components/ui/Icons'

export default function Navbar({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { user, logout } = useAuth()
  const { currentWorkspace, workspaces, setCurrentWorkspace } = useWorkspace()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function handleLogout() {
    logout()
    navigate('/auth/login', { replace: true })
  }

  return (
    <nav className="h-14 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] flex items-center px-4 gap-3 shrink-0">
      <button
        onClick={onToggleSidebar}
        className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        <IconMenu />
      </button>

      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-brand-500 flex items-center justify-center">
          <span className="text-white text-xs font-bold">X</span>
        </div>
        <span className="text-sm font-semibold text-[var(--text-primary)] hidden sm:block">
          Xplore.ai
        </span>
      </div>

      {workspaces.length > 0 && (
        <div className="hidden sm:flex items-center gap-2 min-w-0 max-w-[200px]">
          <span className="text-xs text-[var(--text-tertiary)] shrink-0">Workspace</span>
          <select
            value={currentWorkspace?.id ?? ''}
            onChange={(e) => {
              const id = Number(e.target.value)
              const next = workspaces.find((w) => w.id === id)
              if (next) setCurrentWorkspace(next)
            }}
            className="h-8 flex-1 min-w-0 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-primary)] text-sm px-2 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
            aria-label="Select workspace"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex-1 max-w-md mx-auto hidden md:block">
        <div className="relative">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            type="text"
            placeholder="Search your knowledge base..."
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors"
          />
        </div>
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
        >
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-brand-500/20 flex items-center justify-center">
              <IconUser className="text-brand-500" />
            </div>
            <span className="text-sm text-[var(--text-primary)] hidden sm:block max-w-[120px] truncate">
              {user?.username || 'User'}
            </span>
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-lg py-1 z-50">
              <div className="px-3 py-2 border-b border-[var(--border-primary)]">
                <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                  {user?.username || 'User'}
                </p>
                <p className="text-xs text-[var(--text-tertiary)] truncate">
                  {user?.email || ''}
                </p>
              </div>
              <button
                onClick={() => { setMenuOpen(false); navigate('/settings') }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                <IconSettings />
                Settings
              </button>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--color-error)] hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                <IconLogout />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}
