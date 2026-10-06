"""Unified AI orchestration: conversation + agent + knowledge + tools + LLM."""

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.agent import Agent
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
from app.services.agent_service import AgentService
from app.services.conversation_service import ConversationService, parse_kb_ids
from app.services.knowledge_service import KnowledgeBaseService
from app.services.llm_observability_service import create_llm_call_log, elapsed_ms, start_timer
from app.services.providers import ChatMessage, get_llm_provider
from app.services.providers.factory import get_llm_provider as _get_llm_provider
from app.services.rag_service import RAGService, RetrievalHit
from app.services.tool_registry import (
    MAX_TOOL_CALLS_PER_REQUEST,
    ToolExecutionContext,
    ToolRegistry,
)
from app.services.workspace_service import WorkspaceAccess
from app.utils.errors import AppException


@dataclass
class OrchestrationResult:
    user_message: Message
    assistant_message: Message
    hits: list[RetrievalHit]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def _title_from_content(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    if not cleaned:
        return "New conversation"
    return cleaned[:80] + ("…" if len(cleaned) > 80 else "")


def _resolve_provider(user: User, agent: Optional[Agent]):
    if agent and (agent.provider or agent.model_name):
        class _Overlay:
            pass

        overlay = _Overlay()
        overlay.id = user.id
        overlay.has_custom_llm_key = user.has_custom_llm_key
        overlay.llm_api_key_encrypted = user.llm_api_key_encrypted
        overlay.llm_provider = agent.provider or user.llm_provider
        overlay.llm_base_url = user.llm_base_url
        overlay.llm_model_name = agent.model_name or user.llm_model_name
        return _get_llm_provider(overlay)  # type: ignore[arg-type]
    return get_llm_provider(user)


def _build_messages(
    *,
    history: list[Message],
    user_content: str,
    hits: list[RetrievalHit],
    system_prompt: Optional[str] = None,
) -> list[ChatMessage]:
    base_prompt = (system_prompt or "").strip() or (
        "You are a helpful assistant for Xplore.ai. Answer clearly and concisely."
    )
    if hits:
        context_texts = [
            f"[Source passage {i}]:\n{hit.chunk.content}" for i, hit in enumerate(hits, 1)
        ]
        prompt = (
            f"{base_prompt}\n\n"
            "When reference material is provided, prefer it for factual answers. "
            "If the answer is not present, say so directly and do not invent details.\n\n"
            f"=== Reference material ===\n{chr(10).join(context_texts)}\n=== End reference material ==="
        )
    else:
        prompt = base_prompt

    messages: list[ChatMessage] = [ChatMessage(role="system", content=prompt)]
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

    def _load_agent(
        self,
        *,
        access: WorkspaceAccess,
        conversation: Conversation,
        agent_id: Optional[int],
    ) -> Optional[Agent]:
        resolved_id = agent_id if agent_id is not None else conversation.agent_id
        if resolved_id is None:
            return None
        access.require_permission("agents:read")
        agent = AgentService.get_for_workspace(
            self.db, agent_id=resolved_id, workspace_id=access.workspace.id
        )
        if not agent.is_enabled:
            raise AppException(
                code=10400,
                msg="The selected agent is disabled",
                status_code=400,
            )
        return agent

    def _resolve_kb_ids(
        self,
        *,
        access: WorkspaceAccess,
        conversation: Conversation,
        agent: Optional[Agent],
        use_knowledge: Optional[bool],
        knowledge_base_ids: Optional[list[int]],
    ) -> tuple[bool, list[int]]:
        # Explicit request overrides conversation, which overrides agent defaults
        if use_knowledge is False:
            return False, []

        if knowledge_base_ids is not None:
            if not knowledge_base_ids and use_knowledge is not True:
                # Explicit empty list with no force-enable → no retrieval unless use_knowledge True
                if use_knowledge is True:
                    access.require_permission("knowledge:read")
                    KnowledgeBaseService.ensure_default_for_workspace(
                        self.db, workspace=access.workspace
                    )
                    return True, []
                return False, []
            access.require_permission("knowledge:read")
            ConversationService._validate_knowledge_bases(
                self.db,
                workspace_id=access.workspace.id,
                knowledge_base_ids=knowledge_base_ids,
            )
            return True, knowledge_base_ids

        if use_knowledge is True or conversation.use_knowledge:
            access.require_permission("knowledge:read")
            kb_ids = parse_kb_ids(conversation.knowledge_base_ids)
            ConversationService._validate_knowledge_bases(
                self.db, workspace_id=access.workspace.id, knowledge_base_ids=kb_ids
            )
            KnowledgeBaseService.ensure_default_for_workspace(
                self.db, workspace=access.workspace
            )
            return True, kb_ids

        if agent is not None:
            agent_kb_ids = AgentService.knowledge_base_ids(agent)
            if agent_kb_ids:
                access.require_permission("knowledge:read")
                ConversationService._validate_knowledge_bases(
                    self.db,
                    workspace_id=access.workspace.id,
                    knowledge_base_ids=agent_kb_ids,
                )
                return True, agent_kb_ids

        return False, []

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
        return [
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
            for hit in hits
        ]

    async def _run_tool_loop(
        self,
        *,
        provider,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        access: WorkspaceAccess,
        user: User,
        agent: Optional[Agent],
        allowed_tool_names: list[str],
    ) -> tuple[str, list[dict[str, Any]], int, int, int]:
        """Multi-round tool calling with a hard cap. Returns final text + audit trail."""
        access.require_permission("tools:use")
        tool_audit: list[dict[str, Any]] = []
        prompt_tokens = completion_tokens = total_tokens = 0
        rounds = 0

        while rounds < MAX_TOOL_CALLS_PER_REQUEST:
            rounds += 1
            result = await provider.complete(
                messages,
                temperature=0.2,
                tools=tools,
                tool_choice="auto",
            )
            prompt_tokens += result.prompt_tokens
            completion_tokens += result.completion_tokens
            total_tokens += result.total_tokens

            if not result.tool_calls:
                return result.content, tool_audit, prompt_tokens, completion_tokens, total_tokens

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=result.content or None,
                    tool_calls=result.tool_calls,
                )
            )

            context = ToolExecutionContext(
                db=self.db,
                user_id=user.id,
                workspace_id=access.workspace.id,
                agent_id=agent.id if agent else None,
                allowed_tool_names=set(allowed_tool_names),
            )
            for tc in result.tool_calls:
                tool_result = await ToolRegistry.execute(
                    name=tc.name,
                    arguments=tc.arguments,
                    context=context,
                )
                tool_audit.append(
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "result": tool_result.content,
                        "success": tool_result.success,
                    }
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=tool_result.content,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )

        # Cap reached: one final completion without tools
        final = await provider.complete(messages, temperature=0.2)
        prompt_tokens += final.prompt_tokens
        completion_tokens += final.completion_tokens
        total_tokens += final.total_tokens
        return final.content, tool_audit, prompt_tokens, completion_tokens, total_tokens

    async def send_message(
        self,
        *,
        access: WorkspaceAccess,
        user: User,
        conversation_id: int,
        content: str,
        use_knowledge: Optional[bool] = None,
        knowledge_base_ids: Optional[list[int]] = None,
        agent_id: Optional[int] = None,
        top_k: int = 3,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> OrchestrationResult:
        access.require_permission("conversations:write")
        conversation = ConversationService.get_for_workspace(
            self.db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        agent = self._load_agent(access=access, conversation=conversation, agent_id=agent_id)
        if agent_id is not None and conversation.agent_id != agent_id:
            conversation.agent_id = agent.id if agent else None

        enabled, kb_ids = self._resolve_kb_ids(
            access=access,
            conversation=conversation,
            agent=agent,
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

        provider = _resolve_provider(user, agent)
        system_prompt = agent.system_prompt if agent else None
        llm_messages = _build_messages(
            history=history,
            user_content=content,
            hits=hits,
            system_prompt=system_prompt,
        )

        tool_names = AgentService.enabled_tool_names(agent)
        tools = ToolRegistry.openai_tools_for_names(
            tool_names, db=self.db, workspace_id=access.workspace.id
        )
        started_at = start_timer()
        tool_audit: list[dict[str, Any]] = []
        try:
            if tools and getattr(provider, "supports_tools", False):
                (
                    reply_text,
                    tool_audit,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                ) = await self._run_tool_loop(
                    provider=provider,
                    messages=llm_messages,
                    tools=tools,
                    access=access,
                    user=user,
                    agent=agent,
                    allowed_tool_names=tool_names,
                )
            else:
                result = await provider.complete(llm_messages, temperature=0.2)
                reply_text = result.content
                prompt_tokens = result.prompt_tokens
                completion_tokens = result.completion_tokens
                total_tokens = result.total_tokens

            assistant = Message(
                conversation_id=conversation.id,
                role=MESSAGE_ROLE_ASSISTANT,
                content=reply_text,
                status=MESSAGE_STATUS_COMPLETE,
                tool_calls_json=json.dumps(tool_audit, ensure_ascii=False) if tool_audit else None,
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
                response=reply_text,
                tool_calls=tool_audit or None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=elapsed_ms(started_at),
                status="success",
            )
            return OrchestrationResult(
                user_message=user_message,
                assistant_message=assistant,
                hits=hits,
                tool_calls=tool_audit,
            )
        except AppException:
            raise
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
        agent_id: Optional[int] = None,
        top_k: int = 3,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> AsyncIterator[str]:
        """SSE stream. Tool rounds (if any) run before token streaming of the final answer."""
        access.require_permission("conversations:write")
        conversation = ConversationService.get_for_workspace(
            self.db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        agent = self._load_agent(access=access, conversation=conversation, agent_id=agent_id)
        if agent_id is not None:
            conversation.agent_id = agent.id if agent else None

        enabled, kb_ids = self._resolve_kb_ids(
            access=access,
            conversation=conversation,
            agent=agent,
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

        provider = _resolve_provider(user, agent)
        system_prompt = agent.system_prompt if agent else None
        llm_messages = _build_messages(
            history=history,
            user_content=content,
            hits=hits,
            system_prompt=system_prompt,
        )
        tool_names = AgentService.enabled_tool_names(agent)
        tools = ToolRegistry.openai_tools_for_names(
            tool_names, db=self.db, workspace_id=access.workspace.id
        )
        started_at = start_timer()
        tool_audit: list[dict[str, Any]] = []
        full_response = ""

        try:
            # Tool rounds (non-stream) then stream final answer without tools
            if tools and getattr(provider, "supports_tools", False):
                (
                    _unused,
                    tool_audit,
                    _pt,
                    _ct,
                    _tt,
                ) = await self._run_tool_loop(
                    provider=provider,
                    messages=llm_messages,
                    tools=tools,
                    access=access,
                    user=user,
                    agent=agent,
                    allowed_tool_names=tool_names,
                )
                if tool_audit:
                    yield f"data: {json.dumps({'tool_calls': tool_audit}, ensure_ascii=False)}\n\n"
                # After tool loop, llm_messages already contains the final assistant text path
                # Re-stream: if last loop returned content without tools, we already have reply.
                # _run_tool_loop returns final text — stream that to client as chunks for UX.
                full_response = _unused
                for i in range(0, len(full_response), 24):
                    piece = full_response[i : i + 24]
                    yield f"data: {json.dumps({'content': piece}, ensure_ascii=False)}\n\n"
            else:
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
                tool_calls_json=json.dumps(tool_audit, ensure_ascii=False) if tool_audit else None,
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
                tool_calls=tool_audit or None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=elapsed_ms(started_at),
                status="success",
            )
            yield f"data: {json.dumps({'assistant_message_id': assistant.id, 'sources': self._citation_payload(hits), 'tool_calls': tool_audit}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except AppException as exc:
            yield f"data: {json.dumps({'error': exc.msg}, ensure_ascii=False)}\n\n"
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
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
