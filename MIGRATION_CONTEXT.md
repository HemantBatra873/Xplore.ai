# Xplore.ai Migration Context

## Phase 1 status: PASS WITH FIXES

Phase 1 identity cleanup is complete at repository root `C:\Users\HemantBatra\Desktop\Code\Personal\Xplore.ai`. See the Phase 1 section history in git for the full Phase 1 audit record. Summary: Xplore.ai branding, English product surface, `xplore_token` / `xplore_user`, `xplore_db`, and no nested `fastapi_starter` package.

---

## Phase 2 status: PASS WITH FIXES

Phase 2 implements the **Workspace & Membership foundation** only. Agents, Conversations, Knowledge Bases/Collections, integrations, and RAG redesign were not implemented.

### Architecture

**New models / entities**

- `Workspace` (`app/models/workspace.py`): `id`, `name`, `slug` (unique), `created_by_id`, `is_active`, `created_at`, `updated_at`
- `WorkspaceMembership`: `workspace_id`, `user_id`, `role`, timestamps, unique `(workspace_id, user_id)`
- `User.default_workspace_id` → preferred workspace for clients that omit `X-Workspace-Id`
- Resource tenancy columns:
  - `Task.workspace_id` (required)
  - `Document.workspace_id` (nullable for legacy orphans; set for normal use)
  - `LLMCallLog.workspace_id` (nullable)

**Relationships**

```text
User
 ├── default_workspace_id → Workspace
 ├── WorkspaceMembership* → Workspace
 └── created Workspace*
Workspace
 ├── Membership* (user + role)
 ├── Task*
 ├── Document*
 └── LLMCallLog*
```

Creator attribution (`Task.owner_id`, `Document.owner_id`, `LLMCallLog.user_id`) is preserved. **Tenancy boundary is `workspace_id`.**

**Role / permission design**

- Roles: `owner` > `admin` > `member` (rank-based in `app/services/workspace_permissions.py`)
- Permission keys: `workspace:read|update|delete`, `members:read|invite|manage|remove`, `resources:read|write`
- New permissions can be added to `PERMISSIONS` without rewriting models

**Workspace ownership strategy**

- Every new user gets a personal workspace + `owner` membership (`UserService` → `WorkspaceService.create_personal_workspace`)
- Existing users are backfilled by Alembic migration to a personal workspace named `{username}'s Workspace` with slug `user-{id}-{username}`
- Existing tasks/documents/LLM logs for a user are attached to that user's personal workspace
- Additional workspaces can be created; members can be invited with roles

### Database

**Migration file created**

- `alembic/versions/d8e4f1a2b3c4_add_workspace_foundation.py`
- `down_revision`: `b35f62ae79bf` (previous head)

**Backfill strategy**

1. Create `workspaces` + `workspace_memberships`
2. Add nullable `workspace_id` / `default_workspace_id` columns
3. For each existing user: insert personal workspace, owner membership, set `default_workspace_id`, update owned tasks/documents/logs
4. Make `tasks.workspace_id` NOT NULL

**Assumptions**

- Alembic is the schema authority; `Base.metadata.create_all()` at startup remains for local convenience but must not replace migrations
- Migration SQL uses `RETURNING` (PostgreSQL). Production/CI DB is PostgreSQL/`xplore_db`

**Migration execution in this environment**

- **BLOCKED** — no usable host Python; Docker Desktop engine not running. Migration was authored and reviewed but not applied to a live database in this session.

### API

