# Change Log

## Phase 6: MCP & External Integrations

- Added workspace-scoped `Integration` / `IntegrationTool` models with Alembic migration `b3c8d5e6f7a8`.
- Introduced `IntegrationAdapter` framework with MCP HTTP JSON-RPC transport and read-only GitHub adapter.
- Extended `ToolRegistry` to discover/execute `ext:{integration_id}:{tool}` tools alongside internal MCPService tools.
- Credentials encrypted with existing Fernet helpers; never returned in API responses (`has_credentials` only).
- Added `/api/v1/integrations` CRUD + connect/refresh-tools; permissions `integrations:read|manage`.
- Frontend Integrations page; Agents tool list shows integration sources; mock mode coverage.
- Added `tests/test_integrations.py`; `httpx` added to `requirements.txt`.

## Phase 5: Agents & Tools

- Added workspace-scoped `Agent` and `AgentKnowledgeBase` models with Alembic migration `a2b7c4d5e6f7`.
- Introduced `ToolRegistry` over the existing in-process MCPService (validation, allowlists, max tool rounds).
- Extended `AIOrchestrator` for agent system prompts, KB links, controlled tool calling, and `tool_calls_json` persistence.
- Conversations may optionally reference an Agent (`agent_id`, SET NULL on delete).
- Added `/api/v1/agents` CRUD + knowledge/tools configuration; permissions `agents:read|manage`, `tools:use`.
- Frontend: Agents page, chat agent selector, tool-call display via existing ToolCallCard.
- Added `tests/test_agents.py`.

## Phase 4: Conversations, Unified AI & Providers

- Added workspace-scoped `Conversation`, `Message`, and `MessageCitation` models with Alembic migration `f1a6b3c4d5e6`.
- Introduced unified `AIOrchestrator` that persists turns, optionally retrieves via `retrieve_with_citations`, and calls provider-agnostic LLMs.
- Added `/api/v1/conversations` CRUD + message/stream endpoints; `/api/v1/chat` is a thin compatibility wrapper.
- Refactored LLM access into provider factory (OpenAI, Anthropic, Gemini, DeepSeek, Ollama, OpenAI-compatible, mock) and separated `EmbeddingProvider`.
- Frontend chat now has persistent conversation list, knowledge toggle/KB selection, streaming, and citation display.
- Added `tests/test_conversations.py` and `tests/test_providers.py`.

## Phase 3: Knowledge / RAG Evolution

- Added workspace-scoped `KnowledgeBase` model, default "General" KB per workspace, and document `knowledge_base_id`.
- Alembic migration `e9f5a2b3c4d5` creates knowledge bases, backfills documents, adds HNSW + `content_tsv` GIN indexes.
- Extended RAG retrieval with optional KB filtering, PostgreSQL hybrid search (tsvector + RRF), and optional BGE reranking.
- Added `/api/v1/knowledge-bases` CRUD, document upload/query/stream endpoints with citation sources.
- Updated `/api/v1/rag` upload/query to assign default KB, optional KB filter, and return structured citations.
- Frontend Knowledge page/panel: select/create/delete knowledge bases, upload documents, show processing/failure status.
- Added `tests/test_knowledge.py` and retrieval isolation cases in `tests/test_rag_service.py`.

## Phase 2: Workspace & Identity Architecture

- Added `Workspace` and `WorkspaceMembership` models with owner/admin/member roles and centralized permission helpers.
- Added Alembic migration `d8e4f1a2b3c4` that creates workspace tables and backfills a personal workspace for every existing user, attaching tasks/documents/LLM logs.
- Scoped tasks, RAG documents, worker document ops, chat tools, and observability to the current workspace via `X-Workspace-Id` (default workspace fallback).
- Added `/api/v1/workspaces` CRUD + membership APIs.
- Hardened auth: inactive users cannot sign in; non-superusers cannot read other user profiles by ID.
- Frontend: workspace context, `xplore_workspace` persistence, navbar switcher, and `X-Workspace-Id` on API/SSE calls.
- Added `tests/test_workspaces.py` for cross-workspace isolation and membership permissions.

## Phase 1: Identity and Foundation Cleanup

- Rebranded runtime metadata, frontend metadata, navigation, Docker services, monitoring labels, and documentation to Xplore.ai.
- Preserved the existing Python import package `app` to avoid unnecessary runtime and migration risk.
- Converted authentication/setup copy and starter seed content to English.
- Removed the legacy standalone HTML demo and old sample-lore artifacts.
- Removed stale starter review, resume, deployment, frontend planning, and Chinese MVP packaging documents.
- Renamed the default database from `fastapi_db` to `xplore_db` across config, Compose, CI, Makefile, and backup scripts.
- Made frontend auth storage keys consistent as `xplore_token` / `xplore_user` across API, chat streaming, and RAG streaming clients.
- Translated remaining Chinese comments, docstrings, log messages, Makefile help text, Compose/Prometheus notes, bootstrap script output, and `.env.example` comments to English.
- Preserved current chat, task, document, RAG, background processing, authentication, mock mode, and observability behavior.
- Added `MIGRATION_CONTEXT.md` as the migration handoff record.

Phase 7+ features (automation platforms, multi-agent orchestration, broad connectors) remain out of scope until their phase.
