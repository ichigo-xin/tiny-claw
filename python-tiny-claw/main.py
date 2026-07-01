import json
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
from internal.feishu.bot import FeishuBot
from internal.feishu.approval import get_global_approval_mgr, is_dangerous_command
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

    registry.register(new_edit_file_tool(work_dir))

    eng = AgentEngine(llm_provider, registry, enable_thinking=False, plan_mode=False)

    session_id = "test_command_intercept_001"
    sess = global_session_mgr.get_or_create(session_id, work_dir)
    sess.append(Message(role=Role.USER, content=""))

    bot = None
    if os.getenv("FEISHU_APP_ID") and os.getenv("FEISHU_APP_SECRET"):
        app_id = os.getenv("FEISHU_APP_ID")
        app_secret = os.getenv("FEISHU_APP_SECRET")
        bot = FeishuBot(app_id, app_secret, eng, sess)

    registry.use(lambda call: _security_middleware(call, bot))

    if bot:
        logger.info("检测到飞书配置，启动飞书模式...")
        try:
            bot.start()
        except Exception as e:
            logger.error("飞书长连接启动失败: %s", e)
    else:
        logger.info("未检测到飞书配置，启动终端模式...")
        reporter = TerminalReporter()
        prompt = input("请输入指令: ")
        sess.append(Message(role=Role.USER, content=prompt))
        try:
            eng.run(sess, reporter)
        except Exception as e:
            logger.error("引擎运行崩溃: %s", e)


def _security_middleware(call, bot):
    args_str = json.dumps(call.arguments)

    if is_dangerous_command(call.name, args_str):
        task_id = call.id
        reporter = bot.reporter() if bot else None
        allowed, reason = get_global_approval_mgr().wait_for_approval(
            task_id, call.name, args_str, reporter
        )
        if not allowed:
            return False, reason
        return True, ""

    return True, ""


if __name__ == "__main__":
    main()