from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from internal.context.compactor import Compactor
from internal.context.composer import PromptComposer
from internal.context.recovery import RecoveryManager
from internal.context.session import Session
from internal.engine.reporter import Reporter
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
        plan_mode: bool = False,
    ):
        self.provider = provider
        self.registry = registry
        self.enable_thinking = enable_thinking
        self.plan_mode = plan_mode  # 【新增】暴露给外部的计划模式开关
        self.compactor = Compactor(max_chars=3000, retain_last_msgs=6)
        self.recovery = RecoveryManager()  # 【新增】自愈管理器

    def run(self, session: Session, reporter: Optional[Reporter] = None) -> None:
        """【核心改造】: 移除 user_prompt 参数，改为接收一个具体的 Session 实例

        Args:
            session: 本次交互所属的会话，提供工作区、历史记忆与并发隔离。
            reporter: 可选的事件上报器，用于向终端/飞书等展现层推送状态。
        """
        logger.info(
            "[Engine] 唤醒会话 [%s]，锁定工作区: %s (PlanMode: %s)",
            session.id,
            session.work_dir,
            self.plan_mode,
        )

        # 在每次运行前，动态生成组装器并传入当前的 PlanMode 状态
        composer = PromptComposer(session.work_dir, self.plan_mode)
        system_msg = composer.build()

        while True:
            available_tools = self.registry.get_available_tools()

            # 1. 从 Session 提取出近期的 Working Memory (例如最近 20 条，给压缩器留下充足的判断空间)
            working_memory = session.get_working_memory(20)

            context_history: list[Message] = [system_msg, *working_memory]

            # 2. 【核心注入点】: 在向 Provider 发起推理前，过一遍内存压缩器！
            # 无论你带出了多少上下文，如果字符总数超标，早期日志将被掩码化，超大日志将被掐头去尾
            compacted_context = self.compactor.compact(context_history)

            # 3. 后续的 Provider.Generate 全面使用被保护过的新鲜上下文 (compacted_context)
            current_turn_thinking_content = ""

            # ================= Phase 1: Thinking =================
            if self.enable_thinking:
                if reporter is not None:
                    reporter.on_thinking()

                think_resp = self.provider.generate(compacted_context, None)
                if think_resp.content:
                    current_turn_thinking_content = think_resp.content
                    compacted_context.append(think_resp)

            # ================= Phase 2: Action =================
            action_resp = self.provider.generate(compacted_context, available_tools)

            # (合并为合法的单条 Assistant 消息)
            combined_content = (current_turn_thinking_content + "\n" + action_resp.content).strip()
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

            # ================= 执行工具并注入自愈模板 =================
            observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)

            def _execute_tool(idx: int, call):
                if reporter is not None:
                    reporter.on_tool_call(call.name, call.arguments)

                result = self.registry.execute(call)

                # 【核心拦截与注入】
                final_output = result.output
                if result.is_error:
                    # 发生错误，交由 RecoveryManager 诊断并注入"锦囊妙计"
                    final_output = self.recovery.analyze_and_inject(call.name, result.output)
                    logger.info("  -> [Py-%d] ❌ 注入救援指南: %s", idx, final_output)
                else:
                    logger.info("  -> [Py-%d] ✅ 工具执行成功 (返回 %d 字节)", idx, len(result.output))

                if reporter is not None:
                    display_output = final_output
                    if len(display_output) > 200:
                        display_output = display_output[:200] + "... (已截断)"
                    reporter.on_tool_result(call.name, display_output, result.is_error)

                # 将注入过 Recovery Hint 的最终结果写入上下文历史
                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=final_output,
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

            # 将全量观测结果持久化到 Session 中
            session.append(*[m for m in observation_msgs if m is not None])
