"""
Notification abstraction layer for TradingAgents.

Supports multiple notification channels:
- Feishu (飞书) custom robot webhook
- ServerChan (Server酱) — WeChat push
- PushPlus — multi-channel push
- OpenClaw — 定时报告推送到 OpenClaw Agent

Usage:
    from tradingagents.notifier import create_notifier

    notifiers = create_notifier(config)
    for n in notifiers:
        n.send_markdown("今日信号", "## 关键信号\n- 600519: Buy")
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------


class Notifier(ABC):
    """Base notification interface.

    All notifier implementations must provide send_text and send_markdown.
    """

    @abstractmethod
    def send_text(self, title: str, content: str) -> bool:
        """Send a plain-text notification.

        Returns True on success, False on failure.
        """
        ...

    @abstractmethod
    def send_markdown(self, title: str, content: str) -> bool:
        """Send a markdown-formatted notification.

        Returns True on success, False on failure.
        """
        ...


# ------------------------------------------------------------------
# Feishu (飞书) custom robot
# ------------------------------------------------------------------


class FeishuNotifier(Notifier):
    """Send notifications via Feishu (飞书) custom robot webhook.

    Webhook URL can be the full URL or just the hook ID.
    Config key: "feishu_webhook"  Env var: FEISHU_WEBHOOK
    """

    BASE_URL = "https://open.feishu.cn/open-apis/bot/v2/hook"

    def __init__(self, webhook: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize with a webhook URL or hook ID.

        Webhook is resolved in order:
        1. explicit webhook argument
        2. config["feishu_webhook"]
        3. os.environ["FEISHU_WEBHOOK"]
        """
        config = config or {}
        hook = webhook or config.get("feishu_webhook") or os.environ.get("FEISHU_WEBHOOK", "")

        if not hook:
            self._url: str = ""
        elif hook.startswith("http://") or hook.startswith("https://"):
            self._url = hook
        else:
            # Assume it's just the hook ID
            self._url = f"{self.BASE_URL}/{hook}"

    @property
    def configured(self) -> bool:
        return bool(self._url)

    def send_text(self, title: str, content: str) -> bool:
        return self._post(self._build_text_payload(title, content))

    def send_markdown(self, title: str, content: str) -> bool:
        # Feishu post format treats content as text paragraphs;
        # markdown is rendered as-is in the post content.
        return self._post(self._build_text_payload(title, content))

    def _build_text_payload(self, title: str, content: str) -> Dict[str, Any]:
        """Build Feishu post message JSON payload."""
        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [
                            [{"tag": "text", "text": content}]
                        ],
                    }
                }
            },
        }

    def _post(self, payload: Dict[str, Any]) -> bool:
        if not self._url:
            logger.warning("FeishuNotifier: webhook URL not configured")
            return False
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0 or result.get("code") is None:
                    return True
                logger.warning("Feishu API error: %s", result)
            else:
                logger.warning("Feishu HTTP %d: %s", resp.status_code, resp.text[:200])
            return False
        except requests.RequestException as exc:
            logger.warning("FeishuNotifier request failed: %s", exc)
            return False


# ------------------------------------------------------------------
# ServerChan (Server酱) — WeChat push
# ------------------------------------------------------------------


