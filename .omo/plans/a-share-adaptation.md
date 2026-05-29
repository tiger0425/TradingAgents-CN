# TradingAgents A 股适配实施计划

## 摘要

将 TradingAgents（基于 LangGraph 的多智能体金融交易框架）从纯美股环境改造为同时支持 A 股市场。核心策略是**增量式改造**：利用框架现有的 vendor 路由机制和 LangGraph 状态扩展能力，以 akshare 替换 yfinance 作为数据供应商，注入 A 股特有的涨跌停、T+1、交易日历等市场规则，同时保持对美股市场的向后兼容。

**总预估工时**：9-11 天 / 4 个波段

---

## 背景

TradingAgents 是一个 68.5k stars 的高质量开源多智能体金融交易框架，但其数据层仅支持 yfinance 和 Alpha Vantage 两个美股供应商，基准回测硬编码 SPY，不包含 A 股市场特有规则（涨跌停、T+1、交易日历等）。本计划旨在以最小侵入性完成 A 股适配，同时保持框架原有架构优势。

---

## 目标

1. **主目标**：用户可通过配置 `market_type: "A_SHARE"` 使用 A 股数据和分析流程
2. **数据层**：接入 akshare 作为主数据源，覆盖 OHLCV、基本面、新闻三类数据
3. **市场规则**：注入涨跌停约束、T+1 检查、A 股交易日历
4. **向后兼容**：不破坏现有美股流程，通过配置切换市场
5. **中文支持**：analyst 报告和最终决策支持中文输出

---

## 范围

### 包含

- akshare 数据供应商完整实现（9 个 vendor 方法）
- A 股交易日历模块
- 涨跌停价格约束注入
- T+1 交易规则检查
- 基准替换（SPY → 沪深300，可配置）
- 东方财富新闻源适配
- A 股基本面财报适配
- 中文报告输出
- 端到端验证（至少 3 只 A 股跑通完整流程）

### 不包含（后续迭代）

- 分钟级 K 线数据支持
- 北向资金 / 融资融券情绪分析
- A 股回测框架（历史绩效评估）
- 板块轮动策略
- Docker 部署适配（A 股版）
- GUI / Web 前端

---

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| A 股数据源 | akshare v1.18+ | 完全免费、400+ 接口全覆盖、18.5k stars、活跃维护 |
| 架构改造方式 | 增量式 vendor 扩展 | 不改动 LangGraph 编排核心，仅在数据层和市场规则层扩展 |
| State Schema 扩展 | 子类化 MessagesState 新增可选字段 | 不破坏现有序列化，checkpoint 自动兼容 |
| 基准指数 | 沪深300（可配置） | A 股标准基准，通过 `default_config.py` 切换 |
| 技术指标计算 | 继续使用 stockstats | stockstats 基于 OHLCV，与数据源无关 |
| Agent Prompt 策略 | 最小改动 | prompt 中无美股硬编码，仅微调 context 描述 |
| 输出语言 | 通过 `output_language` 配置切换 | 已有机制，内部 debate 保持英文 |
| 中美股兼容 | 配置标记路由 | `market_type` 字段决定使用哪个 ToolNode 组 |

---

## 执行策略

4 个波段，每个波段 4-6 个任务，复杂度递增，每个任务可在半天内完成。

### 波段一：数据供应商接入（Day 1-3）

**复杂度**：⭐⭐ 低 — 纯粹的接口实现工作，跟着现有 yfinance 代码照猫画虎

**目标**：用户用 `600519` 作为 ticker 就能拿到正确的 K 线和技术指标

| # | 任务 | 描述 | 文件 | 预计 |
|---|------|------|------|:---:|
| 1.1 | 新建 akshare vendor 模块 | 在 `dataflows/akshare.py` 中实现 `get_stock_data` 和 `get_indicators` 两个 method。`get_stock_data` 调用 `ak.stock_zh_a_hist(adjust="qfq")`，返回 CSV 格式（与 yfinance 一致）。`get_indicators` 复用现有 stockstats 计算管线 | `dataflows/akshare.py`（新建） | 0.5天 |
| 1.2 | 注册 akshare 到 vendor 路由 | 在 `interface.py` 的 `VENDOR_LIST` 和 `VENDOR_METHODS` 中注册 akshare，更新 `default_config.py` 的 `data_vendors` 指向 akshare。验证 `route_to_vendor()` 正确分发 | `dataflows/interface.py`、`default_config.py` | 0.5天 |
| 1.3 | 修改 stockstats 数据源 | 将 `stockstats_utils.py` 中 `load_ohlcv()` 的 `yf.download()` 替换为 akshare 调用，保持缓存机制不变。验证 stockstats 技术指标计算正常 | `dataflows/stockstats_utils.py` | 0.5天 |
| 1.4 | 实现基本面 4 个 method | `get_fundamentals` → 合并 akshare 新浪/东财双源财务指标；`get_balance_sheet`/`get_cashflow`/`get_income_statement` → akshare 新浪财报接口。统一返回 CSV 格式 | `dataflows/akshare.py` | 1天 |
| 1.5 | 实现新闻 3 个 method | `get_news` → `ak.stock_news_em()` 东方财富个股新闻；`get_global_news` → A 股宏观资讯（央行/经济数据）；`get_insider_transactions` → `ak.stock_hold_management_detail_em()` 大股东增减持 | `dataflows/akshare.py` | 0.5天 |

