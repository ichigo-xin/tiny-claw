from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Optional


class Role:
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: bytes

    @property
    def arguments_json(self) -> Any:
        return json.loads(self.arguments) if self.arguments else None


@dataclass
class ToolResult:
    tool_call_id: str
    output: str
    is_error: bool = False


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    usage: Optional[Usage] = None

    def to_dict(self) -> dict:
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments.decode("utf-8") if isinstance(tc.arguments, bytes) else tc.arguments
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.usage:
            result["usage"] = {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens
            }
        return result


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Any
