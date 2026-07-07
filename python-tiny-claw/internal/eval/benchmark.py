from __future__ import annotations

import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from internal.context.session import Session
from internal.engine.loop import AgentEngine
from internal.observability.tracker import CostTracker
from internal.provider.openai import OpenAIProvider
from internal.schema.message import Message, Role
from internal.tools import (
    new_bash_tool,
    new_edit_file_tool,
    new_powershell_tool,
    new_read_file_tool,
    new_registry,
    new_write_file_tool,
)

logger = logging.getLogger(__name__)


def new_script_command(script: str) -> list[str]:
    """根据操作系统选择执行脚本的命令行"""
    if platform.system() == "Windows":
        if script.startswith("powershell"):
            return ["powershell", "-Command", script[len("powershell -Command "):]]
        return ["cmd", "/c", script]
    return ["bash", "-c", script]


@dataclass
class TestCase:
    """定义了一个需要 Agent 去完成并验证的独立任务"""

    id: str
    name: str
    setup_script: str = ""
    setup_files: dict[str, str] = field(default_factory=dict)
    task_prompt: str = ""
    validate_script: str = ""
    validate_files: dict[str, str] = field(default_factory=dict)
    max_turns: int = 0


@dataclass
class TestResult:
    """存放单次跑分结果"""

    test_case_id: str
    passed: bool
    total_cost_cny: float = 0.0
    duration_ms: int = 0
    error_msg: str = ""


class BenchmarkRunner:
    """跑分执行器"""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def run_suite(self, testcases: list[TestCase]) -> None:
        logger.info("==================================================")
        logger.info("🚀 启动自动化 Harness Benchmark 评估... | 模型: %s", self.model_name)
        logger.info("==================================================")

        results: list[TestResult] = []
        passed_count = 0
        total_cost = 0.0

        for tc in testcases:
            logger.info("\n>>> ⏳ 正在执行用例 [%s]: %s", tc.id, tc.name)

            res = self._run_single_test(tc)
            results.append(res)

            if res.passed:
                passed_count += 1
                logger.info(
                    ">>> ✅ 用例 [%s] 测试通过! | 耗时: %dms | 花费: $%.6f",
                    tc.id, res.duration_ms, res.total_cost_cny,
                )
            else:
                logger.info(
                    ">>> ❌ 用例 [%s] 测试失败! | 错误: %s",
                    tc.id, res.error_msg,
                )
            total_cost += res.total_cost_cny

        # 打印终极报表
        logger.info("\n================ 🏆 跑分终极报告 ================")
        total = len(testcases)
        success_rate = (passed_count / total * 100) if total > 0 else 0.0
        logger.info("总用例数: %d | 成功数: %d | 成功率: %.2f%%", total, passed_count, success_rate)
        logger.info("总消耗成本: $%.6f", total_cost)
        logger.info("==================================================")

    def _run_single_test(self, tc: TestCase) -> TestResult:
        start_time = time.time()

        # 1. 为每个用例创建一个绝对干净的沙箱目录 (物理隔离)
        cwd = os.getcwd()
        work_dir = os.path.join(cwd, "workspace", f"{tc.id}_{int(time.time())}")
        os.makedirs(work_dir, exist_ok=True)

        # 2. (可选) 创建准备文件（跨平台兼容）
        for filename, content in tc.setup_files.items():
            file_path = os.path.join(work_dir, filename)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except OSError as e:
                return TestResult(
                    test_case_id=tc.id,
                    passed=False,
                    error_msg=f"创建准备文件失败: {e}",
                )

        # 3. (可选) 执行 Setup 脚本准备靶机代码
        if tc.setup_script:
            cmd = new_script_command(tc.setup_script)
            try:
                subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                return TestResult(test_case_id=tc.id, passed=False, error_msg="靶机 Setup 失败")

        # 4. 组装具备打点能力 (Tracker) 的引擎
        real_provider = OpenAIProvider(self.model_name)
        session = Session(tc.id, work_dir)
        tracked_provider = CostTracker(real_provider, self.model_name, session)

        registry = new_registry()
        registry.register(new_read_file_tool(work_dir))
        registry.register(new_write_file_tool(work_dir))
        if platform.system() == "Windows":
            registry.register(new_powershell_tool(work_dir))
        else:
            registry.register(new_bash_tool(work_dir))
        registry.register(new_edit_file_tool(work_dir))

        eng = AgentEngine(tracked_provider, registry, enable_thinking=False, plan_mode=False)

        # 5. 让 Agent 开始干活
        session.append(Message(role=Role.USER, content=tc.task_prompt))
        try:
            eng.run(session, None)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            return TestResult(
                test_case_id=tc.id,
                passed=False,
                error_msg=f"Agent 崩溃: {e}",
            )

        # 6. 【核心断言】Agent 跑完了，我们来验收成果！
        duration = int((time.time() - start_time) * 1000)

        if tc.validate_files:
            for filename, expected_content in tc.validate_files.items():
                file_path = os.path.join(work_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError as e:
                    return TestResult(
                        test_case_id=tc.id,
                        passed=False,
                        total_cost_cny=session.total_cost_cny,
                        duration_ms=duration,
                        error_msg=f"读取验证文件失败: {e}",
                    )
                if content != expected_content:
                    return TestResult(
                        test_case_id=tc.id,
                        passed=False,
                        total_cost_cny=session.total_cost_cny,
                        duration_ms=duration,
                        error_msg=f"文件内容不匹配: {filename}",
                    )
        elif tc.validate_script:
            cmd = new_script_command(tc.validate_script)
            result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)

            if result.returncode != 0:
                return TestResult(
                    test_case_id=tc.id,
                    passed=False,
                    total_cost_cny=session.total_cost_cny,
                    duration_ms=duration,
                    error_msg=f"验证脚本执行失败: {result.stdout + result.stderr}",
                )

        return TestResult(
            test_case_id=tc.id,
            passed=True,
            total_cost_cny=session.total_cost_cny,
            duration_ms=duration,
        )


def new_benchmark_runner(model: str) -> BenchmarkRunner:
    return BenchmarkRunner(model)
