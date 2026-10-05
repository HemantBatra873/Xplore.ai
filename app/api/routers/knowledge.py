import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_workspace_access
from app.models.user import User
from app.schemas.knowledge import (
    CitationSource,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)
from app.schemas.rag import DocumentResponse
from app.services.knowledge_service import KnowledgeBaseService
from app.services.llm_observability_service import (
    create_llm_call_log,
    elapsed_ms,
    extract_usage,
    start_timer,
)
from app.services.llm_service import get_llm_client
from app.services.rag_service import RAGService, RetrievalHit, append_session_message, load_session_history
from app.services.workspace_service import WorkspaceAccess
from app.utils.file_parser import get_supported_extensions, parse_file
from app.worker.tasks import process_document_task

router = APIRouter()

SUPPORTED_EXTENSIONS = get_supported_extensions()
SUPPORTED_EXT_TEXT = ", ".join(SUPPORTED_EXTENSIONS)


def _current_user(db: Session, access: WorkspaceAccess) -> User:
    return db.get(User, access.membership.user_id)


def _kb_out(db: Session, kb) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        workspace_id=kb.workspace_id,
        name=kb.name,
        description=kb.description,
        created_by_id=kb.created_by_id,
        document_count=KnowledgeBaseService.document_count(db, knowledge_base_id=kb.id),
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _citation_sources(hits: list[RetrievalHit]) -> list[CitationSource]:
    sources: list[CitationSource] = []
    for hit in hits:
        kb_id = hit.document.knowledge_base_id or 0
        sources.append(
            CitationSource(
                chunk_id=hit.chunk.id,
                document_id=hit.document.id,
                knowledge_base_id=kb_id,
                knowledge_base_name=hit.knowledge_base.name if hit.knowledge_base else None,
                filename=hit.document.filename,
                chunk_index=hit.chunk.chunk_index,
                excerpt=hit.chunk.content[:500],
                score=hit.score,
                vector_score=hit.vector_score,
                keyword_score=hit.keyword_score,
            )
        )
    return sources


def _build_rag_messages(*, query: str, hits: list[RetrievalHit], session_history: list[dict] | None):
    context_texts = [
        f"[Source passage {i}]:\n{hit.chunk.content}" for i, hit in enumerate(hits, 1)
    ]
    context_str = "\n\n".join(context_texts)
    system_prompt = (
        "You are a careful question-answering assistant. Answer using the reference material below.\n"
        "If the answer is not present, say so directly and do not invent details.\n\n"
        f"=== Reference material ===\n{context_str}\n=== End reference material ==="
    )
    if session_history:
        return (
            [{"role": "system", "content": system_prompt}]
            + session_history
            + [{"role": "user", "content": query}]
        )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]


