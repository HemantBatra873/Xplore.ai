"""
RAG service unit tests (service layer, not HTTP).
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from app.models.document import (
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    DOCUMENT_STATUS_QUEUED,
    DOCUMENT_STATUS_READY,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.models.workspace import Workspace
from app.services.knowledge_service import KnowledgeBaseService
from app.services.rag_service import RAGService
from app.services.workspace_service import WorkspaceService

_owner_counter = 99000

_MAX_TEST_USER_ID = 99020


def _ensure_test_users_exist(db):
    existing = set(
        row[0]
        for row in db.execute(
            text("SELECT id FROM users WHERE id >= :min_id"),
            {"min_id": 99001},
        ).fetchall()
    )
    for uid in range(99001, _MAX_TEST_USER_ID + 1):
        if uid not in existing:
            db.add(
                User(
                    id=uid,
                    username=f"ragtest_{uid}",
                    email=f"ragtest_{uid}@example.com",
                    hashed_password="hashed",
                    is_active=True,
                )
            )
    db.commit()
    for uid in range(99001, _MAX_TEST_USER_ID + 1):
        user = db.get(User, uid)
        if user is not None and user.default_workspace_id is None:
            WorkspaceService.create_personal_workspace(db, user)


def _ws(db, owner_id: int) -> int:
    user = db.get(User, owner_id)
    if user is None:
        raise ValueError(f"User {owner_id} not found")
    if user.default_workspace_id is None:
        WorkspaceService.create_personal_workspace(db, user)
        db.refresh(user)
    return user.default_workspace_id


def _kb(db, workspace_id: int) -> int:
    workspace = db.get(Workspace, workspace_id)
    kb = KnowledgeBaseService.ensure_default_for_workspace(db, workspace=workspace)
    return kb.id


def _create_doc(svc, db, *, owner_id: int, filename: str, content: str, workspace_id: int | None = None):
    ws = workspace_id if workspace_id is not None else _ws(db, owner_id)
    return svc.create_document_record(
        filename=filename,
        content=content,
        owner_id=owner_id,
        workspace_id=ws,
        knowledge_base_id=_kb(db, ws),
    )


@pytest.fixture(autouse=True)
def _setup_rag_test_users(db_session):
    _ensure_test_users_exist(db_session)
    yield


def _next_owner():
    global _owner_counter
    _owner_counter += 1
    return _owner_counter


class TestRAGDocumentCreate:
    def test_create_document_record(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(
            svc, db_session, owner_id=owner, filename="test.txt", content="hello world"
        )
        assert doc.id is not None
        assert doc.filename == "test.txt"
        assert doc.status == DOCUMENT_STATUS_QUEUED
        assert doc.chunks_count == 0

    def test_attach_processing_task(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="a.txt", content="c")
        updated = svc.attach_processing_task(
            document_id=doc.id, workspace_id=_ws(db_session, owner), task_id="task-123"
        )
        assert updated.processing_task_id == "task-123"
        assert updated.status == DOCUMENT_STATUS_QUEUED

    def test_attach_processing_task_wrong_owner_raises(self, db_session):
        owner = _next_owner()
        other = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="a.txt", content="c")
        with pytest.raises(ValueError):
            svc.attach_processing_task(
                document_id=doc.id, workspace_id=_ws(db_session, other), task_id="task-x"
            )


class TestRAGDocumentQuery:
    def test_list_documents_for_user(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        _create_doc(svc, db_session, owner_id=owner, filename="a.txt", content="a")
        _create_doc(svc, db_session, owner_id=owner, filename="b.txt", content="b")
        docs = svc.list_documents_for_user(owner_id=owner)
        assert len(docs) == 2

    def test_list_documents_user_isolation(self, db_session):
        owner_a = _next_owner()
        owner_b = _next_owner()
        svc = RAGService(db_session)
        _create_doc(svc, db_session, owner_id=owner_a, filename="user1.txt", content="1")
        _create_doc(svc, db_session, owner_id=owner_b, filename="user2.txt", content="2")
        assert len(svc.list_documents_for_user(owner_id=owner_a)) == 1
        assert len(svc.list_documents_for_user(owner_id=owner_b)) == 1

    def test_list_documents_empty_for_new_owner(self, db_session):
        svc = RAGService(db_session)
        docs = svc.list_documents_for_user(owner_id=99999)
        assert docs == []

    def test_get_document_for_user(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="f.txt", content="c")
        found = svc.get_document_for_user(document_id=doc.id, owner_id=owner)
        assert found is not None
        assert found.filename == "f.txt"

    def test_get_document_not_found(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        assert svc.get_document_for_user(document_id=99999, owner_id=owner) is None

    def test_get_document_by_task_id(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="t.txt", content="c")
        svc.attach_processing_task(
            document_id=doc.id, workspace_id=_ws(db_session, owner), task_id="celery-abc"
        )
        found = svc.get_document_by_task_id_for_user(task_id="celery-abc", owner_id=owner)
        assert found is not None
        assert found.id == doc.id

    def test_has_ready_documents_false_initially(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        _create_doc(svc, db_session, owner_id=owner, filename="q.txt", content="q")
        assert svc.has_ready_documents(workspace_id=_ws(db_session, owner)) is False


class TestRAGDocumentStatusTransitions:
    def test_mark_document_processing(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="p.txt", content="p")
        updated = svc.mark_document_processing(document_id=doc.id)
        assert updated.status == DOCUMENT_STATUS_PROCESSING

    def test_mark_document_failed(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="f.txt", content="f")
        svc.mark_document_failed(document_id=doc.id, error_message="embedding error")
        db_session.refresh(doc)
        assert doc.status == DOCUMENT_STATUS_FAILED
        assert doc.error_message == "embedding error"

    def test_requeue_document(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="r.txt", content="r")
        updated = svc.requeue_document(
            document_id=doc.id, workspace_id=_ws(db_session, owner), task_id="retry-1"
        )
        assert updated.status == DOCUMENT_STATUS_QUEUED
        assert updated.processing_task_id == "retry-1"
        assert updated.error_message is None

    def test_requeue_document_wrong_owner_raises(self, db_session):
        owner = _next_owner()
        other = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="r2.txt", content="r2")
        with pytest.raises(ValueError):
            svc.requeue_document(
                document_id=doc.id, workspace_id=_ws(db_session, other), task_id="retry-x"
            )


class TestRAGDocumentProcessing:
    def test_process_document_empty_content(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(svc, db_session, owner_id=owner, filename="empty.txt", content="")
        processed = asyncio.run(svc.process_document(document_id=doc.id))
        assert processed.status == DOCUMENT_STATUS_READY
        assert processed.chunks_count == 0

    def test_process_document_with_content(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        content = "Artificial intelligence is a branch of computer science.\nIt aims to build systems that mimic human intelligence."
        doc = _create_doc(svc, db_session, owner_id=owner, filename="ai.txt", content=content)

        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        with patch.object(svc, "get_embeddings", side_effect=fake_embeddings):
            processed = asyncio.run(svc.process_document(document_id=doc.id))
        assert processed.status == DOCUMENT_STATUS_READY
        assert processed.chunks_count > 0


class TestRAGRetrievalIsolation:
    def _process_with_fake_embeddings(self, svc, doc_id: int):
        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        with patch.object(svc, "get_embeddings", side_effect=fake_embeddings):
            return asyncio.run(svc.process_document(document_id=doc_id))

    def test_retrieve_empty_for_other_workspace(self, db_session):
        owner_a = _next_owner()
        owner_b = _next_owner()
        svc = RAGService(db_session)
        doc = _create_doc(
            svc, db_session, owner_id=owner_a, filename="secret.txt", content="workspace a secret material"
        )
        self._process_with_fake_embeddings(svc, doc.id)
        ws_a = _ws(db_session, owner_a)
        ws_b = _ws(db_session, owner_b)
        assert svc.has_ready_documents(workspace_id=ws_a) is True
        assert svc.has_ready_documents(workspace_id=ws_b) is False

        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        with patch.object(svc, "get_embeddings", side_effect=fake_embeddings):
            hits = asyncio.run(
                svc.retrieve_with_citations(
                    query="secret material",
                    workspace_id=ws_b,
                    top_k=3,
                    enable_rerank=False,
                    enable_hybrid=False,
                )
            )
        assert hits == []

    def test_retrieve_filters_by_knowledge_base(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        ws_id = _ws(db_session, owner)
        general_kb = _kb(db_session, ws_id)

        other_kb = KnowledgeBase(
            workspace_id=ws_id,
            name="Other KB",
            description="isolated",
            created_by_id=owner,
        )
        db_session.add(other_kb)
        db_session.commit()
        db_session.refresh(other_kb)

        doc = svc.create_document_record(
            filename="only-other.txt",
            content="unique phrase in other knowledge base",
            owner_id=owner,
            workspace_id=ws_id,
            knowledge_base_id=other_kb.id,
        )
        self._process_with_fake_embeddings(svc, doc.id)

        assert svc.has_ready_documents(workspace_id=ws_id, knowledge_base_id=other_kb.id) is True
        assert svc.has_ready_documents(workspace_id=ws_id, knowledge_base_id=general_kb) is False

        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        with patch.object(svc, "get_embeddings", side_effect=fake_embeddings):
            hits = asyncio.run(
                svc.retrieve_with_citations(
                    query="unique phrase",
                    workspace_id=ws_id,
                    knowledge_base_id=general_kb,
                    top_k=3,
                    enable_rerank=False,
                    enable_hybrid=False,
                )
            )
        assert hits == []

    def test_deleted_document_excluded_from_retrieval(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        ws_id = _ws(db_session, owner)
        doc = _create_doc(
            svc, db_session, owner_id=owner, filename="temp.txt", content="temporary retrieval content"
        )
        self._process_with_fake_embeddings(svc, doc.id)
        assert svc.has_ready_documents(workspace_id=ws_id) is True
        svc.delete_document(document_id=doc.id, workspace_id=ws_id)
        assert svc.has_ready_documents(workspace_id=ws_id) is False

        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        with patch.object(svc, "get_embeddings", side_effect=fake_embeddings):
            hits = asyncio.run(
                svc.retrieve_with_citations(
                    query="temporary retrieval",
                    workspace_id=ws_id,
                    top_k=3,
                    enable_rerank=False,
                    enable_hybrid=False,
                )
            )
        assert hits == []

    def test_retrieve_with_citations_includes_source_metadata(self, db_session):
        owner = _next_owner()
        svc = RAGService(db_session)
        ws_id = _ws(db_session, owner)
        kb_id = _kb(db_session, ws_id)
        doc = _create_doc(
            svc,
            db_session,
            owner_id=owner,
            filename="cite-me.txt",
            content="Citation metadata should include this document name and excerpt text.",
        )
        self._process_with_fake_embeddings(svc, doc.id)

        from app.models.document import DocumentChunk

        chunk = db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        ).scalar_one()

        async def fake_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]

        async def fake_vector_search(*, query_vector, filters, limit):
            kb = db_session.get(KnowledgeBase, kb_id)
            return [(chunk, doc, kb, 0.9)]

        with (
            patch.object(svc, "get_embeddings", side_effect=fake_embeddings),
            patch.object(svc, "_vector_search_candidates", side_effect=fake_vector_search),
        ):
            hits = asyncio.run(
                svc.retrieve_with_citations(
                    query="Citation metadata",
                    workspace_id=ws_id,
                    knowledge_base_id=kb_id,
                    top_k=3,
                    enable_rerank=False,
                    enable_hybrid=False,
                )
            )
        assert len(hits) == 1
        assert hits[0].document.filename == "cite-me.txt"
        assert hits[0].knowledge_base is not None
        assert hits[0].knowledge_base.id == kb_id
        assert hits[0].chunk.id == chunk.id
        assert hits[0].score is not None
