from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.schemas import NewsReport, render_news_report
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_news,
    get_global_news,
    get_language_instruction,
    get_degradation_instruction,
    sanitize_messages_for_deepseek,
    filter_valid_tool_calls,
    _is_first_entry,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    structured_llm = bind_structured(llm, NewsReport, "News Analyst")

    def news_analyst_node(state):
        current_date = state["trade_date"]
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name, quick_llm=llm)
        if industry:
            instrument_context += f"\n\n**行业政策关注：** 该公司属于 {industry} 行业，请重点关注该行业的产业政策、监管动态和行业重大新闻。\n"

        # FIX-8 P0: 工具循环计数起点，首次进入时固化
        if state.get("news_start_idx", -1) < 0:
            state["news_start_idx"] = len(state["messages"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and macro-economic trends over the past week. Please write a comprehensive report of the current state of the macro environment and news that are most relevant to the company being researched. Look at news and trends across multiple sectors."
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
            + get_anti_hallucination_instruction("analyst")
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

        if not has_tool_calls and content:
            try:
                fmt_prompt = (
                    f"Reformat the following news analysis for {company_name} "
                    f"({state['company_of_interest']}) into a structured news report.\n\n"
                    f"Analysis:\n{content}"
                )
                content = invoke_structured_or_freetext(
                    structured_llm, llm, fmt_prompt,
                    render_news_report, "News Analyst",
                )
            except Exception:
                pass

        return {
            "messages": [result],
            "news_report": content,
            "news_start_idx": state["news_start_idx"],
        }

    return news_analyst_node
