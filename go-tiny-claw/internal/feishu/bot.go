// internal/feishu/bot.go
package feishu

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"

	larkcore "github.com/larksuite/oapi-sdk-go/v3/core"
	"github.com/larksuite/oapi-sdk-go/v3/event/dispatcher"
	larkim "github.com/larksuite/oapi-sdk-go/v3/service/im/v1"
	larkws "github.com/larksuite/oapi-sdk-go/v3/ws"
	"github.com/yourname/go-tiny-claw/internal/engine"

	lark "github.com/larksuite/oapi-sdk-go/v3"
)

// FeishuBot 封装了飞书机器人的配置与核心业务流
type FeishuBot struct {
	client    *lark.Client
	appID     string
	appSecret string
	engine    *engine.AgentEngine // 持有核心引擎引用
}

func NewFeishuBot(appID, appSecret string, eng *engine.AgentEngine) *FeishuBot {
	// 实例化飞书官方客户端
	client := lark.NewClient(appID, appSecret)

	return &FeishuBot{
		client:    client,
		appID:     appID,
		appSecret: appSecret,
		engine:    eng,
	}
}

// Start 通过长连接（WebSocket）方式启动飞书事件监听，无需公网 IP 和内网穿透
func (b *FeishuBot) Start(ctx context.Context) error {
	// 长连接模式下，verifyToken 和 encryptKey 必须传空字符串
	eventHandler := dispatcher.NewEventDispatcher("", "").
		OnP2MessageReceiveV1(func(ctx context.Context, event *larkim.P2MessageReceiveV1) error {
			contentStr := *event.Event.Message.Content
			contentStr = strings.TrimPrefix(contentStr, `{"text":"`)
			contentStr = strings.TrimSuffix(contentStr, `"}`)

			chatId := *event.Event.Message.ChatId
			log.Printf("[Feishu] 收到会话 %s 消息: %s\n", chatId, contentStr)

			go b.handleAgentRun(chatId, contentStr)

			return nil
		}).
		OnP2MessageReadV1(func(ctx context.Context, event *larkim.P2MessageReadV1) error {
			return nil
		})

	// 创建长连接客户端
	cli := larkws.NewClient(b.appID, b.appSecret,
		larkws.WithEventHandler(eventHandler),
		larkws.WithLogLevel(larkcore.LogLevelDebug),
	)

	log.Println("🚀 go-tiny-claw 正在通过长连接（WebSocket）方式连接飞书...")

	// Start 会阻塞主线程，直到连接断开
	return cli.Start(ctx)
}

// handleAgentRun 是连接飞书与底层引擎的桥梁
func (b *FeishuBot) handleAgentRun(chatId string, prompt string) {
	// 为当前聊天窗口实例化一个专属的 Reporter
	reporter := &FeishuReporter{
		client: b.client,
		chatId: chatId,
	}

	// 启动引擎！
	err := b.engine.Run(context.Background(), prompt, reporter)
	if err != nil {
		reporter.sendMsg(fmt.Sprintf("❌ Agent 运行崩溃: %v", err))
	}
}

// ==========================================
// FeishuReporter: 将引擎的输出格式化后发给飞书
// ==========================================
type FeishuReporter struct {
	client *lark.Client
	chatId string
}

// sendMsg 封装了调用飞书 OpenAPI 发送卡片/文本的操作
func (r *FeishuReporter) sendMsg(text string) {
	// 构建文本消息内容
	textContent := map[string]string{
		"text": text,
	}
	contentBytes, _ := json.Marshal(textContent)
	contentStr := string(contentBytes)

	msgReq := larkim.NewCreateMessageReqBuilder().
		ReceiveIdType("chat_id").
		Body(larkim.NewCreateMessageReqBodyBuilder().
			ReceiveId(r.chatId).
			MsgType("text").
			Content(contentStr).
			Build()).
		Build()

	_, _ = r.client.Im.Message.Create(context.Background(), msgReq)
}

func (r *FeishuReporter) OnThinking(ctx context.Context) {
	// 仅发一个轻量级提示，避免飞书刷屏
	r.sendMsg("🤔 模型正在慢思考 (Thinking)...")
}

func (r *FeishuReporter) OnToolCall(ctx context.Context, toolName string, args string) {
	r.sendMsg(fmt.Sprintf("🛠️ **正在执行工具**：`%s`\n参数：`%s`", toolName, args))
}

func (r *FeishuReporter) OnToolResult(ctx context.Context, toolName string, result string, isError bool) {
	if isError {
		r.sendMsg(fmt.Sprintf("⚠️ **执行报错** (%s)：\n%s", toolName, result))
	} else {
		// 成功时仅汇报成功，不刷全量日志
		r.sendMsg(fmt.Sprintf("✅ **执行成功** (%s)", toolName))
	}
}

func (r *FeishuReporter) OnMessage(ctx context.Context, content string) {
	// 将模型最终的纯文本回答发给用户
	r.sendMsg(content)
}

// 编译时类型检查：确保 FeishuReporter 实现了 Reporter 接口
var _ engine.Reporter = (*FeishuReporter)(nil)
