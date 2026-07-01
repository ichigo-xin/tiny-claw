from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from internal.schema.message import Message, Role, ToolCall, ToolResult

logger = logging.getLogger(__name__)


class ReminderInjector:
    """负责在运行时监控上下文，并在模型陷入执念时动态注入强力打断信息"""

    def __init__(self):
        self.consecutive_failures: dict[str, int] = {}

    def _generate_fingerprint(self, tool_name: str, args: dict) -> str:
        """生成工具调用的唯一指纹，用于判断大模型是否在重复相同的动作"""
        hasher = hashlib.md5()
        hasher.update(tool_name.encode("utf-8"))
        args_str = json.dumps(args, sort_keys=True)
        hasher.update(args_str.encode("utf-8"))
        return hasher.hexdigest()

    def check_and_inject(self, last_tool_call: ToolCall, last_result: ToolResult) -> Optional[Message]:
        """分析本轮的执行结果，决定是否要在 Context 尾部追加 Reminder

        返回的 Message 将作为最新的用户输入，强制大模型优先阅读。
        """
        fingerprint = self._generate_fingerprint(last_tool_call.name, last_tool_call.arguments)

        if not last_result.is_error:
            self.consecutive_failures = {}
            return None

        self.consecutive_failures[fingerprint] = self.consecutive_failures.get(fingerprint, 0) + 1
        fail_count = self.consecutive_failures[fingerprint]

        logger.info(
            "[Reminder] 监控到工具 %s 执行失败，该参数特征连续失败次数: %d",
            last_tool_call.name,
            fail_count,
        )

        if fail_count >= 3:
            logger.info("[Reminder] ⚠️ 触发死循环干预！注入强力修正指令。")

            nudge_msg = (
                f"[SYSTEM REMINDER 警告] \n"
                f"你似乎陷入了死循环。你刚刚连续 {fail_count} 次使用相同的参数调用了 '{last_tool_call.name}' 工具，并且都失败了。\n"
                f"请立即停止这种无效的重试！你的注意力被当前的报错过度吸引了。\n"
                f"你需要：\n"
                f"1. 停止猜测参数。跳出当前的局部思维。\n"
                f"2. 彻底改变你的策略。\n"
                f"3. 如果你确实无法通过系统工具解决当前问题，请直接结束任务并向用户说明你需要什么人工帮助，而不是继续盲目消耗 API 资源尝试。"
            )

            return Message(
                role=Role.USER,
                content=nudge_msg,
            )

        return None


def new_reminder_injector() -> ReminderInjector:
    """创建一个新的提醒注入器实例"""
    return ReminderInjector()