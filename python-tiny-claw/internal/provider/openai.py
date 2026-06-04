from __future__ import annotations

import os

from openai import OpenAI

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role, ToolCall, ToolDefinition


class OpenAIProvider(LLMProvider):

    def __init__(self, model: str):
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY 环境变量")
        
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
    ) -> Message:
        openai_messages = []

        for msg in messages:
            match msg.role:
                case Role.SYSTEM:
                    openai_messages.append({"role": "system", "content": msg.content})
                case Role.USER:
                    if msg.tool_call_id:
                        openai_messages.append({
                            "role": "user",
                            "content": msg.content,
                            "tool_call_id": msg.tool_call_id,
                        })
                    else:
                        openai_messages.append({"role": "user", "content": msg.content})
                case Role.ASSISTANT:
                    assistant_msg: dict[str, any] = {"role": "assistant"}
                    
                    if msg.content:
                        assistant_msg["content"] = msg.content
                    else:
                        assistant_msg["content"] = None
                    
                    if msg.tool_calls:
                        tool_calls = []
                        for tc in msg.tool_calls:
                            tool_calls.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                },
                            })
                        assistant_msg["tool_calls"] = tool_calls
                    
                    openai_messages.append(assistant_msg)

        openai_tools = []
        if available_tools:
            for tool_def in available_tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "parameters": tool_def.input_schema,
                    },
                })

        params: dict[str, any] = {
            "model": self.model,
            "messages": openai_messages,
        }

        if openai_tools:
            params["tools"] = openai_tools

        resp = self.client.chat.completions.create(**params)

        choice = resp.choices[0]
        result_msg = Message(
            role=Role.ASSISTANT,
            content=choice.message.content or "",
        )

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                result_msg.tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        return result_msg
