# Xplore.ai Migration Context

## Phase 1 status: PASS WITH FIXES

Phase 1 identity cleanup is complete at repository root `C:\Users\HemantBatra\Desktop\Code\Personal\Xplore.ai`. Summary: Xplore.ai branding, English product surface, `xplore_token` / `xplore_user`, `xplore_db`, and no nested `fastapi_starter` package.

---

## Phase 2 status: PASS WITH FIXES

Phase 2 implements the **Workspace & Membership foundation**. Tenancy key is `workspace_id` via `get_workspace_access` / `X-Workspace-Id` (default workspace fallback). Roles: owner > admin > member. Migration `d8e4f1a2b3c4`. See Phase 2 section history for full API/security detail.

---

## Phase 3 status: PASS WITH FIXES

Phase 3 evolves documents/RAG into a workspace-scoped **Knowledge** system with knowledge bases, SQL-side filtered retrieval, optional hybrid search + rerank, and citation metadata. Conversations, Agents, tools framework, and integrations were **not** implemented.

### Architecture

**KnowledgeBase design**

- Model: `app/models/knowledge_base.py` — `KnowledgeBase`
- Fields: `id`, `workspace_id` (CASCADE), `name`, `description`, `created_by_id`, `created_at`, `updated_at`
- Constraint: unique `(workspace_id, name)`
- Default KB: every workspace gets **"General"** on create (and via migration backfill)
- Permissions: `knowledge:read|write` (member+), `knowledge:admin` (admin+/delete KB)

**Document / Chunk relationships**

```text
Workspace
 └── KnowledgeBase (1..n)
      └── Document (workspace_id + knowledge_base_id)
           └── DocumentChunk (CASCADE on document delete)
```

- Documents are workspace-scoped and belong to a knowledge base (`knowledge_base_id` required after migration when backfill succeeds)
- `owner_id` retained for audit only; isolation is `workspace_id` + membership
- Statuses: `queued` → `processing` → `ready` | `failed` (`error_message` on failure)
- Deleting a document cascades chunks; deleting a KB cascades documents (workspace must keep ≥1 KB)
- Ingestion pipeline unchanged: upload → Celery `process_document_task` → chunk + embed

**Retrieval architecture**

- Entry: `RAGService.retrieve_with_citations(...)`
- Filters applied **in SQL** before ranking: `Document.workspace_id`, `Document.status == ready`, optional `knowledge_base_id`
- Vector: pgvector cosine distance (HNSW index on PostgreSQL)
- Hybrid (optional, PostgreSQL only): keyword via generated `content_tsv` + `plainto_tsquery` / `ts_rank`, fused with vector via Reciprocal Rank Fusion (`RRF_K=60`)
- SQLite / keyword failure → vector-only (logged warning)
- Config: `RAG_ENABLE_HYBRID`, `RAG_ENABLE_RERANK`, `RAG_VECTOR_CANDIDATES`, `RAG_KEYWORD_CANDIDATES`

**Reranking architecture**

- Optional stage after candidate fusion
- Uses existing BGE CrossEncoder (`sentence_transformers`) when installed and `RAG_ENABLE_RERANK` / request flag allow it
- If unavailable or disabled, RRF/vector scores are used unchanged — system still works

**Citation / source design**

- `RetrievalHit` carries chunk, document, knowledge_base, score, vector_score, keyword_score
- API `CitationSource`: `chunk_id`, `document_id`, `knowledge_base_id`, `knowledge_base_name`, `filename`, `chunk_index`, `excerpt`, scores
- Returned by `/api/v1/knowledge-bases/{id}/query` and `/api/v1/rag/query` (plus stream variants)
- No persistent Conversation citation UX yet (Phase 4)

### Database

**Migration created**

- `alembic/versions/e9f5a2b3c4d5_add_knowledge_bases_and_retrieval_indexes.py`
- `down_revision`: `d8e4f1a2b3c4`

