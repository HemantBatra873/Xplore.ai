import { useState, useEffect, useRef, useCallback, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Document, KnowledgeBase } from '@/types'
import {
  listKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBaseDocuments,
  uploadKnowledgeBaseDocument,
  deleteKnowledgeBaseDocument,
} from '@/services/knowledgeService'
import { IconFile, IconUpload, IconTrash, IconRefresh, IconPlus } from '@/components/ui/Icons'
import { statusLabels, statusColors } from '@/components/knowledge/constants'

export default function KnowledgePage() {
  const navigate = useNavigate()
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbId, setSelectedKbId] = useState<number | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [kbLoading, setKbLoading] = useState(true)
  const [docsLoading, setDocsLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [creatingKb, setCreatingKb] = useState(false)
  const [newKbName, setNewKbName] = useState('')
  const [error, setError] = useState('')
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card')
  const fileRef = useRef<HTMLInputElement>(null)

  const selectedKb = knowledgeBases.find((kb) => kb.id === selectedKbId) ?? null

  const loadKnowledgeBases = useCallback(async (preferId?: number | null) => {
    setError('')
    try {
      const data = await listKnowledgeBases()
      setKnowledgeBases(data)
      setSelectedKbId((current) => {
        if (preferId != null && data.some((kb) => kb.id === preferId)) return preferId
        if (current != null && data.some((kb) => kb.id === current)) return current
        return data[0]?.id ?? null
      })
    } catch {
      setError('Failed to load knowledge bases')
    } finally {
      setKbLoading(false)
    }
  }, [])

  const loadDocs = useCallback(
    async (silent = false) => {
      if (selectedKbId == null) {
        setDocs([])
        return
      }
      if (!silent) setDocsLoading(true)
      setError('')
      try {
        const data = await listKnowledgeBaseDocuments(selectedKbId)
        setDocs(data)
      } catch {
        setError('Failed to load documents')
      } finally {
        if (!silent) setDocsLoading(false)
      }
    },
    [selectedKbId],
  )

  useEffect(() => {
    loadKnowledgeBases()
  }, [loadKnowledgeBases])

  useEffect(() => {
    if (selectedKbId == null) {
      setDocs([])
      return
    }
    loadDocs()
  }, [selectedKbId, loadDocs])

  const hasPendingDocs = docs.some((d) => d.status === 'queued' || d.status === 'processing')

  useEffect(() => {
    if (selectedKbId == null || !hasPendingDocs) return
    const timer = window.setInterval(() => {
      loadDocs(true)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [selectedKbId, hasPendingDocs, loadDocs])

  async function handleCreateKb(e: FormEvent) {
    e.preventDefault()
    const name = newKbName.trim()
    if (!name || creatingKb) return
    setError('')
    setCreatingKb(true)
    try {
      const kb = await createKnowledgeBase({ name })
      setNewKbName('')
      await loadKnowledgeBases(kb.id)
    } catch {
      setError('Failed to create knowledge base')
    } finally {
      setCreatingKb(false)
    }
  }

  async function handleDeleteKb(id: number, name: string) {
    if (!window.confirm(`Delete "${name}"? All documents in this knowledge base will be removed.`)) return
    setError('')
    try {
      await deleteKnowledgeBase(id)
      await loadKnowledgeBases()
    } catch {
      setError('Failed to delete knowledge base')
    }
  }

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || selectedKbId == null) return
    setError('')
    setUploading(true)
    try {
      await uploadKnowledgeBaseDocument(selectedKbId, file)
      await loadDocs()
      await loadKnowledgeBases(selectedKbId)
    } catch {
      setError('Upload failed. Please try again.')
    }
    if (fileRef.current) fileRef.current.value = ''
    setUploading(false)
  }

  async function handleDeleteDoc(id: number) {
    if (selectedKbId == null) return
    setError('')
    try {
      await deleteKnowledgeBaseDocument(selectedKbId, id)
      await loadDocs()
      await loadKnowledgeBases(selectedKbId)
    } catch {
      setError('Delete failed. Please try again.')
    }
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="h-14 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] flex items-center px-6 gap-4">
        <button onClick={() => navigate('/chat')} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
          ← Back
        </button>
        <h1 className="text-sm font-semibold text-[var(--text-primary)]">Knowledge bases</h1>
      </header>

      <div className="max-w-6xl mx-auto p-6 flex flex-col lg:flex-row gap-6">
        <aside className="lg:w-72 shrink-0 space-y-4">
          <form onSubmit={handleCreateKb} className="flex gap-2">
            <input
              value={newKbName}
              onChange={(e) => setNewKbName(e.target.value)}
              placeholder="New knowledge base name"
              className="flex-1 min-w-0 h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
            />
            <button
              type="submit"
              disabled={creatingKb || !newKbName.trim()}
              className="h-9 px-3 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 disabled:opacity-50 flex items-center gap-1"
            >
              <IconPlus />
              Add
            </button>
          </form>

          <div className="rounded-xl border border-[var(--border-primary)] overflow-hidden">
            <div className="px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border-primary)] flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Knowledge bases</span>
              <button onClick={() => loadKnowledgeBases()} className="p-1 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
                <IconRefresh />
              </button>
            </div>
            {kbLoading ? (
              <div className="p-3 space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-12 rounded-lg bg-[var(--bg-tertiary)] animate-pulse" />
                ))}
              </div>
            ) : knowledgeBases.length === 0 ? (
              <p className="p-4 text-sm text-[var(--text-tertiary)]">Create a knowledge base to get started.</p>
            ) : (
              <ul className="divide-y divide-[var(--border-secondary)]">
                {knowledgeBases.map((kb) => (
                  <li key={kb.id}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedKbId(kb.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedKbId(kb.id)
                        }
                      }}
                      className={`w-full text-left px-3 py-3 flex items-start justify-between gap-2 transition-colors cursor-pointer ${
                        selectedKbId === kb.id ? 'bg-[var(--bg-secondary)]' : 'hover:bg-[var(--bg-secondary)]/60'
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">{kb.name}</p>
                        <p className="text-xs text-[var(--text-tertiary)]">{kb.document_count} documents</p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteKb(kb.id, kb.name)
                        }}
                        className="shrink-0 p-1 rounded text-[var(--text-tertiary)] hover:text-[var(--color-error)]"
                        aria-label={`Delete ${kb.name}`}
                      >
                        <IconTrash />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="flex-1 min-w-0 space-y-6">
          {!selectedKb ? (
            <div className="text-center py-16 rounded-xl border border-[var(--border-primary)]">
              <p className="text-sm text-[var(--text-tertiary)]">Select or create a knowledge base to manage documents.</p>
            </div>
          ) : (
            <>
              <div>
                <h2 className="text-base font-semibold text-[var(--text-primary)]">{selectedKb.name}</h2>
                {selectedKb.description && (
                  <p className="text-sm text-[var(--text-tertiary)] mt-1">{selectedKb.description}</p>
                )}
              </div>

              <div className="border-2 border-dashed border-[var(--border-primary)] rounded-xl p-8 text-center hover:border-brand-500/50 transition-colors">
                <input ref={fileRef} type="file" accept=".txt,.md,.pdf" onChange={handleUpload} className="hidden" />
                <button onClick={() => fileRef.current?.click()} disabled={uploading} className="disabled:opacity-50">
                  <IconUpload className="mx-auto mb-3 text-[var(--text-tertiary)]" />
                  <p className="text-sm text-[var(--text-tertiary)]">{uploading ? 'Uploading...' : 'Drag or click to upload a document'}</p>
                  <p className="text-xs text-[var(--text-tertiary)] mt-1">TXT, Markdown, and PDF files are supported</p>
                </button>
              </div>

              {error && <p className="text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 rounded-lg px-3 py-2">{error}</p>}

              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Documents ({docs.length})</h3>
                <div className="flex items-center gap-2">
                  {hasPendingDocs && (
                    <span className="text-xs text-[var(--text-tertiary)]">Auto-refreshing status…</span>
                  )}
                  <button onClick={() => setViewMode(viewMode === 'card' ? 'table' : 'card')} className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
                    {viewMode === 'card' ? 'Table view' : 'Card view'}
                  </button>
                  <button onClick={() => loadDocs()} className="p-1.5 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
                    <IconRefresh />
                  </button>
                </div>
              </div>

              {docsLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-24 rounded-xl bg-[var(--bg-tertiary)] animate-pulse" />
                  ))}
                </div>
              ) : docs.length === 0 ? (
                <div className="text-center py-16">
                  <IconFile className="mx-auto mb-3 text-[var(--text-tertiary)]" />
                  <p className="text-sm text-[var(--text-tertiary)]">No documents yet</p>
                  <p className="text-xs text-[var(--text-tertiary)] mt-1">Upload a document to this knowledge base</p>
                </div>
              ) : viewMode === 'table' ? (
                <div className="rounded-xl border border-[var(--border-primary)] overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-[var(--bg-secondary)] text-[var(--text-tertiary)] text-xs uppercase tracking-wider">
                        <th className="text-left px-4 py-3 font-medium">Filename</th>
                        <th className="text-left px-4 py-3 font-medium">Type</th>
                        <th className="text-left px-4 py-3 font-medium">Status</th>
                        <th className="text-left px-4 py-3 font-medium">Chunks</th>
                        <th className="text-left px-4 py-3 font-medium">Uploaded</th>
                        <th className="text-right px-4 py-3 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border-secondary)]">
                      {docs.map((doc) => (
                        <tr key={doc.id} className="hover:bg-[var(--bg-secondary)] transition-colors">
                          <td className="px-4 py-3">
                            <p className="text-[var(--text-primary)]">{doc.filename}</p>
                            {doc.status === 'failed' && doc.error_message && (
                              <p className="text-xs text-[var(--color-error)] mt-0.5">{doc.error_message}</p>
                            )}
                          </td>
                          <td className="px-4 py-3 text-[var(--text-secondary)]">{doc.file_type}</td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center gap-1.5 text-xs ${statusColors[doc.status] === 'bg-[var(--color-success)]' ? 'text-[var(--color-success)]' : 'text-[var(--text-tertiary)]'}`}>
                              <span className={`w-2 h-2 rounded-full ${statusColors[doc.status]}`} />
                              {statusLabels[doc.status] || doc.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-[var(--text-secondary)]">{doc.chunks_count}</td>
                          <td className="px-4 py-3 text-[var(--text-tertiary)] text-xs">
                            {new Date(doc.created_at).toLocaleString('en-US')}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button onClick={() => handleDeleteDoc(doc.id)} className="p-1.5 rounded text-[var(--text-tertiary)] hover:text-[var(--color-error)] transition-colors">
                              <IconTrash />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {docs.map((doc) => (
                    <div key={doc.id} className="p-4 rounded-xl border border-[var(--border-primary)] hover:bg-[var(--bg-secondary)] transition-colors group">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-[var(--bg-tertiary)] flex items-center justify-center">
                            <IconFile className="text-[var(--text-tertiary)]" />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[var(--text-primary)]">{doc.filename}</p>
                            <p className="text-xs text-[var(--text-tertiary)]">{doc.file_type}</p>
                          </div>
                        </div>
                        <button onClick={() => handleDeleteDoc(doc.id)} className="p-1.5 rounded text-[var(--text-tertiary)] opacity-0 group-hover:opacity-100 hover:text-[var(--color-error)] transition-all">
                          <IconTrash />
                        </button>
                      </div>
                      <div className="flex items-center gap-3 mt-3 text-xs text-[var(--text-tertiary)]">
                        <span className="inline-flex items-center gap-1">
                          <span className={`w-2 h-2 rounded-full ${statusColors[doc.status]}`} />
                          {statusLabels[doc.status] || doc.status}
                        </span>
                        {doc.status === 'ready' && <span>{doc.chunks_count} chunks</span>}
                        <span>{new Date(doc.created_at).toLocaleDateString('en-US')}</span>
                      </div>
                      {doc.status === 'failed' && doc.error_message && (
                        <p className="mt-2 text-xs text-[var(--color-error)]">{doc.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
