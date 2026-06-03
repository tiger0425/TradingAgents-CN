from langchain_core.messages import HumanMessage, RemoveMessage
from typing import Any

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


_MULTI_INDUSTRY_COMPANIES: dict[str, str] = {
    "600418": (
        '江淮汽车（600418）虽交易所分类为商用载货车，但实际业务横跨多个领域：'
        '①乘用车（含与华为合作的高端新能源品牌尊界/MAEXTRO）；'
        '②商用车（轻型、中型、重型卡车及客车底盘）；'
        '③新能源车制造（江淮iEV系列、为蔚来NIO代工）；'
        '④传统燃油车发动机。'
        '分析时必须综合考虑多业务线协同效应，不可仅局限于商用车框架。'
        '华为合作（尊界品牌）和蔚来代工是重要的估值驱动因子，不能遗漏。'
    ),
}


def _get_multi_industry_context(ticker: str, company_name: str) -> str:
    """Return supplemental business context for multi-industry companies."""
    ctx = _MULTI_INDUSTRY_COMPANIES.get(ticker, "")
    if not ctx and company_name:
        ctx = _MULTI_INDUSTRY_COMPANIES.get(company_name, "")
    return ctx


def build_instrument_context(ticker: str, industry: str = "", company_name: str = "", quick_llm: Any = None) -> str:
    """Describe the exact instrument so agents preserve market-appropriate ticker formats.

    Args:
        ticker: The stock ticker symbol.
        industry: Optional industry classification (e.g. "商用载货车").
                  When non-empty, appends industry context to the prompt.
        company_name: Optional human-readable company name (e.g. "江淮汽车").
                      When non-empty, displayed alongside the ticker for LLM grounding.
        quick_llm: Optional LangChain-compatible LLM for auto-generating frameworks
                   for unknown industries.
    """
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
    display_name = f"{company_name} ({ticker})" if company_name else f"`{ticker}`"
    base = (
        f"The instrument to analyze is {display_name}. "
        f"{exchange_hint} "
        "Use this exact ticker in every tool call, report, and recommendation."
    )

    # ── Multi-industry company context: inject supplemental business description ──
    multi_ctx = _get_multi_industry_context(ticker, company_name)
    if multi_ctx:
        base += f"\n\n**⚠️ 跨行业公司提醒：** {multi_ctx}"

    if industry:
        # Inject industry framework (correct_metrics + anti_patterns) when available
        framework = None
        try:
            from tradingagents.industry.frameworks import IndustryFramework  # lazy import
            framework = IndustryFramework().lookup(industry, quick_llm=quick_llm)
        except Exception:
            pass

        base += f"\n\n**行业背景：** 该股票属于 {industry} 行业。分析时请关注该行业的核心指标和竞争格局。"

        if framework:
            correct_metrics = framework.get("correct_metrics", [])
            anti_patterns = framework.get("anti_patterns", [])
            if correct_metrics or anti_patterns:
                base += "\n\n**行业分析框架（必须遵守）：**"
                if correct_metrics:
                    base += "\n- 核心指标：" + "、".join(correct_metrics)
                if anti_patterns:
                    base += "\n- 不适用指标：" + "、".join(anti_patterns)
                ctx = framework.get("context_instruction", "")
                if ctx:
                    base += f"\n\n分析指导：{ctx}"
    return base

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


def _is_first_entry(messages: list) -> bool:
    """Check if this is the analyst's first entry (not re-entering after tool exec).

    When re-entering after a ToolNode execution, the last message is the
    ToolMessage containing the tool result.  In that case we must NOT sanitize
    because the LLM needs to see the full context (including what was already
    fetched) to avoid redundant tool calls.
    """
    if not messages:
        return True
    from langchain_core.messages import ToolMessage
    return not isinstance(messages[-1], ToolMessage)


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
    4. Injects a data-availability summary at the start so the LLM
       remembers which tools have already returned data even after
       the history is trimmed (prevents re-calling same tool).

    Returns a **new list** — original message objects are never
    mutated so ``state["messages"]`` stays intact for other nodes.
    """
    from copy import copy as _shallow_copy
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

    n = len(messages)

    # ── Pre-extraction: build data-availability summary from FULL history ──
    fetched: dict[str, set[str]] = {}  # tool_name → {arg_summary, ...}
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                name = tc.get("name", "")
                args_str = ",".join(
                    f"{k}={v}" for k, v in sorted(tc.get("args", {}).items())
                )
                fetched.setdefault(name, set()).add(args_str)
        elif isinstance(m, ToolMessage):
            pass  # ToolResult already accounted by AIMessage

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
    # Also strip orphaned ToolMessages (no preceding assistent with matching tool_calls).
    # MiniMax enforces this strictly (error 2013).
    valid_ids = set()
    for m in result:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                if "id" in tc:
                    valid_ids.add(tc["id"])
    result = [m for m in result if not (
        isinstance(m, ToolMessage) and m.tool_call_id not in valid_ids
    )]

    # ── Phase 3: prepend data-availability summary ──
    if fetched:
        lines = ["[已获取数据摘要 / Data already retrieved]"]
        for tool_name, args_set in sorted(fetched.items()):
            if len(args_set) <= 3:
                for a in sorted(args_set):
                    lines.append(f"  ✅ {tool_name}({a}) — 成功获取")
            else:
                lines.append(f"  ✅ {tool_name} — {len(args_set)} 次调用均成功获取")
        lines.append("如果已获取的数据足够完成分析，请不要再调用这些工具。直接基于已有数据生成报告。")
        summary = "\n".join(lines)
        result.insert(0, HumanMessage(content=summary))

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
