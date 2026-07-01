// cmd/claw/main.go
package main

import (
	"context"
	"log"
	"os"

	"runtime"

	"github.com/joho/godotenv"
	ctxpkg "github.com/yourname/go-tiny-claw/internal/context"
	"github.com/yourname/go-tiny-claw/internal/engine"
	"github.com/yourname/go-tiny-claw/internal/feishu"
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
	eng := engine.NewAgentEngine(llmProvider, registry, false, false)

	// 假设一个bot绑定一个session
	sessionID := "test_command_intercept_001"
	sess := ctxpkg.GlobalSessionMgr.GetOrCreate(sessionID, workDir)
	sess.Append(schema.Message{Role: schema.RoleUser, Content: ""})

	bot := feishu.NewFeishuBot(eng, sess)

	// 【核心注入】注册安全拦截 Middleware
	registry.Use(func(ctx context.Context, call schema.ToolCall) (bool, string) {
		argsStr := string(call.Arguments)

		if feishu.IsDangerousCommand(call.Name, argsStr) {
			taskID := call.ID

			allowed, reason := feishu.GlobalApprovalMgr.WaitForApproval(taskID, call.Name, argsStr, bot.Reporter())

			if !allowed {
				return false, reason
			}
			return true, ""
		}

		return true, ""
	})

	// 使用 WebSocket 长连接方式启动飞书机器人（无需公网 IP）
	err := bot.Start(context.Background())
	if err != nil {
		log.Fatalf("飞书长连接启动失败: %v", err)
	}
}
