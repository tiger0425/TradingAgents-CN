from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)


@tool
def get_current_price(
    symbol: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
) -> str:
    """
    Retrieve the current real-time stock quote for a given ticker.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol, e.g. 600519 for A-shares
    Returns:
        str: Formatted string with current price, change, volume, and other real-time data.
    """
    return route_to_vendor("get_current_price", symbol)
