from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from internal.context.compactor import Compactor
from internal.context.composer import PromptComposer
from internal.context.recovery import RecoveryManager
from internal.context.session import Session
from internal.engine.reporter import Reporter
from internal.engine.reminder import ReminderInjector, new_reminder_injector
from internal.observability.trace import Span, export_trace_to_file, start_span
from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role, ToolCall, ToolResult
from internal.tools.registry import RegistryImpl as Registry

logger = logging.getLogger(__name__)


class AgentEngine:
    """Agent 引擎本身是无状态的，它不绑定 WorkDir，而是跟随传入的 Session。"""

    def __init__(
        self,
        provider: LLMProvider,
        registry: Registry,
        enable_thinking: bool = False,
        plan_mode: bool = False,
    ):
        self.provider = provider
        self.registry = registry
        self.enable_thinking = enable_thinking
        self.plan_mode = plan_mode
        self.compactor = Compactor(max_chars=3000, retain_last_msgs=6)
        self.recovery = RecoveryManager()
        self.injector = new_reminder_injector()

    def run(self, session: Session, reporter: Optional[Reporter] = None) -> None:
        logger.info(
            "[Engine] 唤醒会话 [%s]，锁定工作区: %s (PlanMode: %s)",
            session.id,
            session.work_dir,
            self.plan_mode,
        )

        ctx, root_span = start_span({}, "Agent.Run")
        root_span.add_attribute("SessionID", session.id)
        root_span.add_attribute("WorkDir", session.work_dir)

        try:
            composer = PromptComposer(session.work_dir, self.plan_mode)
            system_msg = composer.build()

            turn_count = 0
            while True:
                turn_count += 1
                turn_ctx, turn_span = start_span(ctx, f"Turn-{turn_count}")

                try:
                    available_tools = self.registry.get_available_tools()

                    working_memory = session.get_working_memory(20)

                    context_history: list[Message] = [system_msg, *working_memory]
                    compacted_context = self.compactor.compact(context_history)

                    turn_span.add_attribute("context_message_count", len(compacted_context))

                    current_turn_thinking_content = ""

                    if self.enable_thinking:
                        if reporter is not None:
                            reporter.on_thinking()

                        think_ctx, think_span = start_span(turn_ctx, "LLM.Thinking")
                        think_resp = self.provider.generate(compacted_context, None)
                        think_span.end_span()

                        if think_resp.content:
                            current_turn_thinking_content = think_resp.content
                            compacted_context.append(think_resp)

                    act_ctx, act_span = start_span(turn_ctx, "LLM.Action")
                    action_resp = self.provider.generate(compacted_context, available_tools)
                    act_span.end_span()

                    combined_content = (
                        current_turn_thinking_content + "\n" + action_resp.content
                    ).strip()
                    final_assistant_msg = Message(
                        role=Role.ASSISTANT,
                        content=combined_content,
                        tool_calls=action_resp.tool_calls,
                    )
                    session.append(final_assistant_msg)

                    if action_resp.content and reporter is not None:
                        reporter.on_message(action_resp.content)

                    if not action_resp.tool_calls:
                        break

                    observation_msgs: list[Message | None] = [
                        None
                    ] * len(action_resp.tool_calls)

                    last_tool_call: ToolCall | None = None
                    last_tool_result: ToolResult | None = None

                    def _execute_tool(idx: int, call):
                        nonlocal last_tool_call, last_tool_result

                        if reporter is not None:
                            reporter.on_tool_call(call.name, call.arguments)

                        result = self.registry.execute(turn_ctx, call)

                        if idx == 0:
                            last_tool_call = call
                            last_tool_result = result

                        final_output = result.output
                        if result.is_error:
                            final_output = self.recovery.analyze_and_inject(
                                call.name, result.output
                            )
                            logger.info(
                                "  -> [Py-%d] ❌ 注入救援指南: %s", idx, final_output
                            )
                        else:
                            logger.info(
                                "  -> [Py-%d] ✅ 工具执行成功 (返回 %d 字节)",
                                idx,
                                len(result.output),
                            )

                        if reporter is not None:
                            display_output = final_output
                            if len(display_output) > 200:
                                display_output = display_output[:200] + "... (已截断)"
                            reporter.on_tool_result(
                                call.name, display_output, result.is_error
                            )

                        observation_msgs[idx] = Message(
                            role=Role.USER,
                            content=final_output,
                            tool_call_id=call.id,
                        )
                        return idx

                    with ThreadPoolExecutor(
                        max_workers=len(action_resp.tool_calls)
                    ) as executor:
                        futures = [
                            executor.submit(_execute_tool, i, tool_call)
                            for i, tool_call in enumerate(action_resp.tool_calls)
                        ]
                        for future in as_completed(futures):
                            future.result()

                    session.append(*[m for m in observation_msgs if m is not None])

                    if last_tool_call is not None and last_tool_result is not None:
                        reminder_msg = self.injector.check_and_inject(
                            last_tool_call, last_tool_result
                        )
                        if reminder_msg is not None:
                            session.append(reminder_msg)
                finally:
                    turn_span.end_span()
        finally:
            root_span.end_span()
            export_trace_to_file(root_span, session.work_dir, session.id)

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any,
    ) -> tuple[str, Exception | None]:
        context_history: list[Message] = [
            Message(
                role=Role.SYSTEM,
                content="""你是一个专门负责深度探索的探路者 (Explorer Subagent)。
你的任务是根据主架构师的指令，在当前工作区内仔细阅读代码、查阅日志，搜集足够的信息。

【核心纪律】
1. 你必须、且只能依靠内置工具（如 bash 的 find/grep，或 read_file）去寻找答案。绝对不允许凭空捏造或猜测！
2. 如果你没有找到确切的答案，你必须继续使用工具深入搜索。
3. 当且仅当你找到了确切的线索后，停止调用工具，直接输出一段纯文本作为你的终极汇报。主架构师会根据你的汇报来做下一步决策。""",
            ),
            Message(role=Role.USER, content=task_prompt),
        ]

        max_sub_turns = 10
        turn_count = 0

        while True:
            turn_count += 1
            if turn_count > max_sub_turns:
                return "", Exception(
                    f"子智能体探索过于深入，超过 {max_sub_turns} 轮被强制召回，请主 Agent 给它更明确的指令"
                )

            available_tools = read_only_registry.get_available_tools()

            compacted_context = self.compactor.compact(context_history)

            action_resp = self.provider.generate(compacted_context, available_tools)

            context_history.append(action_resp)

            if not action_resp.tool_calls:
                return action_resp.content, None

            observation_msgs: list[Message | None] = [
                None
            ] * len(action_resp.tool_calls)

            def _execute_sub_tool(idx: int, call):
                r: Reporter | None = None
                if reporter is not None:
                    r = reporter
                    r.on_tool_call(f"[Subagent] {call.name}", call.arguments)

                result = read_only_registry.execute({}, call)

                final_output = result.output
                if result.is_error:
                    final_output = self.recovery.analyze_and_inject(
                        call.name, result.output
                    )

                if reporter is not None and r is not None:
                    display = final_output
                    if len(display) > 200:
                        display = display[:200] + "... (已截断)"
                    r.on_tool_result(
                        f"[Subagent] {call.name}", display, result.is_error
                    )

                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=final_output,
                    tool_call_id=call.id,
                )
                return idx

            with ThreadPoolExecutor(
                max_workers=len(action_resp.tool_calls)
            ) as executor:
                futures = [
                    executor.submit(_execute_sub_tool, i, tool_call)
                    for i, tool_call in enumerate(action_resp.tool_calls)
                ]
                for future in as_completed(futures):
                    future.result()

            context_history.extend([m for m in observation_msgs if m is not None])