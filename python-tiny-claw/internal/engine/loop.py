from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from internal.context.composer import PromptComposer
from internal.engine.reporter import Reporter
from internal.engine.session import Session
from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role
from internal.tools.registry import RegistryImpl as Registry

logger = logging.getLogger(__name__)


class AgentEngine:
    """Agent 引擎本身是无状态的，它不绑定 WorkDir，而是跟随传入的 Session。"""

    def __init__(
        self,
        provider: LLMProvider,
        registry: Registry,
        enable_thinking: bool = False,
    ):
        self.provider = provider
        self.registry = registry
        self.enable_thinking = enable_thinking

    def run(self, session: Session, reporter: Optional[Reporter] = None) -> None:
        """【核心改造】: 移除 user_prompt 参数，改为接收一个具体的 Session 实例

        Args:
            session: 本次交互所属的会话，提供工作区、历史记忆与并发隔离。
            reporter: 可选的事件上报器，用于向终端/飞书等展现层推送状态。
        """
        logger.info("[Engine] 唤醒会话 [%s]，锁定工作区: %s", session.id, session.work_dir)

        # 根据当前 Session 的工作区，动态组装最新的 System Prompt
        composer = PromptComposer(session.work_dir)
        system_msg = composer.build()

        while True:
            available_tools = self.registry.get_available_tools()

            # 1. 【上下文组装】: System Prompt + 截取最近的 6 条消息作为 Working Memory
            # 在实际业务中，由于工具返回结果可能很长，短期工作记忆往往设为 6-10 条足以维系连贯对话
            working_memory = session.get_working_memory(6)

            context_history: list[Message] = [system_msg, *working_memory]

            # 2. ================= Phase 1: Thinking =================
            if self.enable_thinking:
                if reporter is not None:
                    reporter.on_thinking()

                think_resp = self.provider.generate(context_history, None)
                if think_resp.content:
                    # 将思考过程持久化到 Session 中！
                    session.append(think_resp)
                    # 把它追加到当前这一轮的临时上下文中，供 Action 阶段使用
                    context_history.append(think_resp)

            # 3. ================= Phase 2: Action =================
            action_resp = self.provider.generate(context_history, available_tools)

            # 将大模型的行动响应持久化到 Session 中
            session.append(action_resp)
            context_history.append(action_resp)

            if action_resp.content and reporter is not None:
                reporter.on_message(action_resp.content)

            # 如果没有工具调用，说明本次任务已完成，打破 ReAct 循环，挂起等待人类的下一条指令
            if not action_resp.tool_calls:
                break

            # 4. ================= 并发执行底层工具 =================
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

            # 将所有的工具执行结果（Observation）持久化到 Session 中，开启下一轮的复盘与推理
            session.append(*[m for m in observation_msgs if m is not None])
