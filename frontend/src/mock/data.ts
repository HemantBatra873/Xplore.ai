import type {
  User,
  Document,
  Task,
  LLMStats,
  LLMCallLog,
  HealthStatus,
  Workspace,
  KnowledgeBase,
  CitationSource,
} from '@/types'

const NOW = new Date().toISOString()

function daysAgo(n: number): string {
  const d = new Date(Date.now() - n * 86400000)
  return d.toISOString()
}

const mockUser: User = {
  id: 1,
  username: 'DemoUser',
  email: 'demo@example.com',
  full_name: 'Demo User',
  is_active: true,
  is_superuser: false,
  has_custom_llm_key: false,
  llm_provider: null,
  llm_base_url: null,
  llm_model_name: null,
}

const mockDocuments: Document[] = [
  { id: 1, filename: 'Getting Started.md', file_type: 'md', status: 'ready', chunks_count: 5, workspace_id: 1, knowledge_base_id: 1, processing_task_id: null, error_message: null, created_at: daysAgo(2) },
  { id: 2, filename: 'Product Notes.pdf', file_type: 'pdf', status: 'ready', chunks_count: 12, workspace_id: 1, knowledge_base_id: 1, processing_task_id: null, error_message: null, created_at: daysAgo(1) },
  { id: 3, filename: 'API Reference.txt', file_type: 'txt', status: 'processing', chunks_count: 0, workspace_id: 1, knowledge_base_id: 1, processing_task_id: 'task-abc', error_message: null, created_at: NOW },
  { id: 4, filename: 'Design Notes.md', file_type: 'md', status: 'failed', chunks_count: 0, workspace_id: 1, knowledge_base_id: 1, processing_task_id: null, error_message: 'Embedding failed: dimension mismatch', created_at: daysAgo(3) },
]

const mockKnowledgeBases: KnowledgeBase[] = [
  {
    id: 1,
    workspace_id: 1,
    name: 'Product docs',
    description: 'Core product documentation',
    created_by_id: 1,
    document_count: 4,
    created_at: daysAgo(14),
    updated_at: NOW,
  },
  {
    id: 2,
    workspace_id: 1,
    name: 'Engineering',
    description: null,
    created_by_id: 1,
    document_count: 0,
    created_at: daysAgo(3),
    updated_at: NOW,
  },
]

const mockKbDocuments: Record<number, Document[]> = {
  1: [...mockDocuments],
  2: [],
}

function knowledgeBaseIdFromUrl(url: string): number {
  const parts = url.split('/').filter(Boolean)
  const idx = parts.indexOf('knowledge-bases')
  if (idx === -1 || !parts[idx + 1]) return 1
  const id = Number(parts[idx + 1])
  return Number.isFinite(id) ? id : 1
}

function syncKnowledgeBaseDocumentCounts(): void {
  for (const kb of mockKnowledgeBases) {
    kb.document_count = mockKbDocuments[kb.id]?.length ?? 0
  }
}

const mockCitationSources: CitationSource[] = [
  {
    chunk_id: 101,
    document_id: 1,
    knowledge_base_id: 1,
    knowledge_base_name: 'Product docs',
    filename: 'Getting Started.md',
    chunk_index: 0,
    excerpt: 'Xplore.ai uses FastAPI to build the API.',
    score: 0.92,
  },
  {
    chunk_id: 102,
    document_id: 2,
    knowledge_base_id: 1,
    knowledge_base_name: 'Product docs',
    filename: 'Product Notes.pdf',
    chunk_index: 3,
    excerpt: 'SQLAlchemy provides the PostgreSQL ORM layer.',
    score: 0.87,
  },
  {
    chunk_id: 103,
    document_id: 1,
    knowledge_base_id: 1,
    knowledge_base_name: 'Product docs',
    filename: 'Getting Started.md',
    chunk_index: 2,
    excerpt: 'RAG uses pgvector for vector similarity search.',
    score: 0.81,
  },
]

const mockWorkspaces: Workspace[] = [
  {
    id: 1,
    name: 'Personal',
    slug: 'personal',
    created_by_id: 1,
    is_active: true,
    role: 'owner',
    created_at: daysAgo(30),
    updated_at: NOW,
  },
  {
    id: 2,
    name: 'Team Demo',
    slug: 'team-demo',
    created_by_id: 1,
    is_active: true,
    role: 'owner',
    created_at: daysAgo(7),
    updated_at: NOW,
  },
]

const mockTasks: Task[] = [
  { id: 1, title: 'Finish the sign-in page', description: 'Implement the email and password form with validation', status: 'completed', created_at: daysAgo(5), updated_at: daysAgo(2) },
  { id: 2, title: 'Connect the SSE stream', description: 'Parse the stream with fetch and ReadableStream', status: 'in_progress', created_at: daysAgo(3), updated_at: daysAgo(1) },
  { id: 3, title: 'Build the observability view', description: 'Use Recharts to display LLM call statistics', status: 'in_progress', created_at: daysAgo(1), updated_at: NOW },
  { id: 4, title: 'Write unit tests', description: '', status: 'pending', created_at: NOW, updated_at: NOW },
]

