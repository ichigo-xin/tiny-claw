from __future__ import annotations

import json
import os

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class WriteFileTool(BaseTool):
    """创建或覆盖写入文件的工具"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "write_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="创建或覆盖写入一个文件。如果目录不存在会自动创建。请提供相对于工作区的相对路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径，如 src/main.go",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, args: str) -> tuple[str, Exception | None]:
        try:
            input_data = json.loads(args)
            file_path = input_data.get("path", "")
            content = input_data.get("content", "")

            if not file_path:
                return "", ValueError("参数解析失败：缺少 path 参数")

            # 拼接绝对路径
            full_path = os.path.join(self.work_dir, file_path)

            # 自动创建缺失的父级目录
            parent_dir = os.path.dirname(full_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # 写入文件
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return f"成功将内容写入到文件: {file_path}", None

        except json.JSONDecodeError as e:
            return "", ValueError(f"参数解析失败: {e}")
        except Exception as e:
            return "", Exception(f"写入文件失败: {e}")


def new_write_file_tool(work_dir: str) -> WriteFileTool:
    return WriteFileTool(work_dir)
