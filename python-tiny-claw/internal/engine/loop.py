from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role
from internal.tools.registry import RegistryImpl as Registry

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

            # Phase 1: 慢思考阶段
            if self.enable_thinking:
                logger.info("[Engine][Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...")

                think_resp = self.provider.generate(context_history, None)
                if think_resp.content:
                    print(f"🧠 [内部思考 Trace]: \n{think_resp.content}")
                    context_history.append(think_resp)

            # Phase 2: 行动阶段
            logger.info("[Engine][Phase 2] 恢复工具挂载，等待模型采取行动...")

            action_resp = self.provider.generate(context_history, available_tools)
            context_history.append(action_resp)

            if action_resp.content:
                print(f"🤖 [对外回复]: \n{action_resp.content}")

            if not action_resp.tool_calls:
                logger.info("[Engine] 模型未请求调用工具，任务宣告完成。")
                break

            logger.info("[Engine] 模型请求并发调用 %d 个工具...", len(action_resp.tool_calls))

            # ================= 并发执行逻辑 =================

            # 预分配列表以保证顺序
            observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)

            def _execute_tool(idx: int, call):
                logger.info("  -> [Thread-%d] 🛠️ 触发并行执行: %s", idx, call.name)
                result = self.registry.execute(call)

                if result.is_error:
                    logger.info("  -> [Thread-%d] ❌ 工具执行报错: %s", idx, result.output)
                else:
                    logger.info("  -> [Thread-%d] ✅ 工具执行成功 (返回 %d 字节)", idx, len(result.output.encode("utf-8")))

                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=result.output,
                    tool_call_id=call.id,
                )
                return idx

            with ThreadPoolExecutor(max_workers=len(action_resp.tool_calls)) as executor:
                futures = [
                    executor.submit(_execute_tool, i, tool_call)
                    for i, tool_call in enumerate(action_resp.tool_calls)
                ]
                for future in as_completed(futures):
                    future.result()

            logger.info("[Engine] 所有并发工具执行完毕，开始聚合观察结果 (Observation)...")

            # 按序追加回 Context
            for obs in observation_msgs:
                context_history.append(obs)
