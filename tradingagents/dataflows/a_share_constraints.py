"""
A-share market trading constraints: limit up/down, T+1 rules, and format helpers.
These functions compute price constraints based on A-share exchange rules.
"""


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