function generateDailyStats(days: number) {
  const result = []
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000)
    result.push({
      date: d.toISOString().slice(0, 10),
      calls: Math.floor(Math.random() * 50) + 5,
      tokens: Math.floor(Math.random() * 5000) + 500,
      cost_usd: parseFloat((Math.random() * 0.05 + 0.005).toFixed(4)),
      avg_latency_ms: Math.floor(Math.random() * 3000) + 500,
    })
  }
  return result
}

const mockStats: LLMStats = {
  total_calls: 234,
  successful_calls: 228,
  failed_calls: 6,
  total_tokens: 45678,
  total_cost_usd: 0.0523,
  avg_latency_ms: 2150,
  daily_stats: generateDailyStats(7),
  endpoint_stats: [
    { endpoint: '/api/v1/chat', calls: 145, tokens: 28900 },
    { endpoint: '/api/v1/rag/query', calls: 62, tokens: 12400 },
    { endpoint: '/api/v1/rag/query/stream', calls: 27, tokens: 4378 },
  ],
  per_user_stats: [
    { user_id: 1, calls: 234, tokens: 45678, cost_usd: 0.0523 },
  ],
}

const mockCallLogs: LLMCallLog[] = Array.from({ length: 20 }).map((_, i) => ({
  id: i + 1,
  endpoint: i % 3 === 0 ? '/api/v1/chat' : '/api/v1/rag/query',
  model_name: 'gpt-4o-mini',
  provider: 'openai',
  request_id: `req_${Math.random().toString(36).slice(2, 10)}`,
  prompt: `This is mock prompt ${i + 1}, provided for frontend display.`,
  response: i % 5 === 0 ? null : `This is mock response ${i + 1}, with a representative answer.`,
  tool_calls: i === 0 ? JSON.stringify([{ id: 'call_1', type: 'function', function: { name: 'get_current_weather', arguments: '{"location":"Beijing"}' } }]) : null,
  prompt_tokens: Math.floor(Math.random() * 200) + 30,
  completion_tokens: Math.floor(Math.random() * 400) + 50,
  total_tokens: 0,
  latency_ms: Math.floor(Math.random() * 4000) + 200,
  estimated_cost_usd: parseFloat((Math.random() * 0.002).toFixed(6)),
  status: i % 5 === 0 ? 'failed' : 'success',
  error_message: i % 5 === 0 ? 'Rate limit exceeded' : null,
  created_at: new Date(Date.now() - i * 60000).toISOString(),
})).map((log) => ({ ...log, total_tokens: log.prompt_tokens + log.completion_tokens }))

const mockHealth: HealthStatus = {
  status: 'ok',
  version: '0.1.0',
  dependencies: {
    database: { status: 'up' },
    redis: { status: 'up' },
    ollama: { status: 'up', models: ['qwen2.5:7b', 'nomic-embed-text:v1.5'] },
  },
}

export interface MockEntry {
  method: string
  path: string
  handler: (data?: unknown, url?: string) => unknown
}

