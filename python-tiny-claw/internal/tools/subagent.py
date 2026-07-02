from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool, RegistryImpl

logger = logging.getLogger(__name__)


class AgentRunner(Protocol):
    """定义引擎向外部工具暴露的特定执行能力接口"""
    
    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: RegistryImpl,
        reporter: Any,
    ) -> tuple[str, Exception | None]:
        ...


class SubagentTool(BaseTool):
    """子智能体工具，用于派出专门的探路者进行深度探索"""

    def __init__(
        self,
        runner: AgentRunner,
        read_only_registry: RegistryImpl,
        reporter: Any,
    ):
        self.runner = runner
        self.read_only_registry = read_only_registry
        self.reporter = reporter

    def name(self) -> str:
        return "spawn_subagent"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="派出一个专门用于深度探索（Exploration）的子智能体。当你需要阅读大量代码、跨文件查找逻辑时请调用此工具。它在探索完毕后，会给你返回一份极度精炼的摘要报告。",
            input_schema={
                "type": "object",
                "properties": {
                    "task_prompt": {
                        "type": "string",
                        "description": "给子智能体下达的明确探索指令。",
                    },
                },
                "required": ["task_prompt"],
            },
        )

    def execute(self, args: str) -> tuple[str, Exception | None]:
        try:
            input_data = json.loads(args)
            task_prompt = input_data.get("task_prompt", "")

            if not task_prompt:
                return "", ValueError("参数解析失败：缺少 task_prompt 参数")

            logger.info("[Subagent] 🚀 主 Agent 发起委派！正在拉起探路者: [%s]...", task_prompt)

            summary, err = self.runner.run_sub(
                task_prompt,
                self.read_only_registry,
                self.reporter,
            )

            if err is not None:
                return f"子智能体执行失败: {err}", None

            logger.info("[Subagent] ✅ 子智能体任务结束。报告返回给主干...")

            return f"【子智能体探索报告】:\n{summary}", None

        except json.JSONDecodeError as e:
            return "", ValueError(f"参数解析失败: {e}")
        except Exception as e:
            return "", Exception(f"子智能体调用异常: {e}")


def new_subagent_tool(
    runner: AgentRunner,
    read_only_registry: RegistryImpl,
    reporter: Any,
) -> SubagentTool:
    """创建一个新的 SubagentTool 实例"""
    return SubagentTool(runner, read_only_registry, reporter)
