from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.schemas import MarketReport, render_market_report
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_current_price,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    get_market_context,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
    _is_first_entry,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.config import get_config
from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
from tradingagents.agents.utils.indicator_registry import INDICATORS


def create_market_analyst(llm):
    structured_llm = bind_structured(llm, MarketReport, "Market Analyst")

    def market_analyst_node(state):
        current_date = state["trade_date"]
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name, quick_llm=llm)

        # FIX-8 P0: 工具循环计数起点（仅在首次进入时设置，循环中保持不变）
        if state.get("market_start_idx", -1) < 0:
            state["market_start_idx"] = len(state["messages"])
        industry_section = (
            f"\n\n**行业技术面特征：** 当前分析的股票属于 {industry} 行业。"
            "请注意该行业的典型技术形态、交易活跃度特征和板块联动规律。"
            "行业轮动关系和板块排名可作为技术信号的重要验证。\n"
            if industry
            else ""
        )

        tools = [
            get_current_price,
            get_stock_data,
            get_market_context,
            get_indicators,
        ]

        indicator_list = "\n".join(f"- **{info.name}** ({info.description})" for info in INDICATORS)

        system_message = (
            f"""You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy.

{indicator_list}

Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + """
**A-Share Technical Focus:** When analyzing A-share stocks, pay special attention to: 
   - 涨跌停板 (price limit board): ±10% for most stocks, ±20% for ChiNext/STAR 
   - 龙虎榜 (dragon-tiger榜单) activity and institutional vs retail participation
   - 北向资金 (northbound flow) trends — foreign investor sentiment
   - Volume-price relationship in context of A-share retail-dominant market

**Technical Patterns relevant to A-shares:**
   - 金叉/死叉 (golden/death cross) of moving averages
   - MACD divergence in trending vs range-bound markets
   - Bollinger Band squeezes — common before breakouts
   - Volume confirmation required for all signals
"""
            + get_language_instruction()
            + get_anti_hallucination_instruction("analyst")
            + get_degradation_instruction()
            + industry_section
            + """ **REQUIRED: For each indicator you select, report its SPECIFIC numerical value and cross-state interpretation.** For example: "RSI(14)=35.2, 偏弱但未超卖; MACD柱-0.12, 空头动能衰减". Do NOT just list indicator names without values.
**REQUIRED: List at least 3 specific risk factors** in the 风险提示 section. Do NOT use "数据暂缺" — if you cannot find clear risks from the data, state what typical risks apply to this type of stock based on its price action and volume profile."""
            + " Remember: you are the technical analysis specialist. Your indicators inform the trading decision but you are NOT responsible for the final trading decision."
            + "\n\n**Market Environment Context:**\nThe current market environment data is available via the `get_market_context` tool.\nUse this tool to understand the broader market conditions (index trends, sector rotation, capital flows, market breadth) before interpreting individual stock technical indicators. Factor the market environment into your assessment of whether technical signals indicate genuine trends or market-driven noise.",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system_message}\n\nFor your reference, the current date is {current_date}. {instrument_context}{market_context_section}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        market_context = state.get("market_context", "")
        market_context_section = f"\n\n**当前市场环境：**\n{market_context}" if market_context else ""
        prompt = prompt.partial(market_context_section=market_context_section)

        chain = prompt | llm.bind_tools(tools)

        result_msgs = sanitize_messages_for_deepseek(state["messages"]) if _is_first_entry(state["messages"]) else state["messages"]
        result = chain.invoke(result_msgs)
        filter_valid_tool_calls(result, tools)

        has_tool_calls = hasattr(result, 'tool_calls') and result.tool_calls
        from langchain_core.messages import ToolMessage

        content = result.content if (result.content and result.content != "[Processing]") else ""
        if not content or len(content) < 80:
            for m in reversed(state["messages"]):
                c = str(m.content or "") if m.content else ""
                if (isinstance(m, ToolMessage) and len(c) > 30
                        and "Error:" not in c and "not a valid tool" not in c):
                    content = c[:5000]
                    break

        bm = ""
        for m in reversed(state["messages"]):
            c = getattr(m, 'content', '') or ''
            if "以下工具已经成功获取过数据" in str(c):
                bm = c
                break
        if bm:
            content = bm + ("\n\n" + content if content else "")

        # --- structured_chain: second pass to format content via Pydantic schema ---
        if not has_tool_calls and content:
            try:
                fmt_prompt = (
                    f"Reformat the following technical analysis for {company_name} "
                    f"({state['company_of_interest']}) into a structured market report.\n\n"
                    f"Analysis:\n{content}"
                )
                content = invoke_structured_or_freetext(
                    structured_llm, llm, fmt_prompt,
                    render_market_report, "Market Analyst",
                )
            except Exception:
                pass  # keep original content on structured output failure

        return {
            "messages": [result],
            "market_report": content,
            "market_start_idx": state["market_start_idx"],
        }

    return market_analyst_node
