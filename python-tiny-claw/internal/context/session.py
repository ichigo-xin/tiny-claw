from __future__ import annotations
import threading
import time
from typing import Optional

from internal.schema import Message, Role


class Session:
    def __init__(self, session_id: str, work_dir: str):
        self.id = session_id
        self.work_dir = work_dir
        self.created_at = time.time()
        self.updated_at = time.time()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_cny = 0.0
        self._history: list[Message] = []
        self._lock = threading.RLock()

    def record_usage(self, prompt: int, completion: int, cost: float) -> None:
        with self._lock:
            self.total_prompt_tokens += prompt
            self.total_completion_tokens += completion
            self.total_cost_cny += cost

    def append(self, *msgs: Message) -> None:
        with self._lock:
            self._history.extend(msgs)
            self.updated_at = time.time()

    def get_working_memory(self, limit: int) -> list[Message]:
        with self._lock:
            total = len(self._history)
            if total <= limit or limit <= 0:
                import copy
                return copy.deepcopy(self._history)

            res = self._history[total - limit:]
            res_copy = []
            for msg in res:
                import copy
                res_copy.append(copy.deepcopy(msg))

            while len(res_copy) > 0:
                first = res_copy[0]
                if first.role == Role.USER and first.tool_call_id is not None:
                    res_copy = res_copy[1:]
                else:
                    break

            return res_copy


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def get_or_create(self, session_id: str, work_dir: str) -> Session:
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            sess = Session(session_id, work_dir)
            self._sessions[session_id] = sess
            return sess


global_session_mgr = SessionManager()
