# Xplore.ai Architecture

Xplore.ai is a modular FastAPI monolith with a React SPA. This document records the current Phase 1 foundation. It does not define Phase 2 workspace, agent, retrieval, or integration work.

## Request Flow

```text
React SPA -> FastAPI router -> dependencies -> service layer
                                      -> PostgreSQL / Redis / Celery / LLM provider
```

`app/main.py` creates the application, configures request IDs, CORS, Prometheus metrics, exception handlers, health checks, and API routers.

## Backend Boundaries

- `app/api/routers`: HTTP transport, validation, authentication dependencies, and response formatting
- `app/services`: authentication, users, tasks, chat/LLM calls, RAG, tool dispatch, and observability
- `app/models`: SQLAlchemy persistence models
- `app/schemas`: Pydantic request and response contracts
- `app/worker`: Celery application and document processing task
- `app/core`: settings, security, and logging
- `app/utils`: parsing, encryption, rate limiting, and errors

The Python package is intentionally still named `app`; no package rename is needed for Xplore.ai.

## Main Flows

### Authentication

Users register or complete first-run setup, then receive a JWT. Protected routes resolve the user through `app/api/deps.py`. Passwords use bcrypt and user LLM keys use Fernet encryption.

### Chat and Tools

`app/services/llm_service.py` selects a global or per-user OpenAI-compatible client, supports mock mode and retries, and handles synchronous or streaming chat. `app/services/mcp_service.py` contains the current local tool registry and dispatches task, weather, status, list, and calculation tools.

### Documents and RAG

Uploads are parsed and stored as document records. Celery processes chunks and embeddings, which are stored in pgvector. Queries filter chunks by user ownership, perform cosine-distance retrieval, optionally rerank candidates, and send the selected context to the LLM.

### Observability

Prometheus records HTTP metrics. LLM calls are stored with request IDs, provider/model, token counts, latency, estimated cost, tool calls, and status. Redis provides RAG session history and sliding-window rate limiting.

## Persistence

Alembic migrations are in `alembic/versions`. Docker startup runs migrations before the API starts. Future changes to models must include a migration. Application startup currently also ensures tables exist for local compatibility; this should be reviewed before production hardening.

## Frontend

The SPA uses React Router, Context providers for authentication and theme, service modules for API calls, and a streaming chat hook. `VITE_USE_MOCK=true` enables the local mock adapter. The application routes are setup, authentication, chat, knowledge, tasks, observability, settings, and health.
