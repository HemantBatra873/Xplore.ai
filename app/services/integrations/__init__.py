from fastapi import status

from app.models.integration import INTEGRATION_TYPE_GITHUB, INTEGRATION_TYPE_MCP
from app.services.integrations.base import IntegrationAdapter
from app.services.integrations.github_adapter import GitHubIntegrationAdapter
from app.services.integrations.mcp_adapter import MCPIntegrationAdapter
from app.utils.errors import AppException

_ADAPTERS: dict[str, IntegrationAdapter] = {
    INTEGRATION_TYPE_MCP: MCPIntegrationAdapter(),
    INTEGRATION_TYPE_GITHUB: GitHubIntegrationAdapter(),
}


def get_adapter(integration_type: str) -> IntegrationAdapter:
    adapter = _ADAPTERS.get((integration_type or "").strip().lower())
    if adapter is None:
        raise AppException(
            code=10400,
            msg=f"Unsupported integration type '{integration_type}'",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return adapter


def supported_integration_types() -> list[str]:
    return sorted(_ADAPTERS.keys())
