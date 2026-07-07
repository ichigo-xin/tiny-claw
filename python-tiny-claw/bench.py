import logging
import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        logging.warning("警告: python-dotenv 未安装，将跳过 .env 文件加载")

from internal.eval import BenchmarkRunner, TestCase

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    # 加载 .env 文件
    load_dotenv()

    # 确保已设置 ZHIPU_API_KEY
    if not os.getenv("ZHIPU_API_KEY"):
        raise RuntimeError("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")

    # 构建一套微型评测集
    testcases = [
        TestCase(
            id="test_001_edit",
            name="测试模糊替换工具的准确性",
            setup_files={
                "config.json": '{"name": "tiny-claw", "version": "v1.0.0"}',
            },
            task_prompt="当前目录下有一个 config.json。请你使用 edit_file 工具，将其中的 version 从 v1.0.0 改为 v2.0.0。不要做其他多余操作。",
            validate_files={
                "config.json": '{"name": "tiny-claw", "version": "v2.0.0"}',
            },
        ),
        TestCase(
            id="test_002_code_gen",
            name="测试代码阅读与创建新文件的综合能力",
            setup_files={
                "calc.py": "def multiply(a, b):\n    return a * b\n",
            },
            task_prompt="当前目录下有一个 calc.py。请你仔细阅读它，然后在同级目录下，帮我写一个规范的单元测试文件 test_calc.py，用来测试 multiply 函数。请使用 unittest 框架，务必包含正常的测试用例。",
            validate_script="python -m unittest test_calc -v",
        ),
    ]

    # 启动跑分执行器！
    # 我们选用国内极其廉价但能力不错的 glm-4.5-air 跑分，省点钱。
    runner = BenchmarkRunner("glm-4.5-air")
    runner.run_suite(testcases)


if __name__ == "__main__":
    main()
