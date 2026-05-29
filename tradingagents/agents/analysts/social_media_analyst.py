from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_news, get_degradation_instruction
from tradingagents.agents.utils.social_sentiment_tools import get_social_sentiment_tool


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_social_sentiment_tool,
            get_news,
        ]

        system_message = (
            "You are an A-share social behavior analyst focused on retail investor attention metrics. "
            "Analyze social sentiment indicators such as attention index, participation willingness, "
            "real-time popularity ranking, and cross-platform (Xueqiu/EastMoney) comparison trends. "
            "Provide specific insights on retail investor mood shifts and crowd behavior patterns.\n\n"
            "Note: Your data sources are behavioral metrics (attention volume, ranking changes, willingness indices), "
            "NOT actual social media post content. Use the get_news tool alongside social sentiment tools "
            "to cross-validate findings with news-driven events.\n\n"
            "Degradation: If social sentiment data is temporarily unavailable, state this clearly and "
            "rely on news analysis to supplement. Do NOT fabricate sentiment data.\n\n"
            "Make sure to append a Markdown table at the end of the report to organize key points."
            + get_language_instruction()
            + get_degradation_instruction()
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
        cleaned = []
        pending_tool_ids = set()
        for m in msgs:
            if hasattr(m, "tool_calls") and m.tool_calls:
                tc_ids = {tc.get("id", "") for tc in m.tool_calls if hasattr(tc, "get")}
                pending_tool_ids |= tc_ids
                cleaned.append(m)
            elif hasattr(m, "name") and m.name == "tool" and hasattr(m, "tool_call_id"):
                if m.tool_call_id in pending_tool_ids:
                    pending_tool_ids.discard(m.tool_call_id)
                    cleaned.append(m)
            else:
                cleaned.append(m)

        result = chain.invoke(cleaned)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
