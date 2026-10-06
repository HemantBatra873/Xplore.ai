# Xplore.ai

Xplore.ai is an AI knowledge workspace: multi-tenant workspaces, knowledge bases with hybrid RAG, persistent conversations, configurable agents, controlled tools, and MCP/external integrations — with a single AI execution path through `AIOrchestrator`.

## What it is

- **Workspaces** with owner/admin/member roles and scoped authorization
- **Knowledge bases** with document ingestion, pgvector retrieval, hybrid search, optional reranking, and citations
- **Conversations** with persisted messages, streaming, and knowledge grounding
- **Agents** that bind system prompts, models, knowledge bases, and tools
- **ToolRegistry** for internal tools, MCP HTTP tools, and integrations (e.g. read-only GitHub)
- **Multiple LLM providers** (OpenAI, Anthropic, Gemini, DeepSeek, Ollama, OpenAI-compatible) plus explicit mock mode

## Architecture

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
        pgvector       Internal / MCP / GitHub
        Keyword
        Reranking
```

The Python import package remains `app` by design (renaming would add unnecessary migration risk).

## Tech stack

| Layer | Technologies |
|-------|----------------|
| API | FastAPI, SQLAlchemy 2, Alembic, Pydantic, Celery |
| Data | PostgreSQL + pgvector, Redis |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Observability | Prometheus, Grafana, Flower, structured logs / request IDs |
| Runtime | Docker Compose, Python 3.12 |

## Prerequisites

- Docker Compose v2 (recommended for full stack)
- Or locally: Python 3.12+, Node.js 20+, PostgreSQL 15 with pgvector, Redis 7

## Local development (Docker)

```bash
cp .env.example .env
# Set a strong SECRET_KEY (required). Leave LLM_API_KEY empty to use LLM mock mode.
docker compose up -d --build
```

App: <http://localhost:8000> · API docs: <http://localhost:8000/docs>

```bash
docker compose --profile full up -d     # + Ollama
docker compose --profile monitor up -d  # + Prometheus / Grafana / Flower
make seed                               # demo@example.com / demo123456 (local only)
```

## Local development (host Python + frontend)

```bash
# Infrastructure (Postgres published on localhost:5433 to avoid host Postgres conflicts)
docker compose up -d db redis

# Backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
# DATABASE_URL should use localhost:5433 (see .env.example)
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm ci
npm run dev
```

Set `VITE_USE_MOCK=true` for offline UI development against mock handlers. Production frontend builds are served from the API image (`npm run build` → `app/static`).

## Configuration

See `.env.example`. Important variables:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT + Fernet encryption key material (must not use the default in production) |
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://...`) |
| `REDIS_URL` | Redis for rate limits / Celery / caches |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL_NAME` | Chat provider |
| `LLM_MOCK` | Explicit canned LLM responses; also auto-enabled when `LLM_API_KEY` is empty |
| `EMBEDDING_*` | Embedding endpoint/model/dimension (independent of chat) |

Provider API keys and integration credentials are stored encrypted server-side and are never returned by normal API responses. Users may also configure BYOK keys in Settings.

## Testing

```bash
# Backend (from repo root, with venv active)
pytest
# or: python -m pytest -q

# Frontend
cd frontend
npm ci
npm run lint
npm run build
```

CI runs ruff + pytest against PostgreSQL/Redis service containers (see `.github/workflows/ci.yml`).

## Project structure

```text
app/                 FastAPI routers, services, models, schemas, workers
alembic/             Database migrations (workspace → knowledge → conversations → agents → integrations)
frontend/            React SPA
tests/               Backend test suite
scripts/             Bootstrap, seed, E2E helpers
grafana/             Dashboards and provisioning
docs/                Architecture notes and change log
MIGRATION_CONTEXT.md Migration phase handoff record
```

## Current limitations

- MCP transport is HTTP JSON-RPC only (not full MCP SDK / stdio / SSE)
- GitHub integration is read-only (token/PAT; no OAuth platform)
- Streaming + tools: tool rounds complete non-stream, then the final answer is streamed
- Document embeddings typically require a reachable embedding provider (e.g. Ollama)

## Documentation

- [Architecture guide](docs/CODE_WIKI.md)
- [Change log](docs/changes.md)
- [Migration context](MIGRATION_CONTEXT.md)
