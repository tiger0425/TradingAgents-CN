from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
)
from tradingagents.agents.utils.social_sentiment_tools import get_social_sentiment_tool
from tradingagents.agents.utils.a_stock_data_tools import get_cls_flash, get_hot_stock_reasons


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name)
        if industry:
            instrument_context += f"\n\n**行业舆情特征：** 该公司属于 {industry} 行业，请结合该行业的舆情特点和市场关注焦点进行分析。\n"

        tools = [
            get_social_sentiment_tool,
            get_news,
            get_cls_flash,
            get_hot_stock_reasons,
        ]

        system_message = (
            "You are an A-share social behavior analyst focused on retail investor attention metrics. "
            "Analyze social sentiment indicators such as attention index, participation willingness, "
            "real-time popularity ranking, and cross-platform (Xueqiu/EastMoney) comparison trends. "
            "Provide specific insights on retail investor mood shifts and crowd behavior patterns.\n\n"
            "Note: Your data sources are behavioral metrics (attention volume, ranking changes, willingness indices), "
            "NOT actual social media post content. Use the get_news tool alongside social sentiment tools "
            "to cross-validate findings with news-driven events.\n\n"
            "Available tools and recommended usage:\n"
            "1. get_social_sentiment_tool — core behavioral metrics (attention, participation, ranking). "
            "Always start with this to gauge retail mood. Compare Xueqiu vs EastMoney trends for cross-platform divergence.\n"
            "2. get_news — news headlines for the stock. Use alongside social sentiment to correlate mood spikes with specific events.\n"
            "3. get_cls_flash — real-time financial news flashes from 财联社 (cls.cn). "
            "Use to catch breaking news that may explain sudden changes in attention/ranking. "
            "Call this when you see rapid shifts in sentiment indicators.\n"
            "4. get_hot_stock_reasons — top active stocks and their theme/subject tags (e.g. '算力租赁+AI'). "
            "Use to identify whether the stock is riding a broader market narrative and to contextualize popularity ranking moves.\n\n"
            "Cross-reference strategy: When attention index spikes or ranking surges, "
            "check get_cls_flash for breaking catalysts, then use get_news for the stock-specific story. "
            "If the stock appears on get_hot_stock_reasons, note the theme tag to connect retail attention to market narratives.\n\n"
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

        result_msgs = sanitize_messages_for_deepseek(state["messages"])
        result = chain.invoke(result_msgs)
        filter_valid_tool_calls(result, tools)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
