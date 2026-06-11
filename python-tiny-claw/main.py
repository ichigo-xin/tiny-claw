import logging
import os
import platform

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.engine.loop import AgentEngine
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

    # 开启慢思考，促使大模型一次性规划出并行的工具调用
    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=True)

    prompt = """
    我当前目录下有 a.txt, b.txt, c.txt 三个文件。(如果没有请忽略找不到的报错)
    为了节省时间，请你同时一次性利用工具读取这三个文件，并将它们的内容综合起来告诉我。
    """

    eng.run(prompt)


if __name__ == "__main__":
    main()
