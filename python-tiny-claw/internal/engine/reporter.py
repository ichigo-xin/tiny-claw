from __future__ import annotations
from abc import ABC, abstractmethod


class Reporter(ABC):
    @abstractmethod
    def on_thinking(self) -> None:
        pass

    @abstractmethod
    def on_tool_call(self, tool_name: str, args: str) -> None:
        pass

    @abstractmethod
    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        pass

    @abstractmethod
    def on_message(self, content: str) -> None:
        pass
