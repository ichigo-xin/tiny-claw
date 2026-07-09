from __future__ import annotations
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from internal.schema import ToolDefinition
from .registry import Registry, BaseTool


class AgentRunner(ABC):
    @abstractmethod
    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Any,
    ) -> str:
        pass


class SubagentTool(BaseTool):
    def __init__(self, runner: AgentRunner, read_only_registry: Registry, reporter: Any):
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

    def execute(self, args: bytes) -> str:
        try:
            input_data = json.loads(args.decode("utf-8") if isinstance(args, bytes) else args)
            task_prompt = input_data["task_prompt"]
        except Exception as e:
            raise RuntimeError(f"解析参数失败: {str(e)}")

        logging.info(f"[Subagent] 🚀 主 Agent 发起委派！正在拉起探路者: [{task_prompt}]...")

        try:
            summary = self.runner.run_sub(task_prompt, self.read_only_registry, self.reporter)
        except Exception as e:
            return f"子智能体执行失败: {str(e)}"

        logging.info("[Subagent] ✅ 子智能体任务结束。报告返回给主干...")
        return f"【子智能体探索报告】:\n{summary}"
