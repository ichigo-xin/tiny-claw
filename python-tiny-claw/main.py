import logging
import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.engine.loop import AgentEngine
from internal.provider.claude import ClaudeProvider
from internal.provider.openai import OpenAIProvider
from internal.schema.message import Message, Role, ToolCall, ToolDefinition, ToolResult
from internal.tools.registry import Registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MockRegistry(Registry):

    def get_available_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description="获取指定城市的当前天气情况。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                        },
                    },
                    "required": ["city"],
                },
            ),
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        logger.info("  -> [Mock 工具执行] 获取 %s 的天气中...", call.name)
        return ToolResult(
            tool_call_id=call.id,
            output="API 返回：今天是晴天，气温 25 度。",
            is_error=False,
        )


def main():
    load_dotenv()

    if not os.getenv("ZHIPU_API_KEY"):
        logger.error("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
        return

    work_dir = os.getcwd()

    llm_provider = OpenAIProvider("glm-4.5-air")

    registry = MockRegistry()

    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)

    prompt = "我想去北京跑步，帮我查查天气适合吗？"

    eng.run(prompt)


if __name__ == "__main__":
    main()
