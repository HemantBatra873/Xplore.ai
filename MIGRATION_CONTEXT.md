# Xplore.ai Migration Context

## Phase 1–3 status: PASS WITH FIXES

Identity cleanup, Workspace/Membership tenancy, and Knowledge/RAG evolution are complete. See earlier phase notes in git history for full detail. Alembic head after Phase 3: `e9f5a2b3c4d5`.

---

## Phase 4 status: PASS WITH FIXES

Persistent Conversations, unified `AIOrchestrator`, provider/embedding abstractions, citations. Migration `f1a6b3c4d5e6`.

---

## Phase 5 status: PASS WITH FIXES

Phase 5 adds workspace-scoped **Agents**, a controlled **Tool** layer over the existing in-process MCPService, and integrates both into `AIOrchestrator` without a second AI/chat stack.

### 1. Phase 5 objective

Introduce Agents as the configuration boundary (system prompt, model overrides, knowledge bases, tools) and wire controlled tool execution into the Phase 4 conversation orchestration flow.

### 2. Architecture before / after

**Before:** Conversation → optional KB retrieval → LLMProvider (no agents/tools in orchestrator).

**After:**

```text
Conversation (optional agent_id)
      ↓
Agent config (prompt, model, KBs, tools)
      ↓
AIOrchestrator
  ├── Knowledge retrieval (Phase 3 retrieve_with_citations)
  └── ToolRegistry → MCPService handlers (capped rounds)
      ↓
LLMProvider (tools when supported)
      ↓
Message + Citations + tool_calls_json
```

### 3. Files added

- `app/models/agent.py`
- `app/schemas/agent.py`
- `app/services/agent_service.py`
- `app/services/tool_registry.py`
- `app/api/routers/agents.py`
- `alembic/versions/a2b7c4d5e6f7_add_agents_and_conversation_agent_link.py`
- `tests/test_agents.py`
- `frontend/src/services/agentService.ts`
- `frontend/src/pages/AgentsPage.tsx`

### 4. Files modified (important)

- `app/services/ai_orchestrator.py` — agent + tool loop
- `app/services/providers/base.py`, `openai_compatible.py`, `mock.py` — tool message/result support
- `app/models/conversation.py` — `agent_id`, `tool_calls_json`
- `app/services/conversation_service.py`, `app/schemas/conversation.py`, `app/api/routers/conversations.py`
- `app/services/workspace_permissions.py` — `agents:*`, `tools:use`
- `app/main.py`, `app/models/__init__.py`
- Frontend: `useChat.ts`, `ChatArea.tsx`, `App.tsx`, `Sidebar.tsx`, `types/index.ts`, `mock/data.ts`, `conversationService.ts`
- `docs/changes.md`, this file

### 5. Database migration

- **Revision:** `a2b7c4d5e6f7`
- **Parent:** `f1a6b3c4d5e6`
- Tables: `agents`, `agent_knowledge_bases`
- Columns: `conversations.agent_id` (FK SET NULL), `messages.tool_calls_json`
- No data backfill required

### 6. Agent model design

- Fields: `id`, `workspace_id`, `created_by_id`, `name`, `description`, `system_prompt`, optional `provider` / `model_name`, `is_enabled`, `enabled_tools` (comma-separated names), timestamps
- Unique `(workspace_id, name)`
- Many-to-many Knowledge via `AgentKnowledgeBase`
- Conversation.agent_id optional; deleted agents null out the reference

### 7. Tool abstraction design

- `ToolRegistry` / `ToolDefinition` / `ToolExecutionContext` / `ToolResult`
- Discovers tools from `MCPService.list_tools()` / handlers
- Validates arguments (Pydantic dynamic models from JSON schema)
- Enforce agent allowlist + `tools:use` permission + workspace/user requirements
- `MAX_TOOL_CALLS_PER_REQUEST = 5`

### 8. MCPService changes

- **Not replaced.** Remains the in-process registry/executor.
- New code calls MCP only through `ToolRegistry.execute(...)`.
- No external MCP servers or transport added.

### 9. AIOrchestrator changes

- Loads optional Agent (conversation or per-request `agent_id`)
- System prompt from Agent when present
- Knowledge: request → conversation → agent KB links
- Tool loop via `provider.complete(..., tools=...)` when `supports_tools`
- Mock / non-tool providers skip tools cleanly
- Streaming: tool rounds run non-stream first, then content is emitted; citations preserved
- Persists `tool_calls_json` on assistant messages; no assistant row on failure

### 10. Conversation integration

- Optional `agent_id` on create/update/send/stream
- Existing conversations without agents unchanged
- Agent delete → `SET NULL` on conversations

