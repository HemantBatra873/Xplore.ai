import { useState, useEffect, useRef, useCallback, type ChangeEvent } from 'react'
import type { Document, KnowledgeBase, KnowledgeQueryResult } from '@/types'
import {
  listKnowledgeBases,
  listKnowledgeBaseDocuments,
  uploadKnowledgeBaseDocument,
  deleteKnowledgeBaseDocument,
  queryKnowledgeBase,
} from '@/services/knowledgeService'
import { IconFile, IconUpload, IconTrash, IconSearch, IconRefresh, IconX } from '@/components/ui/Icons'
import { statusLabels, statusColors } from '@/components/knowledge/constants'

function QuerySources({ result }: { result: KnowledgeQueryResult }) {
  if (result.sources.length > 0) {
    return (
      <div className="mt-2 pt-2 border-t border-[var(--border-primary)]">
        <p className="text-xs text-[var(--text-tertiary)] mb-1">Sources ({result.sources.length})</p>
        {result.sources.map((source) => (
          <div key={source.chunk_id} className="mt-2">
            <p className="text-xs font-medium text-[var(--text-secondary)]">{source.filename}</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5 line-clamp-3">{source.excerpt}</p>
          </div>
        ))}
      </div>
    )
  }
  if (result.source_chunks.length > 0) {
    return (
      <div className="mt-2 pt-2 border-t border-[var(--border-primary)]">
        <p className="text-xs text-[var(--text-tertiary)] mb-1">Source passages ({result.source_chunks.length})</p>
        {result.source_chunks.map((chunk, i) => (
          <p key={i} className="text-xs text-[var(--text-tertiary)] mt-1 line-clamp-2">
            [{i + 1}] {chunk}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function KnowledgePanel() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbId, setSelectedKbId] = useState<number | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [queryResult, setQueryResult] = useState<KnowledgeQueryResult | null>(null)
  const [querying, setQuerying] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const loadKnowledgeBases = useCallback(async () => {
    setError('')
    try {
      const data = await listKnowledgeBases()
      setKnowledgeBases(data)
      setSelectedKbId((current) => {
        if (current != null && data.some((kb) => kb.id === current)) return current
        return data[0]?.id ?? null
      })
    } catch {
      setError('Failed to load knowledge bases')
    }
  }, [])

  const loadDocs = useCallback(
    async (silent = false) => {
      if (selectedKbId == null) {
        setDocuments([])
        if (!silent) setLoading(false)
        return
      }
      if (!silent) setLoading(true)
      setError('')
      try {
        const data = await listKnowledgeBaseDocuments(selectedKbId)
        setDocuments(data)
      } catch {
        setError('Failed to load documents')
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [selectedKbId],
  )

  useEffect(() => {
    loadKnowledgeBases().finally(() => setLoading(false))
  }, [loadKnowledgeBases])

  useEffect(() => {
    loadDocs()
  }, [selectedKbId, loadDocs])

  const hasPendingDocs = documents.some((d) => d.status === 'queued' || d.status === 'processing')

  useEffect(() => {
    if (selectedKbId == null || !hasPendingDocs) return
    const timer = window.setInterval(() => loadDocs(true), 5000)
    return () => window.clearInterval(timer)
  }, [selectedKbId, hasPendingDocs, loadDocs])

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || selectedKbId == null) return
    setError('')
    setUploading(true)
    try {
      await uploadKnowledgeBaseDocument(selectedKbId, file)
      await loadDocs()
      await loadKnowledgeBases()
    } catch {
      setError('Upload failed. Please try again.')
    }
    if (fileRef.current) fileRef.current.value = ''
    setUploading(false)
  }

  async function handleDelete(id: number) {
    if (selectedKbId == null) return
    setError('')
    try {
      await deleteKnowledgeBaseDocument(selectedKbId, id)
      await loadDocs()
      await loadKnowledgeBases()
    } catch {
      setError('Delete failed. Please try again.')
    }
  }

  async function handleQuery() {
    if (!query.trim() || querying || selectedKbId == null) return
    setQuerying(true)
    setQueryResult(null)
    try {
      const result = await queryKnowledgeBase(selectedKbId, query.trim())
      setQueryResult(result)
    } catch {
      setError('Query failed. Please try again.')
    } finally {
      setQuerying(false)
    }
  }

  return (
    <div className="space-y-4">
      {knowledgeBases.length > 0 ? (
        <label className="block">
          <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Knowledge base</span>
          <select
            value={selectedKbId ?? ''}
            onChange={(e) => setSelectedKbId(Number(e.target.value))}
            className="mt-1 w-full h-9 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
          >
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        !loading && (
          <p className="text-sm text-[var(--text-tertiary)]">Create a knowledge base on the Knowledge page to upload documents.</p>
        )
      )}

      <div className="relative">
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.pdf"
          onChange={handleUpload}
          className="hidden"
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading || selectedKbId == null}
          className="w-full border-2 border-dashed border-[var(--border-primary)] rounded-xl p-6 text-center hover:border-brand-500/50 transition-colors cursor-pointer disabled:opacity-50"
        >
          <IconUpload className="mx-auto mb-2 text-[var(--text-tertiary)]" />
          <p className="text-sm text-[var(--text-tertiary)]">
            {uploading ? 'Uploading...' : 'Click to upload a document'}
          </p>
          <p className="text-xs text-[var(--text-tertiary)] mt-1">TXT, Markdown, and PDF files are supported</p>
        </button>
      </div>

      {error && <p className="text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 rounded-lg px-3 py-2">{error}</p>}

      <div>
        <div className="relative">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
            placeholder="Search the knowledge base..."
            disabled={selectedKbId == null}
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-colors disabled:opacity-50"
          />
        </div>

        {querying && (
          <div className="mt-2 text-xs text-[var(--text-tertiary)] flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
            Searching...
          </div>
        )}

        {queryResult && (
          <div className="mt-2 p-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase">Query results</span>
              <button onClick={() => setQueryResult(null)} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
                <IconX />
              </button>
            </div>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">{queryResult.answer}</p>
            <QuerySources result={queryResult} />
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
            Documents
          </span>
          <button
            onClick={() => loadDocs()}
            disabled={selectedKbId == null}
            className="p-1 rounded text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors disabled:opacity-50"
          >
            <IconRefresh />
          </button>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 rounded-lg bg-[var(--bg-tertiary)] animate-pulse" />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-sm text-[var(--text-tertiary)]">No documents yet</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-1">Upload a document to this knowledge base</p>
          </div>
        ) : (
          <div className="space-y-1">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-[var(--bg-tertiary)] transition-colors group">
                <div className="w-8 h-8 rounded-lg bg-[var(--bg-tertiary)] flex items-center justify-center shrink-0">
                  <IconFile className="text-[var(--text-tertiary)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[var(--text-primary)] truncate">{doc.filename}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {statusLabels[doc.status] || doc.status}
                    {doc.status === 'ready' && ` · ${doc.chunks_count} chunks`}
                  </p>
                  {doc.status === 'failed' && doc.error_message && (
                    <p className="text-xs text-[var(--color-error)] truncate" title={doc.error_message}>
                      {doc.error_message}
                    </p>
                  )}
                </div>
                <span className={`w-2 h-2 rounded-full shrink-0 ${statusColors[doc.status] || statusColors.queued}`} />
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="shrink-0 p-1 rounded text-[var(--text-tertiary)] opacity-0 group-hover:opacity-100 hover:text-[var(--color-error)] transition-all"
                >
                  <IconTrash />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
