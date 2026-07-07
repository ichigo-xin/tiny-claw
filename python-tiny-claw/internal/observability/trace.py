from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class _TraceKey:
    pass


_TRACE_KEY = _TraceKey()


@dataclass
class Span:
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List[Span] = field(default_factory=list)

    _mu: threading.Lock = field(default_factory=threading.Lock)

    def end_span(self) -> None:
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)

    def add_attribute(self, key: str, value: Any) -> None:
        with self._mu:
            self.attributes[key] = value


def start_span(ctx: dict[str, Any], name: str) -> tuple[dict[str, Any], Span]:
    span = Span(name=name)

    if _TRACE_KEY in ctx:
        parent = ctx[_TRACE_KEY]
        with parent._mu:
            parent.children.append(span)

    new_ctx = ctx.copy()
    new_ctx[_TRACE_KEY] = span
    return new_ctx, span


def export_trace_to_file(root_span: Span, work_dir: str, session_id: str) -> None:
    trace_dir = os.path.join(work_dir, ".claw", "traces")
    os.makedirs(trace_dir, exist_ok=True)

    filename = os.path.join(trace_dir, f"trace_{session_id}_{int(time.time())}.json")

    def _serialize(span: Span) -> dict[str, Any]:
        return {
            "name": span.name,
            "start_time": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(span.start_time)
            ),
            "end_time": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(span.end_time)
            ),
            "duration_ms": span.duration_ms,
            "attributes": span.attributes,
            "children": [_serialize(child) for child in span.children],
        }

    data = _serialize(root_span)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"📊 [Tracing] 本次任务的执行回放链路已保存至工作区的 .claw/traces 目录下")