import argparse
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
    # 通过命令行参数接收用户的 prompt
    parser = argparse.ArgumentParser(description="python-tiny-claw")
    parser.add_argument("-prompt", dest="prompt", default="", help="要交给 Agent 执行的任务描述")
    args = parser.parse_args()

    if not args.prompt:
        print('用法: python main.py -prompt "你的任务指令"')
        return

    load_dotenv()

    if not os.getenv("ZHIPU_API_KEY"):
        logger.error("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
        return

    work_dir = str(Path(__file__).resolve().parent) + "/workspace"
    llm_provider = OpenAIProvider("glm-4.5-air")

    registry = new_registry()
    registry.register(new_read_file_tool(work_dir))
    registry.register(new_write_file_tool(work_dir))

    if platform.system() == "Windows":
        registry.register(new_powershell_tool(work_dir))
    else:
        registry.register(new_bash_tool(work_dir))

    registry.register(new_edit_file_tool(work_dir))

    # 实例化引擎并开启计划模式 (plan_mode=True)
    eng = AgentEngine(llm_provider, registry, enable_thinking=False, plan_mode=True)
    reporter = TerminalReporter()

    # 我们使用一个固定的 SessionID，以便在多次运行之间共享基于内存的“短期工作记忆”。
    # (在真实的 CLI 中，如果进程重启，Session 的内存历史其实是丢失的。
    # 但这正是我们要演示的重点：即便短期内存丢失，只要 TODO.md 还在，任务就能继续！)
    session_id = "task_web_server_01"
    sess = global_session_mgr.get_or_create(session_id, work_dir)

    logger.info(">>> 🚀 收到指令: %s", args.prompt)

    # 将用户的 Prompt 压入 Session
    sess.append(Message(role=Role.USER, content=args.prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)


if __name__ == "__main__":
    main()
