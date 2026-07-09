from __future__ import annotations
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from internal.context import (
    Session,
    PromptComposer,
    Compactor,
    RecoveryManager,
)
from internal.observability import start_span, export_trace_to_file
from internal.provider import LLMProvider
from internal.schema import Message, Role, ToolCall, ToolResult
from internal.tools import Registry, AgentRunner
from .reporter import Reporter
from .reminder import ReminderInjector


class AgentEngine(AgentRunner):
    def __init__(
        self,
        provider: LLMProvider,
        registry: Registry,
        enable_thinking: bool = False,
        plan_mode: bool = True,
    ):
        self.provider = provider
        self.registry = registry
        self.enable_thinking = enable_thinking
        self.plan_mode = plan_mode
        self.compactor = Compactor(20000, 6)
        self.recovery = RecoveryManager()
        self.injector = ReminderInjector()

    def run(self, session: Session, reporter: Reporter | None = None) -> None:
        logging.info(
            f"[Engine] 唤醒会话 [{session.id}]，锁定工作区: {session.work_dir} (PlanMode: {self.plan_mode})"
        )

        _, root_span = start_span("Agent.Run")
        root_span.add_attribute("SessionID", session.id)
        root_span.add_attribute("WorkDir", session.work_dir)

        try:
            composer = PromptComposer(session.work_dir, self.plan_mode)
            system_msg = composer.build()

            turn_count = 0
            while True:
                turn_count += 1
                _, turn_span = start_span(f"Turn-{turn_count}")

                try:
                    available_tools = self.registry.get_available_tools()
                    working_memory = session.get_working_memory(20)

                    context_history = [system_msg] + working_memory
                    compacted_context = self.compactor.compact(context_history)

                    turn_span.add_attribute("context_message_count", len(compacted_context))

                    current_turn_thinking_content = ""

                    if self.enable_thinking:
                        if reporter:
                            reporter.on_thinking()

                        _, think_span = start_span("LLM.Thinking")
                        think_resp = self.provider.generate(compacted_context, [])
                        think_span.end_span()

                        if think_resp.content:
                            current_turn_thinking_content = think_resp.content
                            compacted_context.append(think_resp)

                    _, act_span = start_span("LLM.Action")
                    action_resp = self.provider.generate(compacted_context, available_tools)
                    act_span.end_span()

                    final_content = (current_turn_thinking_content + "\n" + action_resp.content).strip()
                    final_assistant_msg = Message(
                        role=Role.ASSISTANT,
                        content=final_content,
                        tool_calls=action_resp.tool_calls,
                    )
                    session.append(final_assistant_msg)

                    if action_resp.content and reporter:
                        reporter.on_message(action_resp.content)

                    if not action_resp.tool_calls:
                        break

                    observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)
                    last_tool_call = None
                    last_tool_result = None

                    with ThreadPoolExecutor(max_workers=len(action_resp.tool_calls)) as executor:
                        futures = {}
                        for i, tool_call in enumerate(action_resp.tool_calls):
                            def execute_tool(idx: int, call: ToolCall):
                                if reporter:
                                    reporter.on_tool_call(call.name, call.arguments.decode("utf-8") if isinstance(call.arguments, bytes) else str(call.arguments))

                                result = self.registry.execute(call)

                                final_output = result.output
                                if result.is_error:
                                    final_output = self.recovery.analyze_and_inject(call.name, result.output)

                                if reporter:
                                    display_output = final_output
                                    if len(display_output) > 200:
                                        display_output = display_output[:200] + "... (已截断)"
                                    reporter.on_tool_result(call.name, display_output, result.is_error)

                                obs_msg = Message(
                                    role=Role.USER,
                                    content=final_output,
                                    tool_call_id=call.id,
                                )

                                return idx, call, result, obs_msg

                            futures[executor.submit(execute_tool, i, tool_call)] = i

                        for future in as_completed(futures):
                            idx, call, result, obs_msg = future.result()
                            observation_msgs[idx] = obs_msg
                            if idx == 0:
                                last_tool_call = call
                                last_tool_result = result

                    valid_observations = [msg for msg in observation_msgs if msg is not None]
                    session.append(*valid_observations)

                    reminder_msg = self.injector.check_and_inject(last_tool_call, last_tool_result) if last_tool_call and last_tool_result else None
                    if reminder_msg:
                        session.append(reminder_msg)
                finally:
                    turn_span.end_span()
        finally:
            root_span.end_span()
            export_trace_to_file(root_span, session.work_dir, session.id)
            logging.info("📊 [Tracing] 本次任务的执行回放链路已保存至工作区的 .claw/traces 目录下")

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any = None,
    ) -> str:
        context_history = [
            Message(
                role=Role.SYSTEM,
                content="""你是一个专门负责深度探索的探路者 (Explorer Subagent)。
你的任务是根据主架构师的指令，在当前工作区内仔细阅读代码、查阅日志，搜集足够的信息。

【核心纪律】
1. 你必须、且只能依靠内置工具（如 powershell 的 Get-ChildItem/Select-String，或 read_file）去寻找答案。绝对不允许凭空捏造或猜测！
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
                raise RuntimeError(f"子智能体探索过于深入，超过 {max_sub_turns} 轮被强制召回，请主 Agent 给它更明确的指令")

            available_tools = read_only_registry.get_available_tools()
            compacted_context = self.compactor.compact(context_history)

            action_resp = self.provider.generate(compacted_context, available_tools)
            context_history.append(action_resp)

            if not action_resp.tool_calls:
                return action_resp.content

            observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)

            with ThreadPoolExecutor(max_workers=len(action_resp.tool_calls)) as executor:
                futures = {}
                for i, tool_call in enumerate(action_resp.tool_calls):
                    def execute_sub_tool(idx: int, call: ToolCall):
                        r = None
                        if reporter is not None and hasattr(reporter, '__class__'):
                            try:
                                r = reporter
                                r.on_tool_call(f"[Subagent] {call.name}", call.arguments.decode("utf-8") if isinstance(call.arguments, bytes) else str(call.arguments))
                            except Exception:
                                pass

                        result = read_only_registry.execute(call)

                        final_output = result.output
                        if result.is_error:
                            final_output = self.recovery.analyze_and_inject(call.name, result.output)

                        if r is not None:
                            try:
                                display = final_output
                                if len(display) > 200:
                                    display = display[:200] + "... (已截断)"
                                r.on_tool_result(f"[Subagent] {call.name}", display, result.is_error)
                            except Exception:
                                pass

                        obs_msg = Message(
                            role=Role.USER,
                            content=final_output,
                            tool_call_id=call.id,
                        )
                        return idx, obs_msg

                    futures[executor.submit(execute_sub_tool, i, tool_call)] = i

                for future in as_completed(futures):
                    idx, obs_msg = future.result()
                    observation_msgs[idx] = obs_msg

            valid_observations = [msg for msg in observation_msgs if msg is not None]
            context_history.extend(valid_observations)
