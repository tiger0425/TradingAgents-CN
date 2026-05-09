"""
Direct notification command for TradingAgents CLI.

Usage:
    tradingagents notify feishu --title "今日信号" --content "..."
    tradingagents notify wechat --title "预警" --content "..."
    tradingagents notify all --title "测试" --content "..."
"""

from __future__ import annotations

from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.notifier import (
    create_notifier,
    FeishuNotifier,
    ServerChanNotifier,
    PushPlusNotifier,
)

notify_app = typer.Typer(
    name="notify",
    help="发送通知到配置的渠道: feishu / wechat / all",
    add_completion=False,
)


def _get_feishu(config: dict) -> Optional[FeishuNotifier]:
    n = FeishuNotifier(config=config)
    return n if n.configured else None


def _get_wechat_notifiers(config: dict) -> list:
    notifiers = []
    sc = ServerChanNotifier(config=config)
    if sc.configured:
        notifiers.append(sc)
    pp = PushPlusNotifier(config=config)
    if pp.configured:
        notifiers.append(pp)
    return notifiers


def _do_send(notifiers, title: str, content: str, markdown: bool):
    if not notifiers:
        typer.echo("错误: 没有配置通知渠道。请在配置中设置 feishu_webhook / server_chan_key / pushplus_token", err=True)
        raise typer.Exit(code=1)

    success_count = 0
    for n in notifiers:
        name = type(n).__name__
        try:
            ok = n.send_markdown(title, content) if markdown else n.send_text(title, content)
        except Exception as exc:
            typer.echo(f"  {name}: 错误 - {exc}", err=True)
            continue
        if ok:
            success_count += 1
            typer.echo(f"  {name}: ✓ 发送成功")
        else:
            typer.echo(f"  {name}: ✗ 发送失败", err=True)

    if success_count == 0:
        raise typer.Exit(code=1)


@notify_app.command(name="feishu")
def notify_feishu(
    title: str = typer.Option(..., "--title", "-t", help="消息标题"),
    content: str = typer.Option(..., "--content", "-c", help="消息内容"),
    markdown: bool = typer.Option(False, "--markdown", help="以 Markdown 格式发送"),
) -> None:
    """发送通知到飞书（仅飞书）。"""
    config = DEFAULT_CONFIG.copy()
    n = _get_feishu(config)
    if n is None:
        typer.echo("错误: 飞书未配置。请设置 feishu_webhook 配置项或 FEISHU_WEBHOOK 环境变量", err=True)
        raise typer.Exit(code=1)
    _do_send([n], title, content, markdown)


@notify_app.command(name="wechat")
def notify_wechat(
    title: str = typer.Option(..., "--title", "-t", help="消息标题"),
    content: str = typer.Option(..., "--content", "-c", help="消息内容"),
    markdown: bool = typer.Option(False, "--markdown", help="以 Markdown 格式发送"),
) -> None:
    """发送通知到微信渠道（Server酱 / PushPlus）。"""
    config = DEFAULT_CONFIG.copy()
    notifiers = _get_wechat_notifiers(config)
    _do_send(notifiers, title, content, markdown)


@notify_app.command(name="all")
def notify_all(
    title: str = typer.Option(..., "--title", "-t", help="消息标题"),
    content: str = typer.Option(..., "--content", "-c", help="消息内容"),
    markdown: bool = typer.Option(False, "--markdown", help="以 Markdown 格式发送"),
) -> None:
    """发送通知到所有已配置的渠道。"""
    config = DEFAULT_CONFIG.copy()
    all_notifiers = create_notifier(config)
    _do_send(all_notifiers, title, content, markdown)