**验证标准**：运行 `python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; ta = TradingAgentsGraph(); print(ta.propagate('600519', '2026-03-15'))"` 不报数据源错误（Decision 内容可能不合理属正常）。

---

### 波段二：A 股市场规则注入（Day 4-5）

**复杂度**：⭐⭐⭐ 中 — 需要在状态层和决策层施加约束

**目标**：系统在生成交易建议时考虑涨跌停和 T+1 限制

| # | 任务 | 描述 | 文件 | 预计 |
|---|------|------|------|:---:|
| 2.1 | 新增 A 股交易日历模块 | 新建 `dataflows/a_share_calendar.py`，封装 akshare `tool_trade_date_hist_sina` 提供 `is_trade_day()`、`next_trade_day()`、`prev_trade_day()` 函数。在 `get_stock_data` 中自动跳转到最近交易日 | `dataflows/a_share_calendar.py`（新建） | 0.5天 |
| 2.2 | 基准替换 SPY → 配置化 | 在 `default_config.py` 新增 `benchmark_ticker` 和 `benchmark_name` 配置。修改 `trading_graph.py:_fetch_returns()` 使用配置的基准（默认沪深300）替代硬编码 SPY。修改 `reflection.py` 提示词中的 "Alpha vs SPY" 文本 | `default_config.py`、`graph/trading_graph.py`、`graph/reflection.py` | 0.5天 |
| 2.3 | 涨跌停约束注入 | 新建 `a_share_constraints.py` 模块。在 `get_stock_data` 返回数据中附带上日收盘价，用于计算涨跌停价。修改 Trader agent prompt（`trader.py`）在用户消息中注入当日涨跌停价格约束。修改 Portfolio Manager prompt 注入 "价格必须在涨跌停范围内" 约束 | `dataflows/a_share_constraints.py`（新建）、`agents/trader/trader.py`、`agents/managers/portfolio_manager.py` | 1天 |
| 2.4 | T+1 交易规则检查 | 扩展 `AgentState` 新增 `position_opened_date` 字段。在 Portfolio Manager 决策前检查：若为买入且当日持仓为0天，则允许买入；若为卖出且持仓不足1个交易日且市场为A_SHARE，则改为 Hold 并附说明 | `agents/utils/agent_states.py`、`agents/managers/portfolio_manager.py` | 0.5天 |

**验证标准**：对于持仓 0 天的 A 股，PM 不应输出 Sell 决策。决策中不应出现超过涨跌停范围的建议价格。

---

### 波段三：中文生态适配（Day 6-7）

**复杂度**：⭐⭐ 低~中 — 主要是数据映射和 prompt 微调

**目标**：分析师输出中文报告，基本面数据使用 A 股财报口径

| # | 任务 | 描述 | 文件 | 预计 |
|---|------|------|------|:---:|
| 3.1 | 基本面数据 A 股财报适配 | 在 `get_fundamentals` 中增加 A 股特有指标映射（PE/PB/ROE/毛利率/资产负债率/净利润增长率等），使用 akshare 新浪财务指标接口。确保字段名与现有 analyst prompt 兼容 | `dataflows/akshare.py` | 0.5天 |
| 3.2 | build_instrument_context 适配 | 修改 `agent_utils.py` 中 `build_instrument_context()`：当市场为 A_SHARE 时，描述 A 股 6 位代码格式。说明 `.SS`（上海）或 `.SZ`（深圳）后缀规则 | `agents/utils/agent_utils.py` | 0.5天 |
| 3.3 | 中文输出验证与调优 | 设置 `output_language: "Chinese"`，跑通完整流程。检查所有 analyst 报告和 PM 最终决策的中文质量。对翻译不自然的地方微调 prompt（如 fundamentals "over the past week" → "过去一周" 等时间描述的本地化） | 全部 analyst 文件 + `default_config.py` | 0.5天 |
| 3.4 | 记忆系统 A 股兼容验证 | 运行 2-3 次同一 ticker 的 propagate，验证 `memory.py` 正确记录 A 股决策和反思。检查 `_fetch_returns()` 使用沪深300 基准计算 alpha 是否正确 | `graph/trading_graph.py`、`graph/reflection.py` | 0.5天 |

