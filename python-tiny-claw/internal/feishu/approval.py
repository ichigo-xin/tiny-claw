from __future__ import annotations

import logging
import re
import threading
from typing import Optional

from internal.engine.reporter import Reporter

logger = logging.getLogger(__name__)


class ApprovalResult:
    allowed: bool
    reason: str

    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason


class ApprovalManager:
    def __init__(self):
        self._mu = threading.RLock()
        self._pending_tasks: dict[str, dict] = {}

    def wait_for_approval(
        self, task_id: str, tool_name: str, args: str, reporter: Optional[Reporter] = None
    ) -> tuple[bool, str]:
        event = threading.Event()
        result_container = {"result": None}

        with self._mu:
            self._pending_tasks[task_id] = {
                "event": event,
                "result": result_container,
            }

        notice_msg = f"""⚠️ **高危操作审批请求**
Agent 试图执行以下动作:
- 工具: {tool_name}
- 参数: {args}

任务 ID: **{task_id}**

👉 请回复 "approve {task_id}" 或 "reject {task_id}" 决定是否放行。"""

        if reporter is not None:
            reporter.send_msg(notice_msg)
        else:
            print(f"\033[31m[需要审批 TaskID: {task_id}]\033[0m {notice_msg}")

        logger.info("[Approval] 发送审批请求 (TaskID: %s)，线程挂起等待...", task_id)

        event.wait()

        with self._mu:
            del self._pending_tasks[task_id]

        result = result_container["result"]
        return result.allowed, result.reason

    def resolve_approval(self, task_id: str, allowed: bool, reason: str) -> None:
        with self._mu:
            item = self._pending_tasks.get(task_id)
            if not item:
                return

        logger.info("[Approval] 收到飞书审批结果 (TaskID: %s, Allowed: %s)", task_id, allowed)

        item["result"]["result"] = ApprovalResult(allowed, reason)
        item["event"].set()


_global_approval_mgr = ApprovalManager()


def get_global_approval_mgr() -> ApprovalManager:
    return _global_approval_mgr


def is_dangerous_command(tool_name: str, args: str) -> bool:
    if tool_name not in ("bash", "powershell", "write_file", "edit_file"):
        return False

    if tool_name == "bash":
        dangerous_patterns = [r"rm\s+-r", r"sudo\s+", r"drop\s+", r">.*\.go"]
        for pattern in dangerous_patterns:
            if re.search(pattern, args):
                return True

    if tool_name == "powershell":
        dangerous_patterns = [
            r"rm\s+-r",
            r"rm\s+-rf",
            r"Remove-Item",
            r"rmdir",
            r"del\s+",
            r"erase\s+",
            r"format\s+",
            r"sudo\s+",
            r"drop\s+",
            r">.*\.go",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, args):
                return True

    return False