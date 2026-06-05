from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from internal.schema.message import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """所有具体工具必须实现的通用接口"""

    @abstractmethod
    def name(self) -> str:
        """返回工具的全局唯一名称 (大模型通过这个名字调用它)"""
        ...

    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回用于提交给大模型的工具元信息和参数 JSON Schema"""
        ...

    @abstractmethod
    def execute(self, args: str) -> tuple[str, Exception | None]:
        """接收大模型吐出的 JSON 参数，执行具体业务逻辑
        
        Args:
            args: JSON 格式的参数字符串
        
        Returns:
            元组 (输出内容, 错误对象)，错误为 None 表示成功
        """
        ...


class RegistryImpl(ABC):
    """Registry 接口的默认实现"""

    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """挂载一个新的工具到系统中"""
        name = tool.name()
        if name in self.tools:
            logger.warning(f"工具 '{name}' 已经被注册，将被覆盖。")
        self.tools[name] = tool
        logger.info(f"[Registry] 成功挂载工具: {name}")

    def get_available_tools(self) -> list[ToolDefinition]:
        """返回当前系统挂载的所有工具的 Schema"""
        return [tool.definition() for tool in self.tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        """实际路由并执行模型请求的工具调用"""
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

        return ToolResult(
            tool_call_id=call.id,
            output=output,
            is_error=False,
        )


def new_registry() -> RegistryImpl:
    """创建一个新的工具注册表实例"""
    return RegistryImpl()
