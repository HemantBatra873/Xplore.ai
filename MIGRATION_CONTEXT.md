# Xplore.ai Migration Context

## Phase status

| Phase | Name | Status |
|-------|------|--------|
| 1 | Identity & Foundation | Complete |
| 2 | Workspace Architecture | Complete |
| 3 | Knowledge & RAG | Complete |
| 4 | Conversations & Unified AI | Complete |
| 5 | Agents & Tools | Complete |
| 6 | MCP & External Integrations | Complete |
| 7 | Final Hardening, Validation & Release Readiness | Complete |

Historical phase notes for Phases 1–6 remain in git history. This document is the **final** migration handoff.

---

## Phase 7 — Final hardening

### Objective

Remove environment blockers, validate migrations and the full test suite, harden security/error paths, clean branding/docs, and leave Xplore.ai portfolio-ready — without adding major new product features.

### Issues resolved in Phase 7

**Environment**

- Installed Python 3.12.10 and created project `.venv`
- Started Docker Desktop; Postgres (`pgvector/pg15`) + Redis healthy
- Remapped Compose Postgres host port to `5433` to avoid clashing with a local Windows Postgres on `5432`
- Updated `.env.example` / README accordingly

**Code / tests**

- Fixed `ToolRegistry` misuse of `MCPService.list_handlers()` (dict keyed by name)
- Removed startup `Base.metadata.create_all()` (schema owned by Alembic)
- User delete now clears workspace memberships / nulls `created_by_id` safely
- Migration `c4d9e6f7a8b9`: `workspaces.created_by_id` nullable + `ON DELETE SET NULL`
- Updated chat advanced tests to mock `AIOrchestrator` (compat `/chat` path)
- Fixed root health test for SPA HTML responses
- Expanded RAG test user ID range / on-demand user creation
- Hardened `tests/conftest.py` against destroying Alembic state on shared Postgres DBs
- Added `pytest-asyncio`; CI/Python target moved to 3.12
- Frontend ESLint: intentional mount-fetch patterns allowed; empty `catch` blocks fixed; lint PASS
- Dockerfile base image switched from Huawei mirror to `python:3.12-slim`
- Rewrote README for the actual Xplore.ai product

### Final architecture

```text
                              Xplore.ai
                                   │
                              Workspace
                                   │
             ┌─────────────────────┼─────────────────────┐
             │                     │                     │
         Knowledge             Conversations           Agents
             │                     │                     │
       Documents/Chunks        Messages          Model/System Prompt
             │                     │                     │
             └──────────────┬──────┴─────────────────────┘
                            │
                     AIOrchestrator
                            │
             ┌──────────────┼──────────────┐
             │              │              │
        Retrieval       ToolRegistry    LLM Providers
             │              │              │
        pgvector     Internal / MCP / GitHub
        Keyword              │
        Reranking     External Services
```

There is **one** AI execution path: Conversation → Agent → `AIOrchestrator` → retrieval / `ToolRegistry` / providers. `/api/v1/chat` remains a thin compatibility wrapper.

### Final database schema overview

Alembic head: `c4d9e6f7a8b9`

Chain (Phases 2–7):

```text
… → d8e4f1a2b3c4 (workspaces)
  → e9f5a2b3c4d5 (knowledge bases)
  → f1a6b3c4d5e6 (conversations)
  → a2b7c4d5e6f7 (agents)
  → b3c8d5e6f7a8 (integrations)
  → c4d9e6f7a8b9 (nullable workspace created_by)
```

Core tables: `users`, `workspaces`, `workspace_memberships`, `knowledge_bases`, `documents`, `document_chunks`, `conversations`, `messages`, `message_citations`, `agents`, `agent_knowledge_bases`, `integrations`, `integration_tools`, `tasks`, `llm_call_logs`.

### Final API overview

| Area | Prefix |
|------|--------|
| Auth / users | `/api/v1/auth`, `/api/v1/users` |
| Workspaces | `/api/v1/workspaces` |
| Knowledge | `/api/v1/knowledge-bases` |
| Conversations | `/api/v1/conversations` |
| Chat (compat) | `/api/v1/chat` |
| Agents / tools | `/api/v1/agents` |
| Integrations | `/api/v1/integrations` |
| Tasks / RAG / worker | `/api/v1/tasks`, `/api/v1/rag`, `/api/v1/worker` |
| Health / observability | `/api/v1/health`, `/api/v1/observability` |

### Security model

- JWT auth; inactive users rejected
- Workspace membership + role ranks (`workspace_permissions.py`)
- Resources scoped by `workspace_id` / membership checks (IDOR-resistant lookups)
- Provider and integration credentials encrypted (Fernet); never returned in API bodies
- External tools: SSRF guards, fixed GitHub host, reject destination args, untrusted result wrappers
- Tool allowlists, schema validation, max tool rounds

### Tool & integration architecture

- Internal tools: in-process `MCPService` via `ToolRegistry`
- External: `IntegrationAdapter` → MCP HTTP JSON-RPC or GitHub read-only
- Registry names: `ext:{integration_id}:{remote_name}`
- Discovery cached in `integration_tools`; refresh replaces stale cache

### Deployment model

- Docker Compose: `api`, `db` (pgvector), `redis`, `celery_worker` (+ optional Ollama/monitor profiles)
- Host Postgres published on **5433**; in-network `db:5432`
- Migrations: `alembic upgrade head` (Compose API command / local venv)
- Frontend production assets baked into API image / `frontend/dist`

### Validation results (Phase 7)

| Check | Result | Notes |
|-------|--------|-------|
| Python environment | PASS | 3.12.10 + `.venv` |
| Docker environment | PASS | Desktop engine running; db/redis healthy |
| Alembic history / heads | PASS | Head `c4d9e6f7a8b9` |
| Alembic upgrade head | PASS | Clean DB through full chain |
| Alembic downgrade -1 / upgrade | PASS | Phase 7 migration reversible |
| Backend tests (SQLite) | PASS | 179 passed |
| Backend tests (Postgres `xplore_test`) | PASS | 179 passed |
| `ruff check` | PASS | |
| Frontend lint | PASS | 0 errors |
| Frontend build | PASS | |
| Auth / workspace / agent / conversation smoke | PASS | Live uvicorn + Docker Postgres/Redis |
| Integrations types endpoint | PASS | `github`, `mcp` |
| Secrets audit | PASS | `.env` gitignored; no real secrets committed |
| Documentation | PASS | README + this file |

### Known limitations

- MCP transport is HTTP JSON-RPC subset (not full SDK / stdio / SSE)
- GitHub integration is read-only (PAT; no OAuth)
- Streaming + tools: tool rounds complete non-stream, then final text streams
- Embeddings require a reachable embedding provider for real document indexing
- Host machines with Postgres already on 5432 must use Compose port 5433
- Full Docker image rebuild of `api` was not required for validation (host uvicorn + Compose db/redis)

### Future improvements (do not start here)

1. Official MCP client SDK + additional transports behind adapters
2. OAuth / token refresh for SaaS connectors
3. Approval gates for write/destructive tools
4. Deeper external-tool observability
5. Avoid multi-agent orchestration / marketplaces / automation platforms unless product direction changes

**Migration complete. Do not begin a Phase 8 product expansion from this handoff.**
