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
from tradingagents.agents.utils.market_context_tools import (
    get_market_context,
)
from tradingagents.agents.utils.guosen_tools import (
    get_macro_data,
    screen_stocks,
    get_rankings,
    get_fund_flow,
    get_multi_quote,
    compare_funds,
    filter_etf_pro,
    filter_etf_custom,
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


def get_degradation_instruction() -> str:
    """Return a prompt instruction for handling empty/limited data.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, trader, managers).
    Internal debate agents skip this to keep their prompts lean.
    """
    from tradingagents.dataflows.config import get_config
    lang = (get_config().get("output_language") or "English")
    if lang.strip().lower() == "english":
        return ""
    return (
        " 降级策略：若数据源返回空或不可用，请在报告中明确标注数据局限性，"
        "并基于已有信息提供有限分析。不得编造数据或虚构未获取到的信息。"
        "若关键数据缺失导致无法形成有效结论，应坦诚告知并建议延后决策。"
    )


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
        return {"messages": [HumanMessage(content="Continue")]}
    return delete_messages


def sanitize_messages_for_deepseek(messages: list) -> list:
    """Trim message history to the last valid tool cycle, stripping orphans.

    DeepSeek's API is stricter than OpenAI about message ordering:
    every assistant message with ``tool_calls`` MUST have matching
    ``ToolMessage`` responses immediately following it.  Orphaned
    tool_calls cause HTTP 400 errors.

    This function:
    1. Scans backward to find the last complete tool cycle
       (AIMessage with tool_calls + matching ToolMessages).
    2. Drops all older messages to reduce context bloat.
    3. Strips any remaining orphaned tool_calls from the tail so
       the payload reaches the DeepSeek client sanitizer clean.

    Returns a **new list** — original message objects are never
    mutated so ``state["messages"]`` stays intact for other nodes.
    """
    from copy import copy as _shallow_copy
    from langchain_core.messages import AIMessage, ToolMessage

    n = len(messages)
    cut = n

    # Phase 1: find the last complete tool cycle
    for i in range(n - 1, -1, -1):
        if isinstance(messages[i], AIMessage) and messages[i].tool_calls:
            tc_ids = {tc["id"] for tc in messages[i].tool_calls if "id" in tc}
            has_match = any(
                isinstance(messages[j], ToolMessage) and messages[j].tool_call_id in tc_ids
                for j in range(i + 1, n)
            )
            if has_match:
                cut = i
                break
        elif i < cut and isinstance(messages[i], ToolMessage):
            cut = min(cut, i + 1)

    # If no tool cycle found, keep all messages as-is
    if cut == n:
        return list(messages)

    # Phase 2: strip orphaned tool_calls from the tail (never mutate originals)
    result = []
    for mi, m in enumerate(messages[cut:]):
        if isinstance(m, AIMessage) and m.tool_calls:
            tc_ids = {tc["id"] for tc in m.tool_calls if "id" in tc}
            has_match = any(
                isinstance(messages[cut:][j], ToolMessage)
                and messages[cut:][j].tool_call_id in tc_ids
                for j in range(mi + 1, len(messages) - cut)
            )
            if not has_match:
                mc = _shallow_copy(m)
                if mc.content:
                    mc.tool_calls = []
                else:
                    mc.content = "[Tool results processed]"
                    mc.tool_calls = []
                result.append(mc)
                continue
        result.append(m)
    return result


def filter_valid_tool_calls(result, valid_tools: list) -> None:
    """Strip hallucinated tool_calls not in the bound tools list.

    Some LLMs (notably DeepSeek) ignore ``bind_tools()`` and invent
    tool calls based on training data.  When the ToolNode can't find
    the hallucinated tool, it returns an error → LLM retries → loop.

    This mutates ``result.tool_calls`` in-place, removing any call
    whose name is not in ``{t.name for t in valid_tools}`` so only
    actually-available tools reach the graph ToolNode.

    Also ensures non-empty content when tool_calls are present, which
    MiniMax requires (returns 400 "chat content is empty" otherwise).
    """
    if not hasattr(result, 'tool_calls') or not result.tool_calls:
        return
    valid_names = {t.name for t in valid_tools}
    filtered = [tc for tc in result.tool_calls if tc.get('name') in valid_names]
    if len(filtered) != len(result.tool_calls):
        result.tool_calls = filtered
    if not result.content:
        result.content = "[Processing]"