@router.get("/", response_model=list[KnowledgeBaseOut], summary="List knowledge bases", tags=["Knowledge"])
async def list_knowledge_bases(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    kbs = KnowledgeBaseService.list_for_workspace(db, workspace_id=access.workspace.id)
    return [_kb_out(db, kb) for kb in kbs]


@router.post(
    "/",
    response_model=KnowledgeBaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a knowledge base",
    tags=["Knowledge"],
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    kb = KnowledgeBaseService.create(db, access=access, payload=payload)
    return _kb_out(db, kb)


@router.get("/{kb_id}", response_model=KnowledgeBaseOut, summary="Get a knowledge base", tags=["Knowledge"])
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    kb = KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    return _kb_out(db, kb)


@router.patch("/{kb_id}", response_model=KnowledgeBaseOut, summary="Update a knowledge base", tags=["Knowledge"])
async def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    kb = KnowledgeBaseService.update(
        db, access=access, knowledge_base_id=kb_id, payload=payload
    )
    return _kb_out(db, kb)


@router.delete("/{kb_id}", summary="Delete a knowledge base", tags=["Knowledge"])
async def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    kb = KnowledgeBaseService.delete(db, access=access, knowledge_base_id=kb_id)
    return JSONResponse(
        content={"message": f"Knowledge base '{kb.name}' deleted", "knowledge_base_id": kb.id}
    )


@router.get(
    "/{kb_id}/documents",
    response_model=list[DocumentResponse],
    summary="List documents in a knowledge base",
    tags=["Knowledge"],
)
async def list_kb_documents(
    kb_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    rag_service = RAGService(db)
    return rag_service.list_documents_for_knowledge_base(
        workspace_id=access.workspace.id, knowledge_base_id=kb_id
    )


@router.post(
    "/{kb_id}/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document into a knowledge base",
    tags=["Knowledge"],
)
async def upload_kb_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:write")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    current_user = _current_user(db, access)
    workspace_id = access.workspace.id

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    if len(file.filename) > 255:
        raise HTTPException(status_code=400, detail="Filename too long (max 255 characters).")

    name_lower = file.filename.lower()
    if not any(name_lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {SUPPORTED_EXT_TEXT}",
        )

    raw_bytes = await file.read()
    try:
        parsed = parse_file(file.filename, raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if not parsed.plain_text.strip():
        raise HTTPException(status_code=400, detail="File contains no extractable text.")

    rag_service = RAGService(db)
    doc = None
    try:
        doc = rag_service.create_document_record(
            filename=file.filename,
            file_type=parsed.file_type,
            content=parsed.plain_text,
            owner_id=current_user.id,
            workspace_id=workspace_id,
            knowledge_base_id=kb_id,
        )
        task = process_document_task.delay(doc.id)
        doc = rag_service.attach_processing_task(
            document_id=doc.id,
            workspace_id=workspace_id,
            task_id=task.id,
        )
        return doc
    except Exception as e:
        if doc is not None:
            rag_service.mark_document_failed(document_id=doc.id, error_message=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@router.get(
    "/{kb_id}/documents/{doc_id}",
    response_model=DocumentResponse,
    summary="Get document status in a knowledge base",
    tags=["Knowledge"],
)
async def get_kb_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    rag_service = RAGService(db)
    document = rag_service.get_document_for_knowledge_base(
        document_id=doc_id,
        workspace_id=access.workspace.id,
        knowledge_base_id=kb_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.delete(
    "/{kb_id}/documents/{doc_id}",
    summary="Delete a document from a knowledge base",
    tags=["Knowledge"],
)
async def delete_kb_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:write")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    rag_service = RAGService(db)
    document = rag_service.get_document_for_knowledge_base(
        document_id=doc_id,
        workspace_id=access.workspace.id,
        knowledge_base_id=kb_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    rag_service.delete_document(document_id=doc_id, workspace_id=access.workspace.id)
    return JSONResponse(
        content={"message": f"Document '{document.filename}' deleted", "document_id": document.id}
    )


@router.post(
    "/{kb_id}/documents/{doc_id}/reprocess",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reprocess a document",
    tags=["Knowledge"],
)
async def reprocess_kb_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:write")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    rag_service = RAGService(db)
    document = rag_service.get_document_for_knowledge_base(
        document_id=doc_id,
        workspace_id=access.workspace.id,
        knowledge_base_id=kb_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    task = process_document_task.delay(document.id)
    updated = rag_service.requeue_document(
        document_id=document.id,
        workspace_id=access.workspace.id,
        task_id=task.id,
    )
    return updated


@router.post(
    "/{kb_id}/query",
    response_model=KnowledgeQueryResponse,
    summary="Query a knowledge base",
    tags=["Knowledge"],
)
async def query_knowledge_base(
    kb_id: int,
    request: KnowledgeQueryRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    current_user = _current_user(db, access)
    workspace_id = access.workspace.id

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    rag_service = RAGService(db)
    started_at = start_timer()
    try:
        hits = await rag_service.retrieve_with_citations(
            query=request.query,
            workspace_id=workspace_id,
            top_k=request.top_k,
            knowledge_base_id=kb_id,
            enable_rerank=request.enable_rerank,
            enable_hybrid=request.enable_hybrid,
        )
        if not hits:
            return KnowledgeQueryResponse(
                query=request.query,
                answer="No processed documents match this query. Upload a document and wait for processing to finish.",
                sources=[],
                source_chunks=[],
            )

        session_history = None
        if request.session_id:
            session_history = await load_session_history(current_user.id, request.session_id)

        messages = _build_rag_messages(
            query=request.query, hits=hits, session_history=session_history
        )
        llm_info = get_llm_client(current_user)
        response = await llm_info.client.chat.completions.create(
            model=llm_info.model_name,
            messages=messages,
            temperature=0.1,
        )
        response_text = response.choices[0].message.content
        prompt_tokens, completion_tokens, total_tokens = extract_usage(response)

        if request.session_id:
            await append_session_message(current_user.id, request.session_id, "user", request.query)
            await append_session_message(
                current_user.id, request.session_id, "assistant", response_text
            )

        sources = _citation_sources(hits)
        create_llm_call_log(
            db,
            user_id=current_user.id,
            workspace_id=workspace_id,
            endpoint=f"/api/v1/knowledge-bases/{kb_id}/query",
            prompt=request.query,
            response=response_text,
            tool_calls=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=elapsed_ms(started_at),
            status="success",
        )
        return KnowledgeQueryResponse(
            query=request.query,
            answer=response_text,
            sources=sources,
            source_chunks=[s.excerpt for s in sources],
        )
    except Exception as e:
        create_llm_call_log(
            db,
            user_id=current_user.id,
            workspace_id=workspace_id,
            endpoint=f"/api/v1/knowledge-bases/{kb_id}/query",
            prompt=request.query,
            response=None,
            tool_calls=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=elapsed_ms(started_at),
            status="failed",
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Knowledge query failed: {str(e)}")


@router.post(
    "/{kb_id}/query/stream",
    summary="Stream a knowledge base query (SSE)",
    tags=["Knowledge"],
)
async def query_knowledge_base_stream(
    kb_id: int,
    request: KnowledgeQueryRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    KnowledgeBaseService.get_for_workspace(
        db, knowledge_base_id=kb_id, workspace_id=access.workspace.id
    )
    current_user = _current_user(db, access)

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    rag_service = RAGService(db)
    hits = await rag_service.retrieve_with_citations(
        query=request.query,
        workspace_id=access.workspace.id,
        top_k=request.top_k,
        knowledge_base_id=kb_id,
        enable_rerank=request.enable_rerank,
        enable_hybrid=request.enable_hybrid,
    )

    if not hits:

        async def _empty():
            data = json.dumps(
                {
                    "content": "No processed documents match this query. Upload a document and wait for processing to finish.",
                    "sources": [],
                    "source_chunks": [],
                },
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_empty(), media_type="text/event-stream")

    sources = _citation_sources(hits)
    source_chunks = [s.excerpt for s in sources]
    messages = _build_rag_messages(query=request.query, hits=hits, session_history=None)

    async def _stream():
        llm_info = get_llm_client(current_user)
        full_response = ""
        stream_messages = messages
        if request.session_id:
            session_history = await load_session_history(current_user.id, request.session_id)
            await append_session_message(current_user.id, request.session_id, "user", request.query)
            stream_messages = _build_rag_messages(
                query=request.query, hits=hits, session_history=session_history
            )

        try:
            response = await llm_info.client.chat.completions.create(
                model=llm_info.model_name,
                messages=stream_messages,
                temperature=0.1,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    data = json.dumps({"content": content}, ensure_ascii=False)
                    yield f"data: {data}\n\n"

            if request.session_id and full_response:
                await append_session_message(
                    current_user.id, request.session_id, "assistant", full_response
                )

            data = json.dumps(
                {"sources": [s.model_dump() for s in sources], "source_chunks": source_chunks},
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