**验证标准**：analyst 报告为自然流畅的中文。决策日志中的基本面数据包含 PE、ROE、净利润增长率等 A 股投资者熟悉的指标。记忆系统正确记录沪深300 基准 alpha。

---

### 波段四：端到端集成与边缘测试（Day 8-9）

**复杂度**：⭐⭐⭐ 中 — 需要发现并修复边界条件问题

**目标**：多只 A 股、多个交易日、多种市场环境下的稳定性验证

| # | 任务 | 描述 | 文件 | 预计 |
|---|------|------|------|:---:|
| 4.1 | 多 ticker 集成测试 | 测试至少 5 只不同类型 A 股：蓝筹（600519 茅台）、成长（300750 宁德时代）、金融（601398 工商银行）、中小板（002415 海康威视）、ST（任意）。确保每只都能拿到完整数据 | 测试脚本（新建 `tests/test_a_share.py`） | 0.5天 |
| 4.2 | 边缘日期测试 | 测试交易日边界：春节前最后交易日、国庆后首个交易日、当前日期（数据时效性）、历史上限（2000年前数据）。验证交易日历模块的正确性 | `tests/test_a_share.py` | 0.5天 |
| 4.3 | 中美股配置切换测试 | 测试 `market_type: "US_STOCK"` 回退到 yfinance 正常运作，`market_type: "A_SHARE"` 使用 akshare。确保两次 propagate 互不污染缓存和 checkpoint | `tests/test_a_share.py` | 0.5天 |
| 4.4 | checkpoint 恢复测试 | 开启 `checkpoint_enabled`，中途 kill 进程后重新 propagate，验证从断点恢复且 akshare 数据缓存不损坏 | `tests/test_a_share.py` | 0.5天 |
| 4.5 | 文档与配置说明 | 更新 `README.md`（A 股使用章节），补充 `default_config.py` 注释中的 A 股配置示例 | `README.md`、`default_config.py` | 0.5天 |

**验证标准**：全部测试通过。不同类型的 A 股均返回合理的决策（不要求决策正确性，只要求流程不报错、不崩溃、不返回空数据）。

---

## 待办事项

- [x] **波段一**：数据供应商接入（任务 1.1 ~ 1.5）
- [x] **波段二**：A 股市场规则注入（任务 2.1 ~ 2.4）
- [x] **波段三**：中文生态适配（任务 3.1 ~ 3.4）
- [x] **波段四**：端到端集成与边缘测试（任务 4.1 ~ 4.5）

---

## 风险与约束

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|------|
| akshare 接口因东方财富改版临时失效 | 中 | 高 — 数据阻塞 | 多数据源互备（新浪/腾讯为 fallback）；akshare 社区 24-48h 内修复 |
| akshare 中国际化股票代码格式不一致 | 低 | 中 — agent 混乱 | 统一内部使用 6 位代码 + market 标记，在 vendor 层做转换 |
| yfinance 和 akshare 返回的财务数据字段名差异大 | 高 | 中 — 分析师读取数据混乱 | 在 vendor 方法中统一字段输出格式 |
| 涨跌停下无法成交导致决策失效 | 低 | 低 — 系统是研究性质 | 在 prompt 中以"约束条件"形式注入，不硬编码拒绝逻辑 |
| LangGraph checkpoint 中新增 state 字段可能导致旧 checkpoint 不兼容 | 低 | 中 — 旧缓存损坏 | 先 `--clear-checkpoints` 清空旧缓存启动 |

---

## 成功标准

- [ ] 数据层：用 `600519`（贵州茅台）运行 `propagate("600519", "2026-01-15")`，所有 4 类数据（行情、指标、财报、新闻）返回非空结果
- [ ] 规则层：Trader 建议价格在涨跌停范围内；PM 对持仓 0 天的 A 股不输出 Sell
- [ ] 语言层：设置 `output_language: "Chinese"` 后，analysts 报告为流畅中文
- [ ] 兼容层：切换 `market_type: "US_STOCK"` 后，美股流程正常运作无退化
- [ ] 稳定性：5 只不同类型 A 股连续运行不报错、不崩溃