### 11. API endpoints

| Method | Path |
|--------|------|
| GET | `/api/v1/agents/tools` |
| GET/POST | `/api/v1/agents/` |
| GET/PUT/PATCH/DELETE | `/api/v1/agents/{id}` |
| PUT | `/api/v1/agents/{id}/knowledge-bases` |
| PUT | `/api/v1/agents/{id}/tools` |

Conversation message APIs accept optional `agent_id`.

### 12. Frontend changes

- `/agents` management page (prompt, KBs, tools, enable/disable)
- Chat toolbar agent selector
- Tool calls rendered via existing `ToolCallCard`
- Sidebar Agents tab links to management page
- Mock handlers for agents/tools

### 13. Authorization / security

| Permission | Min role |
|------------|----------|
| `agents:read` | member |
| `agents:manage` | admin |
| `tools:use` | member |

- Cross-workspace agent/KB access blocked via workspace-scoped lookups
- Tools not on agent allowlist → 403
- Invalid tool args → 400
- Provider API keys still never returned to frontend

### 14. Tests added

- `tests/test_agents.py`: isolation, member cannot manage, foreign KB attach, conversation without agent, tool validation, allowlist, tool limit constant, tools list auth

### 15. Validation results

| Command | Result | Notes |
|---------|--------|-------|
| Architecture inspection | PASS | MCP/orchestrator/conversations reviewed first |
| Alembic `a2b7c4d5e6f7` authored | PASS | Chain `f1a6b3c4d5e6` → `a2b7c4d5e6f7` |
| `alembic upgrade head` | BLOCKED | No usable host Python; Docker engine down |
| `pytest` | BLOCKED | Same environment limitation |
| `npm run build` | PASS | Succeeded after mock/data fix |
| Static review of dual AI stacks | PASS | Chat remains thin wrapper over orchestrator |

### 16. Known issues

- Streaming tool UX runs tool rounds then chunks the final text (not native stream+tools deltas)
- Anthropic/Gemini tool calling depends on OpenAI-compatible surfaces
- Member invite test assumes workspace members API shape; not executed live
- Frontend eslint debt remains pre-existing
- `Base.metadata.create_all()` still runs at startup alongside Alembic

### 17. Environment limitations

- Host Python is Microsoft Store stub only
- Docker Desktop Linux engine not running
- Therefore Alembic upgrade and pytest were not executed

### 18. Phase 6 handoff recommendations

Completed in Phase 6 below. Historical recommendations retained for audit trail only.

---

## Phase 6 status: PASS WITH FIXES

Phase 6 extends the Phase 5 `ToolRegistry` with workspace-scoped **Integrations** (MCP HTTP + read-only GitHub) without creating a second AI execution path. `AIOrchestrator` remains the single entry point.

### 1. Phase 6 objective

Support external tools and MCP-compatible servers behind the existing Agent → AIOrchestrator → ToolRegistry architecture, with encrypted credentials, discovery, workspace isolation, and a minimal Integrations UI.

### 2. Architecture before / after

**Before:** ToolRegistry → in-process MCPService handlers only.

**After:**

```text
Conversation → Agent → AIOrchestrator
  ├── Knowledge retrieval
  └── ToolRegistry
        ├── Internal tools (MCPService)
        ├── MCP tools (MCPHttpTransport → remote server)
        └── Integration tools (e.g. GitHub adapter)
              ↓
        External services
```

### 3. Integration abstraction

- Models: `Integration`, `IntegrationTool` (`app/models/integration.py`)
- Service: `IntegrationService` (CRUD, encrypt credentials, discover, execute)
- Adapter interface: `IntegrationAdapter` (`connect`/`validate`/`discover_tools`/`execute`)
- Factory: `get_adapter(type)` for `mcp` and `github`
- Credentials stored as Fernet-encrypted JSON (`credentials_encrypted`); API exposes only `has_credentials`

### 4. MCP architecture

- `MCPHttpTransport`: JSON-RPC over HTTP (`initialize`, `tools/list`, `tools/call`)
- `MCPIntegrationAdapter` wraps transport; normalizes tools into `DiscoveredTool` / registry names `ext:{integration_id}:{remote_name}`
- In-process Phase 5 `MCPService` remains for built-in tools (not replaced)

### 5. MCP transport implementation

- Practical initial transport: **HTTP JSON-RPC** only (`config.transport = "http"`)
- SSRF guards via `assert_safe_http_url` (scheme, host allowlists optional, private/link-local blocked unless `allow_private=true`)
- No stdio/SSE transports in this phase; structure allows adding later
- Uses `httpx` (added to `requirements.txt`)

