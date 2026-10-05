# Xplore.ai Development Guide

## Scope

Preserve the current modular FastAPI and React architecture during Phase 1. Do not implement workspaces, agents, a new RAG architecture, or external integrations as part of identity cleanup.

## Backend Conventions

- Keep routers focused on HTTP concerns and validation.
- Put business logic in `app/services`.
- Keep SQLAlchemy models in `app/models` and Pydantic contracts in `app/schemas`.
- Use dependency injection for database sessions and authentication.
- Add Alembic migrations for model changes.
- Use the project logger for operational events.
- Keep expensive document work in Celery tasks.

## Frontend Conventions

- Use strict TypeScript and existing React patterns.
- Keep API calls in `frontend/src/services`.
- Preserve mock mode and existing route behavior.
- Keep product-facing text in English and use the `en-US` locale.

## Validation

Backend changes should be checked with `python -m pytest -q`. Frontend changes should be checked with `npm run build` and `npm run lint` from `frontend/`.

## Documentation

Update `docs/changes.md` for substantive changes and keep the README and architecture guide aligned with runtime behavior. Record phase boundaries and migration decisions in `MIGRATION_CONTEXT.md`.
