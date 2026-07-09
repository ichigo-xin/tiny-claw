from __future__ import annotations
import json
from pathlib import Path

from internal.schema import ToolDefinition
from .registry import BaseTool


def _fuzzy_replace(original_content: str, old_text: str, new_text: str) -> str:
    count = original_content.count(old_text)
    if count == 1:
        return original_content.replace(old_text, new_text, 1)
    if count > 1:
        raise RuntimeError(f"old_text 匹配到了 {count} 处，请提供更多的上下文代码以确保唯一性")

    normalized_content = original_content.replace("\r\n", "\n")
    normalized_old = old_text.replace("\r\n", "\n")

    count = normalized_content.count(normalized_old)
    if count == 1:
        return normalized_content.replace(normalized_old, new_text, 1)

    trimmed_old = normalized_old.strip()
    if trimmed_old:
        count = normalized_content.count(trimmed_old)
        if count == 1:
            return normalized_content.replace(trimmed_old, new_text, 1)

    return _line_by_line_replace(normalized_content, normalized_old, new_text)


def _line_by_line_replace(content: str, old_text: str, new_text: str) -> str:
    content_lines = content.split("\n")
    old_lines = [line.strip() for line in old_text.strip().split("\n") if line.strip()]

    if len(old_lines) == 0 or len(content_lines) < len(old_lines):
        raise RuntimeError("找不到该代码片段")

    match_count = 0
    match_start_index = -1
    match_end_index = -1

    for i in range(len(content_lines) - len(old_lines) + 1):
        is_match = True
        for j in range(len(old_lines)):
            if content_lines[i + j].strip() != old_lines[j]:
                is_match = False
                break
        if is_match:
            match_count += 1
            match_start_index = i
            match_end_index = i + len(old_lines)

    if match_count == 0:
        raise RuntimeError("在文件中未找到 old_text，请大模型先调用 read_file 仔细确认文件内容和缩进")
    if match_count > 1:
        raise RuntimeError(f"模糊匹配到了 {match_count} 处相似代码，请提供更多上下行代码以精确定位")

    new_content_lines = content_lines[:match_start_index]
    new_content_lines.append(new_text)
    new_content_lines.extend(content_lines[match_end_index:])

    return "\n".join(new_content_lines)


class EditFileTool(BaseTool):
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "edit_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="对现有文件进行局部的字符串替换。这比重写整个文件更安全、更快速。请提供足够的 old_text 上下文以确保匹配的唯一性。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要修改的文件路径",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "文件中原有的文本。必须包含足够的上下文（建议上下各多包含几行），以确保在文件中的唯一性。",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "要替换成的新文本",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def execute(self, args: bytes) -> str:
        try:
            input_data = json.loads(args.decode("utf-8") if isinstance(args, bytes) else args)
            file_path = input_data["path"]
            old_text = input_data["old_text"]
            new_text = input_data["new_text"]
        except Exception as e:
            raise RuntimeError(f"参数解析失败: {str(e)}")

        full_path = Path(self.work_dir) / file_path

        try:
            original_content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            raise RuntimeError(f"读取文件失败，请确认路径是否正确: {str(e)}")

        try:
            new_content = _fuzzy_replace(original_content, old_text, new_text)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"替换失败: {str(e)}")

        try:
            full_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            raise RuntimeError(f"写回文件失败: {str(e)}")

        return f"✅ 成功修改文件: {file_path}"
