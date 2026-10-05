import ast
import asyncio
import json
import operator
from dataclasses import dataclass
from typing import Union

import psutil
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import logger
from app.models.task import Task
from app.models.user import User
from app.services.llm_observability_service import (
    create_llm_call_log,
    elapsed_ms,
    extract_usage,
    serialize_tool_calls,
    start_timer,
)
from app.services.mcp_service import MCPService
from app.utils.encryption import decrypt_api_key

# 全局复用一个 AsyncOpenAI 客户端 (针对未配置自有 Key 的情况)
_global_client = None


@dataclass
class LLMClientInfo:
    client: Union[AsyncOpenAI, "MockLLMClient"]
    model_name: str


# ==========================================
# MockLLMClient — 无需 API Key 的模拟客户端
# ==========================================
class _MockUsage:
    prompt_tokens = 10
    completion_tokens = 20
    total_tokens = 30


class _MockDelta:
    def __init__(self, content: str = "", reasoning_content: str = None):
        self.content = content
        self.reasoning_content = reasoning_content


class _MockChoice:
    def __init__(self, delta: _MockDelta = None, message_content: str = ""):
        if delta is not None:
            self.delta = delta
        else:
            self.message = _MockMessage(content=message_content)


class _MockMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


class _MockChunk:
    def __init__(self, delta: _MockDelta):
        self.choices = [_MockChoice(delta=delta)]


class _MockResponse:
    def __init__(self, content: str):
        self.choices = [_MockChoice(message_content=content)]
        self.usage = _MockUsage()


class _MockChatCompletions:
    async def create(self, model: str, messages: list, **kwargs) -> _MockResponse:
        stream = kwargs.get("stream", False)
        if stream:
            return self._stream_response()
        return _MockResponse(
            content="This is a mock response. Xplore.ai is running offline without a live LLM provider."
        )

    async def _stream_response(self):
        content = "This is a streamed mock response. Xplore.ai is running offline without a live LLM provider."
        for char in content:
            yield _MockChunk(delta=_MockDelta(content=char))
            await asyncio.sleep(0.01)
        yield _MockChunk(delta=_MockDelta(content=""))


class _MockChat:
    completions = _MockChatCompletions()


class MockLLMClient:
    """模拟 LLM 客户端，返回预设回复，无需 API Key"""

    chat = _MockChat()
    api_key = "mock"


def get_llm_client(user: User = None) -> LLMClientInfo:
    """
    动态获取 LLM 客户端和模型名称。
    优先使用用户自定义的配置（支持多租户独立 Key），若用户未配置，则回退到系统global configuration。
    当 LLM_MOCK=true 时，返回 MockLLMClient，无需任何 API Key。
    用户自定义 Key 解密失败时，自动降级到global configuration。
    """
    if settings.LLM_MOCK:
        logger.info("==> LLM mock mode is enabled; using the mock client")
        return LLMClientInfo(client=MockLLMClient(), model_name="mock-model")

    if user and user.has_custom_llm_key:
        try:
            api_key = decrypt_api_key(user.llm_api_key_encrypted)
            base_url = user.llm_base_url or settings.LLM_BASE_URL
            model_name = user.llm_model_name or settings.LLM_MODEL_NAME

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
            return LLMClientInfo(client=client, model_name=model_name)
        except Exception as e:
            logger.warning(f"Unable to decrypt the custom LLM key for user {user.id}; using the global configuration: {e}")

    global _global_client
    if _global_client is None:
        _global_client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return LLMClientInfo(client=_global_client, model_name=settings.LLM_MODEL_NAME)


# ==========================================
# 1. 定义本地Tool函数 (模拟查询天气与系统状态)
# ==========================================
def get_current_weather(location: str) -> str:
    """模拟天气查询函数，实际中这里可以调用外部天气 API"""
    logger.info(f"==> 执行本地Tool: 查询 {location} 的天气")
    # 为了演示，写死几个城市的天气
    weather_data = {
        "Beijing": "Clear, 25 C, light wind",
        "Shanghai": "Cloudy, 28 C, possible showers",
        "Guangzhou": "Light rain, 26 C, humid",
    }
    # 默认返回
    return weather_data.get(location, f"Weather is unknown for {location}; temperature is about 20 C")


