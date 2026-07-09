from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

from internal.schema import ToolCall, ToolDefinition, ToolResult


class BaseTool(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def definition(self) -> ToolDefinition:
        pass

    @abstractmethod
    def execute(self, args: bytes) -> str:
        pass


MiddlewareFunc = Callable[[ToolCall], tuple[bool, str]]


class Registry(ABC):
    @abstractmethod
    def register(self, tool: BaseTool) -> None:
        pass

    @abstractmethod
    def use(self, mw: MiddlewareFunc) -> None:
        pass

    @abstractmethod
    def get_available_tools(self) -> list[ToolDefinition]:
        pass

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        pass


class _RegistryImpl(Registry):
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._middlewares: list[MiddlewareFunc] = []

    def use(self, mw: MiddlewareFunc) -> None:
        self._middlewares.append(mw)

    def register(self, tool: BaseTool) -> None:
        name = tool.name()
        if name in self._tools:
            logging.warning(f"[Warning] 工具 '{name}' 已经被注册，将被覆盖。")
        self._tools[name] = tool
        logging.info(f"[Registry] 成功挂载工具: {name}")

    def get_available_tools(self) -> list[ToolDefinition]:
        defs = []
        for tool in self._tools.values():
            defs.append(tool.definition())
        return defs

    def execute(self, call: ToolCall) -> ToolResult:
        import internal.observability as observability
        _, span = observability.start_span("Tool.Execute")
        span.add_attribute("tool_name", call.name)
        span.add_attribute("arguments", call.arguments.decode("utf-8") if isinstance(call.arguments, bytes) else str(call.arguments))

        try:
            tool = self._tools.get(call.name)
            if tool is None:
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"Error: 系统中不存在名为 '{call.name}' 的工具。",
                    is_error=True,
                )

            for mw in self._middlewares:
                allowed, reason = mw(call)
                if not allowed:
                    logging.warning(f"[Registry] ⚠️ 工具 {call.name} 被 Middleware 拦截: {reason}")
                    span.add_attribute("intercepted", True)
                    span.add_attribute("reject_reason", reason)
                    return ToolResult(
                        tool_call_id=call.id,
                        output=f"执行被系统拦截。原因: {reason}",
                        is_error=True,
                    )

            try:
                output = tool.execute(call.arguments)
                span.add_attribute("output_preview", self._truncate(output, 100))
                return ToolResult(
                    tool_call_id=call.id,
                    output=output,
                    is_error=False,
                )
            except Exception as e:
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"Error executing {call.name}: {str(e)}",
                    is_error=True,
                )
        finally:
            span.end_span()

    def _truncate(self, s: str, max_len: int) -> str:
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s


def new_registry() -> Registry:
    return _RegistryImpl()
