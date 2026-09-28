# Xplore.ai Phase 1 Migration Context

## Scope

Phase 1 rebrands and cleans the existing FastAPI + React starter foundation. Current functionality was preserved. Workspaces, agents, new RAG architecture, integrations, and other Phase 2+ features were not implemented.

## Exact Changes

- Rebranded the runtime application, browser metadata, setup/auth screens, navigation, environment template, Docker service names, Prometheus job name, Grafana queries, CI image tag, license attribution, README, architecture docs, frontend guide, and change log to Xplore.ai.
- Changed frontend date/time formatting from `zh-CN` to `en-US`.
- Changed frontend auth storage keys from `agent_token` / `agent_user` to `xplore_token` / `xplore_user`.
- Translated frontend UI, mock data, API errors, prompts, backend OpenAPI descriptions, RAG prompts/results, tool schemas, seed records, and user-visible backend messages into English.
- Replaced starter seed content with English Xplore.ai knowledge-base and task records.
- Kept the Python import package named `app`. There is no `fastapi_starter` import package, and renaming `app` would create unnecessary runtime risk in Phase 1.
- Updated monitoring and container identities to `xplore-ai-*`.
- Removed the legacy standalone `app/static/demo.html` page and demo-only browser scripts.
- Removed old sample knowledge files, Chinese README, starter project review, resume material, deployment guide, frontend PRD, and improvement-plan documents.
- Replaced architecture/development documentation with concise English Xplore.ai versions.
- Updated RAG live/format test fixtures to use existing repository documentation instead of deleted sample files.
- Removed Orion/Aegis-style fixture lore from parser and RAG tests.

## Files Added

- `README.md` rewritten as the Xplore.ai project guide.
- `MIGRATION_CONTEXT.md`.
- `docs/CODE_WIKI.md` rewritten as the English architecture guide.
- `docs/changes.md` rewritten with the Phase 1 baseline.
- `CLAUDE.md` rewritten as the English development guide.
- `frontend/README.md` rewritten as the English frontend guide.

## Files Deleted

- `app/static/demo.html`
- `README.zh-CN.md`
- `.resume_project.md`
- `docs/PROJECT_REVIEW.md`
- `docs/DEPLOY_RAILWAY.md`
- `docs/FRONTEND_PRD.md`
- `docs/IMPROVEMENT_PLAN.md`
- `scripts/capture_screenshots.py`
- `scripts/debug_auth.py`
- `scripts/test_demo_e2e.py`
- `scripts/test_demo_interaction.py`
- `sample_knowledge.md`
- `sample_knowledge.txt`

The binary `sample_knowledge.pdf` was removed from the repository.

## Important Decisions

- API routes, database models, migrations, service boundaries, and the `app` package were preserved.
- Existing local seed behavior remains available through `scripts/seed_demo_data.py`; it still uses demo credentials for local development only.
- Third-party dependency provenance URLs in `frontend/package-lock.json` were not modified.
- No secrets or real credentials were added or changed.

## Validation

- Static VS Code diagnostics: passed for `app` and `frontend/src`.
- Legacy identity scan: passed for application-owned files when excluding this handoff; no active `FastAPI Starter`, `FastAPI AI Agent`, `fastapi-starter`, Orion, GXYY, Aegis, `zh-CN`, deleted demo-file, or deleted sample-file references remain.
- Frontend Chinese-text scan: passed for `frontend/src`.
- Backend tests: not run because Python is not installed or available on PATH in the current Windows environment.
- Frontend build: not completed. `npm.cmd` was available, but dependencies were not initially installed; `npm ci` entered a stalled package-install state and was stopped. A clean environment should run `npm ci`, `npm run build`, and `npm run lint`.
- Application startup: not verified because Python is unavailable and the Docker runtime was not started.

## Known Issues

- Internal backend comments, docstrings, and some log wording remain in Chinese because they are not product-facing. Product UI, prompts, API-visible descriptions, seed content, and test/demo text were translated.
- The handoff document intentionally mentions removed legacy names and files for migration traceability; those are not active project references.
- The existing application still calls `Base.metadata.create_all()` at startup in addition to Compose migrations. This was intentionally left unchanged because it is outside Phase 1 identity cleanup.
- Existing local demo credentials remain documented for development and must not be used in production.

## Phase 2 Notes

Start from the Xplore.ai identity and preserve the `app` package decision unless there is a coordinated package migration plan. Treat the current chat, RAG, tools, task, and user APIs as legacy contracts to evaluate before designing Workspaces or Agents. Do not assume the current `owner_id` filtering is a complete organization/tenant model.
