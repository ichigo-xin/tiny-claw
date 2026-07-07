import logging
import os
import platform
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.context.session import global_session_mgr
from internal.engine.loop import AgentEngine
from internal.engine.terminal_reporter import TerminalReporter
from internal.provider.openai import OpenAIProvider
from internal.schema.message import Message, Role
from internal.tools import (
    new_powershell_tool,
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

    work_dir = str(Path(__file__).resolve().parent) + "/workspace"
    llm_provider = OpenAIProvider("glm-4.5-air")

    registry = new_registry()
    registry.register(new_powershell_tool(work_dir))
    registry.register(new_write_file_tool(work_dir))

    eng = AgentEngine(llm_provider, registry, enable_thinking=False, plan_mode=False)
    reporter = TerminalReporter()
    sess = global_session_mgr.get_or_create("test_trace_001", work_dir)

    prompt = """
为了加快执行速度，请你在一轮回复中，【同时并行】完成以下两件事：
1. 使用 powershell 工具执行 'Start-Sleep -Seconds 2; Write-Output "系统环境检查完毕"'
2. 使用 write_file 工具，在当前目录下创建一个 'trace_test.md'，内容写上 "测试并发的写入"。
请确保你是分别调用两个不同的工具，不要试图把它们合并成一个命令！
"""
    sess.append(Message(role=Role.USER, content=prompt))

    logger.info("\n>>> 🚀 启动带 Tracing 链路追踪的测试...")
    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎崩溃: %s", e)


if __name__ == "__main__":
    main()