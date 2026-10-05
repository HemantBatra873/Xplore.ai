import asyncio
import json
from dataclasses import dataclass
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import AsyncOpenAI
from redis.asyncio import Redis
from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.document import (
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    DOCUMENT_STATUS_QUEUED,
    DOCUMENT_STATUS_READY,
    Document,
    DocumentChunk,
)
from app.models.knowledge_base import KnowledgeBase

try:
    from sentence_transformers import CrossEncoder

    _reranker = None
except ImportError:
    CrossEncoder = None
    _reranker = None

_embedding_client = None

RRF_K = 60


@dataclass
class RetrievalHit:
    chunk: DocumentChunk
    document: Document
    knowledge_base: Optional[KnowledgeBase]
    score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None


def _get_embedding_client() -> AsyncOpenAI:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
        )
    return _embedding_client


def get_reranker():
    global _reranker
    if CrossEncoder is not None and _reranker is None:
        logger.info("==> Loading the BGE reranker model; this may take a moment...")
        _reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
    return _reranker


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50, separators=["\n\n", "\n", " ", ""]
        )

    def create_document_record(
        self,
        *,
        filename: str,
        content: str,
        owner_id: int,
        workspace_id: int,
        knowledge_base_id: int,
        file_type: str = "txt",
    ) -> Document:
        document = Document(
            owner_id=owner_id,
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_type=file_type,
            content=content,
            status=DOCUMENT_STATUS_QUEUED,
            chunks_count=0,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def attach_processing_task(
        self, *, document_id: int, workspace_id: int, task_id: str
    ) -> Document:
        document = self.get_document_for_workspace(
            document_id=document_id, workspace_id=workspace_id
        )
        if document is None:
            raise ValueError(f"Document {document_id} not found for workspace {workspace_id}")

        document.processing_task_id = task_id
        document.status = DOCUMENT_STATUS_QUEUED
        document.error_message = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_documents_for_workspace(self, *, workspace_id: int) -> List[Document]:
        stmt = (
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_document_for_workspace(
        self, *, document_id: int, workspace_id: int
    ) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_documents_for_knowledge_base(
        self, *, workspace_id: int, knowledge_base_id: int
    ) -> List[Document]:
        stmt = (
            select(Document)
            .where(
                Document.workspace_id == workspace_id,
                Document.knowledge_base_id == knowledge_base_id,
            )
            .order_by(Document.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_document_for_knowledge_base(
        self, *, document_id: int, workspace_id: int, knowledge_base_id: int
    ) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_document_by_task_id_for_workspace(
        self, *, task_id: str, workspace_id: int
    ) -> Optional[Document]:
        stmt = select(Document).where(
            Document.processing_task_id == task_id,
            Document.workspace_id == workspace_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def delete_document(self, *, document_id: int, workspace_id: int) -> Optional[Document]:
        document = self.get_document_for_workspace(
            document_id=document_id, workspace_id=workspace_id
        )
        if document is None:
            return None
        self.db.delete(document)
        self.db.commit()
        return document

    def has_ready_documents(
        self, *, workspace_id: int, knowledge_base_id: Optional[int] = None
    ) -> bool:
        stmt = select(func.count(Document.id)).where(
            Document.workspace_id == workspace_id,
            Document.status == DOCUMENT_STATUS_READY,
        )
        if knowledge_base_id is not None:
            stmt = stmt.where(Document.knowledge_base_id == knowledge_base_id)
        return bool(self.db.scalar(stmt))

    # Compatibility aliases used by older call sites/tests during Phase 2 transition
    def list_documents_for_user(self, *, owner_id: int) -> List[Document]:
        stmt = (
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_document_for_user(self, *, document_id: int, owner_id: int) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.owner_id == owner_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_document_by_task_id_for_user(
        self, *, task_id: str, owner_id: int
    ) -> Optional[Document]:
        stmt = select(Document).where(
            Document.processing_task_id == task_id,
            Document.owner_id == owner_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def mark_document_processing(
        self, *, document_id: int, task_id: Optional[str] = None
    ) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        document.status = DOCUMENT_STATUS_PROCESSING
        document.error_message = None
        if task_id:
            document.processing_task_id = task_id
        self.db.commit()
        self.db.refresh(document)
        return document

    def mark_document_failed(
        self, *, document_id: int, error_message: str, task_id: Optional[str] = None
    ) -> None:
        document = self.db.get(Document, document_id)
        if document is None:
            return

        document.status = DOCUMENT_STATUS_FAILED
        document.error_message = error_message[:2000]
        if task_id:
            document.processing_task_id = task_id
        self.db.commit()

    def requeue_document(
        self, *, document_id: int, workspace_id: int, task_id: str
    ) -> Document:
        document = self.get_document_for_workspace(
            document_id=document_id, workspace_id=workspace_id
        )
        if document is None:
            raise ValueError(f"Document {document_id} not found for workspace {workspace_id}")

        document.status = DOCUMENT_STATUS_QUEUED
        document.processing_task_id = task_id
        document.error_message = None
        document.chunks_count = 0
        self.db.commit()
        self.db.refresh(document)
        return document

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Call the embedding API to generate vectors"""
        try:
            # Collapse whitespace to reduce token noise
            texts = [text.replace("\n", " ") for text in texts]
            response = await _get_embedding_client().embeddings.create(
                input=texts, model=settings.EMBEDDING_MODEL_NAME
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            raise e

    async def process_document(
        self, *, document_id: int, task_id: Optional[str] = None
    ) -> Document:
        """Process an uploaded document by chunking, embedding, and storing its vectors."""
        document = self.mark_document_processing(document_id=document_id, task_id=task_id)

        chunks = self.text_splitter.split_text(document.content)
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        self.db.flush()

        if not chunks:
            document.chunks_count = 0
            document.status = DOCUMENT_STATUS_READY
            document.error_message = None
            self.db.commit()
            self.db.refresh(document)
            return document

        batch_size = 10
        embeddings: List[List[float]] = []
        for index in range(0, len(chunks), batch_size):
            batch_chunks = chunks[index : index + batch_size]
            batch_embeddings = await self.get_embeddings(batch_chunks)
            embeddings.extend(batch_embeddings)

        db_chunks = []
        for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunks.append(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=idx,
                    content=chunk_text,
                    embedding=embedding,
                )
            )

        self.db.add_all(db_chunks)
        document.chunks_count = len(db_chunks)
        document.status = DOCUMENT_STATUS_READY
        document.error_message = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def _document_chunk_filters(
        self,
        *,
        workspace_id: int,
        knowledge_base_id: Optional[int] = None,
        owner_id: Optional[int] = None,
    ) -> list:
        filters = [
            Document.workspace_id == workspace_id,
            Document.status == DOCUMENT_STATUS_READY,
        ]
        if knowledge_base_id is not None:
            filters.append(Document.knowledge_base_id == knowledge_base_id)
        if owner_id is not None:
            filters.append(Document.owner_id == owner_id)
        return filters

    def _reciprocal_rank_fusion(
        self, ranked_chunk_ids: list[list[int]]
    ) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for ranked in ranked_chunk_ids:
            for rank, chunk_id in enumerate(ranked, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    async def _vector_search_candidates(
        self,
        *,
        query_vector: list[float],
        filters: list,
        limit: int,
    ) -> list[tuple[DocumentChunk, Document, Optional[KnowledgeBase], float]]:
        distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = (
            select(DocumentChunk, Document, KnowledgeBase, distance_expr.label("distance"))
            .join(Document, DocumentChunk.document_id == Document.id)
            .outerjoin(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(*filters)
            .order_by(distance_expr)
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        results: list[tuple[DocumentChunk, Document, Optional[KnowledgeBase], float]] = []
        for chunk, document, kb, distance in rows:
            dist = float(distance) if distance is not None else 1.0
            vector_score = max(0.0, 1.0 - dist)
            results.append((chunk, document, kb, vector_score))
        return results

    def _keyword_search_candidates(
        self,
        *,
        query: str,
        filters: list,
        limit: int,
    ) -> list[tuple[DocumentChunk, Document, Optional[KnowledgeBase], float]]:
        tsq = func.plainto_tsquery("english", query)
        content_tsv = literal_column("document_chunks.content_tsv")
        rank_expr = func.ts_rank(content_tsv, tsq).label("keyword_score")
        stmt = (
            select(DocumentChunk, Document, KnowledgeBase, rank_expr)
            .join(Document, DocumentChunk.document_id == Document.id)
            .outerjoin(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(*filters, content_tsv.bool_op("@@")(tsq))
            .order_by(rank_expr.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [
            (chunk, document, kb, float(keyword_score) if keyword_score is not None else 0.0)
            for chunk, document, kb, keyword_score in rows
        ]

    async def retrieve_with_citations(
        self,
        *,
        query: str,
        workspace_id: int,
        top_k: int = 3,
        knowledge_base_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> List[RetrievalHit]:
        if not self.has_ready_documents(
            workspace_id=workspace_id, knowledge_base_id=knowledge_base_id
        ):
            return []

        query_embeddings = await self.get_embeddings([query])
        query_vector = query_embeddings[0]
        filters = self._document_chunk_filters(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
        )

        vector_limit = settings.RAG_VECTOR_CANDIDATES
        vector_rows = await self._vector_search_candidates(
            query_vector=query_vector, filters=filters, limit=vector_limit
        )
        vector_ranked = [row[0].id for row in vector_rows]

        keyword_rows: list[tuple[DocumentChunk, Document, Optional[KnowledgeBase], float]] = []
        keyword_ranked: list[int] = []
        use_hybrid = enable_hybrid is not False and settings.RAG_ENABLE_HYBRID
        dialect = self.db.get_bind().dialect.name
        if use_hybrid and dialect == "postgresql":
            try:
                keyword_rows = self._keyword_search_candidates(
                    query=query,
                    filters=filters,
                    limit=settings.RAG_KEYWORD_CANDIDATES,
                )
                keyword_ranked = [row[0].id for row in keyword_rows]
            except Exception as exc:
                logger.warning(f"Hybrid keyword search failed, using vector-only: {exc}")

        rank_lists = [vector_ranked]
        if keyword_ranked:
            rank_lists.append(keyword_ranked)
        fused = self._reciprocal_rank_fusion(rank_lists)

        meta: dict[int, tuple[DocumentChunk, Document, Optional[KnowledgeBase], Optional[float], Optional[float]]] = {}
        for chunk, document, kb, vector_score in vector_rows:
            meta[chunk.id] = (chunk, document, kb, vector_score, None)
        for chunk, document, kb, keyword_score in keyword_rows:
            if chunk.id in meta:
                existing = meta[chunk.id]
                meta[chunk.id] = (existing[0], existing[1], existing[2], existing[3], keyword_score)
            else:
                meta[chunk.id] = (chunk, document, kb, None, keyword_score)

        recall_k = max(top_k * 3, top_k)
        fused_ids = [chunk_id for chunk_id, _ in fused[:recall_k]]
        if not fused_ids:
            return []

        candidates: list[RetrievalHit] = []
        for chunk_id, rrf_score in fused[:recall_k]:
            if chunk_id not in meta:
                continue
            chunk, document, kb, vector_score, keyword_score = meta[chunk_id]
            candidates.append(
                RetrievalHit(
                    chunk=chunk,
                    document=document,
                    knowledge_base=kb,
                    score=rrf_score,
                    vector_score=vector_score,
                    keyword_score=keyword_score,
                )
            )

        do_rerank = enable_rerank is not False and settings.RAG_ENABLE_RERANK
        reranker = get_reranker() if do_rerank else None
        if reranker is not None and candidates:
            logger.info(f"==> Reranking {len(candidates)} candidate chunks with BGE-Reranker...")
            pairs = [[query, hit.chunk.content] for hit in candidates]
            rerank_scores = await self._predict_rerank_scores(reranker, pairs)
            for hit, rerank_score in zip(candidates, rerank_scores):
                hit.score = float(rerank_score)
            candidates.sort(key=lambda h: h.score, reverse=True)
        elif do_rerank and reranker is None:
            logger.warning("sentence-transformers is unavailable, so reranking is skipped.")

        return candidates[:top_k]

    async def retrieve_relevant_chunks(
        self,
        *,
        query: str,
        workspace_id: int,
        top_k: int = 3,
        owner_id: Optional[int] = None,
        knowledge_base_id: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
        enable_hybrid: Optional[bool] = None,
    ) -> List[DocumentChunk]:
        """Retrieve the most relevant document chunks (compat wrapper around retrieve_with_citations)."""
        hits = await self.retrieve_with_citations(
            query=query,
            workspace_id=workspace_id,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
            enable_rerank=enable_rerank,
            enable_hybrid=enable_hybrid,
        )
        return [hit.chunk for hit in hits]

    async def _predict_rerank_scores(self, reranker, pairs: list[list[str]]) -> list[float]:
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(None, reranker.predict, pairs)
        return list(scores)


SESSION_PREFIX = "rag_session"
SESSION_TTL = 3600


async def _get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def load_session_history(user_id: int, session_id: str) -> list[dict]:
    key = f"{SESSION_PREFIX}:{user_id}:{session_id}"
    r = await _get_redis()
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return []


async def save_session_history(user_id: int, session_id: str, history: list[dict]):
    key = f"{SESSION_PREFIX}:{user_id}:{session_id}"
    r = await _get_redis()
    await r.set(key, json.dumps(history, ensure_ascii=False), ex=SESSION_TTL)


async def append_session_message(user_id: int, session_id: str, role: str, content: str):
    history = await load_session_history(user_id, session_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        history = history[-20:]
    await save_session_history(user_id, session_id, history)
