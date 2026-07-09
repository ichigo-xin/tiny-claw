from __future__ import annotations
import os
import json
from typing import Any

from openai import OpenAI

from internal.schema import (
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    Usage,
)
from .interface import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str):
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise RuntimeError("请设置 ZHIPU_API_KEY 环境变量")
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition],
    ) -> Message:
        openai_messages = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                if msg.tool_call_id:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    })
                else:
                    openai_messages.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                ast_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content if msg.content is not None else "",
                }
                if msg.tool_calls:
                    ast_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments.decode("utf-8") if isinstance(tc.arguments, bytes) else tc.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                openai_messages.append(ast_msg)

        tools = []
        for tool_def in available_tools:
            if isinstance(tool_def.input_schema, dict):
                params = tool_def.input_schema
            else:
                params = json.loads(json.dumps(tool_def.input_schema))
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": params,
                },
            })

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = tools

        resp = self.client.chat.completions.create(**kwargs)
        if not resp.choices:
            raise RuntimeError("API 返回了空的 Choices")

        choice = resp.choices[0].message
        result_msg = Message(
            role=Role.ASSISTANT,
            content=choice.content or "",
        )

        if resp.usage and (resp.usage.prompt_tokens > 0 or resp.usage.completion_tokens > 0):
            result_msg.usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
            )

        if choice.tool_calls:
            for tc in choice.tool_calls:
                if tc.type == "function":
                    args_str = tc.function.arguments
                    result_msg.tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args_str.encode("utf-8") if isinstance(args_str, str) else args_str,
                    ))

        return result_msg
