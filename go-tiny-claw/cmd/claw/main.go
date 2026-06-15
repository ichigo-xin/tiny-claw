// cmd/claw/main.go
package main

import (
	"context"
	"log"
	"os"
	"runtime"

	"github.com/joho/godotenv"
	"github.com/yourname/go-tiny-claw/internal/engine"
	"github.com/yourname/go-tiny-claw/internal/provider"
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

	// 确保已设置飞书凭证
	feishuAppID := os.Getenv("FEISHU_APP_ID")
	feishuAppSecret := os.Getenv("FEISHU_APP_SECRET")
	if feishuAppID == "" || feishuAppSecret == "" {
		log.Fatal("请先导出 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量或在 .env 文件中配置")
	}

	workDir, _ := os.Getwd()

	// 2. 初始化真实的大脑 (指向智谱 GLM-4.5，使用上一讲的 OpenAI 适配器)
	llmProvider := provider.NewZhipuOpenAIProvider("glm-4.5-air")

	// 3. 初始化真实的 Tool Registry
	registry := tools.NewRegistry()

	// 挂载极简工具集
	registry.Register(tools.NewReadFileTool(workDir))
	registry.Register(tools.NewWriteFileTool(workDir))

	// 根据操作系统注册对应的命令执行工具
	if runtime.GOOS == "windows" {
		registry.Register(tools.NewPowerShellTool(workDir))
	} else {
		registry.Register(tools.NewBashTool(workDir))
	}

	// 【新增挂载】
	registry.Register(tools.NewEditFileTool(workDir))

	// 开启慢思考
	eng := engine.NewAgentEngine(llmProvider, registry, workDir, true)

	// 【注入新实现的终端输出器】
	reporter := engine.NewTerminalReporter()

	prompt := `
    我需要在当前目录下新建一个 ping.go，提供一个简单的 http ping 接口。
    写完之后，帮我把代码用 git 提交一下。
    `

	err := eng.Run(context.Background(), prompt, reporter)
	if err != nil {
		log.Fatalf("引擎运行崩溃: %v", err)
	}

}
