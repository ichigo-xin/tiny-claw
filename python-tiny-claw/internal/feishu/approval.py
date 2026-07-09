from __future__ import annotations
import re
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Optional


@dataclass
class ApprovalResult:
    allowed: bool
    reason: str


class ApprovalManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._pending_tasks: dict[str, Queue[ApprovalResult]] = {}

    def wait_for_approval(
        self,
        task_id: str,
        tool_name: str,
        args: str,
        reporter=None,
    ) -> tuple[bool, str]:
        ch: Queue[ApprovalResult] = Queue(maxsize=1)

        with self._lock:
            self._pending_tasks[task_id] = ch

        notice_msg = f"""⚠️ **高危操作审批请求**
Agent 试图执行以下动作:
- 工具: {tool_name}
- 参数: {args}

任务 ID: **{task_id}**

👉 请回复 "approve {task_id}" 或 "reject {task_id}" 决定是否放行。"""

        if reporter is not None and hasattr(reporter, 'send_msg'):
            try:
                reporter.send_msg(notice_msg)
            except Exception:
                print(f"\n\033[31m[需要审批 TaskID: {task_id}]\033[0m {notice_msg}")
        else:
            print(f"\n\033[31m[需要审批 TaskID: {task_id}]\033[0m {notice_msg}")

        import logging
        logging.info(f"[Approval] 发送审批请求 (TaskID: {task_id})，协程挂起等待...")

        result = ch.get()

        with self._lock:
            if task_id in self._pending_tasks:
                del self._pending_tasks[task_id]

        return result.allowed, result.reason

    def resolve_approval(self, task_id: str, allowed: bool, reason: str) -> None:
        with self._lock:
            ch = self._pending_tasks.get(task_id)

        if ch is not None:
            import logging
            logging.info(f"[Approval] 收到审批结果 (TaskID: {task_id}, Allowed: {allowed})")
            ch.put(ApprovalResult(allowed=allowed, reason=reason))


def is_dangerous_command(tool_name: str, args: str) -> bool:
    if tool_name not in ("bash", "powershell", "write_file", "edit_file"):
        return False

    dangerous_patterns = []
    if tool_name == "bash":
        dangerous_patterns = [r"rm\s+-r", r"sudo\s+", r"drop\s+", r">.*\.go"]
    elif tool_name == "powershell":
        dangerous_patterns = [
            r"rm\s+-r", r"rm\s+-rf", r"Remove-Item", r"rmdir",
            r"del\s+", r"erase\s+", r"format\s+", r"sudo\s+",
            r"drop\s+", r">.*\.go",
        ]

    for p in dangerous_patterns:
        if re.search(p, args, re.IGNORECASE):
            return True

    return False


global_approval_mgr = ApprovalManager()
