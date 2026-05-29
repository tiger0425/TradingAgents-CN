# learnings — market_collector.py 真实数据获取实现

## 执行日期
2026-05-13

## 关键发现

### 1. fetch_market_context 输出格式
- `fetch_market_context(date, market_type)` 返回纯 Markdown 字符串
- A_SHARE 市场包含四节：指数状态、板块轮动、资金流向、市场宽度
- 部分数据可能返回 `（数据暂不可用）` 占位符（如板块轮动、资金流向）
- US 市场直接返回 `"Market context unavailable for US stocks"`
- 输出上限 2000 字符，超出截断

### 2. asyncio.to_thread 包裹同步调用
- `fetch_market_context` 和底层 akshare 函数均是同步的
- `MarketDataCollector.collect()` 是 async 方法，必须用 `asyncio.to_thread()` 包裹
- 工作正常，无需额外配置

### 3. 规则兜底摘要质量
- 当 LLM 不可用时（`_llm=None`），`_fallback_summary()` 按行过滤
- `（数据暂不可用）` 文本行被跳过，但小节标题（`## 板块轮动`）仍会保留
- 对于仅含标题无内容的行，兜底结果略显空泛，但已满足"非空字符串"要求
- LLM 路径为优先路径，兜底仅用于异常情况

### 4. 交易日检查
- `_is_trading_day()` 使用简单周一到周五检查：`date.today().weekday() < 5`
- 不考虑中国法定假日调休，当前为 MVP 级别实现
- 如需要，后续可接入 `chinese_calendar` 或 akshare 交易日历

### 5. 导入路径
- collector 中使用 `from ..dataflows.market_context import fetch_market_context`
- 与 agents/utils/market_context_tools.py 模式一致
- 注意不要从 `agents/` 目录导入，应直接从 `dataflows/` 导入

### 6. sentiment_collector 实现要点（T4）
- `get_global_news(curr_date, look_back_days=7, limit=5)` 返回 Markdown 格式字符串，以 `## Global Market News` 开头，每条新闻用 `### Title (source: ...)` 格式
- 返回值是纯 Markdown 字符串（非列表/字典），需要解析为结构化列表
- 解析代码兼容多种格式：跳过 `#` 标题行、跳过 `*` `-` 列表项、捕获 `**粗体**` 标题、其余行作为纯文本
- 解析策略偏保守（宁可少捕获），`_summarize()` 用 `a.get("title", a.get("text", ""))` 优先取标题、回退取文本
- `get_global_news` 使用 `ak.stock_info_global_em()` (东方财富全球财经) 作为主数据源，`ak.stock_info_sse()` 作为回退
- 返回空结果或 `"No news"` 时跳过、返回 None
- 已移除未使用导入 `timedelta`
- 所有同步 akshare 调用均通过 `asyncio.to_thread()` 包裹，与 market_collector 一致
- LLM 调用使用 `self._llm.invoke(prompt)` 模式，`resp.content` 提取内容
- 回退字符串为中文：`"今日采集N条财经新闻，整体情绪中性。"`

### 7. announcement_collector 实现要点
- `get_individual_notices(symbol, days_back=7, notice_type="全部")` 返回 Markdown 格式字符串，含公告标题/时间/分类/内容
- 双数据源策略：优先 `stock_individual_notice_report`、回退 `stock_notice_report`（按股票代码过滤）
- 无公告时返回 `"未找到 **{symbol}** 最近 {days_back} 天的公告。"`（中文），错误时返回 `"Error: ..."`
- 同步函数，须用 `asyncio.to_thread()` 包裹
- 交易日检查 `_is_trading_day()` 与 market_collector 同一模式：`date.today().weekday() < 5`
- `_fetch_announcements()` 通过 `PortfolioManager()` 自动读取 `~/.tradingagents/users/{user_id}/portfolio/portfolio.yaml` 获取持仓和自选股列表
- 无 portfolio 文件时 `PortfolioManager.load()` 返回 `DEFAULT_PORTFOLIO`（空列表），不会抛异常
- scheduler 调用 `collect()` 时不传参数（`watchlist=None, hot_stocks=None`），collector 内部从 PortfolioManager 获取股票列表
- `_annotate()` 优先 LLM 总结（1-2句话中文），回退方案提取第一条非标题/非列表/非表格行
- LLM 调用模式：`self._llm.invoke(prompt)` → 提取 `resp.content`，与 market_collector、sentiment_collector 一致
- 过滤条件 `"No data" not in raw and "Error" not in raw` 对中文"未找到"文本不生效（已知差异，当前按 spec 保留英文检查）

### 8. policy_collector 实现要点
- `get_global_news(curr_date, look_back_days=7, limit=5)` 返回 Markdown 格式字符串，使用 `ak.stock_info_global_em()` 主源 + `ak.stock_info_sse()` 回退
- `_fetch_policy_news()` 用 `asyncio.to_thread()` 包裹同步 akshare 调用，与 market/announcement/sentiment collector 模式一致
- 标题提取逻辑：跳过 `#` `*` `-` `|` `>` 开头的行，取第一个非此类行作为 title，最长 100 字符
- `_is_new()` 通过 `raw.get("title", "")` 与 `_seen_policies` 集合做去重，无需修改
- `_analyze()` 优先 LLM（中文 2-3 条政策要点），回退字符串 `"今日财经动态：{title}"`
- LLM 调用模式与已有 collector 一致：`self._llm.invoke(prompt)` → `resp.content`
- 交易日检查 `_is_trading_day()` 使用 `date.today().weekday() < 5`（周一到周五），与 market/announcement collector 相同
- 导入路径 `from ..dataflows.akshare import get_global_news`，不经过 agents/ 目录
- `collect()` 在 `try` 之前执行交易日检查，非交易日直接返回 None（日志 `debug` 级别）
