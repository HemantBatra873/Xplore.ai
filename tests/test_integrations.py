"""Phase 6 integration isolation, credential protection, and ToolRegistry wiring."""

from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest

from app.services.integrations.base import (
    AdapterExecutionResult,
    DiscoveredTool,
    assert_safe_http_url,
    parse_registry_tool_name,
    registry_tool_name,
)
from app.services.tool_registry import ToolExecutionContext, ToolRegistry
from app.utils.errors import AppException


def _register_and_login(client, suffix: str) -> Tuple[str, dict]:
    email = f"integ-{suffix}@example.com"
    password = "password123"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"integuser_{suffix}",
            "email": email,
            "password": password,
            "full_name": f"Integ User {suffix}",
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


def _create_github_integration(client, token: str, workspace_id: int, name: str = "GH"):
    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.validate_config",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = client.post(
            "/api/v1/integrations/",
            headers=_auth(token, workspace_id),
            json={
                "type": "github",
                "name": name,
                "config": {},
                "credentials": {"access_token": "ghp_secret_token_do_not_leak"},
                "is_enabled": True,
            },
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_isolation_for_integrations(client):
    token_a, _ = _register_and_login(client, "iso-a")
    token_b, _ = _register_and_login(client, "iso-b")
    ws_a = _default_workspace(client, token_a)
    created = _create_github_integration(client, token_a, ws_a["id"], "Private GH")

    forbidden = client.get(
        f"/api/v1/integrations/{created['id']}",
        headers=_auth(token_b),
    )
    assert forbidden.status_code in (403, 404)

    listed = client.get("/api/v1/integrations/", headers=_auth(token_b))
    assert listed.status_code == 200
    assert all(row["id"] != created["id"] for row in listed.json())


def test_credentials_never_in_api_responses(client):
    token, _ = _register_and_login(client, "creds")
    ws = _default_workspace(client, token)
    created = _create_github_integration(client, token, ws["id"], "Creds GH")

    body = created
    serialized = str(body)
    assert "ghp_secret_token_do_not_leak" not in serialized
    assert "credentials" not in body or body.get("credentials") is None
    assert "credentials_encrypted" not in body
    assert body["has_credentials"] is True

    fetched = client.get(
        f"/api/v1/integrations/{created['id']}",
        headers=_auth(token, ws["id"]),
    )
    assert fetched.status_code == 200
    assert "ghp_secret_token_do_not_leak" not in fetched.text
    assert "credentials_encrypted" not in fetched.json()


def test_member_cannot_manage_integrations(client):
    token_owner, _ = _register_and_login(client, "own")
    token_member, member = _register_and_login(client, "mem")
    ws = _default_workspace(client, token_owner)
    invite = client.post(
        f"/api/v1/workspaces/{ws['id']}/members",
        headers=_auth(token_owner, ws["id"]),
        json={"user_id": member["id"], "role": "member"},
    )
    assert invite.status_code in (200, 201)

    denied = client.post(
        "/api/v1/integrations/",
        headers=_auth(token_member, ws["id"]),
        json={
            "type": "github",
            "name": "Nope",
            "credentials": {"access_token": "x"},
        },
    )
    assert denied.status_code == 403

    created = _create_github_integration(client, token_owner, ws["id"], "Owner GH")
    readable = client.get(
        f"/api/v1/integrations/{created['id']}",
        headers=_auth(token_member, ws["id"]),
    )
    assert readable.status_code == 200


def test_tool_discovery_normalizes_into_registry(client, db_session):
    token, _ = _register_and_login(client, "discover")
    ws = _default_workspace(client, token)
    created = _create_github_integration(client, token, ws["id"], "Discover GH")

    discovered = [
        DiscoveredTool(
            remote_name="search_repositories",
            description="Search repos",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
    ]
    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.discover_tools",
        new_callable=AsyncMock,
        return_value=discovered,
    ):
        refreshed = client.post(
            f"/api/v1/integrations/{created['id']}/refresh-tools",
            headers=_auth(token, ws["id"]),
        )
    assert refreshed.status_code == 200
    assert refreshed.json()["tool_count"] == 1

    tools = client.get(
        f"/api/v1/integrations/{created['id']}/tools",
        headers=_auth(token, ws["id"]),
    )
    assert tools.status_code == 200
    row = tools.json()[0]
    assert row["registry_name"] == registry_tool_name(created["id"], "search_repositories")
    assert row["remote_name"] == "search_repositories"

    definitions = ToolRegistry.list_definitions(db=db_session, workspace_id=ws["id"])
    names = {d.name for d in definitions}
    assert row["registry_name"] in names


