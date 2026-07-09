from __future__ import annotations
import os
import json
from typing import Any

from anthropic import Anthropic

from internal.schema import (
    Message,
    Role,
    ToolCall,
    ToolDefinition,
)
from .interface import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str):
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise RuntimeError("请设置 ZHIPU_API_KEY 环境变量")
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.client = Anthropic(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition],
    ) -> Message:
        anthropic_messages = []
        system_prompt = ""

        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_prompt = msg.content
            elif msg.role == Role.USER:
                if msg.tool_call_id:
                    anthropic_messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    })
                else:
                    anthropic_messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": msg.content}],
                    })
            elif msg.role == Role.ASSISTANT:
                blocks = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    input_map = json.loads(tc.arguments.decode("utf-8") if isinstance(tc.arguments, bytes) else tc.arguments)
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": input_map,
                    })
                if blocks:
                    anthropic_messages.append({"role": "assistant", "content": blocks})

        anthropic_tools = []
        for tool_def in available_tools:
            properties = {}
            required = []
            if isinstance(tool_def.input_schema, dict):
                if "properties" in tool_def.input_schema:
                    properties = tool_def.input_schema["properties"]
                if "required" in tool_def.input_schema:
                    required = tool_def.input_schema["required"]
            anthropic_tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        resp = self.client.messages.create(**kwargs)

        result_msg = Message(role=Role.ASSISTANT)
        for block in resp.content:
            if block.type == "text":
                result_msg.content += block.text
            elif block.type == "tool_use":
                args_bytes = json.dumps(block.input).encode("utf-8")
                result_msg.tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=args_bytes,
                ))

        return result_msg