const MOCK_RESPONSES: MockEntry[] = [
  { method: 'POST', path: '/auth/login', handler: () => ({ access_token: 'mock-jwt-token.demo.xxx', token_type: 'bearer' }) },
  { method: 'POST', path: '/users/', handler: () => mockUser },
  { method: 'GET', path: '/users/me', handler: () => mockUser },
  { method: 'PUT', path: '/users/me/llm-config', handler: (data) => ({ ...mockUser, has_custom_llm_key: !!(data as Record<string, unknown>)?.api_key }) },
  { method: 'PUT', path: '/users/me/password', handler: () => ({ message: 'Password changed successfully' }) },
  { method: 'GET', path: '/chat/', handler: () => ({ reply: 'This is an offline mock response for frontend development.' }) },
  { method: 'GET', path: '/workspaces/', handler: () => mockWorkspaces },
  { method: 'POST', path: '/workspaces/', handler: (data) => {
    const d = data as { name: string; slug?: string }
    const workspace: Workspace = {
      id: Date.now(),
      name: d.name,
      slug: d.slug || d.name.toLowerCase().replace(/\s+/g, '-'),
      created_by_id: mockUser.id,
      is_active: true,
      role: 'owner',
      created_at: NOW,
      updated_at: NOW,
    }
    mockWorkspaces.push(workspace)
    return workspace
  }},
  { method: 'GET', path: '/workspaces/{id}', handler: () => mockWorkspaces[0] },
  { method: 'GET', path: '/tasks/', handler: () => mockTasks },
  { method: 'POST', path: '/tasks/', handler: (data) => {
    const d = data as { title: string; description?: string }
    const task: Task = { id: Date.now(), title: d.title, description: d.description || null, status: 'pending', created_at: NOW, updated_at: NOW }
    return task
  }},
  { method: 'PUT', path: '/tasks/', handler: (data) => data },
  { method: 'DELETE', path: '/tasks/', handler: () => ({ message: 'Deleted' }) },
  { method: 'GET', path: '/rag/documents', handler: () => mockDocuments },
  { method: 'POST', path: '/rag/upload', handler: () => ({ ...mockDocuments[0], id: Date.now(), filename: 'New Document.md', status: 'queued', chunks_count: 0 }) },
  { method: 'DELETE', path: '/rag/documents/{docId}', handler: () => ({ message: 'Document deleted' }) },
  { method: 'POST', path: '/rag/query', handler: () => ({
    query: 'mock query',
    answer: 'This is an offline mock answer. In production, the backend retrieves relevant chunks with pgvector and asks the LLM to answer.',
    sources: mockCitationSources,
    source_chunks: mockCitationSources.map((s) => s.excerpt),
  })},
  { method: 'GET', path: '/knowledge-bases/', handler: () => mockKnowledgeBases },
  { method: 'POST', path: '/knowledge-bases/', handler: (data) => {
    const d = data as { name: string; description?: string | null }
    const kb: KnowledgeBase = {
      id: Date.now(),
      workspace_id: 1,
      name: d.name,
      description: d.description ?? null,
      created_by_id: mockUser.id,
      document_count: 0,
      created_at: NOW,
      updated_at: NOW,
    }
    mockKnowledgeBases.push(kb)
    mockKbDocuments[kb.id] = []
    return kb
  }},
  { method: 'PATCH', path: '/knowledge-bases/{id}', handler: (data, url) => {
    const id = knowledgeBaseIdFromUrl(url || '')
    const kb = mockKnowledgeBases.find((k) => k.id === id)
    if (!kb) return { detail: 'Not found' }
    const d = data as { name?: string; description?: string | null }
    if (d.name !== undefined) kb.name = d.name
    if (d.description !== undefined) kb.description = d.description
    kb.updated_at = NOW
    return kb
  }},
  { method: 'DELETE', path: '/knowledge-bases/{id}', handler: (_data, url) => {
    const id = knowledgeBaseIdFromUrl(url || '')
    const idx = mockKnowledgeBases.findIndex((k) => k.id === id)
    if (idx !== -1) mockKnowledgeBases.splice(idx, 1)
    delete mockKbDocuments[id]
    return { message: 'Deleted' }
  }},
  { method: 'GET', path: '/knowledge-bases/{id}/documents', handler: (_data, url) => {
    const id = knowledgeBaseIdFromUrl(url || '')
    return mockKbDocuments[id] ?? []
  }},
  { method: 'POST', path: '/knowledge-bases/{id}/documents/upload', handler: (_data, url) => {
    const kbId = knowledgeBaseIdFromUrl(url || '')
    const doc: Document = {
      id: Date.now(),
      filename: 'New Document.md',
      file_type: 'md',
      status: 'queued',
      chunks_count: 0,
      workspace_id: 1,
      knowledge_base_id: kbId,
      processing_task_id: null,
      error_message: null,
      created_at: NOW,
    }
    if (!mockKbDocuments[kbId]) mockKbDocuments[kbId] = []
    mockKbDocuments[kbId].push(doc)
    syncKnowledgeBaseDocumentCounts()
    return doc
  }},
  { method: 'DELETE', path: '/knowledge-bases/{id}/documents/{docId}', handler: (_data, url) => {
    const kbId = knowledgeBaseIdFromUrl(url || '')
    const parts = (url || '').split('/').filter(Boolean)
    const docId = Number(parts[parts.length - 1])
    const docs = mockKbDocuments[kbId]
    if (docs) {
      const idx = docs.findIndex((d) => d.id === docId)
      if (idx !== -1) docs.splice(idx, 1)
    }
    syncKnowledgeBaseDocumentCounts()
    return { message: 'Document deleted' }
  }},
  { method: 'POST', path: '/knowledge-bases/{id}/query', handler: (data) => {
    const d = data as { query: string }
    return {
      query: d.query,
      answer: 'This is an offline mock answer. In production, the backend retrieves relevant chunks with pgvector and asks the LLM to answer.',
      sources: mockCitationSources,
      source_chunks: mockCitationSources.map((s) => s.excerpt),
    }
  }},
  { method: 'GET', path: '/observability/llm-stats', handler: () => mockStats },
  { method: 'GET', path: '/observability/llm-calls', handler: () => mockCallLogs },
  { method: 'GET', path: '/health', handler: () => mockHealth },
]

function matchPath(pattern: string, actual: string): boolean {
  const patternParts = pattern.split('/')
  const actualParts = actual.split('/')
  if (patternParts.length !== actualParts.length) return false
  return patternParts.every((part, i) => part.startsWith('{') || part === actualParts[i])
}

export function getMockResponse(method: string, url: string, data?: unknown): { data: unknown } | null {
  for (const entry of MOCK_RESPONSES) {
    if (entry.method === method && matchPath(entry.path, url)) {
      return { data: entry.handler(data, url) }
    }
  }
  return null
}
