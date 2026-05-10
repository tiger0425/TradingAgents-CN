from langchain_core.tools import tool
from typing import Annotated


@tool
def get_market_context(
    trade_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve market environment context including index status, sector fund flow, capital flow, and market breadth.

    Returns a formatted Markdown string with sections for:
    - Index status (SSE Composite performance)
    - Sector rotation (top/bottom sectors by fund flow)
    - Capital flow (institutional money flow)
    - Market breadth (advance/decline ratio, volume)

    This tool provides the overall market context for the analysis date.
    Useful for understanding whether individual stock technical signals
    are amplified or contradicted by the broader market environment.
    """
    from tradingagents.dataflows.config import get_config
    from tradingagents.dataflows.market_context import fetch_market_context

    config = get_config()
    market_type = config.get("market_type", "A_SHARE")
    return fetch_market_context(trade_date, market_type)
