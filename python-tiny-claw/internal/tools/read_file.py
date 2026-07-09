from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass

from internal.schema import ToolDefinition
from .registry import BaseTool


@dataclass
class _ReadFileArgs:
    path: str


class ReadFileTool(BaseTool):
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "read_file"

    def definition(self) -> ToolDefinition:
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

    def execute(self, args: bytes) -> str:
        try:
            input_data = json.loads(args.decode("utf-8") if isinstance(args, bytes) else args)
            file_path = input_data["path"]
        except Exception as e:
            raise RuntimeError(f"参数解析失败: {str(e)}")

        full_path = Path(self.work_dir) / file_path

        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            raise RuntimeError(f"读取文件失败: {str(e)}")

        max_len = 8000
        if len(content) > max_len:
            truncated_msg = f"{content[:max_len]}\n\n...[由于内容过长，已被系统截断至前 {max_len} 字节]..."
            return truncated_msg

        return content
