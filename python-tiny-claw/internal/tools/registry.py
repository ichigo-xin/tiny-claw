from __future__ import annotations

from abc import ABC, abstractmethod

from internal.schema.message import ToolCall, ToolDefinition, ToolResult


class Registry(ABC):

    @abstractmethod
    def get_available_tools(self) -> list[ToolDefinition]:
        ...

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        ...
