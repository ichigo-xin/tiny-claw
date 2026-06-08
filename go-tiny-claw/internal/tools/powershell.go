// internal/tools/powershell.go
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"runtime"
	"time"

	"github.com/yourname/go-tiny-claw/internal/schema"
)

// PowerShellTool 在 Windows 环境下使用 PowerShell 5 执行命令
type PowerShellTool struct {
	workDir string
}

func NewPowerShellTool(workDir string) *PowerShellTool {
	return &PowerShellTool{workDir: workDir}
}

func (t *PowerShellTool) Name() string {
	return "powershell"
}

func (t *PowerShellTool) Definition() schema.ToolDefinition {
	return schema.ToolDefinition{
		Name:        t.Name(),
		Description: "在当前工作区执行 Windows PowerShell 命令。支持管道、分号(;)分隔的多条命令等 PowerShell 语法。返回标准输出(stdout)和标准错误(stderr)。",
		InputSchema: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"command": map[string]interface{}{
					"type":        "string",
					"description": "要执行的 PowerShell 命令，例如: Get-ChildItem 或 go run ./...",
				},
			},
			"required": []string{"command"},
		},
	}
}

type powershellArgs struct {
	Command string `json:"command"`
}

func (t *PowerShellTool) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	var input powershellArgs
	if err := json.Unmarshal(args, &input); err != nil {
		return "", fmt.Errorf("参数解析失败: %w", err)
	}

	// 时间预算与超时控制
	timeoutCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// 根据操作系统选择 PowerShell 可执行文件
	// Windows: powershell.exe (PowerShell 5.1)
	// 其余系统理论上不会走到这里，但做兜底处理
	psCmd := "powershell.exe"
	if runtime.GOOS != "windows" {
		psCmd = "pwsh" // 非 Windows 下尝试使用 PowerShell Core
	}

	// 使用 -NoProfile 避免加载用户配置文件导致启动缓慢
	// 使用 -NonInteractive 避免阻塞等待用户输入
	cmd := exec.CommandContext(timeoutCtx, psCmd, "-NoProfile", "-NonInteractive", "-Command", input.Command)
	cmd.Dir = t.workDir

	out, err := cmd.CombinedOutput()
	outputStr := string(out)

	if timeoutCtx.Err() == context.DeadlineExceeded {
		return outputStr + "\n[警告: 命令执行超时(30s)，已被系统强制终止。如果是启动常驻服务，请尝试将其转入后台。]", nil
	}

	// 错误原样回传，利用大模型的自纠错能力
	if err != nil {
		return fmt.Sprintf("执行报错: %v\n输出:\n%s", err, outputStr), nil
	}

	if outputStr == "" {
		return "命令执行成功，无终端输出。", nil
	}

	// 长度截断保护
	const maxLen = 8000
	if len(outputStr) > maxLen {
		return fmt.Sprintf("%s\n\n...[终端输出过长，已截断至前 %d 字节]...", outputStr[:maxLen], maxLen), nil
	}

	return outputStr, nil
}