def get_system_status() -> str:
    """查询服务器当前的系统负载、内存与磁盘占用状态"""
    logger.info("==> 执行本地Tool: 查询系统状态")
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        status_info = (
            f"CPU usage: {cpu_percent}%\n"
            f"Memory usage: {memory.percent}% (used: {memory.used / (1024**3):.2f} GB, total: {memory.total / (1024**3):.2f} GB)\n"
            f"Disk usage: {disk.percent}% (used: {disk.used / (1024**3):.2f} GB, total: {disk.total / (1024**3):.2f} GB)"
        )
        return status_info
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return "Unable to read system status."


def list_tasks(db: Session, user_id: int, status: str = None) -> str:
    logger.info(f"==> 执行本地Tool: 查询任务列表 (user_id={user_id}, status={status})")
    try:
        stmt = select(Task).where(Task.owner_id == user_id)
        if status:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(Task.created_at.desc()).limit(10)
        tasks = list(db.scalars(stmt).all())
        if not tasks:
            return "There are no tasks yet."
        lines = []
        for t in tasks:
            lines.append(f"  - [ID:{t.id}] [{t.status}] {t.title}")
            if t.description:
                lines.append(f"    Description: {t.description}")
            return "Current tasks:\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"查询任务列表失败: {e}")
        return "An error occurred while listing tasks."


_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
}

_ALLOWED_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
}


def _safe_eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")

    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return _ALLOWED_OPS[op_type](left, right)

    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        operand = _safe_eval_node(node.operand)
        return _ALLOWED_OPS[op_type](operand)

    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("只允许直接函数名调用")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCS:
            raise ValueError(f"不支持的函数: {func_name}")
        args = [_safe_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCS[func_name](*args)

    else:
        raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


def safe_eval(expr: str) -> float:
    """安全计算数学表达式，使用 AST 而非 eval()"""
    node = ast.parse(expr.strip(), mode="eval").body
    return _safe_eval_node(node)


def calculate(expression: str) -> str:
    logger.info(f"==> 执行本地Tool: 计算表达式 '{expression}'")
    try:
        result = safe_eval(expression)
        return f"Calculation: {expression} = {result}"
    except Exception as e:
        return f"Calculation failed: {e}"


# Tool Schema 与处理器已统一托管于 MCPService
# 新增Tool时只需在 mcp_service.py 中注册即可


async def _llm_completion_with_retry(llm_client, **kwargs):
    """LLM API 调用，带指数退避重试（应对 429 限流和临时网络问题）"""
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda retry_state: logger.warning(
            f"LLM API 调用失败 (第 {retry_state.attempt_number} 次重试): "
            f"{retry_state.outcome.exception()}"
        ),
    ):
        with attempt:
            return await llm_client.chat.completions.create(**kwargs)


