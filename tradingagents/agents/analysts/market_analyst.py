from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_current_price,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
    _is_first_entry,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name, quick_llm=llm)
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
            get_indicators,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy.

Categories:
- **Moving Averages**: close_50_sma (50 SMA), close_200_sma (200 SMA), close_10_ema (10 EMA)
- **MACD Related**: macd (MACD line), macds (MACD Signal), macdh (MACD Histogram)
- **Momentum**: rsi (Relative Strength Index)
- **Volatility**: boll (Bollinger Middle), boll_ub (Bollinger Upper), boll_lb (Bollinger Lower), atr (Average True Range)
- **Volume-Based**: vwma (Volume-Weighted MA)

Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
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
            + get_degradation_instruction()
            + industry_section
            + " Remember: you are the technical analysis specialist. Your indicators inform the trading decision but you are NOT responsible for the final trading decision."
            + "\n\n**Market Environment Context:**\nThe current market environment data is available via the `get_market_context` tool.\nCall this tool at the START of your analysis to understand the broader market conditions (index trends, sector rotation, capital flows, market breadth) before interpreting individual stock technical indicators. Factor the market environment into your assessment of whether technical signals indicate genuine trends or market-driven noise.",
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
        content = result.content if (result.content and result.content != "[Processing]") else state.get("_break_msg", "")

        return {
            "messages": [result],
            "market_report": content,
        }

    return market_analyst_node
