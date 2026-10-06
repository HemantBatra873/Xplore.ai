import { useState } from 'react'
import { Link } from 'react-router-dom'
import { IconFile, IconWrench, IconX } from '@/components/ui/Icons'
import KnowledgePanel from '@/components/knowledge/KnowledgePanel'
import TasksPanel from '@/components/tasks/TasksPanel'

type Tab = 'knowledge' | 'tasks' | 'agents' | 'integrations'

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<Tab>('knowledge')

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-30 lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`
          fixed lg:absolute inset-y-0 left-0 w-80 z-40
          border-r border-[var(--border-primary)] bg-[var(--bg-secondary)]
          flex flex-col
          transition-transform duration-200 ease-in-out
          ${open ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <div className="flex border-b border-[var(--border-primary)]">
          <button
            onClick={() => setActiveTab('knowledge')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'knowledge'
                ? 'text-brand-500 border-b-2 border-brand-500'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
            }`}
          >
            <IconFile />
            Knowledge
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'agents'
                ? 'text-brand-500 border-b-2 border-brand-500'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
            }`}
          >
            <IconWrench />
            Agents
          </button>
          <button
            onClick={() => setActiveTab('integrations')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'integrations'
                ? 'text-brand-500 border-b-2 border-brand-500'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
            }`}
          >
            <IconWrench />
            Integrations
          </button>
          <button
            onClick={() => setActiveTab('tasks')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'tasks'
                ? 'text-brand-500 border-b-2 border-brand-500'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
            }`}
          >
            <IconWrench />
            Tasks
          </button>
          <button
            onClick={onClose}
            className="px-3 py-3 text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <IconX />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {activeTab === 'knowledge' ? (
            <KnowledgePanel />
          ) : activeTab === 'agents' ? (
            <div className="space-y-3 text-sm text-[var(--text-secondary)]">
              <p>Create and configure agents on the Agents page.</p>
              <Link
                to="/agents"
                className="inline-flex items-center text-brand-500 hover:underline"
                onClick={onClose}
              >
                Open Agents
              </Link>
            </div>
          ) : activeTab === 'integrations' ? (
            <div className="space-y-3 text-sm text-[var(--text-secondary)]">
              <p>Connect MCP servers and GitHub. Tools appear in Agent configuration.</p>
              <Link
                to="/integrations"
                className="inline-flex items-center text-brand-500 hover:underline"
                onClick={onClose}
              >
                Open Integrations
              </Link>
            </div>
          ) : (
            <TasksPanel />
          )}
        </div>
      </aside>
    </>
  )
}

