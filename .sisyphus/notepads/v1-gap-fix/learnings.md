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
