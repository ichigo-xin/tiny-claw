from __future__ import annotations
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_thread_local = threading.local()


@dataclass
class Span:
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list["Span"] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _parent: "Span | None" = field(default=None, repr=False)

    def end_span(self) -> None:
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        # 恢复父 span 为当前 span
        if hasattr(_thread_local, 'span_stack'):
            stack = _thread_local.span_stack
            if stack and stack[-1] is self:
                stack.pop()

    def add_attribute(self, key: str, value: Any) -> None:
        with self._lock:
            self.attributes[key] = value


def _get_span_stack() -> list[Span]:
    if not hasattr(_thread_local, 'span_stack'):
        _thread_local.span_stack = []
    return _thread_local.span_stack


def start_span(name: str) -> tuple[Any, Span]:
    stack = _get_span_stack()
    span = Span(name=name)
    if stack:
        parent = stack[-1]
        with parent._lock:
            parent.children.append(span)
            span._parent = parent
    stack.append(span)
    return None, span


def export_trace_to_file(root_span: Span, work_dir: str, session_id: str) -> None:
    trace_dir = Path(work_dir) / ".claw" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    filename = trace_dir / f"trace_{session_id}_{int(time.time())}.json"

    def span_to_dict(s: Span) -> dict:
        return {
            "name": s.name,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "duration_ms": s.duration_ms,
            "attributes": s.attributes,
            "children": [span_to_dict(c) for c in s.children],
        }

    data = json.dumps(span_to_dict(root_span), indent=2, ensure_ascii=False)
    filename.write_text(data, encoding="utf-8")
