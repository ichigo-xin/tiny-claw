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

	// 关闭 Plan 模式，让它在死胡同里专注地展示挣扎过程
	eng := engine.NewAgentEngine(llmProvider, registry, false, false)
	reporter := engine.NewTerminalReporter()

	sessionID := "test_doom_loop_001"
	sess := ctxpkg.GlobalSessionMgr.GetOrCreate(sessionID, workDir)

	prompt := `
    帮我读取当前目录下的 secret_key.txt。
    注意：我们的文件系统现在非常不稳定，经常报 File Not Found。
    如果报错了，请你【千万不要改变参数】，直接原样再次调用 read_file 尝试，直到成功或连续重试 5 次为止。
    `

	log.Println("\n>>> 🚀 启动死循环干预测试...")
	sess.Append(schema.Message{Role: schema.RoleUser, Content: prompt})

	err := eng.Run(context.Background(), sess, reporter)
	if err != nil {
		log.Fatalf("引擎运行崩溃: %v", err)
	}
}
