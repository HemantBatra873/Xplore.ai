"""
MCP (Model Context Protocol) 适配层

将系统内部Tool封装为标准 MCP Tool 接口，支持统一的注册、发现与调用。
遵循 Model Context Protocol 规范，Tool定义兼容 OpenAI function calling 格式。
"""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import logger

# ==========================================
# Tool Schema 定义（集中注册）
# ==========================================
_MCP_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, for example Beijing or Shanghai",
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a task for the current user",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A concise task title",
                    },
                    "description": {
                        "type": "string",
                        "description": "An optional task description",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get CPU, memory, and disk usage when the user asks about server health or load.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List recent tasks for the current user, optionally filtered by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Optional task status filter: pending or completed",
                        "enum": ["pending", "completed"],
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate arithmetic expressions using basic operators and common math functions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "An expression such as 2 + 3 * 4 or round(3.14159, 2)",
                    },
                },
                "required": ["expression"],
            },
        },
    },
]


# ==========================================
# Tool处理器注册表
# 定义 name -> { handler, requires_db, requires_user }
# ==========================================
_MCP_TOOL_HANDLERS: dict[str, dict[str, Any]] = {}


def _register_handler(name: str, requires_db: bool = False, requires_user: bool = False):
    """装饰器：注册一个 MCP Tool处理器"""

    def decorator(func):
        _MCP_TOOL_HANDLERS[name] = {
            "handler": func,
            "requires_db": requires_db,
            "requires_user": requires_user,
        }
        return func

    return decorator


# ==========================================
# 注册 5 个Tool处理器
# 使用懒加载避免与 llm_service 循环引用
# ==========================================


@_register_handler("get_current_weather")
def _handle_weather(location: str) -> str:
    from app.services.llm_service import get_current_weather

    return get_current_weather(location=location)


@_register_handler("get_system_status")
def _handle_system_status() -> str:
    from app.services.llm_service import get_system_status

    return get_system_status()


@_register_handler("list_tasks", requires_db=True, requires_user=True)
def _handle_list_tasks(db: Session, user_id: int, status: Optional[str] = None) -> str:
    from app.services.llm_service import list_tasks

    return list_tasks(db=db, user_id=user_id, status=status)


@_register_handler("create_task", requires_db=True, requires_user=True)
def _handle_create_task(db: Session, user_id: int, title: str, description: str = "") -> str:
    from app.schemas.task import TaskCreate
    from app.services.task_service import TaskService

    logger.info(f"==> [MCP] 模型尝试Create a task: title={title}")
    task_in = TaskCreate(title=title, description=description)
    created_task = TaskService.create_task(db=db, task_in=task_in, owner_id=user_id)
    return f"Task created. ID: {created_task.id}, Title: {created_task.title}"


@_register_handler("calculate")
def _handle_calculate(expression: str) -> str:
    from app.services.llm_service import calculate

    return calculate(expression=expression)


# ==========================================
# MCP 服务入口
# ==========================================
class MCPService:
    """MCP 协议适配层 — 将内部 Tool 暴露为标准 MCP Tool"""

    @staticmethod
    def list_tools() -> list[dict]:
        """获取所有已注册的 MCP Tool Schema（OpenAI function calling 兼容格式）"""
        return list(_MCP_TOOL_DEFINITIONS)

    @staticmethod
    def list_handlers() -> dict[str, dict[str, Any]]:
        """获取Tool处理器注册表信息（用于内省/调试）"""
        return {
            name: {
                "requires_db": info["requires_db"],
                "requires_user": info["requires_user"],
            }
            for name, info in _MCP_TOOL_HANDLERS.items()
        }

    @staticmethod
    async def call_tool(
        name: str,
        arguments: dict,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """
        统一Tool调用入口。
        根据名称路由到对应的处理器，自动注入 db 和 user_id 依赖。
        """
        if name not in _MCP_TOOL_HANDLERS:
            logger.warning(f"==> [MCP] 未知Tool调用: {name}")
            return f"Unknown tool: {name}"

        info = _MCP_TOOL_HANDLERS[name]
        handler = info["handler"]
        logger.info(f"==> [MCP] 调用Tool: {name}, 参数: {arguments}")

        kwargs = dict(arguments)
        if info["requires_db"]:
            kwargs["db"] = db
        if info["requires_user"]:
            kwargs["user_id"] = user_id

        try:
            result = handler(**kwargs)
            return result
        except Exception as e:
            logger.error(f"==> [MCP] Tool '{name}' execution failed: {e}")
            return f"Tool '{name}' execution failed: {e}"
