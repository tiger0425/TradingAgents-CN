from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.akshare import get_social_sentiment


@tool
def get_social_sentiment_tool(
    symbol: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
) -> str:
    """Get social sentiment behavioral metrics for an A-share stock.

    Returns attention index, trend history, participation willingness,
    real-time popularity ranking, and cross-platform (Xueqiu/EastMoney)
    following data as formatted Markdown.  Use for analyzing retail investor
    attention and crowd behavior patterns.  Data is behavioral metrics, not
    social media post content.
    """
    return get_social_sentiment(symbol)