async def generate_chat_reply(message: str, db: Session = None, current_user_id: int = None) -> str:
    """
    调用大语言模型生成回复 (带 Tool Calling 支持)
    """
    user = db.get(User, current_user_id) if db and current_user_id else None

    info = get_llm_client(user)

    if not info.client.api_key:
        return "System notice: no LLM API key is configured. Add one in system or personal settings."

    started_at = start_timer()

    # 初始对话上下文
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant and a personal task-management expert. Use tools to retrieve information or create tasks, then summarize tool results naturally.",
        },
        {"role": "user", "content": message},
    ]
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    tool_calls_payload = None
    final_reply = None

    try:
        # 第一轮调用：告诉模型用户的问题，并附带Tool列表
        logger.info("==> [Round 1] 正在请求大模型...")

        # 针对部分模型（如 Qwen2.5）强化 Prompt
        system_prompt = (
            "You are a helpful assistant and a personal task-management expert. "
            "When the user asks you to create a task, study plan, or schedule item, you must use the 'create_task' tool. "
            "Return valid JSON tool calls without extra text around them."
        )
        messages[0]["content"] = system_prompt

        response = await _llm_completion_with_retry(
            info.client,
            model=info.model_name,
            messages=messages,
            tools=MCPService.list_tools(),
            tool_choice="auto",
            temperature=0.1,
            max_tokens=1000,
        )

        response_message = response.choices[0].message
        prompt_tokens, completion_tokens, used_tokens = extract_usage(response)
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_tokens += used_tokens

        # 检查模型是否决定调用Tool
        if response_message.tool_calls:
            logger.info("==> 模型决定调用Tool！")
            messages.append(response_message)
            tool_calls_payload = serialize_tool_calls(response_message.tool_calls)

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                tool_result = ""
                if function_name == "create_task":
                    logger.info(f"==> 模型尝试Create a task: {arguments}")
                    if db and current_user_id:
                        tool_result = await MCPService.call_tool(
                            name=function_name,
                            arguments=arguments,
                            db=db,
                            user_id=current_user_id,
                        )
                    else:
                        tool_result = "Task creation failed: no database connection or signed-in user was available."

                elif function_name == "list_tasks":
                    tool_result = await MCPService.call_tool(
                        name=function_name,
                        arguments=arguments,
                        db=db,
                        user_id=current_user_id,
                    )

                else:
                    tool_result = await MCPService.call_tool(
                        name=function_name,
                        arguments=arguments,
                    )

                # 将Tool的执行结果追加到上下文中
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result,
                    }
                )

            # 第二轮调用
            logger.info("==> [Round 2] Tool结果已返回，正在请求大模型生成最终回答...")
            second_response = await _llm_completion_with_retry(
                info.client,
                model=info.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )
            prompt_tokens, completion_tokens, used_tokens = extract_usage(second_response)
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            total_tokens += used_tokens
            final_reply = second_response.choices[0].message.content
            if db:
                create_llm_call_log(
                    db,
                    user_id=current_user_id,
                    endpoint="/api/v1/chat",
                    prompt=message,
                    response=final_reply,
                    tool_calls=tool_calls_payload,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=elapsed_ms(started_at),
                    status="success",
                )
            return final_reply

        else:
            logger.info("==> 模型没有调用Tool，直接返回了回答。")
            final_reply = response_message.content
            if db:
                create_llm_call_log(
                    db,
                    user_id=current_user_id,
                    endpoint="/api/v1/chat",
                    prompt=message,
                    response=final_reply,
                    tool_calls=None,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=elapsed_ms(started_at),
                    status="success",
                )
            return final_reply

    except Exception as e:
        logger.error(f"LLM API 调用失败: {str(e)}")
        if db:
            create_llm_call_log(
                db,
                user_id=current_user_id,
                endpoint="/api/v1/chat",
                prompt=message,
                response=final_reply,
                tool_calls=tool_calls_payload,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                total_tokens=total_tokens,
                latency_ms=elapsed_ms(started_at),
                status="failed",
                error_message=str(e),
            )
        return f"System notice: the model call failed. Check the network or API configuration. Details: {str(e)}"


async def generate_chat_reply_stream(message: str, db: Session = None, current_user_id: int = None):
    """
    流式调用大语言模型生成回复 (SSE)。不支持 Tool Calling，如果需要 Tool Calling 建议先判断。
    这里为了演示，提供最基础的流式输出支持。
    """
    user = db.get(User, current_user_id) if db and current_user_id else None
    info = get_llm_client(user)

    if not info.client.api_key:
        yield 'data: {"error": "No API key is configured"}\n\n'
        return

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": message},
    ]

    try:
        response = await info.client.chat.completions.create(
            model=info.model_name, messages=messages, temperature=0.7, stream=True
        )

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            payload = {}
            if getattr(delta, "reasoning_content", None):
                payload["reasoning"] = delta.reasoning_content
            if delta.content:
                payload["content"] = delta.content
            if payload:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"LLM Stream 调用失败: {str(e)}")
        data = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {data}\n\n"
