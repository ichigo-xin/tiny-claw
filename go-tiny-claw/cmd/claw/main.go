// cmd/claw/main.go
package main

import (
	"context"
	"log"
	"os"
	"runtime"

	"github.com/joho/godotenv"
	"github.com/yourname/go-tiny-claw/internal/engine"
	"github.com/yourname/go-tiny-claw/internal/feishu"
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

	// 2. 初始化飞书 Bot，通过长连接方式启动
	bot := feishu.NewFeishuBot(feishuAppID, feishuAppSecret, eng)

	// 3. 启动长连接（WebSocket），无需 HTTP 服务器，无需内网穿透
	err := bot.Start(context.Background())
	if err != nil {
		log.Fatalf("飞书长连接启动失败: %v", err)
	}
}
