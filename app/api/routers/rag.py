import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.rag import DocumentResponse, RAGQueryRequest, RAGQueryResponse
from app.services.llm_observability_service import (
    create_llm_call_log,
    elapsed_ms,
    extract_usage,
    start_timer,
)
from app.services.llm_service import get_llm_client
from app.services.rag_service import RAGService, append_session_message, load_session_history
from app.utils.file_parser import get_supported_extensions, parse_file
from app.worker.tasks import process_document_task

router = APIRouter()

SUPPORTED_EXTENSIONS = get_supported_extensions()
SUPPORTED_EXT_TEXT = ", ".join(SUPPORTED_EXTENSIONS)


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document and build the knowledge base asynchronously (.txt / .md / .pdf)",
    tags=["RAG"],
)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Upload a document, store extracted text, then process chunking and embeddings asynchronously.
    """
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
        )
        task = process_document_task.delay(doc.id)
        doc = rag_service.attach_processing_task(
            document_id=doc.id,
            owner_id=current_user.id,
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
    summary="List the current user documents",
    tags=["RAG"],
)
async def list_documents(
    db: Session = Depends(get_db), current_user=Depends(get_current_active_user)
):
    rag_service = RAGService(db)
    return rag_service.list_documents_for_user(owner_id=current_user.id)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document processing status",
    tags=["RAG"],
)
async def get_document(
    document_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)
):
    rag_service = RAGService(db)
    document = rag_service.get_document_for_user(document_id=document_id, owner_id=current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document and its processed chunks",
    tags=["RAG"],
)
async def delete_document(
    document_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)
):
    rag_service = RAGService(db)
    document = rag_service.delete_document(document_id=document_id, owner_id=current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return JSONResponse(
        content={"message": f"Document '{document.filename}' deleted", "document_id": document.id}
    )


@router.post(
    "/query", response_model=RAGQueryResponse, summary="Retrieve from the knowledge base and answer", tags=["RAG"]
)
async def query_knowledge_base(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    1. Embed the user query
    2. Retrieve the most similar document chunks with pgvector (top_k)
    3. Assemble a prompt and ask the LLM for an answer
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    rag_service = RAGService(db)
    started_at = start_timer()
    try:
        chunks = await rag_service.retrieve_relevant_chunks(
            query=request.query,
            owner_id=current_user.id,
            top_k=request.top_k,
        )

        if not chunks:
            return RAGQueryResponse(
                query=request.query,
                answer="No processed documents match this query. Upload a document and wait for processing to finish.",
                source_chunks=[],
            )

        # 3. Assemble prompt
        context_texts = []
        for i, chunk in enumerate(chunks, 1):
            context_texts.append(f"[Source passage {i}]:\n{chunk.content}")

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
            query=request.query, answer=response_text, source_chunks=[c.content for c in chunks]
        )

    except Exception as e:
        create_llm_call_log(
            db,
            user_id=current_user.id,
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


@router.post("/query/stream", summary="Retrieve from the knowledge base and stream an answer (SSE)", tags=["RAG"])
async def query_knowledge_base_stream(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    rag_service = RAGService(db)
    chunks = await rag_service.retrieve_relevant_chunks(
        query=request.query,
        owner_id=current_user.id,
        top_k=request.top_k,
    )

    if not chunks:

        async def _empty():
            data = json.dumps(
                {
                    "content": "No processed documents match this query. Upload a document and wait for processing to finish.",
                    "source_chunks": [],
                },
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_empty(), media_type="text/event-stream")

    context_texts = [f"[Source passage {i}]:\n{chunk.content}" for i, chunk in enumerate(chunks, 1)]
    context_str = "\n\n".join(context_texts)
    system_prompt = (
        "You are a careful question-answering assistant. Answer using the reference material below.\n"
        "If the answer is not present, say so directly and do not invent details.\n\n"
        f"=== Reference material ===\n{context_str}\n=== End reference material ==="
    )

    source_chunk_contents = [c.content for c in chunks]

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

            data = json.dumps({"source_chunks": source_chunk_contents}, ensure_ascii=False)
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
