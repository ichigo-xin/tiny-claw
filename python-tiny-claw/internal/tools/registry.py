from __future__ import annotations

import inspect
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from internal.observability.trace import start_span
from internal.schema.message import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def definition(self) -> ToolDefinition:
        ...

    @abstractmethod
    def execute(self, args: str) -> tuple[str, Exception | None]:
        ...


class RegistryImpl(ABC):
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}
        self.middlewares: list = []

    def use(self, middleware) -> None:
        self.middlewares.append(middleware)
        logger.info("[Registry] 成功注册中间件")

    def register(self, tool: BaseTool) -> None:
        name = tool.name()
        if name in self.tools:
            logger.warning(f"工具 '{name}' 已经被注册，将被覆盖。")
        self.tools[name] = tool
        logger.info(f"[Registry] 成功挂载工具: {name}")

    def get_available_tools(self) -> list[ToolDefinition]:
        return [tool.definition() for tool in self.tools.values()]

    def execute(self, ctx: dict[str, Any], call: ToolCall) -> ToolResult:
        ctx, span = start_span(ctx, "Tool.Execute")
        span.add_attribute("tool_name", call.name)
        span.add_attribute("arguments", call.arguments)

        try:
            for middleware in self.middlewares:
                sig = inspect.signature(middleware)
                if len(sig.parameters) == 2:
                    allowed, reason = middleware(ctx, call)
                else:
                    allowed, reason = middleware(call)
                if not allowed:
                    logger.info(f"[Registry] ⚠️ 工具 {call.name} 被 Middleware 拦截: {reason}")
                    span.add_attribute("intercepted", True)
                    span.add_attribute("reject_reason", reason)
                    return ToolResult(
                        tool_call_id=call.id,
                        output=f"执行被系统拦截。原因: {reason}",
                        is_error=True,
                    )

            tool = self.tools.get(call.name)
            if not tool:
                err_msg = f"Error: 系统中不存在名为 '{call.name}' 的工具。"
                return ToolResult(
                    tool_call_id=call.id,
                    output=err_msg,
                    is_error=True,
                )

            output, err = tool.execute(call.arguments)

            if err:
                err_msg = f"Error executing {call.name}: {err}"
                return ToolResult(
                    tool_call_id=call.id,
                    output=err_msg,
                    is_error=True,
                )

            span.add_attribute("output_preview", truncate(output, 100))

            return ToolResult(
                tool_call_id=call.id,
                output=output,
                is_error=False,
            )
        finally:
            span.end_span()


def truncate(s: str, max_len: int) -> str:
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def new_registry() -> RegistryImpl:
    return RegistryImpl()