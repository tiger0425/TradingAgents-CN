from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_current_price,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    get_degradation_instruction,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

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
            + get_language_instruction()
            + get_degradation_instruction()
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

        # Keep the last valid tool cycle, strip orphaned tool_calls
        from langchain_core.messages import AIMessage, ToolMessage
        msgs = state["messages"]
        n = len(msgs)
        cut = n
        for i in range(n - 1, -1, -1):
            if isinstance(msgs[i], AIMessage) and msgs[i].tool_calls:
                tc_ids = {tc["id"] for tc in msgs[i].tool_calls if "id" in tc}
                has_match = any(
                    isinstance(msgs[j], ToolMessage) and msgs[j].tool_call_id in tc_ids
                    for j in range(i + 1, n)
                )
                if has_match:
                    cut = i
                    break
            elif i < cut and isinstance(msgs[i], ToolMessage):
                cut = min(cut, i + 1)
        result_msgs = list(msgs[cut:])
        for mi, m in enumerate(result_msgs):
            if isinstance(m, AIMessage) and m.tool_calls:
                tc_ids = {tc["id"] for tc in m.tool_calls if "id" in tc}
                if not any(
                    isinstance(result_msgs[j], ToolMessage) and result_msgs[j].tool_call_id in tc_ids
                    for j in range(mi + 1, len(result_msgs))
                ):
                    if m.content:
                        m.tool_calls = []
                    else:
                        m.content = "[Tool results processed]"
                        m.tool_calls = []
        result = chain.invoke(result_msgs)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
