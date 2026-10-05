# Xplore.ai Migration Context

## Phase 1 status: PASS WITH FIXES

Phase 1 identity cleanup is complete. Summary: Xplore.ai branding, English product surface, `xplore_token` / `xplore_user`, `xplore_db`.

---

## Phase 2 status: PASS WITH FIXES

Workspace & Membership foundation. Tenancy key is `workspace_id` via `get_workspace_access` / `X-Workspace-Id`. Migration `d8e4f1a2b3c4`.

---

## Phase 3 status: PASS WITH FIXES

Workspace-scoped Knowledge Bases, documents/chunks, hybrid retrieval + optional rerank, citation metadata. Migration `e9f5a2b3c4d5`. Retrieval entry point: `RAGService.retrieve_with_citations(...)`.

---

## Phase 4 status: PASS WITH FIXES

Phase 4 adds **persistent Conversations**, unified AI orchestration (optional knowledge retrieval + LLM), provider abstractions for chat and embeddings, and a conversation-first frontend. Agents, Tools, MCP, and external integrations were **not** implemented.

### Architecture

**Conversation model** (`app/models/conversation.py`)

- `id`, `workspace_id`, `created_by_id`, `title`, `use_knowledge`, `knowledge_base_ids` (comma-separated), timestamps
- Workspace-scoped; cascade delete with workspace

**Message model**

- `id`, `conversation_id`, `role` (`user` / `assistant` / `system`), `content`, `status` (`complete` / `failed`), `error_message`, `created_at`
- Ordered by `created_at`; cascade delete with conversation

**Citation model** (`MessageCitation`)

- Attached to assistant messages: `chunk_id`, `document_id`, `knowledge_base_id`, `knowledge_base_name`, `filename`, `chunk_index`, `excerpt`, `score`
- Unique `(message_id, chunk_id)`; FKs SET NULL on source delete so history remains readable

**AI orchestration flow** (`app/services/ai_orchestrator.py`)

```text
Conversation
  → persist user Message
  → optional Knowledge retrieval (use_knowledge + KB ids)
       → RAGService.retrieve_with_citations (workspace-scoped)
  → LLMProvider.complete / .stream
  → persist assistant Message + MessageCitation (only on success)
```

- Knowledge is **opt-in** per conversation/request (not automatic workspace-wide search)
- Empty `knowledge_base_ids` with `use_knowledge=true` ⇒ all KBs in the workspace
- Failed/aborted LLM calls do **not** persist assistant messages

**Provider abstraction** (`app/services/providers/`)

- `LLMProvider` protocol: `complete`, `stream`
- `OpenAICompatibleProvider` implements OpenAI SDK against provider base URLs
- `MockLLMProvider` for offline / empty API key
- Factory: `get_llm_provider(user)` with per-user BYOK + global settings

**Embedding abstraction**

- `EmbeddingProvider` / `get_embedding_provider()` separate from chat providers
- `RAGService.get_embeddings` delegates to embedding provider (pipeline otherwise unchanged)

### Database

**Migration**

- `alembic/versions/f1a6b3c4d5e6_add_conversations_messages_citations.py`
- `down_revision`: `e9f5a2b3c4d5`

**Schema**

- Tables: `conversations`, `messages`, `message_citations`
- Indexes on workspace/conversation FKs, roles, statuses, composite `(workspace_id, updated_at)`, `(conversation_id, created_at)`

**Data migration**

- No backfill (new feature). Redis `rag_session:*` remains for legacy RAG `session_id` callers; primary chat history is DB conversations.

**Migration execution**

- **BLOCKED** in this environment (no usable host Python; Docker Desktop engine down)

### API