### 6. Tool discovery mechanism

- `POST /integrations/{id}/connect` and `/refresh-tools` call adapter `discover_tools`
- Results cached in `integration_tools` (refresh replaces cache to avoid stale permanent duplicates)
- Agent tool list (`GET /agents/tools`) merges internal + workspace discovered tools

### 7. ToolRegistry changes

- `list_definitions(db, workspace_id)` includes enabled integration tools
- `execute` routes `ext:*` tools to `IntegrationService.execute_tool`
- Preserves allowlists, schema validation, `MAX_TOOL_CALLS_PER_REQUEST`, workspace/user/db requirements
- Rejects LLM-supplied `url`/`endpoint`/`command`/`shell`/`executable` args on external tools
- External results prefixed as untrusted content

### 8. Initial integrations implemented

1. **MCP** (HTTP JSON-RPC client)
2. **GitHub** read-only: `search_repositories`, `get_repository`, `list_issues`, `get_issue`, `list_pull_requests` (hardcoded `api.github.com` only)

### 9. Agent integration changes

- Agents continue to store normalized tool name lists
- Validation accepts internal + workspace integration registry names
- No Agent model redesign; UI shows tool `source` / integration name

### 10. API endpoints

Workspace-scoped under `/api/v1/integrations`:

- `GET /types`, `GET /`, `POST /`, `GET /{id}`, `PUT|PATCH /{id}`, `DELETE /{id}`
- `POST /{id}/connect`, `POST /{id}/refresh-tools`, `GET /{id}/tools`

Credentials never returned on GET/list/update responses.

### 11. Database migrations

- New revision: `b3c8d5e6f7a8_add_integrations_and_discovered_tools.py`
- Revises: `a2b7c4d5e6f7`
- Tables: `integrations`, `integration_tools` with indexes/unique constraints

### 12. Security / authorization changes

- Permissions: `integrations:read` (member+), `integrations:manage` (admin+)
- Cross-workspace integration access blocked by workspace FK + service lookups
- Encrypted credential storage; write-only credentials on create/update
- SSRF / private-host rejection for MCP endpoints
- GitHub fixed host; no arbitrary URL/command execution from model args
- External content treated as untrusted in tool result wrappers

### 13. Frontend changes

- `/integrations` page: create/configure/enable, connect/refresh, list discovered tools (no credential display)
- Sidebar link; Agents page shows tool source labels
- Mock mode handlers for integrations

### 14. Tests

- `tests/test_integrations.py`: workspace isolation, credential leakage, discovery normalization, ToolRegistry execution, agent attachment, SSRF/URL rejection, cross-workspace execute denial

### 15. Validation results

| Command | Result | Notes |
|---------|--------|-------|
| Architecture inspection | PASS | Phase 5 ToolRegistry/orchestrator extended in place |
| Alembic `b3c8d5e6f7a8` authored | PASS | Chain `a2b7c4d5e6f7` → `b3c8d5e6f7a8` |
| `alembic upgrade head` | BLOCKED | No usable host Python; Docker engine down |
| `pytest` | BLOCKED | Same environment limitation |
| `npm run build` | PASS | Vite production build succeeded |
| Dual orchestration check | PASS | No second AI stack; orchestrator unchanged as entry |
| Credential / SSRF static review | PASS | Encrypted storage; URL/command arg rejection; GitHub host fixed |

### 16. Known limitations

- MCP transport is HTTP JSON-RPC subset, not full MCP SDK/stdio/SSE
- GitHub OAuth not implemented (PAT/token write-only)
- No write/destructive GitHub tools
- No approval workflow for future dangerous capabilities (boundary documented only)
- Discovery cache can go stale until explicit refresh
- `allow_private` MCP endpoints are trusted-admin opt-in (SSRF risk if misused)

### 17. Environment limitations

- Host Python is Microsoft Store stub only (`python` / `py` unavailable)
- Docker Desktop Linux engine not running
- Therefore Alembic upgrade and pytest were not executed

### 18. Explicit Phase 7 recommendations

Phase 7 should **not** expand into a general automation platform. Prefer:

1. Hardening MCP (official client SDK if available, SSE/stdio transports behind the same adapter)
2. Optional OAuth/token refresh for GitHub and future SaaS connectors
3. Approval gates for write/destructive integration tools
4. Observability for external tool latency/errors
5. Avoid multi-agent orchestration, marketplaces, scheduled autonomous loops

**Out of Phase 6 scope (do not start):** multi-agent orchestration, agent marketplace, autonomous long-running agents, workflow engines, broad enterprise connectors, Phase 7 features.
