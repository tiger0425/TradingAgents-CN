"""Tests for tradingagents/notifier.py — uses unittest.mock for HTTP calls."""

import os
import pytest
from unittest.mock import patch, MagicMock

import requests

from tradingagents.notifier import (
    Notifier,
    FeishuNotifier,
    ServerChanNotifier,
    PushPlusNotifier,
    create_notifier,
)


# ------------------------------------------------------------------
# FeishuNotifier
# ------------------------------------------------------------------


class TestFeishuNotifier:
    def test_configured_with_full_url(self):
        n = FeishuNotifier(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/my-hook-id")
        assert n.configured is True

    def test_configured_with_hook_id_only(self):
        n = FeishuNotifier(webhook="my-hook-id")
        assert n.configured is True
        assert n._url == "https://open.feishu.cn/open-apis/bot/v2/hook/my-hook-id"

    def test_not_configured_with_empty(self):
        n = FeishuNotifier(webhook="")
        assert n.configured is False

    def test_not_configured_by_default(self):
        n = FeishuNotifier()
        assert n.configured is False

    def test_configured_from_config_dict(self):
        n = FeishuNotifier(config={"feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/from-config"})
        assert n.configured is True
        assert "from-config" in n._url

    def test_configured_from_env_var(self):
        with patch.dict(os.environ, {"FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/env-hook"}):
            n = FeishuNotifier()
            assert n.configured is True

    def test_config_dict_priority_over_env(self):
        with patch.dict(os.environ, {"FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/env-hook"}):
            n = FeishuNotifier(config={"feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/config-hook"})
            assert "config-hook" in n._url

    def test_send_text_success(self):
        n = FeishuNotifier(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "msg": "ok"}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_text("Test Title", "Test Content")
            assert result is True
            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            assert payload["msg_type"] == "post"
            assert payload["content"]["post"]["zh_cn"]["title"] == "Test Title"

    def test_send_text_no_url(self):
        n = FeishuNotifier(webhook="")
        result = n.send_text("Title", "Content")
        assert result is False

    def test_send_text_http_error(self):
        n = FeishuNotifier(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("requests.post", return_value=mock_resp):
            result = n.send_text("Title", "Content")
            assert result is False

    def test_send_text_network_error(self):
        n = FeishuNotifier(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test")
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = n.send_text("Title", "Content")
            assert result is False

    def test_send_markdown_delegates_to_post(self):
        n = FeishuNotifier(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_markdown("MD Title", "# Content")
            assert result is True
            mock_post.assert_called_once()


# ------------------------------------------------------------------
# ServerChanNotifier
# ------------------------------------------------------------------


class TestServerChanNotifier:
    def test_configured_with_key(self):
        n = ServerChanNotifier(sendkey="SCU12345")
        assert n.configured is True

    def test_not_configured_empty(self):
        n = ServerChanNotifier(sendkey="")
        assert n.configured is False

    def test_not_configured_default(self):
        n = ServerChanNotifier()
        assert n.configured is False

    def test_configured_from_config_dict(self):
        n = ServerChanNotifier(config={"server_chan_key": "SCUfromconfig"})
        assert n.configured is True
        assert "SCUfromconfig" in n._url

    def test_configured_from_env_var(self):
        with patch.dict(os.environ, {"SERVER_CHAN_KEY": "SCUfromenv"}):
            n = ServerChanNotifier()
            assert n.configured is True

    def test_send_text_success(self):
        n = ServerChanNotifier(sendkey="SCUtest")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_text("Alert", "Message body")
            assert result is True
            call_data = mock_post.call_args[1]["data"]
            assert call_data["title"] == "Alert"
            assert call_data["desp"] == "Message body"

    def test_send_text_no_key(self):
        n = ServerChanNotifier(sendkey="")
        result = n.send_text("Title", "Content")
        assert result is False

    def test_send_text_network_error(self):
        n = ServerChanNotifier(sendkey="SCUtest")
        with patch("requests.post", side_effect=requests.exceptions.Timeout("Timeout")):
            result = n.send_text("Title", "Content")
            assert result is False

    def test_send_markdown_delegates_to_post(self):
        n = ServerChanNotifier(sendkey="SCUtest")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_markdown("MD", "# h1")
            assert result is True
            mock_post.assert_called_once()


# ------------------------------------------------------------------
# PushPlusNotifier
# ------------------------------------------------------------------


class TestPushPlusNotifier:
    def test_configured_with_token(self):
        n = PushPlusNotifier(token="abc123")
        assert n.configured is True

    def test_not_configured_empty(self):
        n = PushPlusNotifier(token="")
        assert n.configured is False

    def test_not_configured_default(self):
        n = PushPlusNotifier()
        assert n.configured is False

    def test_configured_from_config_dict(self):
        n = PushPlusNotifier(config={"pushplus_token": "tokFromConfig"})
        assert n.configured is True
        assert n._token == "tokFromConfig"

    def test_configured_from_env_var(self):
        with patch.dict(os.environ, {"PUSHPLUS_TOKEN": "tokFromEnv"}):
            n = PushPlusNotifier()
            assert n.configured is True

    def test_send_text_sends_txt_template(self):
        n = PushPlusNotifier(token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 200}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_text("Hello", "World")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["token"] == "tok123"
            assert payload["template"] == "txt"

    def test_send_markdown_sends_markdown_template(self):
        n = PushPlusNotifier(token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 200}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = n.send_markdown("MD", "**bold**")
            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["template"] == "markdown"

    def test_send_text_api_error_code(self):
        n = PushPlusNotifier(token="tok123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 500, "msg": "error"}
        with patch("requests.post", return_value=mock_resp):
            result = n.send_text("Title", "Content")
            assert result is False

    def test_send_text_network_error(self):
        n = PushPlusNotifier(token="tok123")
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Network down")):
            result = n.send_text("Title", "Content")
            assert result is False

    def test_send_text_no_token(self):
        n = PushPlusNotifier(token="")
        result = n.send_text("Title", "Content")
        assert result is False


# ------------------------------------------------------------------
# create_notifier factory
# ------------------------------------------------------------------


class TestCreateNotifier:
    def test_returns_empty_when_nothing_configured(self):
        notifiers = create_notifier({})
        assert notifiers == []

    def test_returns_empty_when_no_args(self):
        notifiers = create_notifier()
        assert notifiers == []

    def test_creates_feishu_from_config(self):
        notifiers = create_notifier({"feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/x"})
        assert len(notifiers) == 1
        assert isinstance(notifiers[0], FeishuNotifier)

    def test_creates_serverchan_from_config(self):
        notifiers = create_notifier({"server_chan_key": "SCUx"})
        assert len(notifiers) == 1
        assert isinstance(notifiers[0], ServerChanNotifier)

    def test_creates_pushplus_from_config(self):
        notifiers = create_notifier({"pushplus_token": "tox"})
        assert len(notifiers) == 1
        assert isinstance(notifiers[0], PushPlusNotifier)

    def test_creates_multiple(self):
        notifiers = create_notifier({
            "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/a",
            "server_chan_key": "SCUb",
            "pushplus_token": "toc",
        })
        assert len(notifiers) == 3
        types = {type(n) for n in notifiers}
        assert types == {FeishuNotifier, ServerChanNotifier, PushPlusNotifier}

    def test_respects_env_vars(self):
        with patch.dict(os.environ, {"FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/env-x"}):
            notifiers = create_notifier({})
            assert len(notifiers) == 1
            assert isinstance(notifiers[0], FeishuNotifier)

    def test_ignores_empty_config_values(self):
        notifiers = create_notifier({
            "feishu_webhook": "",
            "server_chan_key": "",
            "pushplus_token": "",
        })
        assert notifiers == []


# ------------------------------------------------------------------
# ABC contract
# ------------------------------------------------------------------


class ConcreteNotifier(Notifier):
    def send_text(self, title: str, content: str) -> bool:
        return True

    def send_markdown(self, title: str, content: str) -> bool:
        return True


class TestNotifierABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Notifier()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        n = ConcreteNotifier()
        assert n.send_text("t", "c") is True
        assert n.send_markdown("t", "c") is True
