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
        self.plan_mode = plan_mode  # 【新增】暴露给外部的计划模式开关
        self.compactor = Compactor(max_chars=3000, retain_last_msgs=6)
        self.recovery = RecoveryManager()  # 【新增】自愈管理器
        self.injector = new_reminder_injector()  # 【新增】提醒注入器

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

            last_tool_call: ToolCall | None = None
            last_tool_result: ToolResult | None = None

            def _execute_tool(idx: int, call):
                nonlocal last_tool_call, last_tool_result

                if reporter is not None:
                    reporter.on_tool_call(call.name, call.arguments)

                result = self.registry.execute(call)

                if idx == 0:
                    last_tool_call = call
                    last_tool_result = result

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

            # 【核心防线】：在准备进入下一轮之前，进行死循环探测！
            if last_tool_call is not None and last_tool_result is not None:
                reminder_msg = self.injector.check_and_inject(last_tool_call, last_tool_result)
                if reminder_msg is not None:
                    session.append(reminder_msg)

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any,
    ) -> tuple[str, Exception | None]:
        """RunSub 是专为 Subagent 拉起的一次性受限循环。
        它不依赖外部 Session，打完就跑。
        Reporter：为了让用户在终端看到子智能体的工作轨迹，我们将主线程的 Reporter 透传进来，并打上特殊标记。
        """
        # 【核心优化】：子智能体极其容易偷懒。我们必须在 System Prompt 中严厉警告它必须使用工具！
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

        # 限制子智能体最多只能跑 10 个 Turn，防止它自己卡死
        max_sub_turns = 10
        turn_count = 0

        while True:
            turn_count += 1
            if turn_count > max_sub_turns:
                return "", Exception(
                    f"子智能体探索过于深入，超过 {max_sub_turns} 轮被强制召回，请主 Agent 给它更明确的指令"
                )

            # 【驾驭底线】：子智能体仅能获取传入的只读工具注册表
            available_tools = read_only_registry.get_available_tools()

            compacted_context = self.compactor.compact(context_history)

            # 子任务要求急速响应，强制关闭主体的慢思考，直接预测行动
            action_resp = self.provider.generate(compacted_context, available_tools)

            context_history.append(action_resp)

            # 【核心退出条件】：子智能体一旦不调用工具了，说明它做好了总结汇报
            if not action_resp.tool_calls:
                # 直接将它的这段汇报内容剥离出来返回给上层
                return action_resp.content, None

            # 执行只读工具的并发循环
            observation_msgs: list[Message | None] = [None] * len(action_resp.tool_calls)

            def _execute_sub_tool(idx: int, call):
                # 【可视化的关键】：让终端用户看到 Subagent 正在干嘛
                r: Reporter | None = None
                if reporter is not None:
                    r = reporter
                    r.on_tool_call(f"[Subagent] {call.name}", call.arguments)

                result = read_only_registry.execute(call)

                final_output = result.output
                if result.is_error:
                    final_output = self.recovery.analyze_and_inject(call.name, result.output)

                if reporter is not None and r is not None:
                    display = final_output
                    if len(display) > 200:
                        display = display[:200] + "... (已截断)"
                    r.on_tool_result(f"[Subagent] {call.name}", display, result.is_error)

                observation_msgs[idx] = Message(
                    role=Role.USER,
                    content=final_output,
                    tool_call_id=call.id,
                )
                return idx

            with ThreadPoolExecutor(max_workers=len(action_resp.tool_calls)) as executor:
                futures = [
                    executor.submit(_execute_sub_tool, i, tool_call)
                    for i, tool_call in enumerate(action_resp.tool_calls)
                ]
                for future in as_completed(futures):
                    future.result()

            context_history.extend([m for m in observation_msgs if m is not None])
