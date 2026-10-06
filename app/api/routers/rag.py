import json
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_workspace_access
from app.models.user import User
from app.schemas.knowledge import CitationSource
from app.schemas.rag import DocumentResponse, RAGQueryRequest, RAGQueryResponse
from app.services.knowledge_service import KnowledgeBaseService
from app.services.llm_observability_service import (
    create_llm_call_log,
    elapsed_ms,
    extract_usage,
    start_timer,
)
from app.services.llm_service import get_llm_client
from app.services.rag_service import (
    RAGService,
    RetrievalHit,
    append_session_message,
    load_session_history,
)
from app.services.workspace_service import WorkspaceAccess
from app.utils.file_parser import get_supported_extensions, parse_file
from app.worker.tasks import process_document_task

router = APIRouter()

SUPPORTED_EXTENSIONS = get_supported_extensions()
SUPPORTED_EXT_TEXT = ", ".join(SUPPORTED_EXTENSIONS)


def _current_user(db: Session, access: WorkspaceAccess) -> User:
    return db.get(User, access.membership.user_id)


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


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document and build the knowledge base asynchronously (.txt / .md / .pdf)",
    tags=["RAG"],
)
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """
    Upload a document, store extracted text, then process chunking and embeddings asynchronously.
    """
    access.require_permission("knowledge:write")
    current_user = _current_user(db, access)
    workspace_id = access.workspace.id
    if knowledge_base_id is not None:
        kb = KnowledgeBaseService.get_for_workspace(
            db, knowledge_base_id=knowledge_base_id, workspace_id=workspace_id
        )
        target_kb_id = kb.id
    else:
        kb = KnowledgeBaseService.ensure_default_for_workspace(
            db, workspace=access.workspace, created_by_id=current_user.id
        )
        target_kb_id = kb.id

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
            knowledge_base_id=target_kb_id,
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
    "/documents",
    response_model=list[DocumentResponse],
    summary="List documents in the current workspace",
    tags=["RAG"],
)
async def list_documents(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    KnowledgeBaseService.ensure_default_for_workspace(db, workspace=access.workspace)
    rag_service = RAGService(db)
    return rag_service.list_documents_for_workspace(workspace_id=access.workspace.id)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document processing status",
    tags=["RAG"],
)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    rag_service = RAGService(db)
    document = rag_service.get_document_for_workspace(
        document_id=document_id, workspace_id=access.workspace.id
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document and its processed chunks",
    tags=["RAG"],
)
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:write")
    rag_service = RAGService(db)
    document = rag_service.delete_document(
        document_id=document_id, workspace_id=access.workspace.id
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return JSONResponse(
        content={"message": f"Document '{document.filename}' deleted", "document_id": document.id}
    )


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Retrieve from the knowledge base and answer",
    tags=["RAG"],
)
async def query_knowledge_base(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """
    1. Embed the user query
    2. Retrieve the most similar document chunks with pgvector (top_k)
    3. Assemble a prompt and ask the LLM for an answer
    """
    access.require_permission("knowledge:read")
    current_user = _current_user(db, access)
    workspace_id = access.workspace.id
    KnowledgeBaseService.ensure_default_for_workspace(db, workspace=access.workspace)

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if request.knowledge_base_id is not None:
        KnowledgeBaseService.get_for_workspace(
            db,
            knowledge_base_id=request.knowledge_base_id,
            workspace_id=workspace_id,
        )

    rag_service = RAGService(db)
    started_at = start_timer()
    try:
        hits = await rag_service.retrieve_with_citations(
            query=request.query,
            workspace_id=workspace_id,
            top_k=request.top_k,
            knowledge_base_id=request.knowledge_base_id,
            enable_rerank=request.enable_rerank,
            enable_hybrid=request.enable_hybrid,
        )

        if not hits:
            return RAGQueryResponse(
                query=request.query,
                answer="No processed documents match this query. Upload a document and wait for processing to finish.",
                sources=[],
                source_chunks=[],
            )

        sources = _citation_sources(hits)
        context_texts = []
        for i, hit in enumerate(hits, 1):
            context_texts.append(f"[Source passage {i}]:\n{hit.chunk.content}")

        context_str = "\n\n".join(context_texts)

        system_prompt = (
            "You are a careful question-answering assistant. Answer using the reference material below.\n"
            "If the answer is not present, say so directly and do not invent details.\n\n"
            f"=== Reference material ===\n{context_str}\n=== End reference material ==="
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.query},
        ]

        if request.session_id:
            session_history = await load_session_history(current_user.id, request.session_id)
            messages = (
                [{"role": "system", "content": system_prompt}]
                + session_history
                + [{"role": "user", "content": request.query}]
            )

        llm_info = get_llm_client(current_user)
        response = await llm_info.client.chat.completions.create(
            model=llm_info.model_name,
            messages=messages,
            temperature=0.1,  # Lower temperature for more stable RAG answers
        )
        response_text = response.choices[0].message.content
        prompt_tokens, completion_tokens, total_tokens = extract_usage(response)

        if request.session_id:
            await append_session_message(current_user.id, request.session_id, "user", request.query)
            await append_session_message(
                current_user.id, request.session_id, "assistant", response_text
            )
        create_llm_call_log(
            db,
            user_id=current_user.id,
            workspace_id=workspace_id,
            endpoint="/api/v1/rag/query",
            prompt=request.query,
            response=response_text,
            tool_calls=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=elapsed_ms(started_at),
            status="success",
        )

        return RAGQueryResponse(
            query=request.query,
            answer=response_text,
            sources=sources,
            source_chunks=[h.chunk.content for h in hits],
        )

    except Exception as e:
        create_llm_call_log(
            db,
            user_id=current_user.id,
            workspace_id=workspace_id,
            endpoint="/api/v1/rag/query",
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
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@router.post(
    "/query/stream",
    summary="Retrieve from the knowledge base and stream an answer (SSE)",
    tags=["RAG"],
)
async def query_knowledge_base_stream(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("knowledge:read")
    current_user = _current_user(db, access)
    workspace_id = access.workspace.id
    KnowledgeBaseService.ensure_default_for_workspace(db, workspace=access.workspace)

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if request.knowledge_base_id is not None:
        KnowledgeBaseService.get_for_workspace(
            db,
            knowledge_base_id=request.knowledge_base_id,
            workspace_id=workspace_id,
        )

    rag_service = RAGService(db)
    hits = await rag_service.retrieve_with_citations(
        query=request.query,
        workspace_id=workspace_id,
        top_k=request.top_k,
        knowledge_base_id=request.knowledge_base_id,
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
    context_texts = [f"[Source passage {i}]:\n{hit.chunk.content}" for i, hit in enumerate(hits, 1)]
    context_str = "\n\n".join(context_texts)
    system_prompt = (
        "You are a careful question-answering assistant. Answer using the reference material below.\n"
        "If the answer is not present, say so directly and do not invent details.\n\n"
        f"=== Reference material ===\n{context_str}\n=== End reference material ==="
    )

    source_chunk_contents = [h.chunk.content for h in hits]

    async def _stream():
        llm_info = get_llm_client(current_user)
        full_response = ""

        stream_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.query},
        ]

        if request.session_id:
            session_history = await load_session_history(current_user.id, request.session_id)
            await append_session_message(current_user.id, request.session_id, "user", request.query)
            stream_messages = (
                [{"role": "system", "content": system_prompt}]
                + session_history
                + [{"role": "user", "content": request.query}]
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
                {
                    "sources": [s.model_dump() for s in sources],
                    "source_chunks": source_chunk_contents,
                },
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
