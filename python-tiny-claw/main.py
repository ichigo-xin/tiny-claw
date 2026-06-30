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

    session_id = "test_recovery_001"
    sess = global_session_mgr.get_or_create(session_id, work_dir)

    # 这是一个巨大的陷阱指令：
    # 我们不给它查看文件的机会，直接命令它凭初始上下文去修改文件，目的是诱发 old_text 不匹配的错误。
    prompt = """
    我当前目录下有一个 auth.go 文件。
    请修改 auth.go 中的 login 函数。
    请直接使用 edit_file 工具替换下面的代码块，将判断条件改为同时允许"admin"、"root"和"guest"三种用户登录：

    // 鉴权入口函数
    func login(user string) bool {
        // 检查用户名
        if user == "admin" {
            return true
        }
        return false
    }
"""

    logger.info("\n>>> 🚀 启动自愈测试任务...")
    sess.append(Message(role=Role.USER, content=prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logger.error("引擎运行崩溃: %s", e)


if __name__ == "__main__":
    main()
