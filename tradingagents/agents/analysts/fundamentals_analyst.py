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

        # DeepSeek 兼容：清理孤立 tool_calls，防止 400 错误
        msgs = state["messages"]

        # 第一遍：收集所有有匹配 ToolMessage 的 tool_call_id
        matched_tool_ids = set()
        for m in msgs:
            if isinstance(m, ToolMessage):
                matched_tool_ids.add(m.tool_call_id)

        # 第二遍：只保留 tool_calls 全部有匹配的 AIMessage
        cleaned = []
        for m in msgs:
            if isinstance(m, AIMessage) and m.tool_calls:
                if all(tc.get("id") in matched_tool_ids for tc in m.tool_calls if "id" in tc):
                    cleaned.append(m)
            elif isinstance(m, ToolMessage):
                cleaned.append(m)
            else:
                cleaned.append(m)

        result = chain.invoke(cleaned)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
