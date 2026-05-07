import logging
import os

from internal.engine.loop import AgentEngine
from internal.provider.interface import LLMProvider
from internal.schema.message import (
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from internal.tools.registry import Registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MockProvider(LLMProvider):

    def __init__(self):
        self.turn = 0

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
    ) -> Message:
        if available_tools is None or len(available_tools) == 0:
            return Message(
                role=Role.ASSISTANT,
                content="【推理中】目标是检查文件。我不能直接盲猜，我需要先调用 bash 工具执行 ls 命令，看看当前目录下有什么，然后再做定夺。",
            )

        self.turn += 1
        if self.turn == 1:
            return Message(
                role=Role.ASSISTANT,
                content="我要执行我刚才计划的步骤了。",
                tool_calls=[
                    ToolCall(
                        id="call_123",
                        name="bash",
                        arguments={"command": "ls -la"},
                    ),
                ],
            )

        return Message(
            role=Role.ASSISTANT,
            content="根据工具返回的结果，我看到了 main.py，任务圆满完成！",
        )


class MockRegistry(Registry):

    def get_available_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(name="bash")]

    def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id,
            output="-rw-r--r--  1 user group  234 Oct 24 10:00 main.py\n",
            is_error=False,
        )


def main():
    work_dir = os.getcwd()

    p = MockProvider()
    r = MockRegistry()

    eng = AgentEngine(p, r, work_dir, enable_thinking=True)

    eng.run("帮我检查当前目录的文件")


if __name__ == "__main__":
    main()
