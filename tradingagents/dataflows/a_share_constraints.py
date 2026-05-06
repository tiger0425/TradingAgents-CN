"""
A-share market trading constraints: limit up/down, T+1 rules, and format helpers.
These functions compute price constraints based on A-share exchange rules.
"""

from typing import Optional


def get_limit_prices(symbol: str, prev_close: float, name: str = "") -> tuple:
    """计算 A 股涨跌停价格。

    Args:
        symbol: 股票代码（6 位数字），用于判断板块（科创板/创业板/北交所）
        prev_close: 前收盘价
        name: 股票名称（用于检测 ST 股票）

    Returns:
        (limit_up, limit_down) 二元组，均为 float
    """
    limit_rate = get_limit_rate(symbol, name)
    limit_up = round(prev_close * (1 + limit_rate), 2)
    limit_down = round(prev_close * (1 - limit_rate), 2)
    return limit_up, limit_down


def get_limit_rate(symbol: str, name: str = "") -> float:
    """根据股票代码和名称返回涨跌幅限制比例。"""
    if symbol:
        if symbol.startswith(("68", "30")):
            return 0.20  # 科创板 / 创业板
        if symbol.startswith("8") and len(symbol) == 6:
            return 0.30  # 北交所
    if "ST" in name or "*ST" in name:
        return 0.05
    return 0.10


def format_limit_constraint(
    limit_up: float, limit_down: float, market_type: str = "A_SHARE"
) -> str:
    """返回用于注入 agent prompt 的限价约束文本。

    Returns empty string when market_type is not A_SHARE (no constraint needed).
    """
    if market_type != "A_SHARE":
        return ""
    return (
        f"\n\n**A-share trading constraints:**\n"
        f"- Daily limit-up price: {limit_up}\n"
        f"- Daily limit-down price: {limit_down}\n"
        f"- All transaction prices MUST be within [{limit_down}, {limit_up}] range.\n"
        f"- If a limit price is hit, the order may not be filled at the proposed price."
    )


def format_t_plus_1_constraint(
    position_opened_date: str, trade_date: str, market_type: str = "A_SHARE"
) -> str:
    """返回 T+1 约束文本。

    A-shares have T+1 settlement: shares bought today cannot be sold until the
    next trading day. Returns empty string when constraint doesn't apply.
    """
    if market_type != "A_SHARE":
        return ""
    if not position_opened_date:
        # No position yet — buying is fine
        return "\n\n**Note:** No existing position. Buying is permitted."

    from datetime import datetime

    try:
        opened = datetime.strptime(position_opened_date, "%Y-%m-%d")
        current = datetime.strptime(trade_date, "%Y-%m-%d")

        # Same-day opened position check
        if position_opened_date == trade_date:
            return (
                f"\n\n**T+1 constraint:** Position was opened today ({position_opened_date}). "
                f"Under A-share T+1 rules, this position CANNOT be sold today. "
                f"Your proposal MUST NOT include Sell or significant position reduction."
            )

        days_held = (current - opened).days
        if days_held < 1:
            return (
                f"\n\n**T+1 constraint:** Position was opened on {position_opened_date}. "
                f"Under A-share T+1 rules, this position CANNOT be sold today (only "
                f"{days_held} trading day(s) held). Your proposal MUST NOT include Sell "
                f"or significant position reduction. Consider Hold or maintaining the position."
            )
    except (ValueError, TypeError):
        pass
    return ""


def format_position_constraint(
    cost_price: float,
    quantity: int,
    limit_up: float,
    limit_down: float,
    current_price: Optional[float] = None,
) -> str:
    """返回持仓相关的市场约束提示文本。

    Checks:
    1. If cost_price > limit_up: position cannot be profitable at current limit
    2. If cost_price < limit_down: position is deeply underwater at limit
    3. (Optional) If current_price is provided: check position vs current price

    Returns empty string when no constraints apply (no position or prices unavailable).
    """
    if cost_price <= 0 or quantity <= 0:
        return ""

    lines = []

    if limit_up > 0 and cost_price > limit_up:
        lines.append(
            f"- 注意：成本价 {cost_price:.2f} 高于涨停价 {limit_up:.2f}，"
            f"当前涨停范围内无法盈利。"
        )

    if limit_down > 0 and cost_price < limit_down:
        lines.append(
            f"- 注意：成本价 {cost_price:.2f} 低于跌停价 {limit_down:.2f}，"
            f"当前跌停范围内浮亏较大。"
        )

    if current_price is not None and limit_up > 0 and limit_down > 0:
        if current_price >= limit_up:
            lines.append(
                f"- 当前价 {current_price:.2f} 已达涨停价 {limit_up:.2f}，"
                f"买入可能无法成交。"
            )
        elif current_price <= limit_down:
            lines.append(
                f"- 当前价 {current_price:.2f} 已达跌停价 {limit_down:.2f}，"
                f"卖出可能无法成交。"
            )

    if not lines:
        return ""

    return "\n**Position Market Constraints:**\n" + "\n".join(lines) + "\n"
