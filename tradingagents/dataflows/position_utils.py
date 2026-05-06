"""
Position tracking utilities: P&L calculation, average cost, and context formatting.
All functions are pure — no side effects, no external state.
"""


def calc_position_pnl(
    current_price: float, cost_price: float, quantity: int
) -> dict:
    """计算持仓浮动盈亏。

    Args:
        current_price: 当前价格（现价）
        cost_price: 持仓成本价（加权平均）
        quantity: 持有股数

    Returns:
        dict with keys: pnl_amount, pnl_pct, cost_price, current_price, quantity
    """
    pnl_amount = (current_price - cost_price) * quantity
    pnl_amount = round(pnl_amount, 2)

    if quantity == 0:
        pnl_pct = 0.0
    elif cost_price == 0:
        pnl_pct = None
    else:
        pnl_pct = (current_price - cost_price) / cost_price
        pnl_pct = round(pnl_pct, 4)

    return {
        "pnl_amount": pnl_amount,
        "pnl_pct": pnl_pct,
        "cost_price": cost_price,
        "current_price": current_price,
        "quantity": quantity,
    }


def calc_avg_cost_after_add(
    old_cost: float, old_qty: int, add_price: float, add_qty: int
) -> float:
    """计算加仓后的加权平均成本价。

    Args:
        old_cost: 原有持仓成本价
        old_qty: 原有持仓股数
        add_price: 加仓买入价格
        add_qty: 加仓买入股数

    Returns:
        加权平均成本价，保留两位小数
    """
    total_cost = old_cost * old_qty + add_price * add_qty
    total_qty = old_qty + add_qty
    if total_qty == 0:
        return 0.0
    return round(total_cost / total_qty, 2)


def calc_realized_pnl(
    sell_price: float, cost_price: float, sell_qty: int
) -> dict:
    """计算已实现盈亏（卖出部分）。

    Args:
        sell_price: 卖出价格
        cost_price: 持仓成本价
        sell_qty: 卖出股数

    Returns:
        dict with keys: realized_pnl, avg_cost_sold
    """
    realized_pnl = (sell_price - cost_price) * sell_qty
    avg_cost_sold = cost_price * sell_qty
    return {
        "realized_pnl": round(realized_pnl, 2),
        "avg_cost_sold": round(avg_cost_sold, 2),
    }


def format_position_context(
    current_price: float,
    cost_price: float,
    quantity: int,
    market_type: str = "A_SHARE",
) -> str:
    """返回用于注入 agent prompt 的持仓上下文文本（中文）。

    仅当 market_type 为 A_SHARE 且存在有效持仓时返回格式化字符串。
    无持仓或非 A 股市场返回空字符串。

    Args:
        current_price: 当前价格
        cost_price: 持仓成本价
        quantity: 持有股数
        market_type: 市场类型（默认 A_SHARE）

    Returns:
        格式化持仓上下文字符串，无持仓时返回空字符串
    """
    if market_type != "A_SHARE":
        return ""
    if quantity == 0 or cost_price == 0:
        return ""

    pnl = calc_position_pnl(current_price, cost_price, quantity)
    pnl_pct_str = f"{pnl['pnl_pct']:.2%}" if pnl["pnl_pct"] is not None else "N/A"

    return (
        f"**当前持仓状况：**\n"
        f"- 成本价：{cost_price:.2f}\n"
        f"- 当前价：{current_price:.2f}\n"
        f"- 持有股数：{quantity}\n"
        f"- 浮动盈亏：{pnl['pnl_amount']:+.2f} 元 ({pnl_pct_str})"
    )


def format_position_for_trader(
    cost_price: float, quantity: int, current_price: float
) -> str:
    """返回用于 Trader agent prompt 的简洁持仓文本（中文）。

    无持仓时返回空字符串。

    Args:
        cost_price: 持仓成本价
        quantity: 持有股数
        current_price: 当前价格

    Returns:
        简洁持仓字符串，无持仓时返回空字符串
    """
    if cost_price == 0 or quantity == 0:
        return ""

    pnl = calc_position_pnl(current_price, cost_price, quantity)
    pnl_pct_str = f"{pnl['pnl_pct']:.2%}" if pnl["pnl_pct"] is not None else "N/A"

    return (
        f"当前持仓：成本价 {cost_price:.2f}，持有 {quantity} 股，现价 {current_price:.2f}\n"
        f"浮动盈亏：{pnl['pnl_amount']:+.2f} 元 ({pnl_pct_str})"
    )


def format_position_for_pm(
    cost_price: float, quantity: int, current_price: float
) -> str:
    """返回用于 Portfolio Manager agent prompt 的详细持仓文本（中文）。

    包含基于盈亏阈值的操作提示和风险调整建议。
    无持仓时返回空字符串。

    Args:
        cost_price: 持仓成本价
        quantity: 持有股数
        current_price: 当前价格

    Returns:
        详细持仓字符串（含操作指引），无持仓时返回空字符串
    """
    if cost_price == 0 or quantity == 0:
        return ""

    pnl = calc_position_pnl(current_price, cost_price, quantity)
    pnl_amount = pnl["pnl_amount"]
    pnl_pct = pnl["pnl_pct"]
    pnl_pct_str = f"{pnl_pct:.2%}" if pnl_pct is not None else "N/A"

    lines = [
        f"当前持仓：成本价 {cost_price:.2f}，持有 {quantity} 股，现价 {current_price:.2f}",
        f"浮动盈亏：{pnl_amount:+.2f} 元 ({pnl_pct_str})",
    ]

    if pnl_pct is not None:
        if pnl_pct > 0.10:
            lines.append(" 提示：当前浮盈超过 10%，可考虑分批止盈锁定利润。")
            lines.append(" 风险调整：浮盈较大，建议适当保守，保护利润。")
        elif pnl_pct < -0.10:
            lines.append(" 提示：当前浮亏超过 10%，请评估是否需要止损，避免深度套牢。")
            lines.append(" 风险调整：浮亏较大，建议理性评估基本面是否发生变化。")
        elif -0.05 <= pnl_pct <= 0.05:
            lines.append(" 提示：当前盈亏在震荡区间，建议持仓观望，等待趋势确认。")

    return "\n".join(lines) + "\n"
