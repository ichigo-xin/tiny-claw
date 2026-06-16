import logging
import os
import platform
import threading
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.engine.loop import AgentEngine
from internal.engine.session import global_session_mgr
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


def _ensure_demo_workdirs(project_root: Path) -> tuple[Path, Path]:
    """准备本次演示所需的两个隔离工作区，并放置一个带密钥的 README 作为探针。"""
    front_dir = project_root / "tmp" / "project_front"
    back_dir = project_root / "tmp" / "project_back"
    front_dir.mkdir(parents=True, exist_ok=True)
    back_dir.mkdir(parents=True, exist_ok=True)

    readme_path = front_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "这是项目 A 的 README，里面包含了一个密钥: token_12345",
            encoding="utf-8",
        )
    return front_dir, back_dir


def main():
    load_dotenv()

    if not os.getenv("ZHIPU_API_KEY"):
        logger.error("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
        return

    project_root = Path(__file__).resolve().parent
    front_work_dir, back_work_dir = _ensure_demo_workdirs(project_root)

    llm_provider = OpenAIProvider("glm-4.5-air")

    # 工具统一注册到前端工作区，对应 go 项目里 registry.Register(new_read_file_tool(frontWorkDir))
    registry = new_registry()
    registry.register(new_read_file_tool(str(front_work_dir)))
    registry.register(new_write_file_tool(str(front_work_dir)))

    if platform.system() == "Windows":
        registry.register(new_powershell_tool(str(front_work_dir)))
    else:
        registry.register(new_bash_tool(str(front_work_dir)))

    registry.register(new_edit_file_tool(str(front_work_dir)))

    # 引擎本身变成无状态的，它不绑定 WorkDir（仅适用于本讲演示）
    eng = AgentEngine(llm_provider, registry, enable_thinking=False)
    reporter = TerminalReporter()

    # ================= 模拟并发场景 1：飞书前端群 =================
    def scenario_front():
        session_a = global_session_mgr.get_or_create("chat_front_001", str(front_work_dir))

        # 回合 1：获取机密
        logger.info("\n>>> 🙋‍♂️ [Session A / Turn 1]: 帮我看看 README.md 里记录了什么密钥？")
        session_a.append(Message(role=Role.USER, content="帮我看看 README.md 里记录了什么密钥？"))
        try:
            eng.run(session_a, reporter)
        except Exception as e:
            logger.error("Session A Turn 1 失败: %s", e)

        # 故意制造大量"废话"对话，刷掉记忆 (假设 Working Memory Limit=6)
        for _ in range(6):
            session_a.append(Message(role=Role.USER, content="这只是一句闲聊占位符。"))
            session_a.append(Message(role=Role.ASSISTANT, content="好的，收到闲聊。"))

        # 回合 2：验证记忆截断 (此时第一轮的密钥已经被挤出 Working Memory 了！)
        logger.info(
            "\n>>> 🙋‍♂️ [Session A / Turn 2]: 请直接告诉我，刚才第一轮你查到的那个密钥是什么？"
        )
        session_a.append(
            Message(
                role=Role.USER,
                content="请直接告诉我，刚才第一轮你查到的那个密钥是什么？不准调用工具！",
            )
        )
        try:
            eng.run(session_a, reporter)
        except Exception as e:
            logger.error("Session A Turn 2 失败: %s", e)

    # ================= 模拟并发场景 2：飞书后端群 =================
    def scenario_back():
        # 稍微错开一点时间发起请求
        time.sleep(1)

        session_b = global_session_mgr.get_or_create("chat_back_002", str(back_work_dir))

        logger.info("\n>>> 🙋‍♂️ [Session B]: 别人查到了一个密钥，你这里能看到吗？")
        session_b.append(
            Message(
                role=Role.USER,
                content="别人查到了一个密钥，你这里能看到吗？不准调用工具！",
            )
        )
        try:
            eng.run(session_b, reporter)
        except Exception as e:
            logger.error("Session B 失败: %s", e)

    t_front = threading.Thread(target=scenario_front)
    t_back = threading.Thread(target=scenario_back)

    t_front.start()
    t_back.start()

    t_front.join()
    t_back.join()


if __name__ == "__main__":
    main()
