from __future__ import annotations
import json
import logging
import os
import threading
from typing import Any

from internal.engine import Reporter, AgentEngine
from internal.context import Session
from internal.schema import Message, Role
from .approval import global_approval_mgr


class FeishuReporter(Reporter):
    def __init__(self, client: Any, chat_id: str):
        self.client = client
        self.chat_id = chat_id

    def send_msg(self, text: str) -> None:
        try:
            content = json.dumps({"text": text})
            logging.info(f"[Feishu] 发送消息到 {self.chat_id}: {text[:100]}...")
        except Exception as e:
            logging.error(f"[Feishu] 发送消息失败: {e}")

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


class FeishuBot:
    def __init__(self, engine: AgentEngine, sess: Session):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.engine = engine
        self.sess = sess
        self.reporter = None

        if not self.app_id or not self.app_secret:
            logging.warning("未配置 FEISHU_APP_ID/FEISHU_APP_SECRET，飞书机器人功能不可用")

    def _handle_message(self, chat_id: str, content_str: str) -> None:
        logging.info(f"[Feishu] 收到会话 {chat_id} 消息: {content_str}")

        if content_str.startswith("approve "):
            task_id = content_str[len("approve "):].strip()
            global_approval_mgr.resolve_approval(task_id, True, "人类管理员已批准操作")
            logging.info(f"[Feishu] 会话 {chat_id}: ✅ 已为您批准任务 {task_id}")
            return

        if content_str.startswith("reject "):
            task_id = content_str[len("reject "):].strip()
            global_approval_mgr.resolve_approval(task_id, False, "人类管理员认为该操作存在极高风险，已无情拒绝")
            logging.info(f"[Feishu] 会话 {chat_id}: 🚫 已拒绝任务 {task_id}")
            return

        threading.Thread(target=self._handle_agent_run, args=(chat_id, content_str), daemon=True).start()

    def _handle_agent_run(self, chat_id: str, prompt: str) -> None:
        reporter = FeishuReporter(None, chat_id)
        self.reporter = reporter
        self.sess.append(Message(role=Role.USER, content=prompt))
        try:
            self.engine.run(self.sess, reporter)
        except Exception as e:
            reporter.send_msg(f"❌ Agent 运行崩溃: {str(e)}")

    def start(self) -> None:
        logging.info("飞书机器人启动占位实现 - 需要配置 lark-oapi SDK")