**New** (`/api/v1/conversations`)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/` | List workspace conversations |
| POST | `/` | Create |
| GET | `/{id}` | Detail + messages + citations |
| PATCH | `/{id}` | Title / knowledge settings |
| DELETE | `/{id}` | Delete conversation |
| GET | `/{id}/messages` | List messages |
| POST | `/{id}/messages` | Send (non-stream) |
| POST | `/{id}/messages/stream` | SSE stream |

Permissions: `conversations:read|write` (member+). Retrieval also requires `knowledge:read` when enabled.

**Changed / compatibility**

- `POST /api/v1/chat/` → thin wrapper: creates a conversation and runs the same orchestrator (no separate AI stack)
- RAG/Knowledge query endpoints unchanged for document-centric workflows
- `get_llm_client()` retained as compatibility shim over `get_llm_provider()`

### Frontend

- Conversation list sidebar (create / open / delete)
- Persistent message history from API
- Streaming via `/conversations/{id}/messages/stream`
- “Use knowledge” toggle + KB multi-select (empty = all KBs)
- Citation display under assistant messages
- Settings provider list: OpenAI, Anthropic, Gemini, DeepSeek, Ollama, OpenAI-compatible
- Mock handlers for conversations API

### Providers

| Provider | Status | Config | Model selection |
|----------|--------|--------|-----------------|
| OpenAI | Implemented (OpenAI-compatible client) | `LLM_API_KEY`, default `api.openai.com/v1` | `gpt-4o-mini` default or `LLM_MODEL_NAME` / user override |
| Anthropic | Implemented via OpenAI-compatible endpoint defaults | API key + `api.anthropic.com/v1` | `claude-3-5-sonnet-latest` default |
| Gemini | Implemented via Google OpenAI-compat URL | API key + generativelanguage OpenAI path | `gemini-2.0-flash` default |
| DeepSeek | Implemented | Existing defaults | `deepseek-chat` default |
| Ollama | Implemented | Local base URL; key optional (`ollama`) | `llama3.2` default |
| OpenAI-compatible | Implemented | Custom `LLM_BASE_URL` | User/global model name |
| Mock | Implemented | `LLM_MOCK=true` or empty `LLM_API_KEY` | `mock-model` |

Credentials: encrypted at rest for BYOK; never returned by `/users/me`.

### Security

| Check | Validation |
|-------|------------|
| Cross-user / cross-workspace conversation access | Authored tests; lookups filter `workspace_id` |
| Messages via foreign conversation ID | Same workspace-scoped get → 404 |
| Knowledge retrieval workspace boundary | Reuses Phase 3 `retrieve_with_citations` filters |
| Foreign KB selection | `ConversationService._validate_knowledge_bases` → 404 |
| Credentials not exposed | `/users/me` omits keys; authored test |
| Failed stream leaves no assistant message | Orchestrator only persists assistant after successful stream; authored tests |

Backend pytest **not executed** live (environment blocked).

### Validation

| Command / check | Result | Notes |
|-----------------|--------|-------|
| Architecture inspection | PASS | Chat/RAG/LLM/frontend surveyed before coding |
| Alembic `f1a6b3c4d5e6` authored | PASS | Chain `e9f5a2b3c4d5` → `f1a6b3c4d5e6` |
| `alembic upgrade head` | BLOCKED | No usable Python; Docker engine down |
| `python -m pytest -q` | BLOCKED | Microsoft Store Python stub only |
| Conversation / provider tests authored | PASS (authored) | `tests/test_conversations.py`, `tests/test_providers.py` |
| `npm run build` (frontend) | PASS | `tsc -b && vite build` succeeded |
| Docker Compose / live migration | BLOCKED | Docker Desktop Linux engine not running |

### Known issues

- Backend tests and Alembic upgrade not run in this session
- Anthropic/Gemini go through OpenAI-compatible HTTP surfaces; native SDKs not required
- Legacy Redis RAG `session_id` still present for `/rag` and `/knowledge-bases` query helpers
- Chat non-stream no longer runs MCP tool-calling path (unified orchestrator; tools deferred to Phase 5)
- Frontend eslint debt remains (pre-existing)
- `Base.metadata.create_all()` still runs at API startup alongside Alembic

### Files (Phase 4)

**Added**

- `app/models/conversation.py`
- `app/schemas/conversation.py`
- `app/services/conversation_service.py`
- `app/services/ai_orchestrator.py`
- `app/services/providers/*`
- `app/api/routers/conversations.py`
- `alembic/versions/f1a6b3c4d5e6_add_conversations_messages_citations.py`
- `tests/test_conversations.py`, `tests/test_providers.py`
- `frontend/src/services/conversationService.ts`
- `frontend/src/components/chat/ConversationList.tsx`

**Modified (important)**

- `app/main.py`, `app/models/__init__.py`, `app/services/workspace_permissions.py`
- `app/services/llm_service.py`, `app/services/rag_service.py`, `app/api/routers/chat.py`
- Frontend: `useChat.ts`, `ChatArea.tsx`, `MessageList.tsx`, `types/index.ts`, `SettingsPage.tsx`, `mock/data.ts`
- Docs: `docs/changes.md`, `.env.example`, this file

### Phase 5 handoff

Phase 5 (Agents & Tools) should plug into the **existing orchestrator**, not replace Conversations:

1. **Hook point**: extend `AIOrchestrator` (or a sibling AgentOrchestrator) after user message persistence and before/around `LLMProvider.complete/stream`
2. **Tools**: register tool definitions on the provider call; persist tool-call metadata on `Message` (new columns/table) without breaking citations
3. **Agents**: store agent config as workspace-scoped resources with `workspace_id`; conversations may reference an optional `agent_id`
4. **Permissions**: add `agents:read|manage`, `tools:use` to `PERMISSIONS` — do not hardcode roles in routers
5. **Providers stay isolated**: Agents must call `get_llm_provider(user)`, never provider-specific SDKs from agent code
6. **Knowledge**: Agents that need RAG should call `retrieve_with_citations` with the conversation’s workspace/KB selection — do not rebuild retrieval
7. **Streaming**: keep SSE contract (`content`, `sources`, `assistant_message_id`, `[DONE]`); add optional `tool_calls` events without breaking the chat UI
8. **Out of Phase 4 scope**: configurable Agents, Tool framework, MCP expansion, external integrations, autonomous loops
