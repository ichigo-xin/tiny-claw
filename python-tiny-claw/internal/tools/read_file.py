from __future__ import annotations

import json
import os
from typing import Any

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class ReadFileTool(BaseTool):
    """实现了读取本地文件内容的工具"""

    def __init__(self, work_dir: str):
        """
        Args:
            work_dir: 工作目录，限制工具只能在此目录及其子目录下操作
        """
        self.work_dir = work_dir

    def name(self) -> str:
        return "read_file"

    def definition(self) -> ToolDefinition:
        """向大模型清晰地描述这个工具的用途和参数格式"""
        return ToolDefinition(
            name=self.name(),
            description="读取指定路径的文件内容。请提供相对工作区的路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径，如 cmd/claw/main.go",
                    },
                },
                "required": ["path"],
            },
        )

    def execute(self, args: str) -> tuple[str, Exception | None]:
        """执行读取文件操作"""
        try:
            input_data = json.loads(args)
            file_path = input_data.get("path", "")

            if not file_path:
                return "", ValueError("参数解析失败：缺少 path 参数")

            full_path = os.path.join(self.work_dir, file_path)

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            max_len = 8000
            if len(content) > max_len:
                truncated_msg = f"{content[:max_len]}\n\n...[由于内容过长，已被系统截断至前 {max_len} 字节]..."
                return truncated_msg, None

            return content, None

        except json.JSONDecodeError as e:
            return "", ValueError(f"参数解析失败: {e}")
        except FileNotFoundError:
            return "", FileNotFoundError(f"打开文件失败: 文件 '{file_path}' 不存在")
        except Exception as e:
            return "", Exception(f"读取文件内容失败: {e}")


def new_read_file_tool(work_dir: str) -> ReadFileTool:
    """创建一个新的 ReadFileTool 实例"""
    return ReadFileTool(work_dir)
