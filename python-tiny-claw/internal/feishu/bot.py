from __future__ import annotations

import json
import logging
import threading
import uuid

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from internal.context.session import Session
from internal.engine.loop import AgentEngine
from internal.engine.reporter import Reporter
from internal.feishu.approval import get_global_approval_mgr
from internal.schema.message import Message, Role

logger = logging.getLogger(__name__)


class FeishuBot:
    """封装了飞书机器人的配置与核心业务流"""

    def __init__(self, app_id: str, app_secret: str, eng: AgentEngine, sess: Session):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.DEBUG) \
            .build()
        self.app_id = app_id
        self.app_secret = app_secret
        self.engine = eng
        self.session = sess
        self._reporter = None

    def reporter(self) -> FeishuReporter | None:
        return self._reporter

    def start(self) -> None:
        """通过长连接（WebSocket）方式启动飞书事件监听，无需公网 IP 和内网穿透"""

        def on_message_receive(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
            content_str = data.event.message.content
            if content_str is None:
                return

            # 解析飞书消息内容：{"text": "用户消息"}
            content_str = content_str.strip()
            text = content_str
            try:
                content_json = json.loads(content_str)
                if "text" in content_json:
                    text = content_json["text"].strip()
            except json.JSONDecodeError:
                pass

            chat_id = data.event.message.chat_id
            logger.info("[Feishu] 收到会话 %s 消息: %s", chat_id, text)

            # 拦截人工审批的特殊口令
            if text.startswith("approve "):
                task_id = text[len("approve "):].strip()
                get_global_approval_mgr().resolve_approval(task_id, True, "人类管理员已批准操作")
                logger.info("[Feishu] 会话 %s: ✅ 已为您批准任务 %s", chat_id, task_id)
                return

            if text.startswith("reject "):
                task_id = text[len("reject "):].strip()
                get_global_approval_mgr().resolve_approval(task_id, False, "人类管理员认为该操作存在极高风险，已无情拒绝")
                logger.info("[Feishu] 会话 %s: 🚫 已拒绝任务 %s", chat_id, task_id)
                return

            # 在新线程中处理，避免阻塞飞书 SDK 的事件处理
            t = threading.Thread(target=self._handle_agent_run, args=(chat_id, text))
            t.daemon = True
            t.start()

        # 长连接模式下，verify_token 和 encrypt_key 必须传空字符串
        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(on_message_receive) \
            .build()

        # 创建长连接客户端
        cli = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.DEBUG,
        )

        logger.info("python-tiny-claw 正在通过长连接（WebSocket）方式连接飞书...")

        # start() 会阻塞主线程，直到连接断开
        cli.start()

    def _handle_agent_run(self, chat_id: str, prompt: str) -> None:
        """连接飞书与底层引擎的桥梁"""
        reporter = FeishuReporter(client=self.client, chat_id=chat_id)
        self._reporter = reporter

        try:
            self.session.append(Message(role=Role.USER, content=prompt))
            self.engine.run(self.session, reporter)
        except Exception as e:
            reporter.send_msg(f"❌ Agent 运行崩溃: {e}")


class FeishuReporter(Reporter):
    """将引擎的输出格式化后发给飞书"""

    def __init__(self, client: lark.Client, chat_id: str):
        self.client = client
        self.chat_id = chat_id

    def send_msg(self, text: str) -> None:
        """封装了调用飞书 OpenAPI 发送文本消息的操作"""
        content = json.dumps({"text": text})

        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                          .receive_id(self.chat_id)
                          .msg_type("text")
                          .content(content)
                          .uuid(str(uuid.uuid4()))
                          .build()) \
            .build()

        response: CreateMessageResponse = self.client.im.v1.message.create(request)

        if not response.success():
            logger.error("[Feishu] 发送消息失败, code: %s, msg: %s, log_id: %s",
                         response.code, response.msg, response.get_log_id())

    def on_thinking(self) -> None:
        self.send_msg("🤔 模型正在慢思考 (Thinking)...")

    def on_tool_call(self, tool_name: str, args: str) -> None:
        self.send_msg(f"🛠️ **正在执行工具**：`{tool_name}`\n参数：`{args}`")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        if is_error:
            self.send_msg(f"⚠️ **执行报错** ({tool_name})：\n{result}")
        else:
            self.send_msg(f"✅ **执行成功** ({tool_name})")

    def on_message(self, content: str) -> None:
        self.send_msg(content)