class ServerChanNotifier(Notifier):
    """Send notifications via Server酱 (ServerChan) for WeChat push.

    API endpoint: https://sctapi.ftqq.com/{SENDKEY}.send
    Config key: "server_chan_key"  Env var: SERVER_CHAN_KEY
    """

    BASE_URL = "https://sctapi.ftqq.com"

    def __init__(self, sendkey: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        key = sendkey or config.get("server_chan_key") or os.environ.get("SERVER_CHAN_KEY", "")
        self._sendkey = key
        self._url = f"{self.BASE_URL}/{key}.send" if key else ""

    @property
    def configured(self) -> bool:
        return bool(self._sendkey)

    def send_text(self, title: str, content: str) -> bool:
        return self._post(title, content)

    def send_markdown(self, title: str, content: str) -> bool:
        # Server酱 supports markdown in the desp field natively
        return self._post(title, content)

    def _post(self, title: str, desp: str) -> bool:
        if not self._url:
            logger.warning("ServerChanNotifier: SENDKEY not configured")
            return False
        try:
            resp = requests.post(
                self._url,
                data={"title": title, "desp": desp},
                timeout=10,
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0 or result.get("code") is None:
                    return True
                logger.warning("ServerChan API error: %s", result)
            else:
                logger.warning("ServerChan HTTP %d: %s", resp.status_code, resp.text[:200])
            return False
        except requests.RequestException as exc:
            logger.warning("ServerChanNotifier request failed: %s", exc)
            return False


# ------------------------------------------------------------------
# PushPlus — multi-channel push
# ------------------------------------------------------------------


class PushPlusNotifier(Notifier):
    """Send notifications via PushPlus (https://www.pushplus.plus).

    API endpoint: https://www.pushplus.plus/send
    Config key: "pushplus_token"  Env var: PUSHPLUS_TOKEN
    """

    API_URL = "https://www.pushplus.plus/send"

    def __init__(self, token: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self._token = token or config.get("pushplus_token") or os.environ.get("PUSHPLUS_TOKEN", "")

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def send_text(self, title: str, content: str) -> bool:
        return self._post(title, content, template="txt")

    def send_markdown(self, title: str, content: str) -> bool:
        return self._post(title, content, template="markdown")

    def _post(self, title: str, content: str, template: str) -> bool:
        if not self._token:
            logger.warning("PushPlusNotifier: token not configured")
            return False
        try:
            payload = {
                "token": self._token,
                "title": title,
                "content": content,
                "template": template,
            }
            resp = requests.post(self.API_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 200:
                    return True
                logger.warning("PushPlus API error: %s", result)
            else:
                logger.warning("PushPlus HTTP %d: %s", resp.status_code, resp.text[:200])
            return False
        except requests.RequestException as exc:
            logger.warning("PushPlusNotifier request failed: %s", exc)
            return False


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def create_notifier(config: Optional[Dict[str, Any]] = None) -> List[Notifier]:
    notifiers: List[Notifier] = []

    feishu = FeishuNotifier(config=config)
    if feishu.configured:
        notifiers.append(feishu)

    server_chan = ServerChanNotifier(config=config)
    if server_chan.configured:
        notifiers.append(server_chan)

    pushplus = PushPlusNotifier(config=config)
    if pushplus.configured:
        notifiers.append(pushplus)

    return notifiers


# ------------------------------------------------------------------
# OpenClaw — 定时报告推送客户端
# ------------------------------------------------------------------


class OpenClawPushClient:
    """将定时报告推送到 OpenClaw，由 OpenClaw 投递至用户渠道。

    调度器调用 push() 将晨会/午评/收盘复盘/周选股报告推送到 OpenClaw。
    支持三种推送方式：
      - push()   → POST /hooks/agent  (推荐，Agent 投递)
      - wake()   → POST /hooks/wake   (轻量唤醒)
      - direct() → POST /hooks/direct (绕过 Agent 直接发送)

    环境变量:
      OPENCLAW_URL         OpenClaw 服务地址 (例: http://openclaw:18789)
      OPENCLAW_HOOK_TOKEN  Webhook 认证令牌
    """

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None):
        self._url = (url or os.environ.get("OPENCLAW_URL", "")).rstrip("/")
        self._token = token or os.environ.get("OPENCLAW_HOOK_TOKEN", "")

    @property
    def configured(self) -> bool:
        return bool(self._url and self._token)

    async def push(self, user_id: str, report: str, report_type: str) -> bool:
        """方式 A: POST /hooks/agent — 推送报告到 OpenClaw Agent 投递。"""
        return await self._post("/hooks/agent", {
            "user_id": user_id,
            "report": report,
            "report_type": report_type,
        })

    async def wake(self, user_id: str, message: str = "") -> bool:
        """方式 B: POST /hooks/wake — 轻量唤醒 Agent。"""
        return await self._post("/hooks/wake", {
            "user_id": user_id,
            "message": message,
        })

    async def direct(self, user_id: str, message: str, method: str = "send_message") -> bool:
        """方式 C: POST /hooks/direct — 绕过 Agent 直接发送消息。"""
        return await self._post("/hooks/direct", {
            "user_id": user_id,
            "message": message,
            "method": method,
        })

    async def _post(self, path: str, payload: Dict[str, Any]) -> bool:
        if not self.configured:
            logger.warning("OpenClawPushClient: OPENCLAW_URL / OPENCLAW_HOOK_TOKEN not configured")
            return False
        try:
            url = f"{self._url}{path}"
            headers = {"X-Hook-Token": self._token}
            resp = await asyncio.to_thread(
                requests.post, url, json=payload, headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                return True
            logger.warning("OpenClaw HTTP %d: %s", resp.status_code, resp.text[:200])
            return False
        except requests.RequestException as exc:
            logger.warning("OpenClawPushClient request failed: %s", exc)
            return False