**New endpoints** (`/api/v1/workspaces`)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/` | Create workspace (caller becomes owner) |
| GET | `/` | List caller's workspaces (+ role) |
| GET | `/{id}` | Get workspace (members only) |
| PATCH | `/{id}` | Update name/slug/active (admin/owner) |
| GET | `/{id}/members` | List members |
| POST | `/{id}/members` | Invite member (admin+) |
| PATCH | `/{id}/members/{user_id}` | Change role |
| DELETE | `/{id}/members/{user_id}` | Remove member |

**Changed endpoints**

- Tasks, RAG, Worker, Chat, Observability now resolve workspace via `get_workspace_access`
- Clients should send header **`X-Workspace-Id`**
- If omitted, the user's **default workspace** is used (compatibility)
- Login rejects inactive users (`code=1006`)
- `GET /users/{id}` restricted: non-superusers may only read themselves
- Chat/tasks/worker routes use `get_current_active_user` (inactive blocked)

**Authorization behavior**

- Centralized in `WorkspaceService.get_workspace_access` + `WorkspaceAccess.require_permission` + `workspace_permissions.py`
- Non-members receive 403 for workspace APIs and when spoofing `X-Workspace-Id`
- Resource queries filter by `workspace_id` (not only `owner_id`)

**Breaking changes**

- Soft break: clients that relied on pure user-owned isolation still work via default workspace + optional header
- Task responses now include `workspace_id`
- Document responses may include `workspace_id`
- Cross-user `GET /users/{id}` now 403 for non-superusers

### Frontend

- `WorkspaceContext` + `xplore_workspace` localStorage key
- Axios + SSE fetch attach `X-Workspace-Id`
- Navbar shows current workspace and a select to switch
- `workspaceService.ts` for list/get/create
- Mock mode covers `/workspaces/`
- Auth keys remain `xplore_token` / `xplore_user`

### Security

- Membership-gated workspace access
- IDOR mitigations: workspace-scoped tasks/docs/worker status; user profile self-or-superuser; inactive login blocked
- Spoofed `X-Workspace-Id` for a non-member workspace → 403
- Celery still processes by `document_id` after authorized enqueue (unchanged trust model for workers)

### Files

**Added**

- `app/models/workspace.py`
- `app/services/workspace_service.py`
- `app/services/workspace_permissions.py`
- `app/schemas/workspace.py`
- `app/api/routers/workspaces.py`
- `alembic/versions/d8e4f1a2b3c4_add_workspace_foundation.py`
- `tests/test_workspaces.py`
- `frontend/src/contexts/WorkspaceContext.tsx`
- `frontend/src/services/workspaceService.ts`

**Modified (important)**

- Models: `user.py`, `task.py`, `document.py`, `llm_call_log.py`, `models/__init__.py`
- Auth/deps: `app/api/deps.py`, `app/api/routers/auth.py`, `users.py`
- Resource routers: `tasks.py`, `rag.py`, `worker.py`, `chat.py`, `observability.py`
- Services: `task_service.py`, `rag_service.py`, `user_service.py`, `llm_service.py`, `mcp_service.py`, `llm_observability_service.py`
- `app/main.py`, `scripts/seed_demo_data.py`
- Tests: `test_rag.py`, `test_rag_service.py`
- Frontend: `App.tsx`, `api.ts`, `Navbar.tsx`, `types/index.ts`, `chatService.ts`, `ragService.ts`, `mock/data.ts`
- Docs: `docs/changes.md`, this file

### Validation

| Command / check | Result | Notes |
|-----------------|--------|-------|
| Architecture inspection | PASS | Models/auth/ownership surveyed before coding |
| Alembic migration authored | PASS | File present; head chain `b35f62ae79bf` → `d8e4f1a2b3c4` |
| `alembic upgrade head` | BLOCKED | No Python + Docker engine down |
| `python -m pytest -q` | BLOCKED | Host Python is Microsoft Store stub only |
| Workspace security tests added | PASS (authored) | `tests/test_workspaces.py` covers isolation, roles, inactive login, default workspace |
| Existing API tests updated for workspace | PASS (authored) | RAG service/HTTP tests updated for `workspace_id` |
| `npm run build` (frontend) | PASS | `tsc -b && vite build` succeeded after workspace UI |
| `npm run lint` | NOT RE-RUN | Previously failed on pre-existing eslint rules; not used as Phase 2 gate |
| Docker Compose / app startup | BLOCKED | Docker Desktop Linux engine not running |

### Known issues

- Backend tests and live migration were not executed in this environment
- Frontend eslint debt remains (pre-existing)
- Documents with historical `owner_id IS NULL` may still have null `workspace_id` after migration
- Worker Celery task does not re-check membership inside the worker process (trusted enqueue path)
- `Base.metadata.create_all()` still runs at API startup in addition to Alembic

### Phase 3 handoff

Phase 3 should build **on top of Workspace**, not replace it:

1. **Tenancy key**: all new Knowledge / Conversation / Agent tables must include `workspace_id` FK and use `get_workspace_access` / `require_permission`
2. **Do not reintroduce user-only ownership** as the isolation boundary; keep `owner_id`/`created_by` for audit only
3. **Header contract**: frontend already sends `X-Workspace-Id` from `xplore_workspace`; new APIs should honor the same dependency
4. **Roles**: extend `PERMISSIONS` in `workspace_permissions.py` (e.g. `agents:manage`, `knowledge:admin`) rather than hardcoding role strings in routers
5. **Migration discipline**: add Alembic revisions after `d8e4f1a2b3c4`; run `alembic upgrade head` before relying on new columns; do not depend on `create_all` for production
6. **Default workspace**: every user should already have `default_workspace_id` after Phase 2 migration/register; Phase 3 features can assume membership exists
7. **Out of Phase 2 scope (still TODO)**: Knowledge Bases/Collections redesign, Conversations/Messages, Agents, tool framework expansion, external integrations, new LLM provider architecture
