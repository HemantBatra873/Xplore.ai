"""Internal tool abstraction over the in-process MCPService registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import status
from pydantic import BaseModel, ValidationError, create_model
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.services.mcp_service import MCPService
from app.utils.errors import AppException

# Maximum tool round-trips per orchestration request
MAX_TOOL_CALLS_PER_REQUEST = 5


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    requires_db: bool = False
    requires_user: bool = False
    requires_workspace: bool = False
    enabled: bool = True
    openai_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionContext:
    db: Optional[Session]
    user_id: Optional[int]
    workspace_id: Optional[int]
    agent_id: Optional[int] = None
    allowed_tool_names: Optional[set[str]] = None


@dataclass
class ToolResult:
    name: str
    content: str
    success: bool = True
    error: Optional[str] = None


class ToolRegistry:
    """Discovery and controlled execution for built-in tools."""

    @classmethod
    def list_definitions(cls) -> list[ToolDefinition]:
        handlers = {h["name"]: h for h in MCPService.list_handlers()}
        definitions: list[ToolDefinition] = []
        for item in MCPService.list_tools():
            fn = item.get("function") or {}
            name = fn.get("name") or ""
            meta = handlers.get(name, {})
            definitions.append(
                ToolDefinition(
                    name=name,
                    description=fn.get("description") or "",
                    input_schema=fn.get("parameters") or {"type": "object", "properties": {}},
                    requires_db=bool(meta.get("requires_db")),
                    requires_user=bool(meta.get("requires_user")),
                    requires_workspace=bool(meta.get("requires_workspace")),
                    enabled=True,
                    openai_schema=item,
                )
            )
        return definitions

    @classmethod
    def get_definition(cls, name: str) -> Optional[ToolDefinition]:
        for definition in cls.list_definitions():
            if definition.name == name:
                return definition
        return None

    @classmethod
    def openai_tools_for_names(cls, names: Optional[list[str]]) -> list[dict[str, Any]]:
        if not names:
            return []
        allowed = set(names)
        return [
            d.openai_schema
            for d in cls.list_definitions()
            if d.name in allowed and d.enabled
        ]

    @classmethod
    def validate_arguments(cls, definition: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
        schema = definition.input_schema or {}
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        field_defs: dict[str, Any] = {}
        for key, prop in properties.items():
            typ = prop.get("type", "string")
            py_type: Any = str
            if typ == "integer":
                py_type = int
            elif typ == "number":
                py_type = float
            elif typ == "boolean":
                py_type = bool
            elif typ == "array":
                py_type = list
            elif typ == "object":
                py_type = dict
            default = ... if key in required else None
            field_defs[key] = (Optional[py_type] if default is None else py_type, default)

        if not field_defs:
            return arguments or {}

        model: type[BaseModel] = create_model(f"ToolArgs_{definition.name}", **field_defs)
        try:
            validated = model.model_validate(arguments or {})
            return validated.model_dump(exclude_none=True)
        except ValidationError as exc:
            raise AppException(
                code=10422,
                msg=f"Invalid arguments for tool '{definition.name}': {exc.errors()}",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from exc

    @classmethod
    async def execute(
        cls,
        *,
        name: str,
        arguments: Any,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if context.allowed_tool_names is not None and name not in context.allowed_tool_names:
            raise AppException(
                code=1007,
                msg=f"Tool '{name}' is not enabled for this agent",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        definition = cls.get_definition(name)
        if definition is None or not definition.enabled:
            raise AppException(
                code=10404,
                msg=f"Tool '{name}' was not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                raise AppException(
                    code=10422,
                    msg=f"Tool '{name}' arguments must be valid JSON",
                    status_code=status.HTTP_400_BAD_REQUEST,
                ) from exc
        if not isinstance(arguments, dict):
            raise AppException(
                code=10422,
                msg=f"Tool '{name}' arguments must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = cls.validate_arguments(definition, arguments)

        if definition.requires_workspace and context.workspace_id is None:
            raise AppException(
                code=1007,
                msg=f"Tool '{name}' requires a workspace context",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if definition.requires_user and context.user_id is None:
            raise AppException(
                code=1007,
                msg=f"Tool '{name}' requires an authenticated user",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if definition.requires_db and context.db is None:
            raise AppException(
                code=10500,
                msg=f"Tool '{name}' requires a database session",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            f"Executing tool '{name}' (agent_id={context.agent_id}, workspace_id={context.workspace_id})"
        )
        try:
            content = await MCPService.call_tool(
                name,
                validated,
                db=context.db,
                user_id=context.user_id,
                workspace_id=context.workspace_id,
            )
            return ToolResult(name=name, content=str(content), success=True)
        except AppException:
            raise
        except Exception as exc:
            logger.error(f"Tool '{name}' failed: {exc}")
            return ToolResult(name=name, content=str(exc), success=False, error=str(exc))


def parse_tool_names(raw: Optional[str]) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def serialize_tool_names(names: Optional[list[str]]) -> Optional[str]:
    if not names:
        return None
    known = {d.name for d in ToolRegistry.list_definitions()}
    cleaned = sorted({n for n in names if n in known})
    return ",".join(cleaned) if cleaned else None
