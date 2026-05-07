from __future__ import annotations

import logging

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role
from internal.tools.registry import Registry

logger = logging.getLogger(__name__)


class AgentEngine:

    def __init__(
        self,
        provider: LLMProvider,
        registry: Registry,
        work_dir: str,
        enable_thinking: bool = False,
    ):
        self.provider = provider
        self.registry = registry
        self.work_dir = work_dir
        self.enable_thinking = enable_thinking

    def run(self, user_prompt: str) -> None:
        logger.info("[Engine] 引擎启动，锁定工作区: %s", self.work_dir)
        logger.info("[Engine] 慢思考模式 (Thinking Phase): %s", self.enable_thinking)

        context_history: list[Message] = [
            Message(
                role=Role.SYSTEM,
                content="You are python-tiny-claw, an expert coding assistant. You have full access to tools in the workspace.",
            ),
            Message(
                role=Role.USER,
                content=user_prompt,
            ),
        ]

        turn_count = 0

        while True:
            turn_count += 1
            logger.info("\n========== [Turn %d] 开始 ==========", turn_count)

            available_tools = self.registry.get_available_tools()

            # ====================================================================
            # Phase 1: 慢思考阶段 (Thinking) - 剥夺工具，强制规划
            # ====================================================================
            if self.enable_thinking:
                logger.info("[Engine][Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...")

                think_resp = self.provider.generate(context_history, None)
                if think_resp.content:
                    print(f"🧠 [内部思考 Trace]: {think_resp.content}")
                    context_history.append(think_resp)

            # ====================================================================
            # Phase 2: 行动阶段 (Action) - 恢复工具，顺着规划执行
            # ====================================================================
            logger.info("[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...")

            action_resp = self.provider.generate(context_history, available_tools)
            context_history.append(action_resp)

            if action_resp.content:
                print(f"🤖 [对外回复]: {action_resp.content}")

            if not action_resp.tool_calls:
                logger.info("[Engine] 模型未请求调用工具，任务宣告完成。")
                break

            logger.info("[Engine] 模型请求调用 %d 个工具...", len(action_resp.tool_calls))

            for tool_call in action_resp.tool_calls:
                logger.info("  -> 🛠️ 执行工具: %s, 参数: %s", tool_call.name, tool_call.arguments)

                result = self.registry.execute(tool_call)

                if result.is_error:
                    logger.info("  -> ❌ 工具执行报错: %s", result.output)
                else:
                    logger.info("  -> ✅ 工具执行成功 (返回 %d 字节)", len(result.output.encode("utf-8")))

                observation_msg = Message(
                    role=Role.USER,
                    content=result.output,
                    tool_call_id=tool_call.id,
                )
                context_history.append(observation_msg)
