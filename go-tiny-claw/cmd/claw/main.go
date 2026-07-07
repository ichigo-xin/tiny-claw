// cmd/claw/main.go
package main

import (
	"context"
	"log"
	"os"

	"github.com/joho/godotenv"
	ctxpkg "github.com/yourname/go-tiny-claw/internal/context"
	"github.com/yourname/go-tiny-claw/internal/engine"
	"github.com/yourname/go-tiny-claw/internal/provider"
	"github.com/yourname/go-tiny-claw/internal/schema"
	"github.com/yourname/go-tiny-claw/internal/tools"
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

	workDir, _ := os.Getwd()
	workDir += "/workspace"
	llmProvider := provider.NewZhipuOpenAIProvider("glm-4.5-air")

	registry := tools.NewRegistry()
	registry.Register(tools.NewPowerShellTool(workDir))
	registry.Register(tools.NewWriteFileTool(workDir))

	eng := engine.NewAgentEngine(llmProvider, registry, false, false)
	reporter := engine.NewTerminalReporter()
	sess := ctxpkg.GlobalSessionMgr.GetOrCreate("test_trace_001", workDir)

	// 触发一个跨工具类型的并发任务
	prompt := `
	为了加快执行速度，请你在一轮回复中，【同时并行】完成以下两件事：
	1. 使用 powershell 工具执行 'Start-Sleep -Seconds 2; Write-Output "系统环境检查完毕"'
	2. 使用 write_file 工具，在当前目录下创建一个 'trace_test.md'，内容写上 "测试并发的写入"。
	请确保你是分别调用两个不同的工具，不要试图把它们合并成一个命令！
	`
	sess.Append(schema.Message{Role: schema.RoleUser, Content: prompt})

	log.Println("\n>>> 🚀 启动带 Tracing 链路追踪的测试...")
	err := eng.Run(context.Background(), sess, reporter)
	if err != nil {
		log.Fatalf("引擎崩溃: %v", err)
	}
}
