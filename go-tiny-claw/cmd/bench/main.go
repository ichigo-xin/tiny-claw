// cmd/bench/main.go
package main

import (
	"context"
	"log"
	"os"

	"github.com/joho/godotenv"

	"github.com/yourname/go-tiny-claw/internal/eval"
)

func main() {
	// 加载 .env 文件
	if err := godotenv.Load(); err != nil {
		log.Printf("警告: 未找到 .env 文件，将使用系统环境变量")
	}

	// 确保已设置 ZHIPU_API_KEY
	if os.Getenv("ZHIPU_API_KEY") == "" {
		log.Fatal("请先导出 ZHIPU_API_KEY 环境变量或在 .env 文件中配置")
	}
	testcases := []eval.TestCase{
		{
			ID:   "test_001_edit",
			Name: "测试模糊替换工具的准确性",
			SetupFiles: map[string]string{
				"config.json": `{"name": "tiny-claw", "version": "v1.0.0"}`,
			},
			TaskPrompt: `当前目录下有一个 config.json。请你使用 edit_file 工具，将其中的 version 从 v1.0.0 改为 v2.0.0。不要做其他多余操作。`,
			ValidateFiles: map[string]string{
				"config.json": `{"name": "tiny-claw", "version": "v2.0.0"}`,
			},
		},
		{
			ID:   "test_002_code_gen",
			Name: "测试代码阅读与创建新文件的综合能力",
			SetupFiles: map[string]string{
				"math.go": `package math

func Multiply(a, b int) int {
	return a * b
}`,
			},
			TaskPrompt:     `当前目录下有一个 math.go。请你仔细阅读它，然后在同级目录下，帮我写一个规范的单元测试文件 math_test.go，用来测试 Multiply 函数。请务必包含正常的测试用例。`,
			ValidateScript: `go mod init bench && go test -v ./...`,
		},
	}

	// 启动跑分执行器！
	// 我们选用国内极其廉价但能力不错的 glm-4.5-air 跑分，省点钱。
	runner := eval.NewBenchmarkRunner("glm-4.5-air")
	runner.RunSuite(context.Background(), testcases)
}
