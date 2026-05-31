from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    get_degradation_instruction,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_insider_transactions,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + """
**A-Share Fundamentals Context:**
   - Consider A-share specific valuation metrics: PE(TTM), PB, PS, dividend yield
   - Market cap classification: 大盘 (large-cap >100B), 中盘 (mid-cap 10-100B), 小盘 (small-cap <10B)
   - 流通市值 (circulating market cap) vs total market cap — important for price impact
   - 股东户数变化 (shareholder count changes) as sentiment indicator

**A-Share Financial Analysis:**
   - Compare financial metrics against industry peers (同行对比)
   - Consider 季度环比 (QoQ) and 同比 (YoY) growth rates
   - ROE and 毛利率 trends over multiple periods
   - Free cash flow yield for value assessment
"""
            + get_language_instruction()
            + get_degradation_instruction()
            + " Remember: you are the fundamentals specialist. Your analysis feeds into the broader investment thesis but you are NOT responsible for the final trading decision.",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system_message}\n\nFor your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
