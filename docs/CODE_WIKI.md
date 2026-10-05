# Xplore.ai Architecture

Xplore.ai is a modular FastAPI monolith with a React SPA. This document records the Phase 1 identity foundation plus the Phase 2 workspace tenancy layer. It does not define Phase 3 agents, knowledge redesign, or integrations.

## Request Flow

```text
React SPA -> FastAPI router -> auth + workspace deps -> service layer
                                      -> PostgreSQL / Redis / Celery / LLM provider
```

`app/main.py` creates the application, configures request IDs, CORS, Prometheus metrics, exception handlers, health checks, and API routers.

## Tenancy (Phase 2)

Resources belong to a **Workspace**. Users join workspaces through **WorkspaceMembership** with roles `owner`, `admin`, or `member`. Clients send `X-Workspace-Id`; when omitted, the user's `default_workspace_id` is used. Authorization is centralized in `app/api/deps.py` (`get_workspace_access`) and `app/services/workspace_permissions.py`.

## Backend Boundaries

- `app/api/routers`: HTTP transport, validation, authentication/workspace dependencies, and response formatting
- `app/services`: authentication, users, workspaces, tasks, chat/LLM calls, RAG, tool dispatch, and observability
- `app/models`: SQLAlchemy persistence models
- `app/schemas`: Pydantic request and response contracts
- `app/worker`: Celery application and document processing task
- `app/core`: settings, security, and logging
- `app/utils`: parsing, encryption, rate limiting, and errors

The Python package is intentionally still named `app`; no package rename is needed for Xplore.ai.

## Main Flows

### Authentication

Users register or complete first-run setup, then receive a JWT. Registration also creates a personal workspace. Protected routes resolve the user through `app/api/deps.py`. Inactive users cannot log in. Passwords use bcrypt and user LLM keys use Fernet encryption.

### Chat and Tools

`app/services/llm_service.py` selects a global or per-user OpenAI-compatible client, supports mock mode and retries, and handles synchronous or streaming chat. Tools that create or list tasks are scoped to the active workspace.

### Documents and RAG

Uploads are parsed and stored as document records owned by a workspace. Celery processes chunks and embeddings, which are stored in pgvector. Queries filter chunks by `workspace_id`, perform cosine-distance retrieval, optionally rerank candidates, and send the selected context to the LLM.

### Observability

LLM call logs are stored with optional `workspace_id` and surfaced through observability endpoints for the active workspace. Prometheus records HTTP metrics. LLM calls capture request IDs, provider/model, token counts, latency, estimated cost, tool calls, and status. Redis provides RAG session history and sliding-window rate limiting.

## Persistence

Alembic migrations are in `alembic/versions` (Phase 2 workspace foundation: `d8e4f1a2b3c4`). Docker startup runs migrations before the API starts. Future changes to models must include a migration. Application startup currently also ensures tables exist for local compatibility; this should be reviewed before production hardening.

## Frontend

The SPA uses React Router, Context providers for authentication, workspace selection, and theme, service modules for API calls, and a streaming chat hook. Authenticated API calls send `X-Workspace-Id` from `xplore_workspace`. `VITE_USE_MOCK=true` enables the local mock adapter. The application routes are setup, authentication, chat, knowledge, tasks, observability, settings, and health.
