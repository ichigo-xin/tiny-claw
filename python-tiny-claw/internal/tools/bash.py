from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

from internal.schema import ToolDefinition
from .registry import BaseTool


class BashTool(BaseTool):
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="在当前工作区执行任意的 bash 命令。支持链式命令(如 &&)。返回标准输出(stdout)和标准错误(stderr)。",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令，例如: ls -la 或 go test ./...",
                    },
                },
                "required": ["command"],
            },
        )

    def execute(self, args: bytes) -> str:
        try:
            input_data = json.loads(args.decode("utf-8") if isinstance(args, bytes) else args)
            command = input_data["command"]
        except Exception as e:
            raise RuntimeError(f"参数解析失败: {str(e)}")

        timeout = 30
        try:
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output_str = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return f"\n[警告: 命令执行超时({timeout}s)，已被系统强制终止。如果是启动常驻服务，请尝试将其转入后台。]"
        except Exception as e:
            return f"执行报错: {str(e)}\n输出:\n"

        if output_str == "":
            return "命令执行成功，无终端输出。"

        max_len = 8000
        if len(output_str) > max_len:
            return f"{output_str[:max_len]}\n\n...[终端输出过长，已截断至前 {max_len} 字节]..."

        return output_str
