from langchain_core.messages import AIMessage, HumanMessage
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

        # Keep only the last tool_call cycle to avoid DeepSeek ordering errors
        filtered = []
        for m in reversed(state["messages"]):
            filtered.insert(0, m)
            # If we hit an AIMessage with tool_calls, keep it + all previous non-tool messages
            if isinstance(m, AIMessage) and m.tool_calls:
                break
        # Start fresh with the filtered (last cycle only)
        # If the last message was a tool result, chain will get [user, ai(tc), tool] = valid
        # If only non-tool messages, chain gets all of them = also valid
        if not filtered:
            filtered = [HumanMessage(content="Continue")]
        result = chain.invoke([])

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
