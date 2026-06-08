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
        shell_tool = "powershell"
    else:
        registry.register(new_bash_tool(work_dir))
        shell_tool = "bash"

    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)

    prompt = f"""
    请帮我执行以下操作：
    1. 用 {shell_tool} 查看一下当前电脑的 Python 版本。
    2. 帮我写一个简单的 helloworld.py 文件，输出 "Hello, python-tiny-claw!"。
    3. 用 {shell_tool} 运行这个 python 文件，确认它能正常工作。
    """

    eng.run(prompt)


if __name__ == "__main__":
    main()
