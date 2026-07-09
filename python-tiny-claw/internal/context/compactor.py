from __future__ import annotations
import copy
import logging

from internal.schema import Message, Role


class Compactor:
    def __init__(self, max_chars: int = 20000, retain_last_msgs: int = 6):
        self.max_chars = max_chars
        self.retain_last_msgs = retain_last_msgs

    def compact(self, msgs: list[Message]) -> list[Message]:
        current_length = self._estimate_length(msgs)

        if current_length < self.max_chars:
            return msgs

        logging.warning(
            f"[Compactor] ⚠️ 内存告警：当前上下文长度 ({current_length} 字符) 超过阈值 ({self.max_chars})，触发压缩清理..."
        )

        compacted: list[Message] = []
        msg_count = len(msgs)

        protect_start_index = msg_count - self.retain_last_msgs
        if protect_start_index < 0:
            protect_start_index = 0

        for i, msg in enumerate(msgs):
            if msg.role == Role.SYSTEM:
                compacted.append(copy.deepcopy(msg))
                continue

            new_msg = copy.deepcopy(msg)
            is_in_working_memory = i >= protect_start_index

            if msg.role == Role.USER and msg.tool_call_id is not None:
                if not is_in_working_memory:
                    if len(msg.content) > 200:
                        new_msg.content = f"...[为了节省内存，早期的工具输出已被系统强制清理。原始长度: {len(msg.content)} 字节]..."
                else:
                    max_keep = 1000
                    if len(msg.content) > max_keep:
                        head = msg.content[:500]
                        tail = msg.content[-500:]
                        new_msg.content = f"{head}\n\n...[内容过长，中间 {len(msg.content) - max_keep} 字节已被系统截断]...\n\n{tail}"
            elif msg.role == Role.ASSISTANT and msg.content != "":
                if not is_in_working_memory and len(msg.content) > 200:
                    new_msg.content = "...[早期的推理思考过程已折叠]..."

            compacted.append(new_msg)

        new_length = self._estimate_length(compacted)
        logging.info(f"[Compactor] ✅ 压缩完成。上下文长度从 {current_length} 降至 {new_length} 字符。")

        return compacted

    def _estimate_length(self, msgs: list[Message]) -> int:
        length = 0
        for msg in msgs:
            length += len(msg.content)
            for tc in msg.tool_calls:
                args_len = len(tc.arguments) if isinstance(tc.arguments, (bytes, str)) else 0
                length += len(tc.name) + args_len
        return length
