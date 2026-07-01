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

    # 【新增挂载】
    registry.register(new_edit_file_tool(work_dir))

    # 关闭 Plan 模式，专注于见证它改变主意的单点纠偏过程
    eng = AgentEngine(llm_provider, registry, enable_thinking=False, plan_mode=False)
    reporter = TerminalReporter()

    session_id = "test_doom_loop_001"
    sess = global_session_mgr.get_or_create(session_id, work_dir)

    prompt = """
    帮我读取当前目录下的 secret_key.txt。
    注意：我们的文件系统现在非常不稳定，经常报 File Not Found。
    如果报错了，请你【千万不要改变参数】，直接原样再次调用 read_file 尝试，直到成功或连续重试 5 次为止。
    """

    logger.info("\n>>> 🚀 启动死循环干预测试...")
    sess.append(Message(role=Role.USER, content=prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)


if __name__ == "__main__":
    main()
