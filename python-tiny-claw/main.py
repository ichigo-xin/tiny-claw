import logging
import os
import platform

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.engine.loop import AgentEngine
from internal.engine.terminal_reporter import TerminalReporter
from internal.provider.openai import OpenAIProvider
from internal.tools import (
    new_bash_tool,
    new_edit_file_tool,
    new_powershell_tool,
    new_read_file_tool,
    new_registry,
    new_write_file_tool,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    if not os.getenv("ZHIPU_API_KEY"):
        logger.error("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
        return

    work_dir = os.getcwd()

    llm_provider = OpenAIProvider("glm-4.5-air")

    registry = new_registry()

    registry.register(new_read_file_tool(work_dir))
    registry.register(new_write_file_tool(work_dir))

    if platform.system() == "Windows":
        registry.register(new_powershell_tool(work_dir))
    else:
        registry.register(new_bash_tool(work_dir))

    registry.register(new_edit_file_tool(work_dir))

    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=True)

    reporter = TerminalReporter()

    prompt = """
    我需要在当前目录下新建一个 ping.py，提供一个简单的 http ping 接口。
    写完之后，帮我把代码用 git 提交一下。
    """

    try:
        eng.run(prompt, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %v", e)


if __name__ == "__main__":
    main()
