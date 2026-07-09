#!/usr/bin/env python3
from __future__ import annotations
import argparse
import logging
import os
import platform
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from internal.context import global_session_mgr
from internal.engine import AgentEngine, TerminalReporter
from internal.observability import CostTracker, start_span, export_trace_to_file
from internal.provider import OpenAIProvider
from internal.schema import Message, Role
from internal.tools import (
    new_registry,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    PowerShellTool,
    BashTool,
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    load_dotenv()

    if not os.getenv("ZHIPU_API_KEY"):
        logging.error("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="python-tiny-claw CLI Agent")
    parser.add_argument("-prompt", "--prompt", type=str, required=True, help="要交给 Agent 执行的任务描述")
    parser.add_argument("-dir", "--dir", type=str, default=".", help="Agent 运行的工作区目录路径 (默认为当前目录)")
    parser.add_argument("-session", "--session", type=str, default="cli_default_session", help="指定会话 ID，支持断点续传")
    args = parser.parse_args()

    work_dir = str(Path(args.dir).resolve())

    print("==================================================")
    print("🚀 启动 python-tiny-claw CLI 引擎...")
    print(f"📁 锁定工作区: {work_dir}")
    print("==================================================")

    model_name = "glm-4.5-air"
    real_provider = OpenAIProvider(model_name)

    sess = global_session_mgr.get_or_create(args.session, work_dir)

    tracked_provider = CostTracker(real_provider, model_name, sess)

    registry = new_registry()
    registry.register(ReadFileTool(work_dir))
    registry.register(WriteFileTool(work_dir))
    registry.register(EditFileTool(work_dir))
    if platform.system() == "Windows":
        registry.register(PowerShellTool(work_dir))
    else:
        registry.register(BashTool(work_dir))

    eng = AgentEngine(tracked_provider, registry, enable_thinking=False, plan_mode=True)

    _, root_span = start_span("CLI.TaskRun")
    root_span.add_attribute("Prompt", args.prompt)
    start_time = time.time()

    reporter = TerminalReporter()

    print(f"\n🎯 收到任务: {args.prompt}\n")

    sess.append(Message(role=Role.USER, content=args.prompt))

    try:
        eng.run(sess, reporter)
    except Exception as e:
        logging.error(f"\n💥 引擎运行崩溃: {e}", exc_info=True)
        sys.exit(1)
    finally:
        root_span.end_span()
        export_trace_to_file(root_span, work_dir, sess.id)

    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"✨ 任务圆满结束。总耗时: {elapsed:.2f}s")
    print(f"💰 Session 累计消耗: ¥{sess.total_cost_cny:.6f} | Token: Input {sess.total_prompt_tokens}, Output {sess.total_completion_tokens}")
    print("==================================================")


if __name__ == "__main__":
    main()
