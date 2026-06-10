from __future__ import annotations

import json
import os

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class EditFileTool(BaseTool):
    """对现有文件进行局部字符串替换的工具"""

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

    def execute(self, args: str) -> tuple[str, Exception | None]:
        try:
            input_data = json.loads(args)
            file_path = input_data.get("path", "")
            old_text = input_data.get("old_text", "")
            new_text = input_data.get("new_text", "")

            if not file_path:
                return "", ValueError("参数解析失败：缺少 path 参数")

            full_path = os.path.join(self.work_dir, file_path)

            # 1. 读取原文件内容
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
            except FileNotFoundError:
                return "", FileNotFoundError(f"读取文件失败，请确认路径是否正确: {file_path}")

            # 2. 调用多级模糊替换算法
            new_content, err = _fuzzy_replace(original_content, old_text, new_text)
            if err:
                return "", err

            # 3. 将新内容写回磁盘
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"✅ 成功修改文件: {file_path}", None

        except json.JSONDecodeError as e:
            return "", ValueError(f"参数解析失败: {e}")
        except Exception as e:
            return "", Exception(f"编辑文件失败: {e}")


def _fuzzy_replace(original_content: str, old_text: str, new_text: str) -> tuple[str, Exception | None]:
    """四级容错降级替换算法"""

    # L1: 精确匹配
    count = original_content.count(old_text)
    if count == 1:
        return original_content.replace(old_text, new_text, 1), None
    if count > 1:
        return "", ValueError(f"old_text 匹配到了 {count} 处，请提供更多的上下文代码以确保唯一性")

    # L2: 换行符归一化 (统一将 \r\n 转换为 \n)
    normalized_content = original_content.replace("\r\n", "\n")
    normalized_old = old_text.replace("\r\n", "\n")

    count = normalized_content.count(normalized_old)
    if count == 1:
        return normalized_content.replace(normalized_old, new_text, 1), None

    # L3: Trim Space 匹配 (忽略首尾的空行和空格)
    trimmed_old = normalized_old.strip()
    if trimmed_old:
        count = normalized_content.count(trimmed_old)
        if count == 1:
            return normalized_content.replace(trimmed_old, new_text, 1), None

    # L4: 逐行去缩进匹配 (最强力的容错：消除大模型遗漏缩进的幻觉)
    return _line_by_line_replace(normalized_content, normalized_old, new_text)


def _line_by_line_replace(content: str, old_text: str, new_text: str) -> tuple[str, Exception | None]:
    """将文本按行切割，去除首尾空白后进行滑动窗口匹配"""
    content_lines = content.split("\n")
    old_lines = old_text.strip().split("\n")

    if not old_lines or len(content_lines) < len(old_lines):
        return "", ValueError("找不到该代码片段")

    # 清理 old_lines 的每行首尾空白
    old_lines = [line.strip() for line in old_lines]

    match_count = 0
    match_start_index = -1
    match_end_index = -1

    # 滑动窗口在原始文件中寻找匹配块
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
        return "", ValueError("在文件中未找到 old_text，请大模型先调用 read_file 仔细确认文件内容和缩进")
    if match_count > 1:
        return "", ValueError(f"模糊匹配到了 {match_count} 处相似代码，请提供更多上下行代码以精确定位")

    # 执行替换：将匹配到的原始行范围替换为 newText
    new_content_lines = content_lines[:match_start_index] + [new_text] + content_lines[match_end_index:]
    return "\n".join(new_content_lines), None


def new_edit_file_tool(work_dir: str) -> EditFileTool:
    return EditFileTool(work_dir)
