from __future__ import annotations

import os
from typing import Any

import anthropic

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, Role, ToolCall, ToolDefinition


class ClaudeProvider(LLMProvider):

    def __init__(self, model: str):
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("请设置 ZHIPU_API_KEY 环境变量")
        
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
    ) -> Message:
        anthropic_messages = []
        system_prompt = ""

        for msg in messages:
            match msg.role:
                case Role.SYSTEM:
                    system_prompt = msg.content
                case Role.USER:
                    if msg.tool_call_id:
                        anthropic_messages.append(
                            anthropic.UserMessage(
                                content=[
                                    anthropic.ToolResultBlock(
                                        tool_call_id=msg.tool_call_id,
                                        content=msg.content,
                                        is_error=False,
                                    )
                                ]
                            )
                        )
                    else:
                        anthropic_messages.append(
                            anthropic.UserMessage(content=msg.content)
                        )
                case Role.ASSISTANT:
                    content = []
                    if msg.content:
                        content.append(anthropic.TextBlock(text=msg.content))
                    
                    for tc in msg.tool_calls:
                        content.append(
                            anthropic.ToolUseBlock(
                                id=tc.id,
                                name=tc.name,
                                input=tc.arguments,
                            )
                        )
                    
                    if content:
                        anthropic_messages.append(
                            anthropic.AssistantMessage(content=content)
                        )

        anthropic_tools = []
        if available_tools:
            for tool_def in available_tools:
                input_schema = tool_def.input_schema.copy()
                input_schema.setdefault("type", "object")
                
                anthropic_tools.append(
                    anthropic.Tool(
                        name=tool_def.name,
                        description=tool_def.description,
                        input_schema=input_schema,
                    )
                )

        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system_prompt:
            params["system"] = system_prompt
        
        if anthropic_tools:
            params["tools"] = anthropic_tools

        resp = self.client.messages.create(**params)

        result_msg = Message(role=Role.ASSISTANT)

        for block in resp.content:
            if isinstance(block, anthropic.TextBlock):
                result_msg.content += block.text
            elif isinstance(block, anthropic.ToolUseBlock):
                result_msg.tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input),
                    )
                )

        return result_msg
