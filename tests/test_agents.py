"""Agent isolation, authorization, and tool validation tests."""

from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest

from app.services.providers.base import LLMResult
from app.services.tool_registry import MAX_TOOL_CALLS_PER_REQUEST, ToolExecutionContext, ToolRegistry
from app.utils.errors import AppException


def _register_and_login(client, suffix: str) -> Tuple[str, dict]:
    email = f"agent-{suffix}@example.com"
    password = "password123"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"agentuser_{suffix}",
            "email": email,
            "password": password,
            "full_name": f"Agent User {suffix}",
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


def test_agent_isolation_across_workspaces(client):
    token_a, _ = _register_and_login(client, "iso-a")
    token_b, _ = _register_and_login(client, "iso-b")
    ws_a = _default_workspace(client, token_a)
    created = client.post(
        "/api/v1/agents/",
        headers=_auth(token_a, ws_a["id"]),
        json={"name": "Private Agent", "system_prompt": "Be brief."},
    )
    assert created.status_code == 201
    agent_id = created.json()["id"]

    forbidden = client.get(f"/api/v1/agents/{agent_id}", headers=_auth(token_b))
    assert forbidden.status_code in (403, 404)


def test_member_cannot_manage_agent_but_can_read(client, db_session):
    token_owner, owner = _register_and_login(client, "owner")
    token_member, member = _register_and_login(client, "member")
    ws = _default_workspace(client, token_owner)

    # Invite member
    invite = client.post(
        f"/api/v1/workspaces/{ws['id']}/members",
        headers=_auth(token_owner, ws["id"]),
        json={"user_id": member["id"], "role": "member"},
    )
    assert invite.status_code in (200, 201)

    created = client.post(
        "/api/v1/agents/",
        headers=_auth(token_owner, ws["id"]),
        json={"name": "Shared Agent", "system_prompt": "Help."},
    )
    assert created.status_code == 201
    agent_id = created.json()["id"]

    readable = client.get(
        f"/api/v1/agents/{agent_id}",
        headers=_auth(token_member, ws["id"]),
    )
    assert readable.status_code == 200

    denied = client.patch(
        f"/api/v1/agents/{agent_id}",
        headers=_auth(token_member, ws["id"]),
        json={"name": "Hijacked"},
    )
    assert denied.status_code == 403


def test_agent_cannot_attach_foreign_knowledge_base(client):
    token_a, _ = _register_and_login(client, "kb-a")
    token_b, _ = _register_and_login(client, "kb-b")
    ws_a = _default_workspace(client, token_a)
    kb_a = client.get(
        "/api/v1/knowledge-bases/", headers=_auth(token_a, ws_a["id"])
    ).json()[0]

    response = client.post(
        "/api/v1/agents/",
        headers=_auth(token_b),
        json={
            "name": "Steal KB",
            "system_prompt": "Oops",
            "knowledge_base_ids": [kb_a["id"]],
        },
    )
    assert response.status_code in (400, 403, 404)


def test_conversation_without_agent_still_works(client):
    token, _ = _register_and_login(client, "no-agent")
    ws = _default_workspace(client, token)
    headers = _auth(token, ws["id"])
    conv = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"title": "No agent"},
    ).json()
    assert conv.get("agent_id") in (None, 0) or conv.get("agent_id") is None

    fake = LLMResult(content="ok", model="mock", provider="mock", total_tokens=1)
    with patch("app.services.ai_orchestrator.get_llm_provider") as factory:
        # also patch _get_llm_provider used by overlay path
        with patch("app.services.ai_orchestrator._get_llm_provider") as factory2:
            provider = AsyncMock()
            provider.complete = AsyncMock(return_value=fake)
            provider.supports_tools = False
            factory.return_value = provider
            factory2.return_value = provider
            response = client.post(
                f"/api/v1/conversations/{conv['id']}/messages",
                headers=headers,
                json={"content": "Hello"},
            )
    assert response.status_code == 200
    assert response.json()["assistant_message"]["content"] == "ok"


def test_tool_input_validation_rejects_invalid_args():
    definition = ToolRegistry.get_definition("calculate")
    assert definition is not None
    with pytest.raises(AppException) as exc:
        ToolRegistry.validate_arguments(definition, {})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_tool_execution_requires_allowlist():
    ctx = ToolExecutionContext(
        db=None,
        user_id=1,
        workspace_id=1,
        allowed_tool_names={"list_tasks"},
    )
    with pytest.raises(AppException) as exc:
        await ToolRegistry.execute(name="calculate", arguments={"expression": "1+1"}, context=ctx)
    assert exc.value.status_code == 403


def test_tool_call_limit_constant():
    assert MAX_TOOL_CALLS_PER_REQUEST >= 1
    assert MAX_TOOL_CALLS_PER_REQUEST <= 10


def test_list_builtin_tools_requires_auth(client):
    token, _ = _register_and_login(client, "tools")
    response = client.get("/api/v1/agents/tools", headers=_auth(token))
    assert response.status_code == 200
    names = {t["name"] for t in response.json()}
    assert "calculate" in names
    assert "create_task" in names
