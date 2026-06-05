import logging
import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.engine.loop import AgentEngine
from internal.provider.openai import OpenAIProvider
from internal.tools import new_read_file_tool, new_registry

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

    read_file_tool = new_read_file_tool(work_dir)
    registry.register(read_file_tool)

    eng = AgentEngine(llm_provider, registry, work_dir, enable_thinking=False)

    prompt = "请调用工具读取一下当前工作区目录下 hello.txt 文件的内容，并用一句话向我总结它说了什么。"

    eng.run(prompt)


if __name__ == "__main__":
    main()
