"""Conversation isolation, persistence, and knowledge selection tests."""

from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.conversation import Message
from app.services.providers.base import LLMResult


def _register_and_login(client, suffix: str) -> Tuple[str, dict]:
    email = f"conv-{suffix}@example.com"
    password = "password123"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"convuser_{suffix}",
            "email": email,
            "password": password,
            "full_name": f"Conv User {suffix}",
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
    return response.json()[0]


def test_create_and_list_conversations(client):
    token, _ = _register_and_login(client, "list")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])

    created = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"title": "Planning", "use_knowledge": False},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "Planning"
    assert created.json()["workspace_id"] == ws["id"]

    listed = client.get("/api/v1/conversations/", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == created.json()["id"] for c in listed.json())


def test_user_cannot_access_other_workspace_conversation(client):
    token_a, _ = _register_and_login(client, "iso-a")
    token_b, _ = _register_and_login(client, "iso-b")
    ws_a = _default_workspace(client, token_a)
    created = client.post(
        "/api/v1/conversations/",
        headers=_auth(token_a, ws_a["id"]),
        json={"title": "Private"},
    )
    assert created.status_code == 201
    conv_id = created.json()["id"]

    forbidden = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers=_auth(token_b),
    )
    assert forbidden.status_code in (403, 404)

    forbidden_msgs = client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=_auth(token_b),
    )
    assert forbidden_msgs.status_code in (403, 404)


def test_cannot_select_foreign_knowledge_base(client):
    token_a, _ = _register_and_login(client, "kb-a")
    token_b, _ = _register_and_login(client, "kb-b")
    ws_a = _default_workspace(client, token_a)
    kb_a = client.get(
        "/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])
    ).json()[0]

    response = client.post(
        "/api/v1/conversations/",
        headers=_auth(token_b),
        json={"title": "Steal KB", "use_knowledge": True, "knowledge_base_ids": [kb_a["id"]]},
    )
    assert response.status_code in (400, 403, 404)


def test_send_message_persists_without_knowledge(client):
    token, _ = _register_and_login(client, "msg")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    conv = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"title": "Chat"},
    ).json()

    fake_result = LLMResult(
        content="Hello from the orchestrator",
        model="mock-model",
        provider="mock",
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
    )

    with patch(
        "app.services.ai_orchestrator.get_llm_provider"
    ) as mock_provider_factory:
        provider = mock_provider_factory.return_value
        provider.complete = AsyncMock(return_value=fake_result)
        response = client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            headers=headers,
            json={"content": "Hi there", "use_knowledge": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_message"]["content"] == "Hi there"
    assert payload["assistant_message"]["content"] == "Hello from the orchestrator"
    assert payload["sources"] == []

    detail = client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2


def test_failed_llm_does_not_persist_assistant(client, db_session):
    token, _ = _register_and_login(client, "fail")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    conv = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"title": "Fail chat"},
    ).json()

    with patch(
        "app.services.ai_orchestrator.get_llm_provider"
    ) as mock_provider_factory:
        provider = mock_provider_factory.return_value
        provider.complete = AsyncMock(side_effect=RuntimeError("provider down"))
        response = client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            headers=headers,
            json={"content": "Will fail"},
        )

    assert response.status_code >= 400
    messages = list(
        db_session.execute(
            select(Message).where(Message.conversation_id == conv["id"])
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    assert messages[0].role == "user"


def test_stream_empty_on_provider_error_leaves_no_assistant(client, db_session):
    token, _ = _register_and_login(client, "stream-fail")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    conv = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"title": "Stream fail"},
    ).json()

    async def failing_stream(*_a, **_k):
        if False:
            yield ""
        raise RuntimeError("stream broken")

    with patch(
        "app.services.ai_orchestrator.get_llm_provider"
    ) as mock_provider_factory:
        provider = mock_provider_factory.return_value
        provider.stream = failing_stream
        with client.stream(
            "POST",
            f"/api/v1/conversations/{conv['id']}/messages/stream",
            headers=headers,
            json={"content": "stream please"},
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
            assert "error" in body or "[DONE]" in body

    messages = list(
        db_session.execute(
            select(Message).where(Message.conversation_id == conv["id"])
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    assert messages[0].role == "user"


def test_llm_config_endpoint_does_not_return_api_key(client):
    token, _ = _register_and_login(client, "creds")
    me = client.get("/api/v1/users/me", headers=_auth(token))
    assert me.status_code == 200
    body = me.json()
    assert "llm_api_key" not in body
    assert "llm_api_key_encrypted" not in body
    assert "api_key" not in body
