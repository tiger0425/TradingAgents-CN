from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_news,
    get_global_news,
    get_language_instruction,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and macro-economic trends over the past week. Please write a comprehensive report of the current state of the macro environment and news that are most relevant to the company being researched. Look at news and trends across multiple sectors. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + """
**A-Share News Analysis Focus:**
   - 政策面分析: impacts of central bank (央行), CSRC (证监会), and government policies
   - 产业政策: industry-level policy changes affecting specific sectors
   - 监管动态: regulatory developments, compliance events, delisting warnings
   - 财报季: earnings season dynamics — positive/negative profit warnings (业绩预告)
   - 北向资金相关新闻: foreign capital flow direction and drivers
   - 大股东增减持: insider buying/selling signals
"""
            + get_language_instruction()
            + get_degradation_instruction()
            + " Remember: you are the news and macro environment specialist. Your insights inform trading decisions but you are NOT responsible for the final decision.",
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

        result_msgs = sanitize_messages_for_deepseek(state["messages"])
        result = chain.invoke(result_msgs)
        filter_valid_tool_calls(result, tools)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
