"""Knowledge base isolation and API security tests."""

from typing import Dict, Optional, Tuple

from sqlalchemy import func, select

from app.models.document import DOCUMENT_STATUS_READY, Document
from app.models.knowledge_base import KnowledgeBase
from app.services.knowledge_service import KnowledgeBaseService


def _register_and_login(client, suffix: str) -> Tuple[str, dict]:
    email = f"kb-{suffix}@example.com"
    password = "password123"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"kbuser_{suffix}",
            "email": email,
            "password": password,
            "full_name": f"KB User {suffix}",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return token, me.json()


def _auth(token: str, workspace_id: Optional[int] = None) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id is not None:
        headers["X-Workspace-Id"] = str(workspace_id)
    return headers


def _default_workspace(client, token: str) -> dict:
    response = client.get("/api/v1/workspaces/", headers=_auth(token))
    assert response.status_code == 200
    assert len(response.json()) >= 1
    return response.json()[0]


def test_new_workspace_has_default_knowledge_base(client):
    token, _ = _register_and_login(client, "default-kb")
    ws = _default_workspace(client, token)
    response = client.get("/api/v1/knowledge-bases/", headers=_auth(token, ws["id"]))
    assert response.status_code == 200
    kbs = response.json()
    assert len(kbs) >= 1
    assert any(kb["name"] == "General" for kb in kbs)


def test_user_cannot_access_knowledge_base_in_other_workspace(client):
    token_a, _ = _register_and_login(client, "kb-iso-a")
    token_b, _ = _register_and_login(client, "kb-iso-b")
    ws_a = _default_workspace(client, token_a)
    kb_a = client.get("/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])).json()[0]

    forbidden = client.get(
        f"/api/v1/knowledge-bases/{kb_a['id']}",
        headers=_auth(token_b),
    )
    assert forbidden.status_code in (403, 404)


def test_cannot_upload_document_to_foreign_knowledge_base(client):
    token_a, _ = _register_and_login(client, "kb-up-a")
    token_b, _ = _register_and_login(client, "kb-up-b")
    ws_a = _default_workspace(client, token_a)
    kb_a = client.get("/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])).json()[0]

    response = client.post(
        f"/api/v1/knowledge-bases/{kb_a['id']}/documents/upload",
        headers=_auth(token_b),
        files={"file": ("steal.txt", b"secret", "text/plain")},
    )
    assert response.status_code in (403, 404)


def test_documents_isolated_across_knowledge_bases(client, db_session):
    token, user = _register_and_login(client, "kb-docs")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])

    created = client.post(
        "/api/v1/knowledge-bases/",
        headers=headers,
        json={"name": "Private Notes", "description": "isolated"},
    )
    assert created.status_code == 201
    private_kb = created.json()

    general = client.get("/api/v1/knowledge-bases/", headers=headers).json()
    general_kb = next(kb for kb in general if kb["name"] == "General")

    doc = Document(
        owner_id=user["id"],
        workspace_id=ws["id"],
        knowledge_base_id=private_kb["id"],
        filename="secret.txt",
        content="top secret content",
        status=DOCUMENT_STATUS_READY,
        chunks_count=0,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    listed_general = client.get(
        f"/api/v1/knowledge-bases/{general_kb['id']}/documents",
        headers=headers,
    )
    assert listed_general.status_code == 200
    assert all(item["id"] != doc.id for item in listed_general.json())

    listed_private = client.get(
        f"/api/v1/knowledge-bases/{private_kb['id']}/documents",
        headers=headers,
    )
    assert listed_private.status_code == 200
    assert any(item["id"] == doc.id for item in listed_private.json())


def test_spoofed_document_id_cannot_cross_workspace(client, db_session):
    token_a, user_a = _register_and_login(client, "kb-spoof-a")
    token_b, _ = _register_and_login(client, "kb-spoof-b")
    ws_a = _default_workspace(client, token_a)
    kb_a = client.get(
        "/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])
    ).json()[0]

    doc = Document(
        owner_id=user_a["id"],
        workspace_id=ws_a["id"],
        knowledge_base_id=kb_a["id"],
        filename="a-only.txt",
        content="workspace a only",
        status=DOCUMENT_STATUS_READY,
        chunks_count=0,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    denied = client.get(
        f"/api/v1/knowledge-bases/{kb_a['id']}/documents/{doc.id}",
        headers=_auth(token_b),
    )
    assert denied.status_code in (403, 404)


def test_deleted_document_removed_from_kb_listing(client, monkeypatch):
    token, _ = _register_and_login(client, "kb-del")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    kb = client.get("/api/v1/knowledge-bases/", headers=headers).json()[0]

    class DummyTask:
        id = "task-kb-del-1"

    monkeypatch.setattr(
        "app.api.routers.knowledge.process_document_task.delay",
        lambda document_id: DummyTask(),
    )

    upload = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/upload",
        headers=headers,
        files={"file": ("gone.txt", b"temporary", "text/plain")},
    )
    assert upload.status_code == 202
    doc_id = upload.json()["id"]

    deleted = client.delete(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/{doc_id}",
        headers=headers,
    )
    assert deleted.status_code == 200

    listed = client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/documents",
        headers=headers,
    )
    assert listed.status_code == 200
    assert all(item["id"] != doc_id for item in listed.json())


def test_cannot_delete_last_knowledge_base(client):
    token, _ = _register_and_login(client, "kb-last")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    kbs = client.get("/api/v1/knowledge-bases/", headers=headers).json()
    assert len(kbs) == 1
    response = client.delete(
        f"/api/v1/knowledge-bases/{kbs[0]['id']}",
        headers=headers,
    )
    assert response.status_code == 400


def test_backfill_helper_creates_default_kb(db_session):
    from app.models.user import User
    from app.services.workspace_service import WorkspaceService

    user = User(
        username="kb_legacy",
        email="kb_legacy@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    workspace = WorkspaceService.ensure_default_workspace(db_session, user)
    kb = KnowledgeBaseService.ensure_default_for_workspace(
        db_session, workspace=workspace, created_by_id=user.id
    )
    assert kb.workspace_id == workspace.id
    assert kb.name == "General"
    count = int(
        db_session.execute(
            select(func.count(KnowledgeBase.id)).where(
                KnowledgeBase.workspace_id == workspace.id
            )
        ).scalar_one()
    )
    assert count >= 1
