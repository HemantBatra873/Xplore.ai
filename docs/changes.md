# Change Log

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

Phase 3+ features (agents, knowledge redesign, conversations, integrations) remain out of scope.
