"""Workspace foundation and cross-workspace isolation tests."""

from typing import Dict, Optional, Tuple

from sqlalchemy import select

from app.models.document import DOCUMENT_STATUS_READY, Document
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.services.workspace_service import WorkspaceService


def _register_and_login(client, suffix: str) -> Tuple[str, dict]:
    email = f"ws-{suffix}@example.com"
    password = "password123"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"wsuser_{suffix}",
            "email": email,
            "password": password,
            "full_name": f"Workspace User {suffix}",
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


def test_new_user_receives_personal_workspace(client):
    token, user = _register_and_login(client, "default")
    response = client.get("/api/v1/workspaces/", headers=_auth(token))
    assert response.status_code == 200
    workspaces = response.json()
    assert len(workspaces) >= 1
    assert workspaces[0]["role"] == "owner"
    assert workspaces[0]["created_by_id"] == user["id"]
    assert workspaces[0]["is_active"] is True


def test_user_cannot_access_another_users_workspace(client):
    token_a, _ = _register_and_login(client, "iso-a")
    token_b, _ = _register_and_login(client, "iso-b")

    ws_a = client.get("/api/v1/workspaces/", headers=_auth(token_a)).json()[0]
    forbidden = client.get(
        f"/api/v1/workspaces/{ws_a['id']}",
        headers=_auth(token_b),
    )
    assert forbidden.status_code == 403


def test_non_member_cannot_list_workspace_members(client):
    token_a, _ = _register_and_login(client, "mem-a")
    token_b, _ = _register_and_login(client, "mem-b")
    ws_a = client.get("/api/v1/workspaces/", headers=_auth(token_a)).json()[0]

    response = client.get(
        f"/api/v1/workspaces/{ws_a['id']}/members",
        headers=_auth(token_b),
    )
    assert response.status_code == 403


def test_member_roles_and_permissions(client, db_session):
    token_owner, owner = _register_and_login(client, "role-owner")
    token_member, member = _register_and_login(client, "role-member")
    ws = client.get("/api/v1/workspaces/", headers=_auth(token_owner)).json()[0]

    add = client.post(
        f"/api/v1/workspaces/{ws['id']}/members",
        headers=_auth(token_owner),
        json={"user_id": member["id"], "role": "member"},
    )
    assert add.status_code == 201
    assert add.json()["role"] == "member"

    # Member can read workspace but cannot update it
    get_ok = client.get(
        f"/api/v1/workspaces/{ws['id']}",
        headers=_auth(token_member, ws["id"]),
    )
    assert get_ok.status_code == 200

    patch_denied = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        headers=_auth(token_member, ws["id"]),
        json={"name": "Hijacked"},
    )
    assert patch_denied.status_code == 403

    # Owner can update
    patch_ok = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        headers=_auth(token_owner, ws["id"]),
        json={"name": "Owner Workspace"},
    )
    assert patch_ok.status_code == 200
    assert patch_ok.json()["name"] == "Owner Workspace"


def test_tasks_are_isolated_across_workspaces(client):
    token_a, _ = _register_and_login(client, "task-a")
    token_b, _ = _register_and_login(client, "task-b")
    ws_a = client.get("/api/v1/workspaces/", headers=_auth(token_a)).json()[0]
    ws_b = client.get("/api/v1/workspaces/", headers=_auth(token_b)).json()[0]

    created = client.post(
        "/api/v1/tasks/",
        headers=_auth(token_a, ws_a["id"]),
        json={"title": "Secret A task"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["workspace_id"] == ws_a["id"]

    # User B listing their own workspace must not see A's task
    list_b = client.get("/api/v1/tasks/", headers=_auth(token_b, ws_b["id"]))
    assert list_b.status_code == 200
    assert all(item["id"] != task_id for item in list_b.json())

    # User B cannot fetch A's task even with an explicit workspace header spoof of A
    spoof = client.get(
        f"/api/v1/tasks/{task_id}",
        headers=_auth(token_b, ws_a["id"]),
    )
    assert spoof.status_code == 403


def test_documents_are_isolated_across_workspaces(client, db_session):
    token_a, user_a = _register_and_login(client, "doc-a")
    token_b, _ = _register_and_login(client, "doc-b")
    ws_a = client.get("/api/v1/workspaces/", headers=_auth(token_a)).json()[0]
    kb_a = client.get("/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])).json()[0]

    doc = Document(
        owner_id=user_a["id"],
        workspace_id=ws_a["id"],
        knowledge_base_id=kb_a["id"],
        filename="private.txt",
        content="secret",
        status=DOCUMENT_STATUS_READY,
        chunks_count=0,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    denied = client.get(
        f"/api/v1/rag/documents/{doc.id}",
        headers=_auth(token_b),
    )
    assert denied.status_code in (403, 404)


def test_inactive_user_cannot_login(client, db_session):
    token, user = _register_and_login(client, "inactive")
    db_user = db_session.get(User, user["id"])
    db_user.is_active = False
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login",
        data={"username": user["email"], "password": "password123"},
    )
    assert login.status_code == 400
    assert login.json()["code"] == 1006


def test_existing_user_migration_helper_creates_workspace(db_session):
    """Simulate a pre-Phase-2 user row and ensure ensure_default_workspace backfills."""
    user = User(
        username="legacy_user",
        email="legacy_user@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.default_workspace_id is None
    workspace = WorkspaceService.ensure_default_workspace(db_session, user)
    db_session.refresh(user)

    assert workspace.id is not None
    assert user.default_workspace_id == workspace.id
    membership = db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
    ).scalar_one()
    assert membership.role == "owner"


def test_create_workspace_and_switch(client):
    token, _ = _register_and_login(client, "switch")
    created = client.post(
        "/api/v1/workspaces/",
        headers=_auth(token),
        json={"name": "Team Alpha", "slug": "team-alpha-switch"},
    )
    assert created.status_code == 201
    ws_id = created.json()["id"]

    listed = client.get("/api/v1/workspaces/", headers=_auth(token))
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert ws_id in ids

    task = client.post(
        "/api/v1/tasks/",
        headers=_auth(token, ws_id),
        json={"title": "Alpha task"},
    )
    assert task.status_code == 201
    assert task.json()["workspace_id"] == ws_id
