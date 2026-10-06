import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.integration import (
    INTEGRATION_TYPES,
    Integration,
    IntegrationTool,
)
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.services.integrations import get_adapter
from app.services.integrations.base import (
    loads_json_object,
    registry_tool_name,
)
from app.services.workspace_service import WorkspaceAccess
from app.utils.encryption import decrypt_api_key, encrypt_api_key
from app.utils.errors import AppException


class IntegrationService:
    @classmethod
    def _encrypt_credentials(cls, credentials: Optional[dict[str, Any]]) -> Optional[str]:
        if not credentials:
            return None
        return encrypt_api_key(json.dumps(credentials))

    @classmethod
    def _decrypt_credentials(cls, encrypted: Optional[str]) -> dict[str, Any]:
        if not encrypted:
            return {}
        raw = decrypt_api_key(encrypted)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _run(coro):
        """Run an async adapter method from sync FastAPI route handlers."""
        import asyncio
        import concurrent.futures

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    @classmethod
    def to_out(cls, integration: Integration) -> dict[str, Any]:
        """Serialize without credentials. Prefer this over model_dump of ORM."""
        config = loads_json_object(integration.config_json, field_name="config")
        tools = list(integration.discovered_tools or [])
        return {
            "id": integration.id,
            "workspace_id": integration.workspace_id,
            "created_by_id": integration.created_by_id,
            "type": integration.type,
            "name": integration.name,
            "description": integration.description,
            "config": config,
            "is_enabled": integration.is_enabled,
            "has_credentials": bool(integration.credentials_encrypted),
            "last_error": integration.last_error,
            "last_discovered_at": integration.last_discovered_at,
            "tool_count": len(tools),
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
        }

    @classmethod
    def tool_to_out(cls, integration: Integration, tool: IntegrationTool) -> dict[str, Any]:
        return {
            "id": tool.id,
            "integration_id": tool.integration_id,
            "remote_name": tool.remote_name,
            "registry_name": tool.registry_name,
            "description": tool.description,
            "input_schema": loads_json_object(tool.input_schema_json, field_name="input_schema"),
            "is_enabled": tool.is_enabled,
            "source_type": integration.type,
            "integration_name": integration.name,
            "discovered_at": tool.discovered_at,
        }

    @classmethod
    def get_for_workspace(
        cls, db: Session, *, integration_id: int, workspace_id: int
    ) -> Integration:
        integration = db.execute(
            select(Integration)
            .options(selectinload(Integration.discovered_tools))
            .where(
                Integration.id == integration_id,
                Integration.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if integration is None:
            raise AppException(
                code=10404,
                msg="Integration not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return integration

    @classmethod
    def list_for_workspace(cls, db: Session, *, workspace_id: int) -> list[Integration]:
        return list(
            db.execute(
                select(Integration)
                .options(selectinload(Integration.discovered_tools))
                .where(Integration.workspace_id == workspace_id)
                .order_by(Integration.created_at.asc())
            )
            .scalars()
            .all()
        )

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        payload: IntegrationCreate,
        created_by_id: int,
    ) -> Integration:
        access.require_permission("integrations:manage")
        itype = payload.type.strip().lower()
        if itype not in INTEGRATION_TYPES:
            raise AppException(
                code=10400,
                msg=f"Unsupported integration type. Expected one of: {', '.join(INTEGRATION_TYPES)}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        name = payload.name.strip()
        existing = db.execute(
            select(Integration).where(
                Integration.workspace_id == access.workspace.id,
                Integration.name == name,
            )
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                code=10409,
                msg="An integration with this name already exists in the workspace",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        adapter = get_adapter(itype)
        config = payload.config or {}
        credentials = payload.credentials or {}
        cls._run(adapter.validate_config(config, credentials))

        integration = Integration(
            workspace_id=access.workspace.id,
            created_by_id=created_by_id,
            type=itype,
            name=name,
            description=payload.description,
            config_json=json.dumps(config),
            credentials_encrypted=cls._encrypt_credentials(credentials),
            is_enabled=payload.is_enabled,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        return cls.get_for_workspace(
            db, integration_id=integration.id, workspace_id=access.workspace.id
        )

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        integration_id: int,
        payload: IntegrationUpdate,
    ) -> Integration:
        access.require_permission("integrations:manage")
        integration = cls.get_for_workspace(
            db, integration_id=integration_id, workspace_id=access.workspace.id
        )
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            name = data["name"].strip()
            clash = db.execute(
                select(Integration).where(
                    Integration.workspace_id == access.workspace.id,
                    Integration.name == name,
                    Integration.id != integration.id,
                )
            ).scalar_one_or_none()
            if clash:
                raise AppException(
                    code=10409,
                    msg="An integration with this name already exists in the workspace",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            integration.name = name
        if "description" in data:
            integration.description = data["description"]
        if "config" in data and data["config"] is not None:
            integration.config_json = json.dumps(data["config"])
        if "credentials" in data and data["credentials"] is not None:
            integration.credentials_encrypted = cls._encrypt_credentials(data["credentials"])
        if "is_enabled" in data and data["is_enabled"] is not None:
            integration.is_enabled = bool(data["is_enabled"])

        adapter = get_adapter(integration.type)
        config = loads_json_object(integration.config_json, field_name="config")
        credentials = cls._decrypt_credentials(integration.credentials_encrypted)
        cls._run(adapter.validate_config(config, credentials))

        integration.updated_at = datetime.now(timezone.utc)
        db.commit()
        return cls.get_for_workspace(
            db, integration_id=integration.id, workspace_id=access.workspace.id
        )

    @classmethod
    def delete(
        cls, db: Session, *, access: WorkspaceAccess, integration_id: int
    ) -> Integration:
        access.require_permission("integrations:manage")
        integration = cls.get_for_workspace(
            db, integration_id=integration_id, workspace_id=access.workspace.id
        )
        db.delete(integration)
        db.commit()
        return integration

    @classmethod
    def refresh_tools(
        cls, db: Session, *, access: WorkspaceAccess, integration_id: int
    ) -> Integration:
        access.require_permission("integrations:manage")
        integration = cls.get_for_workspace(
            db, integration_id=integration_id, workspace_id=access.workspace.id
        )
        if not integration.is_enabled:
            raise AppException(
                code=10400,
                msg="Integration is disabled",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        adapter = get_adapter(integration.type)
        config = loads_json_object(integration.config_json, field_name="config")
        credentials = cls._decrypt_credentials(integration.credentials_encrypted)
        try:
            discovered = cls._run(adapter.discover_tools(config, credentials))
            db.execute(
                delete(IntegrationTool).where(IntegrationTool.integration_id == integration.id)
            )
            for tool in discovered:
                db.add(
                    IntegrationTool(
                        integration_id=integration.id,
                        remote_name=tool.remote_name,
                        registry_name=registry_tool_name(integration.id, tool.remote_name),
                        description=tool.description or "",
                        input_schema_json=json.dumps(tool.input_schema or {}),
                        is_enabled=True,
                        discovered_at=datetime.now(timezone.utc),
                    )
                )
            integration.last_error = None
            integration.last_discovered_at = datetime.now(timezone.utc)
            integration.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            integration.last_error = str(exc)
            integration.updated_at = datetime.now(timezone.utc)
            db.commit()
            if isinstance(exc, AppException):
                raise
            raise AppException(
                code=10502,
                msg=f"Tool discovery failed: {exc}",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        return cls.get_for_workspace(
            db, integration_id=integration.id, workspace_id=access.workspace.id
        )

    @classmethod
    def connect(
        cls, db: Session, *, access: WorkspaceAccess, integration_id: int
    ) -> Integration:
        """Validate connectivity and refresh tools."""
        return cls.refresh_tools(db, access=access, integration_id=integration_id)

    @classmethod
    def list_tools(
        cls, db: Session, *, access: WorkspaceAccess, integration_id: int
    ) -> list[tuple[Integration, IntegrationTool]]:
        access.require_permission("integrations:read")
        integration = cls.get_for_workspace(
            db, integration_id=integration_id, workspace_id=access.workspace.id
        )
        return [(integration, t) for t in (integration.discovered_tools or [])]

    @classmethod
    def list_workspace_tools(
        cls, db: Session, *, workspace_id: int, enabled_only: bool = True
    ) -> list[tuple[Integration, IntegrationTool]]:
        stmt = (
            select(Integration, IntegrationTool)
            .join(IntegrationTool, IntegrationTool.integration_id == Integration.id)
            .where(Integration.workspace_id == workspace_id)
        )
        if enabled_only:
            stmt = stmt.where(Integration.is_enabled.is_(True), IntegrationTool.is_enabled.is_(True))
        return list(db.execute(stmt).all())

    @classmethod
    async def execute_tool(
        cls,
        db: Session,
        *,
        workspace_id: int,
        registry_name: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool, Optional[str]]:
        from app.services.integrations.base import parse_registry_tool_name

        parsed = parse_registry_tool_name(registry_name)
        if parsed is None:
            raise AppException(
                code=10404,
                msg="Invalid external tool name",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        integration_id, remote_name = parsed
        integration = cls.get_for_workspace(
            db, integration_id=integration_id, workspace_id=workspace_id
        )
        if not integration.is_enabled:
            raise AppException(
                code=10400,
                msg="Integration is disabled",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        tool = next(
            (
                t
                for t in (integration.discovered_tools or [])
                if t.remote_name == remote_name and t.is_enabled
            ),
            None,
        )
        if tool is None:
            raise AppException(
                code=10404,
                msg="Integration tool not found. Refresh tools first.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        adapter = get_adapter(integration.type)
        config = loads_json_object(integration.config_json, field_name="config")
        credentials = cls._decrypt_credentials(integration.credentials_encrypted)
        result = await adapter.execute(
            remote_name=remote_name,
            arguments=arguments,
            config=config,
            credentials=credentials,
        )
        return result.content, result.success, result.error