**Schema changes**

- Table `knowledge_bases` + indexes
- Column `documents.knowledge_base_id` FK → `knowledge_bases.id` ON DELETE CASCADE
- Generated column `document_chunks.content_tsv` + GIN index
- HNSW index `ix_document_chunks_embedding_hnsw` on `embedding vector_cosine_ops`
- Index on `document_chunks.document_id` (IF NOT EXISTS)

**Data migration / backfill**

1. For each workspace: insert default KB `General`
2. Attach documents with matching `workspace_id` to that KB
3. Orphan documents: prefer owner's default-workspace KB, else first available KB; also set `workspace_id` when null
4. If no null `knowledge_base_id` remain → set column NOT NULL

**Migration execution in this environment**

- **BLOCKED** — host Python is Microsoft Store stub only; Docker Desktop Linux engine not running. Migration authored/reviewed, not applied to a live DB in this session.

### API

**New endpoints** (`/api/v1/knowledge-bases`)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/` | List KBs in current workspace |
| POST | `/` | Create KB |
| GET | `/{kb_id}` | Get KB |
| PATCH | `/{kb_id}` | Update name/description |
| DELETE | `/{kb_id}` | Delete KB (admin+; cannot delete last) |
| GET | `/{kb_id}/documents` | List documents |
| POST | `/{kb_id}/documents/upload` | Upload + enqueue processing |
| GET | `/{kb_id}/documents/{doc_id}` | Document status |
| DELETE | `/{kb_id}/documents/{doc_id}` | Delete document + chunks |
| POST | `/{kb_id}/documents/{doc_id}/reprocess` | Requeue processing |
| POST | `/{kb_id}/query` | KB-scoped RAG + citations |
| POST | `/{kb_id}/query/stream` | SSE variant |

**Changed endpoints** (`/api/v1/rag`)

- Upload assigns default workspace KB
- List/query/stream honor workspace + optional `knowledge_base_id`
- Query responses include structured `sources` (+ legacy `source_chunks`)
- Permissions use `knowledge:read|write`

**Authorization behavior**

- All knowledge routes use `get_workspace_access` + permission keys
- KB lookups always filter `KnowledgeBase.workspace_id == access.workspace.id` (spoofed KB id → 404)
- Document get/delete/reprocess require matching `workspace_id` **and** `knowledge_base_id`
- Cross-workspace `X-Workspace-Id` spoof → 403 (Phase 2)

### Frontend

- `KnowledgePage`: KB list/create/delete + documents for selected KB (status, upload, delete, failure message)
- `KnowledgePanel` (chat sidebar): KB selector, upload, query with citation excerpts
- `knowledgeService.ts` + mock handlers for `/knowledge-bases`
- Types: `KnowledgeBase`, `CitationSource`, `KnowledgeQueryResult`; documents include `knowledge_base_id`
- Workspace header `X-Workspace-Id` unchanged

### Security

| Check | How validated |
|-------|----------------|
| User A cannot retrieve User B workspace docs | Authored: `tests/test_knowledge.py`, `TestRAGRetrievalIsolation.test_retrieve_empty_for_other_workspace` |
| Cannot retrieve another inaccessible KB | Authored: KB listing/filter tests; retrieve with wrong `knowledge_base_id` returns empty |
| Spoofed document/KB IDs cannot bypass workspace auth | Authored: foreign KB get/upload → 403/404; spoofed doc get → 403/404 |
| Retrieval never returns other-workspace chunks | SQL filters on `workspace_id` + `status=ready`; isolation tests authored |
| Upload cannot target foreign KB | Authored: `test_cannot_upload_document_to_foreign_knowledge_base` |
| Deleted documents excluded from retrieval | CASCADE delete + `has_ready_documents` / retrieve tests authored |

**Note:** Backend pytest was **not executed** in this environment (see Validation). Security claims are based on code paths + authored tests, not a green CI run.

### Validation

| Command / check | Result | Notes |
|-----------------|--------|-------|
| Architecture inspection (models, RAG, workers, UI, migrations) | PASS | Completed before/during implementation |
| Alembic revision `e9f5a2b3c4d5` authored | PASS | Chain `d8e4f1a2b3c4` → `e9f5a2b3c4d5` |
| `alembic upgrade head` | BLOCKED | No usable host Python; Docker engine down |
| `python -m pytest -q` | BLOCKED | Microsoft Store Python stub only |
| `python -m pytest tests/test_knowledge.py tests/test_rag_service.py -q` | BLOCKED | Same as above |
| Knowledge/workspace isolation tests authored | PASS (authored) | `tests/test_knowledge.py`, retrieval isolation in `tests/test_rag_service.py` |
| `npm run build` (frontend) | PASS | `tsc -b && vite build` succeeded |
| `npm run lint` (frontend) | FAIL | Pre-existing eslint rule debt; not used as Phase 3 gate |
| Docker Compose / live migration | BLOCKED | Docker Desktop Linux engine not running |

### Known issues

- Backend tests and Alembic upgrade were not executed live in this session
- Hybrid search and HNSW require PostgreSQL + pgvector; SQLite tests use vector-only / create_all without `content_tsv`
- Reranking requires `sentence-transformers` + model download; gracefully skipped when missing
- Worker still trusts authorized enqueue by `document_id` (no re-check of membership inside Celery)
- `Base.metadata.create_all()` still runs at API startup alongside Alembic
- Frontend eslint failures remain (pre-existing)
- Full chat citation UX / persistent Conversations deferred to Phase 4

### Files (Phase 3)

**Added**

- `app/models/knowledge_base.py`
- `app/services/knowledge_service.py`
- `app/schemas/knowledge.py`
- `app/api/routers/knowledge.py`
- `alembic/versions/e9f5a2b3c4d5_add_knowledge_bases_and_retrieval_indexes.py`
- `tests/test_knowledge.py`
- `frontend/src/services/knowledgeService.ts`

**Modified (important)**

- `app/models/document.py`, `app/models/__init__.py`
- `app/services/rag_service.py`, `app/services/workspace_service.py`, `app/services/workspace_permissions.py`
- `app/api/routers/rag.py`, `app/main.py`, `app/core/config.py`, `app/schemas/rag.py`
- Frontend: `KnowledgePage.tsx`, `KnowledgePanel.tsx`, `types/index.ts`, `mock/data.ts`
- Docs: `docs/changes.md`, `.env.example`, this file
- Tests: `tests/test_rag_service.py`

### Phase 4 handoff

Phase 4 (Conversations / unified AI flow) should build **on** this Knowledge layer:

1. **Tenancy**: Conversations/Messages must include `workspace_id`; never reintroduce user-only isolation
2. **Retrieval contract**: call `RAGService.retrieve_with_citations(workspace_id=..., knowledge_base_id=...)` (or multi-KB list later). Do not load all workspace chunks into memory and filter in Python
3. **Citations**: persist `CitationSource`-shaped metadata on assistant messages (chunk_id, document_id, knowledge_base_id, filename, excerpt, score). API already returns this shape for non-chat RAG
4. **KB selection**: chat UI should let the user pick a knowledge base (or “all in workspace”); default to workspace `General` KB
5. **Permissions**: reuse `knowledge:read` for retrieval; add conversation permissions to `PERMISSIONS` rather than hardcoding roles
6. **Do not redesign RAG**: hybrid/RRF/rerank knobs and Celery ingest should stay; Phase 4 wires them into persistent chat, not a new vector stack
7. **Out of Phase 3 scope (still TODO)**: Conversations/Messages, Agents, configurable Tools, external integrations, new LLM provider architecture
8. **Before relying on hybrid/HNSW in prod**: run `alembic upgrade head` on PostgreSQL and confirm `content_tsv` + HNSW indexes exist
