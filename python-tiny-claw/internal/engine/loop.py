from __future__ import annotations

import logging
import os

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role
from internal.tools.registry import Registry

logger = logging.getLogger(__name__)


class AgentEngine:

    def __init__(self, provider: LLMProvider, registry: Registry, work_dir: str):
        self.provider = provider
        self.registry = registry
        self.work_dir = work_dir

    def run(self, user_prompt: str) -> None:
        logger.info("[Engine] 引擎启动，锁定工作区: %s", self.work_dir)

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
            logger.info("========== [Turn %d] 开始 ==========", turn_count)

            available_tools = self.registry.get_available_tools()

            logger.info("[Engine] 正在思考 (Reasoning)...")
            response_msg = self.provider.generate(context_history, available_tools)

            context_history.append(response_msg)

            if response_msg.content:
                print(f"🤖 模型: {response_msg.content}")

            if not response_msg.tool_calls:
                logger.info("[Engine] 任务完成，退出循环。")
                break

            logger.info("[Engine] 模型请求调用 %d 个工具...", len(response_msg.tool_calls))

            for tool_call in response_msg.tool_calls:
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
