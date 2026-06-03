from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_fundamentals,
    get_language_instruction,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
    _is_first_entry,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name, quick_llm=llm)


        industry_guidance = (
            f"\n\n**行业分析框架：** 该公司属于 {industry} 行业。请参照该行业的估值方法和关键财务指标进行分析，同行对比时以该行业龙头企业为参照。\n"
            if industry else ""
        )

        tools = [
            get_fundamentals,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " TOOL USAGE: You have ONE tool: `get_fundamentals`. It returns real-time price + full balance sheet + income statement + cash flow statement in a SINGLE call. Call it once, then analyze the results and produce your report."
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
            + industry_guidance
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

        result_msgs = sanitize_messages_for_deepseek(state["messages"]) if _is_first_entry(state["messages"]) else state["messages"]
        result = chain.invoke(result_msgs)
        filter_valid_tool_calls(result, tools)

        content = result.content if (result.content and result.content != "[Processing]") else state.get("_break_msg", "")

        return {
            "messages": [result],
            "fundamentals_report": content,
        }

    return fundamentals_analyst_node
