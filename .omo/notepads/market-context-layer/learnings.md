# 市场维度注入计划 — Learnings

（初始为空，执行过程中由 agent 追加发现）

## Task 1 — market_context.py

### akshare API 行为笔记

- `stock_zh_index_daily(symbol="sh000001")`: 成功返回数据，date列自动含历史数据，排序后索引0为最近交易日。
- `stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")`: 在非交易日返回空数据，需通过 try/except 保护。可能部分 akshare 版本列名不同（如 "主力净流入-净额"）。
- `stock_market_fund_flow()`: 成功返回数据，资金流数值以**元**为单位（非亿元），需手动除以 1e8 转换。最后一次行情（`.iloc[-1]`）为最新。
- `stock_sse_deal_daily(date="yyyymmdd")`: 期望 `yyyymmdd` 格式日期（而非 `yyyy-mm-dd`）。非交易日返回空数据。

### 单元问题

- 资本流动值初始以元为单位，输出时需 ÷1e8 转为亿元。
- 市场宽度 `stock_sse_deal_daily` 用 `_ak_date()` 格式化的日期。
- 2026-05-09 (周六) 板块轮动和市场宽度数据不可用，符合预期。

## Task 3 — get_market_context Tool 注册

- 工具文件: `tradingagents/agents/utils/market_context_tools.py`
  - 使用 `@tool` 装饰器，参数以 `Annotated[type, "description"]` 标注
  - 内部延迟导入 `fetch_market_context`（避免循环依赖）
- 导出: `agent_utils.py` 末尾添加 `get_market_context` 导入
- 注册: `trading_graph.py` 的 `_create_tool_nodes()` 方法中，`"market"` ToolNode 添加 `get_market_context`
- Market Analyst 现有工具: `get_stock_data`, `get_indicators`, 加上 `get_market_context` 共 3 个
- 工具注册三步模式: ① 创建工具文件 → ② `agent_utils.py` 导出 → ③ `trading_graph.py` 导入并加入 ToolNode

## Task 4 — Market Context Integration in _run_graph()

### 实现位置

- `trading_graph.py` 第 486-531 行：在 `knowledge_context` 装配（Phase 1）之后、`init_agent_state` 创建之前插入 Phase 1.5 市场上下文装配
- 市场上下文注入位于第 529-531 行，在 `init_agent_state` 创建后立即执行

### 架构决策

- `fetch_market_context` 和 `DataCache` 使用**局部导入**（方法内部 import），避免启动循环依赖
- 缓存命名空间 `"market"`，key 格式 `market_context_{trade_date}.json`
- 缓存内容以 `{"text": string}` dict 包装（DataCache 自动序列化为 JSON）
- `enable_market_context` flag 为 False 时跳过整个装配块，`market_context` 保持 create_initial_state 初始化的 `""`
- 获取失败通过 `try/except` 优雅降级（logger.warning + market_context=""），不阻断主流程

### DataCache 行为笔记

- `DataCache.get(ns, key)`: 对 JSON 文件返回 `dict`，文件不存在返回 `None`
- `DataCache.set(ns, key, data)`: dict 自动序列化为 JSON，DataFrame 序列化为 CSV
- `DataCache("path")` 构造函数自动 expanduser + 创建目录

### QA 结果

- [PASS] AST 分析确认 enable_market_context 逻辑存在于 _run_graph
- [PASS] fetch_market_context 和 DataCache 均为局部导入（无顶层 import）
- [PASS] Python 语法检查通过

## Task 5 — Market Analyst Prompt Injection

### 变更位置
- `tradingagents/agents/analysts/market_analyst.py`
  - 第 40 行: system_message 追加 get_market_context 工具说明
  - 第 47 行: 模板字符串添加 `{market_context_section}` 占位符
  - 第 57-59 行: partial 注入从 state 中读取的 market_context

### 模式
- market_context 为空时注入空字符串，不产生额外文本
- 非空时以 `\n\n**当前市场环境：**\n` 为前缀注入
- 使用 `state.get("market_context", "")` 保险读取

### QA 结果
- [PASS] AST 分析确认 market_context 引用存在于文件
- [PASS] Python 语法检查通过

## Task 6 — Bull Researcher Prompt Injection

### 变更位置
- `tradingagents/agents/researchers/bull_researcher.py`
  - 第 40 行: `market_context = state.get("market_context", "")` 从 state 读取
  - 第 63-72 行: 条件性追加 `**Current Market Environment:**` 及市场上下文到 prompt

### 模式
- `market_context` 为空时跳过注入（if guard）
- 非空时追加到 LLM prompt 末尾（`prompt += f"""..."""`），不影响 `history` 变量
- history 更新使用独立的 `history` 变量，不会混入市场上下文

### 历史污染防护
- prompt 变量仅用于 `llm.invoke(prompt)` 调用
- `new_investment_debate_state` 中的 `"history"` 字段使用原始 `history` 变量拼接
- history 与 prompt 完全隔离，不存在交叉污染

### QA 结果
- [PASS] market_context 引用存在
- [PASS] market_context 不在 history 字符串中
- [PASS] Python 语法检查通过

## Task 9 — Integration Test

### 测试脚本位置
- `/tmp/test-market-context-integration.py`（不提交到仓库）

### 测试覆盖
- 8 个测试全部通过: Imports Clean, Config Flag, State Type, Cache, Market Analyst Prompt, Data Module (no akshare guard), Data Module, Tool Function
- `fetch_market_context("2026-05-08", "A_SHARE")` 返回 163 chars Markdown（含指数状态、板块轮动、资金流向、市场宽度），akshare API 在非交易日返回 "（数据暂不可用）" 的优雅降级
- `fetch_market_context("", "A_SHARE")` 空日期也能返回有效 str（145 chars）
- `get_market_context.invoke()` 工具函数同样返回 163 chars
- DataCache 三元组测试（set/get/get_or_fetch/miss）全部通过
- 模拟 akshare 缺失场景：ImportError 包含友好提示信息

### 技术要点
- Python 3.12 中 `ast.Str` 已废弃，字符串匹配需用 `ast.Constant`
- akshare 已安装，API 能正常返回指数数据（上证指数 4179.95）
- 证据保存至 `.sisyphus/evidence/task-9-integration-test.log`

### 配置验证
- `enable_market_context = True` 在 DEFAULT_CONFIG 第 70 行
- `market_context` 字段在 AgentState 第 59 行，类型 `Annotated[str, ...]`
- Market Analyst prompt 同时包含 `get_market_context` 工具引用和 `market_context_section` 模板占位符
