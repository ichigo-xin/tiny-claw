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
from internal.observability.tracker import CostTracker
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

    model_name = "glm-4.5-air"
    llm_provider = OpenAIProvider(model_name)
    reporter = TerminalReporter()

    session_id = "test_observability_001"
    sess = global_session_mgr.get_or_create(session_id, work_dir)

    tracked_provider = CostTracker(llm_provider, model_name, sess)

    read_only_registry = new_registry()
    read_only_registry.register(new_read_file_tool(work_dir))
    if platform.system() == "Windows":
        read_only_registry.register(new_powershell_tool(work_dir))
    else:
        read_only_registry.register(new_bash_tool(work_dir))

    main_registry = new_registry()
    main_registry.register(new_read_file_tool(work_dir))
    main_registry.register(new_write_file_tool(work_dir))
    main_registry.register(new_edit_file_tool(work_dir))
    if platform.system() == "Windows":
        main_registry.register(new_powershell_tool(work_dir))
    else:
        main_registry.register(new_bash_tool(work_dir))

    eng = AgentEngine(tracked_provider, main_registry, enable_thinking=False, plan_mode=False)

    main_registry.register(new_subagent_tool(eng, read_only_registry, reporter))

    prompt = """
我需要你在这个遗留项目里，找到那个"核心密码"。
为了防止污染主上下文，请你务必派出子智能体（spawn_subagent）去执行探索任务。
你可以让子智能体使用 bash 去查找当前目录（及其所有子目录）下名为 config.txt 的文件。
子智能体拿到密码向你汇报后，请你亲自使用 write_file 工具，将密码写在根目录的 answer.txt 里。
"""

    logger.info("\n>>> 🚀 启动带仪表盘的可观测性测试...")
    sess.append(Message(role=Role.USER, content=prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)

    logger.info("\n================ 财务报表 ================")
    logger.info("会话 ID: %s", sess.id)
    logger.info("总消耗 Input Tokens: %d", sess.total_prompt_tokens)
    logger.info("总消耗 Output Tokens: %d", sess.total_completion_tokens)
    logger.info("总计费用 (CNY): ¥%.6f", sess.total_cost_cny)
    logger.info("===========================================")


if __name__ == "__main__":
    main()
