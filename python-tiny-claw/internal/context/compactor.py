from __future__ import annotations

import json
import logging

from internal.schema.message import Message, Role

logger = logging.getLogger(__name__)


class Compactor:
    """Compactor 负责监控和压缩上下文内存，防止大模型发生 OOM"""

    def __init__(self, max_chars: int, retain_last_msgs: int):
        self.max_chars = max_chars
        self.retain_last_msgs = retain_last_msgs

    def compact(self, msgs: list[Message]) -> list[Message]:
        """Compact 接收准备发送给大模型的消息数组。

        如果总长度超标，对远期历史区进行全量掩码 (Masking)，
        对短期保护区进行超长局部截断 (Truncation)。
        """
        current_length = self._estimate_length(msgs)

        if current_length < self.max_chars:
            return msgs

        logger.warning(
            "[Compactor] ⚠️ 内存告警：当前上下文长度 (%d 字符) 超过阈值 (%d)，触发压缩清理...",
            current_length,
            self.max_chars,
        )

        compacted: list[Message] = []
        msg_count = len(msgs)

        protect_start_index = msg_count - self.retain_last_msgs
        if protect_start_index < 0:
            protect_start_index = 0

        for i, msg in enumerate(msgs):
            if msg.role == Role.SYSTEM:
                compacted.append(msg)
                continue

            new_msg = Message(
                role=msg.role,
                content=msg.content,
                tool_calls=list(msg.tool_calls),
                tool_call_id=msg.tool_call_id,
            )

            is_in_working_memory = i >= protect_start_index

            # 【核心驾驭逻辑】: 双重降级防线
            if msg.role == Role.USER and msg.tool_call_id != "":
                if not is_in_working_memory:
                    # 【第一道防线：远期历史】如果是早期对话，执行无情替换 (Full Masking)
                    if len(msg.content) > 200:
                        new_msg.content = (
                            f"...[为了节省内存，早期的工具输出已被系统强制清理。原始长度: {len(msg.content)} 字节]..."
                        )
                else:
                    # 【第二道防线：短期记忆】即使处于近期保护区，只要单条内容过大，
                    # 也必须截断防 OOM (Head-Tail Truncation)
                    # 保留前 500 字符和后 500 字符（掐头去尾法）
                    max_keep = 1000
                    if len(msg.content) > max_keep:
                        head = msg.content[:500]
                        tail = msg.content[-500:]
                        new_msg.content = (
                            f"{head}\n\n...[内容过长，中间 {len(msg.content) - max_keep} 字节已被系统截断]...\n\n{tail}"
                        )
            elif msg.role == Role.ASSISTANT and msg.content != "":
                if not is_in_working_memory and len(msg.content) > 200:
                    new_msg.content = "...[早期的推理思考过程已折叠]..."

            compacted.append(new_msg)

        new_length = self._estimate_length(compacted)
        logger.warning(
            "[Compactor] ✅ 压缩完成。上下文长度从 %d 降至 %d 字符。",
            current_length,
            new_length,
        )

        return compacted

    def _estimate_length(self, msgs: list[Message]) -> int:
        """粗略计算当前上下文的总字符长度"""
        length = 0
        for msg in msgs:
            length += len(msg.content)
            for tc in msg.tool_calls:
                length += len(tc.name)
                length += len(json.dumps(tc.arguments, ensure_ascii=False))
        return length
