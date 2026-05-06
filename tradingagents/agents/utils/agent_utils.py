from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data,
    get_current_price,
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = (get_config().get("output_language") or "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve market-appropriate ticker formats."""
    # A-shares use 6-digit numeric codes; other markets use alphanumeric tickers
    if ticker and ticker.isdigit() and len(ticker) == 6:
        exchange_hint = (
            f"This is a 6-digit A-share code. "
            f"For Shanghai-listed stocks append `.SS` (e.g. `{ticker}.SS`), "
            f"for Shenzhen append `.SZ` (e.g. `{ticker}.SZ`). "
            f"Use the raw 6-digit code for domestic data sources (akshare)."
        )
    else:
        exchange_hint = (
            "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
        )
    return (
        f"The instrument to analyze is `{ticker}`. "
        f"{exchange_hint} "
        "Use this exact ticker in every tool call, report, and recommendation."
    )

def format_past_context(past_context: str) -> str:
    """Format past trading memory context for Portfolio Manager prompt injection.

    Adds structured section headers and separates same-ticker vs cross-ticker lessons.
    Returns empty string if past_context is empty.
    """
    if not past_context or not past_context.strip():
        return ""
    lines = [
        "**历史经验教训（来自过往决策）：**",
        "",
        past_context.strip(),
        "",
        "---",
    ]
    return "\n".join(lines)


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
