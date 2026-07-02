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
    new_subagent_tool,
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
    reporter = TerminalReporter()

    # 【防御沙箱】为子智能体准备受限的只读注册表
    read_only_registry = new_registry()
    read_only_registry.register(new_read_file_tool(work_dir))
    # 根据操作系统注册对应的命令执行工具
    if platform.system() == "Windows":
        read_only_registry.register(new_powershell_tool(work_dir))
    else:
        read_only_registry.register(new_bash_tool(work_dir))

    # 为主智能体准备全功能注册表
    main_registry = new_registry()
    main_registry.register(new_read_file_tool(work_dir))
    main_registry.register(new_write_file_tool(work_dir))
    main_registry.register(new_edit_file_tool(work_dir))
    if platform.system() == "Windows":
        main_registry.register(new_powershell_tool(work_dir))
    else:
        main_registry.register(new_bash_tool(work_dir))

    # 初始化主引擎
    eng = AgentEngine(llm_provider, main_registry, enable_thinking=False, plan_mode=False)

    # 【核心装配】：将带有 Engine 引用和只读 Registry 的 Subagent 工具注册进主线
    main_registry.register(new_subagent_tool(eng, read_only_registry, reporter))

    session_id = "test_subagent_001"
    sess = global_session_mgr.get_or_create(session_id, work_dir)

    prompt = """
我需要你在这个遗留项目里，找到那个"核心密码"。
为了防止污染主上下文，请你务必派出子智能体（spawn_subagent）去执行探索任务。
你可以让子智能体使用 bash 去查找当前目录（及其所有子目录）下名为 config.txt 的文件。
子智能体拿到密码向你汇报后，请你亲自使用 write_file 工具，将密码写在根目录的 answer.txt 里。
"""

    logger.info("\n>>> 🚀 启动多智能体协同测试...")
    sess.append(Message(role=Role.USER, content=prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)


if __name__ == "__main__":
    main()
