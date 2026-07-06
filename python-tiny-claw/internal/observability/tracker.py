from __future__ import annotations

import logging
import time

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, ToolDefinition

PRICING_MODEL = {
    "glm-4.5-air": {"input_price": 0.15, "output_price": 0.15},
}

logger = logging.getLogger(__name__)


class CostTracker(LLMProvider):
    def __init__(self, next_provider: LLMProvider, model_name: str, session):
        self.next_provider = next_provider
        self.model_name = model_name
        self.session = session

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
    ) -> Message:
        start_time = time.time()

        resp_msg = self.next_provider.generate(messages, available_tools)

        latency = time.time() - start_time

        if resp_msg.usage:
            prompt_tokens = resp_msg.usage.prompt_tokens
            completion_tokens = resp_msg.usage.completion_tokens

            cost = 0.0
            if self.model_name in PRICING_MODEL:
                price = PRICING_MODEL[self.model_name]
                cost = (
                    prompt_tokens * price["input_price"]
                    + completion_tokens * price["output_price"]
                ) / 1000000.0

            logger.info(
                "[Tracker] 📊 API 调用完成 | 耗时: %.4fs | 输入: %d tk | 输出: %d tk | 花费: ¥%.6f",
                latency,
                prompt_tokens,
                completion_tokens,
                cost,
            )

            if self.session:
                self.session.record_usage(prompt_tokens, completion_tokens, cost)
                logger.info(
                    "[Tracker] 💰 当前会话 (%s) 累计花费: ¥%.6f",
                    self.session.id,
                    self.session.total_cost_cny,
                )
        else:
            logger.info("[Tracker] ⚠️ API 调用完成，但未返回 Usage 数据 | 耗时: %.4fs", latency)

        return resp_msg
