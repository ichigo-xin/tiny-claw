from __future__ import annotations
import json
from pathlib import Path

from internal.schema import ToolDefinition
from .registry import BaseTool


class WriteFileTool(BaseTool):
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

    def execute(self, args: bytes) -> str:
        try:
            input_data = json.loads(args.decode("utf-8") if isinstance(args, bytes) else args)
            file_path = input_data["path"]
            content = input_data["content"]
        except Exception as e:
            raise RuntimeError(f"参数解析失败: {str(e)}")

        full_path = Path(self.work_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            full_path.write_text(content, encoding="utf-8")
        except Exception as e:
            raise RuntimeError(f"写入文件失败: {str(e)}")

        return f"成功将内容写入到文件: {file_path}"
