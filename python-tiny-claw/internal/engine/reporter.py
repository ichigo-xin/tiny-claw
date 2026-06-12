from __future__ import annotations

from abc import ABC, abstractmethod


class Reporter(ABC):
    """定义了 Agent 引擎向外界输出信息的规范。
    这使得引擎可以无缝切换终端 (CLI)、飞书、钉钉甚至 WebUI 等不同的展现层。
    """

    @abstractmethod
    def on_thinking(self) -> None:
        """当模型开始进行慢思考 (Reasoning) 时调用"""
        ...

    @abstractmethod
    def on_tool_call(self, tool_name: str, args: str) -> None:
        """当模型决定并发调用工具时调用"""
        ...

    @abstractmethod
    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        """当工具在底层执行完毕并返回结果时调用"""
        ...

    @abstractmethod
    def on_message(self, content: str) -> None:
        """当模型宣告任务完成，向用户输出最终纯文本回答时调用"""
        ...
