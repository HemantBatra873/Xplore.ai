from unittest.mock import AsyncMock, MagicMock, patch

from app.models.conversation import Message
from app.services.ai_orchestrator import AIOrchestrator, OrchestrationResult


def _auth_headers(client, suffix: str) -> dict:
    client.post(
        "/api/v1/users/",
        json={
            "username": f"chat_{suffix}",
            "email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": f"{suffix}@example.com", "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_chat_rate_limiting(client):
    headers = _auth_headers(client, "ratelimit")

    assistant = MagicMock(spec=Message)
    assistant.content = "Mocked Reply"
    fake_result = OrchestrationResult(
        user_message=MagicMock(spec=Message),
        assistant_message=assistant,
        hits=[],
        tool_calls=[],
    )

    with patch.object(
        AIOrchestrator, "send_message", new_callable=AsyncMock, return_value=fake_result
    ):
        status_codes = []
        for _ in range(25):
            response = client.post(
                "/api/v1/chat/", headers=headers, json={"message": "hello", "stream": False}
            )
            status_codes.append(response.status_code)

        assert 429 in status_codes
        assert status_codes.count(200) <= 20
        assert status_codes.count(429) >= 5


def test_chat_sse_stream(client):
    headers = _auth_headers(client, "sse")

    async def mock_stream(*args, **kwargs):
        yield 'data: {"content": "Hello"}\n\n'
        yield "data: [DONE]\n\n"

    with patch.object(AIOrchestrator, "stream_message", mock_stream):
        with client.stream(
            "POST", "/api/v1/chat/", headers=headers, json={"message": "hello", "stream": True}
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            content = response.read().decode("utf-8")
            assert 'data: {"content": "Hello"}' in content
            assert "data: [DONE]" in content
