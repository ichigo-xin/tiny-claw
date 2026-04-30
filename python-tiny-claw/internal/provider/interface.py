from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from internal.schema.message import Message, ToolDefinition


class LLMProvider(ABC):

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
    ) -> Message:
        ...
