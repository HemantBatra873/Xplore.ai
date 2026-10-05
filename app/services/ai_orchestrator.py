"""Unified AI orchestration: conversation + optional knowledge retrieval + LLM."""

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.conversation import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_FAILED,
    Conversation,
    Message,
    MessageCitation,
)
from app.models.user import User
from app.services.conversation_service import ConversationService, parse_kb_ids
from app.services.knowledge_service import KnowledgeBaseService
from app.services.llm_observability_service import create_llm_call_log, elapsed_ms, start_timer
from app.services.providers import ChatMessage, get_llm_provider
from app.services.rag_service import RAGService, RetrievalHit
from app.services.workspace_service import WorkspaceAccess


@dataclass
class OrchestrationResult:
    user_message: Message
    assistant_message: Message
    hits: list[RetrievalHit]


def _title_from_content(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    if not cleaned:
        return "New conversation"
    return cleaned[:80] + ("…" if len(cleaned) > 80 else "")


def _build_messages(
    *,
    history: list[Message],
    user_content: str,
    hits: list[RetrievalHit],
) -> list[ChatMessage]:
    if hits:
        context_texts = [
            f"[Source passage {i}]:\n{hit.chunk.content}" for i, hit in enumerate(hits, 1)
        ]
        system_prompt = (
            "You are a careful question-answering assistant. Answer using the reference material below "
            "when it is relevant. If the answer is not present, say so directly and do not invent details.\n\n"
            f"=== Reference material ===\n{chr(10).join(context_texts)}\n=== End reference material ==="
        )
    else:
        system_prompt = (
            "You are a helpful assistant for Xplore.ai. Answer clearly and concisely."
        )

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
    for msg in history:
        if msg.role in (MESSAGE_ROLE_USER, MESSAGE_ROLE_ASSISTANT) and msg.content:
            if msg.status == MESSAGE_STATUS_FAILED:
                continue
            messages.append(ChatMessage(role=msg.role, content=msg.content))
    messages.append(ChatMessage(role="user", content=user_content))
    return messages


class AIOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.rag = RAGService(db)

    def _resolve_kb_ids(
        self,
        *,
        access: WorkspaceAccess,
        conversation: Conversation,
        use_knowledge: Optional[bool],
        knowledge_base_ids: Optional[list[int]],
    ) -> tuple[bool, list[int]]:
        enabled = conversation.use_knowledge if use_knowledge is None else use_knowledge
        if not enabled:
            return False, []

        access.require_permission("knowledge:read")
        kb_ids = (
            knowledge_base_ids
            if knowledge_base_ids is not None
            else parse_kb_ids(conversation.knowledge_base_ids)
        )
        ConversationService._validate_knowledge_bases(
            self.db, workspace_id=access.workspace.id, knowledge_base_ids=kb_ids
        )
        # Ensure default KB exists when retrieving across the workspace
        KnowledgeBaseService.ensure_default_for_workspace(
            self.db, workspace=access.workspace
        )
        return True, kb_ids

    async def _retrieve(
        self,
        *,
        query: str,
        workspace_id: int,
        kb_ids: list[int],
        top_k: int,
        enable_rerank: Optional[bool],
        enable_hybrid: Optional[bool],
    ) -> list[RetrievalHit]:
        if not kb_ids:
            return await self.rag.retrieve_with_citations(
                query=query,
                workspace_id=workspace_id,
                top_k=top_k,
                knowledge_base_id=None,
                enable_rerank=enable_rerank,
                enable_hybrid=enable_hybrid,
            )

        merged: dict[int, RetrievalHit] = {}
        for kb_id in kb_ids:
            hits = await self.rag.retrieve_with_citations(
                query=query,
                workspace_id=workspace_id,
                top_k=top_k,
                knowledge_base_id=kb_id,
                enable_rerank=enable_rerank,
                enable_hybrid=enable_hybrid,
            )
            for hit in hits:
                existing = merged.get(hit.chunk.id)
                if existing is None or hit.score > existing.score:
                    merged[hit.chunk.id] = hit
        ranked = sorted(merged.values(), key=lambda h: h.score, reverse=True)
        return ranked[:top_k]

    def _persist_citations(self, message: Message, hits: list[RetrievalHit]) -> None:
        for hit in hits:
            self.db.add(
                MessageCitation(
                    message_id=message.id,
                    chunk_id=hit.chunk.id,
                    document_id=hit.document.id,
                    knowledge_base_id=hit.document.knowledge_base_id,
                    knowledge_base_name=hit.knowledge_base.name if hit.knowledge_base else None,
                    filename=hit.document.filename,
                    chunk_index=hit.chunk.chunk_index,
                    excerpt=(hit.chunk.content or "")[:500],
                    score=hit.score,
                )
            )

    def _citation_payload(self, hits: list[RetrievalHit]) -> list[dict[str, Any]]:
        sources = []
        for hit in hits:
            sources.append(
                {
                    "chunk_id": hit.chunk.id,
                    "document_id": hit.document.id,
                    "knowledge_base_id": hit.document.knowledge_base_id,
                    "knowledge_base_name": hit.knowledge_base.name if hit.knowledge_base else None,
                    "filename": hit.document.filename,
                    "chunk_index": hit.chunk.chunk_index,
                    "excerpt": (hit.chunk.content or "")[:500],
                    "score": hit.score,
                    "vector_score": hit.vector_score,
                    "keyword_score": hit.keyword_score,
                }
            )
        return sources

    async def send_message(
        self,
        *,
        access: WorkspaceAccess,
        user: User,
        conversation_id: int,
        content: str,
        use_knowledge: Optional[bool] = None,
        knowledge_base_ids: Optional[list[int]] = None,
        top_k: int = 3,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> OrchestrationResult:
        access.require_permission("conversations:write")
        conversation = ConversationService.get_for_workspace(
            self.db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        enabled, kb_ids = self._resolve_kb_ids(
            access=access,
            conversation=conversation,
            use_knowledge=use_knowledge,
            knowledge_base_ids=knowledge_base_ids,
        )

        history = list(
            self.db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
            )
            .scalars()
            .all()
        )

        user_message = Message(
            conversation_id=conversation.id,
            role=MESSAGE_ROLE_USER,
            content=content.strip(),
            status=MESSAGE_STATUS_COMPLETE,
        )
        self.db.add(user_message)
        if conversation.title == "New conversation":
            conversation.title = _title_from_content(content)
        ConversationService.touch(self.db, conversation)
        self.db.commit()
        self.db.refresh(user_message)

        hits: list[RetrievalHit] = []
        if enabled:
            hits = await self._retrieve(
                query=content,
                workspace_id=access.workspace.id,
                kb_ids=kb_ids,
                top_k=top_k,
                enable_rerank=enable_rerank,
                enable_hybrid=enable_hybrid,
            )

        provider = get_llm_provider(user)
        llm_messages = _build_messages(history=history, user_content=content, hits=hits)
        started_at = start_timer()
        try:
            result = await provider.complete(llm_messages, temperature=0.2)
            assistant = Message(
                conversation_id=conversation.id,
                role=MESSAGE_ROLE_ASSISTANT,
                content=result.content,
                status=MESSAGE_STATUS_COMPLETE,
            )
            self.db.add(assistant)
            self.db.flush()
            if hits:
                self._persist_citations(assistant, hits)
            ConversationService.touch(self.db, conversation)
            self.db.commit()
            self.db.refresh(assistant)
            create_llm_call_log(
                self.db,
                user_id=user.id,
                workspace_id=access.workspace.id,
                endpoint=f"/api/v1/conversations/{conversation.id}/messages",
                prompt=content,
                response=result.content,
                tool_calls=None,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=elapsed_ms(started_at),
                status="success",
            )
            # Reload citations
            assistant = self.db.execute(
                select(Message)
                .where(Message.id == assistant.id)
            ).scalar_one()
            _ = assistant.citations  # ensure loaded
            return OrchestrationResult(
                user_message=user_message, assistant_message=assistant, hits=hits
            )
        except Exception as exc:
            logger.error(f"Conversation LLM call failed: {exc}")
            create_llm_call_log(
                self.db,
                user_id=user.id,
                workspace_id=access.workspace.id,
                endpoint=f"/api/v1/conversations/{conversation.id}/messages",
                prompt=content,
                response=None,
                tool_calls=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=elapsed_ms(started_at),
                status="failed",
                error_message=str(exc),
            )
            # Do not persist a misleading assistant message
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=f"Assistant request failed: {exc}") from exc

    async def stream_message(
        self,
        *,
        access: WorkspaceAccess,
        user: User,
        conversation_id: int,
        content: str,
        use_knowledge: Optional[bool] = None,
        knowledge_base_ids: Optional[list[int]] = None,
        top_k: int = 3,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> AsyncIterator[str]:
        """Yield SSE lines. Persist assistant message only after a successful stream."""
        access.require_permission("conversations:write")
        conversation = ConversationService.get_for_workspace(
            self.db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        enabled, kb_ids = self._resolve_kb_ids(
            access=access,
            conversation=conversation,
            use_knowledge=use_knowledge,
            knowledge_base_ids=knowledge_base_ids,
        )

        history = list(
            self.db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
            )
            .scalars()
            .all()
        )

        user_message = Message(
            conversation_id=conversation.id,
            role=MESSAGE_ROLE_USER,
            content=content.strip(),
            status=MESSAGE_STATUS_COMPLETE,
        )
        self.db.add(user_message)
        if conversation.title == "New conversation":
            conversation.title = _title_from_content(content)
        ConversationService.touch(self.db, conversation)
        self.db.commit()
        self.db.refresh(user_message)

        yield f"data: {json.dumps({'user_message_id': user_message.id}, ensure_ascii=False)}\n\n"

        hits: list[RetrievalHit] = []
        if enabled:
            try:
                hits = await self._retrieve(
                    query=content,
                    workspace_id=access.workspace.id,
                    kb_ids=kb_ids,
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                    enable_hybrid=enable_hybrid,
                )
            except Exception as exc:
                logger.error(f"Conversation retrieval failed: {exc}")
                yield f"data: {json.dumps({'error': f'Retrieval failed: {exc}'}, ensure_ascii=False)}\n\n"
                return

        if hits:
            yield f"data: {json.dumps({'sources': self._citation_payload(hits)}, ensure_ascii=False)}\n\n"

        provider = get_llm_provider(user)
        llm_messages = _build_messages(history=history, user_content=content, hits=hits)
        started_at = start_timer()
        full_response = ""
        try:
            async for chunk in provider.stream(llm_messages, temperature=0.2):
                if chunk.done:
                    break
                payload: dict[str, Any] = {}
                if chunk.content:
                    full_response += chunk.content
                    payload["content"] = chunk.content
                if chunk.reasoning:
                    payload["reasoning"] = chunk.reasoning
                if payload:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if not full_response.strip():
                yield f"data: {json.dumps({'error': 'Empty model response'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            assistant = Message(
                conversation_id=conversation.id,
                role=MESSAGE_ROLE_ASSISTANT,
                content=full_response,
                status=MESSAGE_STATUS_COMPLETE,
            )
            self.db.add(assistant)
            self.db.flush()
            if hits:
                self._persist_citations(assistant, hits)
            ConversationService.touch(self.db, conversation)
            self.db.commit()
            self.db.refresh(assistant)

            create_llm_call_log(
                self.db,
                user_id=user.id,
                workspace_id=access.workspace.id,
                endpoint=f"/api/v1/conversations/{conversation.id}/messages/stream",
                prompt=content,
                response=full_response,
                tool_calls=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=elapsed_ms(started_at),
                status="success",
            )
            yield f"data: {json.dumps({'assistant_message_id': assistant.id, 'sources': self._citation_payload(hits)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error(f"Conversation stream failed: {exc}")
            create_llm_call_log(
                self.db,
                user_id=user.id,
                workspace_id=access.workspace.id,
                endpoint=f"/api/v1/conversations/{conversation.id}/messages/stream",
                prompt=content,
                response=None,
                tool_calls=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=elapsed_ms(started_at),
                status="failed",
                error_message=str(exc),
            )
            # No assistant message persisted on failure
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
