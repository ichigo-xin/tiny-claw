from __future__ import annotations

import json
import platform
import subprocess

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class PowerShellTool(BaseTool):
    """在 Windows 环境下使用 PowerShell 执行命令的工具"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "powershell"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="在当前工作区执行 Windows PowerShell 命令。支持管道、分号(;)分隔的多条命令等 PowerShell 语法。返回标准输出(stdout)和标准错误(stderr)。",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 PowerShell 命令，例如: Get-ChildItem 或 go run ./...",
                    },
                },
                "required": ["command"],
            },
        )

    def execute(self, args: str) -> tuple[str, Exception | None]:
        try:
            input_data = json.loads(args)
            command = input_data.get("command", "")

            if not command:
                return "", ValueError("参数解析失败：缺少 command 参数")

            # 根据操作系统选择 PowerShell 可执行文件
            ps_cmd = "powershell.exe"
            if platform.system() != "Windows":
                ps_cmd = "pwsh"

            # 时间预算与超时控制
            try:
                result = subprocess.run(
                    [ps_cmd, "-NoProfile", "-NonInteractive", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.work_dir,
                )
                output_str = result.stdout + result.stderr

                if result.returncode != 0:
                    return f"执行报错: {result.returncode}\n输出:\n{output_str}", None

                if not output_str.strip():
                    return "命令执行成功，无终端输出。", None

                # 长度截断保护
                max_len = 8000
                if len(output_str) > max_len:
                    return f"{output_str[:max_len]}\n\n...[终端输出过长，已截断至前 {max_len} 字节]...", None

                return output_str, None

            except subprocess.TimeoutExpired:
                return "命令执行超时(30s)，已被系统强制终止。如果是启动常驻服务，请尝试将其转入后台。", None

        except json.JSONDecodeError as e:
            return "", ValueError(f"参数解析失败: {e}")
        except Exception as e:
            return "", Exception(f"执行命令失败: {e}")


def new_powershell_tool(work_dir: str) -> PowerShellTool:
    return PowerShellTool(work_dir)
