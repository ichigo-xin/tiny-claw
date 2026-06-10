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

    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)

    prompt = """
    我当前目录下有一个 server.py 文件。
    请帮我把里面 "TODO: 增加鉴权逻辑" 下面的那个 if 语句，整个替换为：
    if user is None:
        print("Forbidden!")
        return
    """

    eng.run(prompt)


if __name__ == "__main__":
    main()