def test_integration_tool_executes_through_tool_registry(client, db_session):
    import asyncio

    token, _ = _register_and_login(client, "exec")
    ws = _default_workspace(client, token)
    created = _create_github_integration(client, token, ws["id"], "Exec GH")
    registry_name = registry_tool_name(created["id"], "get_repository")

    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.discover_tools",
        new_callable=AsyncMock,
        return_value=[
            DiscoveredTool(
                remote_name="get_repository",
                description="Get repo",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
            )
        ],
    ):
        client.post(
            f"/api/v1/integrations/{created['id']}/refresh-tools",
            headers=_auth(token, ws["id"]),
        )

    async def _run():
        with patch(
            "app.services.integrations.github_adapter.GitHubIntegrationAdapter.execute",
            new_callable=AsyncMock,
            return_value=AdapterExecutionResult(
                content="[Untrusted external GitHub tool result]\nok",
                success=True,
            ),
        ):
            return await ToolRegistry.execute(
                name=registry_name,
                arguments={"owner": "octocat", "repo": "hello"},
                context=ToolExecutionContext(
                    db=db_session,
                    user_id=1,
                    workspace_id=ws["id"],
                    allowed_tool_names={registry_name},
                ),
            )

    result = asyncio.run(_run())
    assert result.success
    assert "ok" in result.content


def test_unauthorized_tool_not_enabled_for_agent(client, db_session):
    import asyncio

    token, _ = _register_and_login(client, "agent-tool")
    ws = _default_workspace(client, token)
    created = _create_github_integration(client, token, ws["id"], "Agent GH")
    registry_name = registry_tool_name(created["id"], "list_issues")

    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.discover_tools",
        new_callable=AsyncMock,
        return_value=[
            DiscoveredTool(
                remote_name="list_issues",
                description="Issues",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
            )
        ],
    ):
        client.post(
            f"/api/v1/integrations/{created['id']}/refresh-tools",
            headers=_auth(token, ws["id"]),
        )

    agent = client.post(
        "/api/v1/agents/",
        headers=_auth(token, ws["id"]),
        json={
            "name": "With GitHub",
            "system_prompt": "Use tools carefully.",
            "enabled_tools": [registry_name],
        },
    )
    assert agent.status_code == 201
    assert registry_name in agent.json()["enabled_tools"]

    async def _run():
        with pytest.raises(AppException) as exc:
            await ToolRegistry.execute(
                name=registry_name,
                arguments={"owner": "a", "repo": "b"},
                context=ToolExecutionContext(
                    db=db_session,
                    user_id=1,
                    workspace_id=ws["id"],
                    allowed_tool_names=set(),
                ),
            )
        assert exc.value.status_code == 403

    asyncio.run(_run())


def test_reject_arbitrary_url_and_private_host():
    with pytest.raises(AppException):
        assert_safe_http_url("ftp://evil.example/cmd")
    with pytest.raises(AppException):
        assert_safe_http_url("http://127.0.0.1/mcp", allow_private=False)
    with pytest.raises(AppException):
        assert_safe_http_url("http://169.254.169.254/latest/meta-data", allow_private=False)


def test_reject_external_tool_url_argument(client, db_session):
    import asyncio

    token, _ = _register_and_login(client, "ssrf-arg")
    ws = _default_workspace(client, token)
    created = _create_github_integration(client, token, ws["id"], "SSRF GH")
    registry_name = registry_tool_name(created["id"], "get_repository")

    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.discover_tools",
        new_callable=AsyncMock,
        return_value=[
            DiscoveredTool(
                remote_name="get_repository",
                description="Get repo",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
            )
        ],
    ):
        client.post(
            f"/api/v1/integrations/{created['id']}/refresh-tools",
            headers=_auth(token, ws["id"]),
        )

    async def _run():
        with pytest.raises(AppException) as exc:
            await ToolRegistry.execute(
                name=registry_name,
                arguments={
                    "owner": "a",
                    "repo": "b",
                    "url": "http://169.254.169.254/",
                },
                context=ToolExecutionContext(
                    db=db_session,
                    user_id=1,
                    workspace_id=ws["id"],
                    allowed_tool_names={registry_name},
                ),
            )
        assert exc.value.status_code == 400

    asyncio.run(_run())


def test_parse_registry_tool_name():
    assert parse_registry_tool_name("ext:12:search_repositories") == (12, "search_repositories")
    assert parse_registry_tool_name("calculate") is None
    assert parse_registry_tool_name("ext:bad:name") is None


def test_cross_workspace_tool_execution_rejected(client, db_session):
    import asyncio

    token_a, _ = _register_and_login(client, "xws-a")
    token_b, _ = _register_and_login(client, "xws-b")
    ws_a = _default_workspace(client, token_a)
    ws_b = _default_workspace(client, token_b)
    created = _create_github_integration(client, token_a, ws_a["id"], "XWS")
    registry_name = registry_tool_name(created["id"], "get_repository")

    with patch(
        "app.services.integrations.github_adapter.GitHubIntegrationAdapter.discover_tools",
        new_callable=AsyncMock,
        return_value=[
            DiscoveredTool(
                remote_name="get_repository",
                description="Get repo",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
            )
        ],
    ):
        client.post(
            f"/api/v1/integrations/{created['id']}/refresh-tools",
            headers=_auth(token_a, ws_a["id"]),
        )

    async def _run():
        with pytest.raises(AppException) as exc:
            await ToolRegistry.execute(
                name=registry_name,
                arguments={"owner": "a", "repo": "b"},
                context=ToolExecutionContext(
                    db=db_session,
                    user_id=1,
                    workspace_id=ws_b["id"],
                    allowed_tool_names={registry_name},
                ),
            )
        assert exc.value.status_code in (403, 404)

    asyncio.run(_run())
