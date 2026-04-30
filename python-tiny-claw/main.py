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
        self.turn += 1
        if self.turn == 1:
            return Message(
                role=Role.ASSISTANT,
                content="让我来看看当前目录下有什么文件。",
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
            content="我看到了文件列表，里面包含 main.py，任务完成！",
        )


class MockRegistry(Registry):

    def get_available_tools(self) -> list[ToolDefinition]:
        return []

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

    eng = AgentEngine(p, r, work_dir)

    eng.run("帮我检查当前目录的文件")


if __name__ == "__main__":
    main()
