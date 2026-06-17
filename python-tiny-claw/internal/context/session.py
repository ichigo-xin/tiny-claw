from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from internal.schema.message import Message, Role


class Session:
    """Session 代表了一次持续的人机交互过程。它负责维护该会话的完整历史。"""

    def __init__(self, id: str, work_dir: str):
        self.id: str = id
        self.work_dir: str = work_dir
        self.created_at: float = time.time()
        self.updated_at: float = time.time()

        self._history: list[Message] = []
        self._lock = threading.RLock()

    def append(self, *msgs: Message) -> None:
        """线程安全地向 Session 中追加消息"""
        with self._lock:
            self._history.extend(msgs)
            self.updated_at = time.time()

    def get_working_memory(self, limit: int) -> list[Message]:
        """get_working_memory 是驾驭工程的核心！

        它不返回全量历史，而是从后往前截取最近的 N 条消息，
        形成 Agent 的"短期工作记忆"。
        """
        with self._lock:
            total = len(self._history)
            if total <= limit or limit <= 0:
                return list(self._history)

            res = list(self._history[total - limit:])

        # 【驾驭防线】：大模型 API 强制要求历史消息的连续性！
        # 如果我们截断的第一条消息恰好是一个 ToolResult (RoleUser 且含有 ToolCallID)，
        # 但发出这个请求的 ToolCall 被我们截断抛弃了，大模型 API 会直接报 400 Bad Request。
        # 因此，如果切片首条属于"孤儿"工具响应，我们必须将其强行舍弃，
        # 顺延到下一条正常的 User/Assistant 消息。
        while res:
            first = res[0]
            if first.role == Role.USER and first.tool_call_id:
                res.pop(0)
            else:
                break

        return res


class SessionManager:
    """全局 Session Manager: 用于多用户/多终端隔离"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def get_or_create(self, id: str, work_dir: str) -> Session:
        """获取或创建一个会话

        若指定 id 为空字符串，则自动生成一个新的 uuid 作为会话 ID。
        """
        with self._lock:
            if not id:
                id = uuid.uuid4().hex

            if id in self._sessions:
                return self._sessions[id]

            sess = Session(id, work_dir)
            self._sessions[id] = sess
            return sess

    def get(self, id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(id)


# 全局单例，对应 go 项目中的 context.GlobalSessionMgr
global_session_mgr = SessionManager()
