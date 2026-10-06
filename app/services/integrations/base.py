"""Integration adapter abstractions and security helpers."""

from __future__ import annotations

import ipaddress
import json
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import status

from app.utils.errors import AppException

MAX_EXTERNAL_RESPONSE_CHARS = 20_000
MAX_DISCOVERED_TOOLS = 100


@dataclass
class DiscoveredTool:
    remote_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterExecutionResult:
    content: str
    success: bool = True
    error: Optional[str] = None


class IntegrationAdapter(ABC):
    """Provider-neutral integration backend."""

    integration_type: str

    @abstractmethod
    async def validate_config(self, config: dict[str, Any], credentials: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def discover_tools(
        self, config: dict[str, Any], credentials: dict[str, Any]
    ) -> list[DiscoveredTool]:
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        *,
        remote_name: str,
        arguments: dict[str, Any],
        config: dict[str, Any],
        credentials: dict[str, Any],
    ) -> AdapterExecutionResult:
        raise NotImplementedError


def registry_tool_name(integration_id: int, remote_name: str) -> str:
    safe_remote = (remote_name or "").strip().replace(" ", "_")
    return f"ext:{integration_id}:{safe_remote}"


def parse_registry_tool_name(name: str) -> Optional[tuple[int, str]]:
    if not name.startswith("ext:"):
        return None
    parts = name.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


def truncate_external_content(content: str) -> str:
    text = content or ""
    if len(text) <= MAX_EXTERNAL_RESPONSE_CHARS:
        return text
    return text[:MAX_EXTERNAL_RESPONSE_CHARS] + "\n...[truncated untrusted external content]"


def assert_safe_http_url(
    url: str,
    *,
    allow_private: bool = False,
    allowed_hosts: Optional[set[str]] = None,
) -> str:
    """Reject non-HTTP(S) URLs and optional private/link-local targets (SSRF guard)."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise AppException(
            code=10400,
            msg="Integration URL must use http or https",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not parsed.hostname:
        raise AppException(
            code=10400,
            msg="Integration URL must include a hostname",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    host = parsed.hostname.lower()
    if allowed_hosts is not None and host not in allowed_hosts:
        raise AppException(
            code=10400,
            msg=f"Host '{host}' is not allowed for this integration type",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if host in {"localhost", "metadata.google.internal"} and not allow_private:
        raise AppException(
            code=10400,
            msg="Private/local hosts are not allowed unless explicitly enabled",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise AppException(
            code=10400,
            msg=f"Unable to resolve host '{host}'",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if not allow_private:
        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise AppException(
                    code=10400,
                    msg="Resolved address is not publicly routable; set allow_private=true for trusted local MCP only",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
    return url.strip()


def loads_json_object(raw: Optional[str], *, field_name: str = "config") -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppException(
            code=10422,
            msg=f"Invalid JSON for {field_name}",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not isinstance(data, dict):
        raise AppException(
            code=10422,
            msg=f"{field_name} must be a JSON object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return data
