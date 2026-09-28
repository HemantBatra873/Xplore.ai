# Xplore.ai

Xplore.ai is a full-stack AI application foundation built with FastAPI and React. Phase 1 preserves the existing chat, task, document, RAG, authentication, and observability capabilities while removing the original starter identity. Future product features are intentionally deferred.

## Stack

- FastAPI, SQLAlchemy 2, Alembic, and Pydantic
- PostgreSQL with pgvector
- Redis and Celery for sessions, rate limiting, and background document processing
- OpenAI-compatible providers or Ollama
- React, TypeScript, Vite, Tailwind CSS, and Recharts
- Prometheus, Grafana, and Flower

## Current Capabilities

- JWT authentication with user-level data isolation
- Synchronous and SSE-streaming chat
- OpenAI-compatible tool calling for tasks, weather, system status, task lists, and calculations
- TXT, Markdown, and PDF document ingestion
- Asynchronous chunking and embedding with pgvector retrieval
- Optional BGE reranking
- Redis-backed RAG session history
- Per-user encrypted LLM provider keys
- LLM call logs with token, latency, and estimated cost data
- Frontend mock mode for offline UI development

Workspaces, agents, new retrieval architecture, and external integrations are Phase 2+ concerns and are not implemented here.

## Repository Layout

```text
app/                 FastAPI application, services, models, schemas, and workers
alembic/              Database migrations
frontend/             React SPA
tests/                Backend tests
scripts/              Bootstrap, seed, E2E, evaluation, and load-test utilities
grafana/              Monitoring dashboards and provisioning
docs/                 Architecture and change documentation
```

The Python import package remains `app`. This is deliberate: changing it would create unnecessary runtime and migration risk during the identity cleanup.

## Quick Start

Prerequisites: Docker Compose v2 and, optionally, Ollama for local models.

```bash
cp .env.example .env
# Set a strong SECRET_KEY. Leave LLM_API_KEY empty for mock mode.
docker compose up -d --build
```

The application is available at <http://localhost:8000>. API documentation is at <http://localhost:8000/docs>.

Optional services:

```bash
docker compose --profile full up -d
# Adds Ollama

docker compose --profile monitor up -d
# Adds Prometheus, Grafana, and Flower
```

Useful commands:

```bash
make setup         # Initialize environment and start the stack
make up            # Start core services
make up-full       # Start all services
make test          # Run backend tests
make seed          # Create the local starter account and sample records
make logs          # Follow API logs
make down          # Stop services
```

The seed command creates `demo@example.com` with password `demo123456` for local development only. Do not use these credentials outside a local environment.

## Frontend Development

```bash
cd frontend
npm install
npm run dev
```

The Vite development server uses the API at `/api/v1`. Set `VITE_USE_MOCK=true` for offline UI development. Production builds are generated with `npm run build` and are included in the Docker image.

## Validation

```bash
python -m pytest -q
cd frontend
npm run build
npm run lint
```

## Documentation

- [Architecture guide](docs/CODE_WIKI.md)
- [Change log](docs/changes.md)
- [Frontend guide](frontend/README.md)
- [Contribution guide](CONTRIBUTING.md)
- [Phase 1 migration context](MIGRATION_CONTEXT.md)

## License

This project is licensed under the [MIT License](LICENSE).
