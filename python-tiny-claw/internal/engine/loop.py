from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from internal.context.composer import PromptComposer
from internal.engine.reporter import Reporter
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
        self.composer = PromptComposer(work_dir)

    def run(self, user_prompt: str, reporter: Optional[Reporter] = None) -> None:
        logger.info("[Engine] 引擎启动，锁定工作区: %s", self.work_dir)

        # 动态组装 System Prompt，彻底替换掉以前硬编码的面条提示词
        system_msg = self.composer.build()

        context_history: list[Message] = [
            system_msg,
            Message(
                role=Role.USER,
                content=user_prompt,
            ),
        ]

        turn_count = 0

        while True:
            turn_count += 1
            available_tools = self.registry.get_available_tools()

            # ================= Phase 1: Thinking =================
            if self.enable_thinking:
                if reporter is not None:
                    reporter.on_thinking()

                think_resp = self.provider.generate(context_history, None)
                if think_resp.content:
                    context_history.append(think_resp)

            # ================= Phase 2: Action =================
            action_resp = self.provider.generate(context_history, available_tools)
            context_history.append(action_resp)

            if action_resp.content and reporter is not None:
                reporter.on_message(action_resp.content)

            # ================= 执行退出与并发控制 =================
            if not action_resp.tool_calls:
                break

            observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)

            def _execute_tool(idx: int, call):
                if reporter is not None:
                    reporter.on_tool_call(call.name, call.arguments)

                result = self.registry.execute(call)

                if reporter is not None:
                    display_output = result.output
                    if len(display_output) > 200:
                        display_output = display_output[:200] + "... (已截断)"
                    reporter.on_tool_result(call.name, display_output, result.is_error)

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

            for obs in observation_msgs:
                context_history.append(obs)
