export interface User {
  id: number
  username: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  has_custom_llm_key: boolean
  llm_provider: string | null
  llm_base_url: string | null
  llm_model_name: string | null
}

export interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
}

export interface Conversation {
  id: number
  workspace_id: number
  created_by_id: number
  title: string
  use_knowledge: boolean
  knowledge_base_ids: number[]
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[]
}

export interface ConversationMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  status: string
  error_message?: string | null
  citations: CitationSource[]
  created_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning?: string
  tool_calls?: ToolCall[]
  citations?: CitationSource[]
  timestamp: number
  serverId?: number
}

export interface ToolCall {
  name: string
  arguments: Record<string, string>
  result?: string
}

export interface SSEChunk {
  reasoning?: string
  content?: string
  error?: string
}

export interface KnowledgeBase {
  id: number
  workspace_id: number
  name: string
  description: string | null
  created_by_id: number | null
  document_count: number
  created_at: string
  updated_at: string
}

export interface Document {
  id: number
  filename: string
  file_type: string
  status: 'queued' | 'processing' | 'ready' | 'failed'
  chunks_count: number
  workspace_id?: number | null
  knowledge_base_id?: number | null
  processing_task_id: string | null
  error_message: string | null
  created_at: string
}

export interface CitationSource {
  chunk_id: number
  document_id: number
  knowledge_base_id: number
  knowledge_base_name?: string | null
  filename: string
  chunk_index: number
  excerpt: string
  score?: number | null
}

export interface KnowledgeQueryResult {
  query: string
  answer: string
  sources: CitationSource[]
  source_chunks: string[]
}

export interface Task {
  id: number
  title: string
  description: string | null
  status: 'pending' | 'in_progress' | 'completed'
  created_at: string
  updated_at: string
}

export interface LLMStats {
  total_calls: number
  successful_calls: number
  failed_calls: number
  total_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
  daily_stats: DailyLLMStats[]
  endpoint_stats: EndpointLLMStats[]
  per_user_stats: UserLLMStats[]
}

export interface DailyLLMStats {
  date: string
  calls: number
  tokens: number
  cost_usd: number
  avg_latency_ms: number
}

export interface EndpointLLMStats {
  endpoint: string
  calls: number
  tokens: number
}

export interface UserLLMStats {
  user_id: number
  calls: number
  tokens: number
  cost_usd: number
}

export interface LLMCallLog {
  id: number
  endpoint: string
  model_name: string
  provider: string
  request_id: string | null
  prompt: string
  response: string | null
  tool_calls: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  estimated_cost_usd: number
  status: string
  error_message: string | null
  created_at: string
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  version: string
  dependencies: {
    database: { status: string; error?: string }
    redis: { status: string; error?: string }
    ollama: { status: string; error?: string; models?: string[] }
  }
}

export interface LLMConfig {
  provider?: string
  base_url?: string
  model_name?: string
  api_key?: string
}

export interface Workspace {
  id: number
  name: string
  slug: string
  created_by_id: number
  is_active: boolean
  role: string
  created_at: string
  updated_at: string
}

export interface WorkspaceCreate {
  name: string
  slug?: string
}
