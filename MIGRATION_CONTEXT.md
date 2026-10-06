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

Phase 6 (external integrations / real MCP) should:

1. Add integration/tool backends behind `ToolRegistry` without changing Agent/Conversation APIs
2. Introduce real MCP transport as an additional ToolRegistry source, not a parallel chat path
3. Keep `AIOrchestrator` as the single orchestration entry
4. Add workspace-scoped credentials vault for integrations (never expose to frontend)
5. Extend permissions (`integrations:manage`) in `workspace_permissions.py`
6. Do not redesign Knowledge retrieval or Conversation persistence

**Out of Phase 5 scope (do not start):** GitHub/Drive/Notion, web browsing, external MCP servers, scheduled agents, multi-agent orchestration, marketplace.
