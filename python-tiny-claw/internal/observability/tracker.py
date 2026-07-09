from __future__ import annotations
import logging
import time
from typing import Any

from internal.provider import LLMProvider
from internal.schema import Message, ToolDefinition
from internal.context.session import Session


PRICING_MODEL = {
    "glm-4.5-air": {"input_price": 0.15, "output_price": 0.15},
}


class CostTracker(LLMProvider):
    def __init__(self, next_provider: LLMProvider, model_name: str, session: Session | None = None):
        self.next_provider = next_provider
        self.model_name = model_name
        self.session = session

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition],
    ) -> Message:
        start_time = time.time()

        resp_msg = self.next_provider.generate(messages, available_tools)

        latency = time.time() - start_time

        if resp_msg is None:
            logging.error(f"[Tracker] ❌ API 调用失败，耗时: {latency:.3f}s")
            return resp_msg

        if resp_msg.usage is not None:
            prompt_tokens = resp_msg.usage.prompt_tokens
            completion_tokens = resp_msg.usage.completion_tokens

            cost = 0.0
            if self.model_name in PRICING_MODEL:
                price = PRICING_MODEL[self.model_name]
                cost = (prompt_tokens * price["input_price"] + completion_tokens * price["output_price"]) / 1000000.0

            logging.info(
                f"[Tracker] 📊 API 调用完成 | 耗时: {latency:.3f}s | 输入: {prompt_tokens} tk | 输出: {completion_tokens} tk | 花费: ¥{cost:.6f}"
            )

            if self.session is not None:
                self.session.record_usage(prompt_tokens, completion_tokens, cost)
                logging.info(
                    f"[Tracker] 💰 当前会话 ({self.session.id}) 累计花费: ¥{self.session.total_cost_cny:.6f}"
                )
        else:
            logging.warning(f"[Tracker] ⚠️ API 调用完成，但未返回 Usage 数据 | 耗时: {latency:.3f}s")

        return resp_msg
