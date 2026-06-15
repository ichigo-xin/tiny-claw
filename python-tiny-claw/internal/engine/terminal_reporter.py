from __future__ import annotations

from internal.engine.reporter import Reporter


class TerminalReporter(Reporter):
    """实现了 Reporter 接口，用于在终端直观地打印 Agent 的状态"""

    def on_thinking(self) -> None:
        print("\n[🤔 思考中] 模型正在推理...")

    def on_tool_call(self, tool_name: str, args: str) -> None:
        # 截断过长的参数显示，保持终端清爽
        display_args = args.replace("\n", "\\n").replace("\r", "\\r")
        if len(display_args) > 150:
            display_args = display_args[:150] + "... (已截断)"
        print(f"[🛠️ 调用工具] {tool_name}")
        print(f"   参数: {display_args}")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        if is_error:
            print(f"[❌ 执行失败] {tool_name}")
            if result:
                print(f"   错误: {result}")
        else:
            print(f"[✅ 执行成功] {tool_name}")

    def on_message(self, content: str) -> None:
        if not content:
            return
        print(f"\n🤖 Agent 回复:\n{content}\n")
