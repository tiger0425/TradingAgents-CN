# 阶段1：A股助手开发计划

## 摘要

在现有多智能体交易分析框架基础上，补齐六个 A 股助手的核心功能。定位为"分析+建议"平台，不做交易执行。全部采用轮询命令模式（crontab 调度），不做常驻 daemon。测试策略：TDD。

## 已确认决策

| 决策项 | 选择 |
|--------|------|
| 功能范围 | 全部6项一次性补齐 |
| 实时监控方式 | 轮询命令（CLI + crontab） |
| 测试策略 | TDD（RED → GREEN → REFACTOR） |
| 实时行情数据源 | akshare (`stock_zh_a_spot_em`) |
| 公告数据源 | akshare (`stock_individual_notice_report`) |
| 研报数据源 | akshare (`stock_research_report_em`) |
| 涨跌停/异动 | akshare (`stock_zt_pool_em`, `stock_zt_pool_zbgc_em`, 等) |
| 通知推送 | 复用现有飞书/ServerChan/PushPlus |
| LLM 摘要 | 复用现有 quick_think_llm |
| 开发顺序 | 按模块化并行开发，无严格前后依赖 |

## 范围

### IN（6项）
1. 实时行情查询与显示
2. 条件单价格预警（实时监控+推送）
3. 短线异动监控（涨停/跌停/炸板/天地板/强势股）
4. 公告快读（抓取+LLM 摘要）
5. 分析师研报（抓取+LLM 摘要）
6. 持仓风险监控（市场下行时自动评估暴露）

### OUT
- 券商交易执行接口
- 常驻 daemon 进程
- 历史 K 线数据（已有）
- 多智能体交易信号生成（已有）

## 技术决策

### 1. 数据供应商注册模式

沿用现有 `interface.py` 的 `VENDOR_METHODS` 注册模式，新增方法：
- `get_real_time_quotes` — 单只或多只股票实时行情
- `get_limit_up_pool` — 涨停股池
- `get_limit_down_pool` — 跌停股池
- `get_zhaban_pool` — 炸板股池
- `get_individual_notices` — 个股公告
- `get_research_reports` — 个股研报
- `get_board_quotes` — 板块实时行情（用于风险监控）

也可选择**不经过 vendor 路由**，直接在 CLI 命令层调用 akshare（因为实时数据请求来自 CLI 命令而不是 agent tool call）。推荐后者——agent 层不需要调用这些新接口。

### 2. CLI 命令结构（扩展现有 typer app）

```python
# cli/main.py 新增
app.command(name="quote")(实时行情)            # tradingagents quote 600519
app.command(name="monitor")(预警监控)           # tradingagents monitor --interval 60
app.command(name="alert-abnormal")(异动监控)    # tradingagents alert-abnormal
app.command(name="notice")(公告快读)            # tradingagents notice 600519
app.command(name="research-report")(研报摘要)   # tradingagents research-report 600519
# portfolio 命令扩展
# tradingagents portfolio risk  # 持仓风险监控
```

### 3. 目录结构变更

```
cli/
  quote.py              # 实时行情命令
  monitor.py            # 条件单实时监控命令
  alert_abnormal.py     # 短线异动监控
  notice.py             # 公告快读
  research_report.py    # 研报摘要
  portfolio.py          # 扩展：添加 risk 子命令

tradingagents/dataflows/
  akshare.py            # 扩展：新增实时行情/涨跌停/公告/研报函数
  a_share_anomalies.py  # 新增：异动检测规则引擎（涨停/跌停/炸板/天地板）
  position_risk.py      # 新增：持仓风险暴露评估模块

tests/
  test_quote.py         # 实时行情测试
  test_monitor.py       # 预警监控测试
  test_alert_abnormal.py # 异动监控测试
  test_notice.py        # 公告快读测试
  test_research_report.py # 研报摘要测试
  test_position_risk.py  # 持仓风险测试
```

### 4. TDD 约定

```
pytest markers: @pytest.mark.unit, @pytest.mark.integration, @pytest.mark.smoke
测试模式: RED（写失败测试）→ GREEN（实现通过）→ REFACTOR（清理）
模拟: 所有网络调用在 unit 级别用 mock 替代，integration 测试走真实 akshare API
```

### 5. LLM 摘要策略

公告和研报摘要复用 `quick_think_llm`（配置化的低成本模型），prompt 模板统一放在 `tradingagents/agents/utils/summarization_prompts.py`。

## 执行策略

### 并行度

六个功能之间**无强依赖关系**，可以同时推进。但考虑到 TDD 节奏，按模块顺序安排：

**Wave 1（并行，3项）**
- 实时行情（基础，被后续引用）
- 公告快读（独立模块）
- 研报摘要（独立模块）

**Wave 2（并行，2项）**
- 条件单预警监控（依赖实时行情数据）
- 短线异动监控（依赖 akshare 涨跌停 API）

**Wave 3（1项）**
- 持仓风险监控（依赖板块数据和组合分析，最难）

### 各模块实现策略

---

#### 功能1：实时行情

**数据源**：`ak.stock_zh_a_spot_em()` — 返回沪深京全部股票实时行情 DataFrame

**实现**：
1. `tradingagents/dataflows/akshare.py` 新增 `get_real_time_quotes(symbol: str) -> str` 
   - 支持单只和多只（逗号分隔）股票
   - 返回 Markdown 表格格式
   - 新增缓存策略（短 TTL，30秒）
2. `cli/quote.py` — CLI 命令
   - `tradingagents quote 600519` → 显示实时行情
   - `tradingagents quote 600519,000858,601318` → 批量显示
   - 支持 `--output json`
3. 测试文件：`tests/test_quote.py`

**TDD 测试用例（单元）**：
- `test_get_single_stock_quote` — 正确获取返回 Markdown
- `test_get_multi_stock_quote` — 逗号分隔返回正确格式
- `test_get_invalid_symbol` — 非法代码返回错误消息
- `test_cache_ttl` — 30秒内重复调用返回缓存
- `test_output_json` — `--output json` 输出有效 JSON

---

#### 功能2：条件单预警监控

**数据源**：实时行情 + 用户自选股配置中的 alert 条件

**现有基础**：`cli/alerts.py` 已有 `_check_price`、`_check_rsi`、`_check_volume_surge`、`_check_ma_cross` 等条件检查函数

**实现**：
1. `cli/monitor.py` — 新增轮询监控命令
   - `tradingagents monitor` → 遍历自选股，检查预警条件，推送触发通知
   - `--interval N` → 轮询间隔（默认60秒）
   - `--once` → 单次运行（crontab 友好）
   - 触发条件推送通知（复用 `notifier` 通道）
   - 已有的 alert 条件从 watchlist 配置读取
2. 扩展 `cli/alerts.py` — 支持实时行情作为输入源（原逻辑用历史数据的 `current_price`）

**TDD 测试用例（单元）**：
- `test_monitor_reads_watchlist` — 正确读取自选股配置
- `test_monitor_triggers_notification` — 触发条件时调用 notifier
- `test_monitor_no_trigger` — 未触发时不发通知
- `test_monitor_interval_respected` — `--once` 模式只运行一次
- `test_monitor_error_handling` — 单只股票数据获取失败不影响其他股票

---

#### 功能3：短线异动监控

**数据源**：
- `ak.stock_zt_pool_em(date)` — 涨停股池
- `ak.stock_zt_pool_dtgc_em(date)` — 跌停股池
- `ak.stock_zt_pool_zbgc_em(date)` — 炸板股池
- `ak.stock_zt_pool_strong_em(date)` — 强势股池
- `ak.stock_zt_pool_previous_em(date)` — 昨日涨停股池

**实现**：
1. `tradingagents/dataflows/a_share_anomalies.py` — 异动检测引擎
   - `detect_limit_ups(date) -> list` — 当前涨停股
   - `detect_limit_downs(date) -> list` — 当前跌停股
   - `detect_zhaban(date) -> list` — 炸板股（曾涨停后打开）
   - `detect_tiandiban(date) -> list` — 天地板（从涨停到跌停或反之）
   - `detect_consecutive_limits(date, days=3) -> list` — 连续涨停/跌停
   - 所有检测结果包含：股票代码、名称、价格、涨跌幅、连板天数等
2. `cli/alert_abnormal.py` CLI 命令
   - `tradingagents alert-abnormal` → 输出当日异动汇总
   - `--push` → 推送通知到飞书/微信
   - `--focus SYMBOL` → 重点关注某只股票
3. `tradingagents/dataflows/akshare.py` 新增对应的 vendor 方法

**TDD 测试用例（单元）**：
- `test_detect_limit_ups_empty` — 返回空列表时格式正确
- `test_detect_zhaban_mocked` — mock akshare 返回模拟炸板数据
- `test_detect_tiandiban` — 识别天地板逻辑正确
- `test_consecutive_limits` — 连板计数正确
- `test_output_format` — 输出 Markdown 表格格式

---

#### 功能4：公告快读

**数据源**：`ak.stock_individual_notice_report(symbol, start_date, end_date)`

**实现**：
1. `tradingagents/dataflows/akshare.py` 新增 `get_individual_notices(symbol, days_back=7) -> str`
   - 返回最近 N 天公告列表
   - 支持按类型过滤（全部/重大事项/财报/风险提示等）
2. `tradingagents/agents/utils/summarization_prompts.py` 新增公告摘要 prompt
3. `cli/notice.py` CLI 命令
   - `tradingagents notice 600519` → 显示并摘要最近公告
   - `tradingagents notice 600519 --type 重大事项` → 按类型过滤
   - `tradingagents notice 600519 --days 3` → 最近3天
   - `tradingagents notice 600519 --push` → 推送摘要到通知渠道
   - `tradingagents notice --scan-watchlist` → 扫描全部自选股的最新公告

**LLM 摘要策略**：
- 对每篇公告正文独立调用 quick_think_llm 做摘要（3-5句话）
- 头条模式：`tradingagents notice --scan-watchlist --push` → 早间推送全部自选股的昨夜今晨公告
- 用户可以选择只看摘要不看全文

**TDD 测试用例（单元）**：
- `test_get_notices_valid` — 返回正确 Markdown 格式
- `test_notices_llm_summary` — mock LLM 返回摘要
- `test_notices_push` — 推送内容包含公告标题+摘要
- `test_notices_scan_watchlist` — 扫描多只自选股
- `test_notices_days_filter` — 天数过滤正确

---

#### 功能5：分析师研报

**数据源**：`ak.stock_research_report_em(symbol)` — 东方财富个股研报

**实现**：
1. `tradingagents/dataflows/akshare.py` 新增 `get_research_reports(symbol, top_n=5) -> str`
   - 返回最近 N 篇研报列表（评级、机构、日期、标题）
   - Markdown 格式
2. `cli/research_report.py` CLI 命令
   - `tradingagents research-report 600519` → 显示最新研报
   - `tradingagents research-report 600519 --top 10` → 显示 10 篇
   - `tradingagents research-report 600519 --detail` → 展开正文摘要
   - `tradingagents research-report 600519 --push` → 推送摘要
   - `tradingagents research-report --scan-watchlist` → 全部自选股

**研报正文获取**：研报列表包含 URL，需要额外抓取正文内容。推荐：
- 使用 `requests` + `parsel`（项目已有依赖）抓取正文
- 或直连东方财富研报详情页

**LLM 摘要策略**：
- 研报正文较长（10-30页），摘要策略为：
  - 提取关键段落（评级、目标价、核心观点）
  - quick_think_llm 压缩为 5-8 句话
  - 专注"为什么买入/卖出"的核心逻辑

**TDD 测试用例（单元）**：
- `test_research_reports_valid` — 正确获取研报列表
- `test_research_reports_llm_summary` — mock LLM 摘要
- `test_research_reports_detail` — 展开详情模式
- `test_reports_scan_watchlist` — 多自选股扫描
- `test_reports_push_format` — 推送格式正确

---

#### 功能6：持仓风险监控

**已有基础**：
- `tradingagents/dataflows/position_utils.py` — 持仓 PnL 计算、平均成本
- `cli/portfolio.py` — 已有持仓管理命令
- `tradingagents/dataflows/market_context.py` — 市场上下文

**实现**：
1. `tradingagents/dataflows/position_risk.py` — 风险暴露评估模块
   - `assess_market_drop_risk(positions, benchmark_drop_pct) -> dict` — 大盘下跌时各持仓风险暴露
   - `assess_concentration_risk(positions) -> dict` — 持仓集中度风险（行业/个股）
   - `assess_correlation_risk(positions) -> dict` — 持仓相关性风险（同涨同跌）
   - `assess_drawdown_risk(positions, lookback_days=20) -> dict` — 各持仓回撤评估
2. CLI 扩展
   - `tradingagents portfolio risk` → 持仓风险评估汇总
   - `tradingagents portfolio risk --market-drop 3` → "大盘跌3%时我的持仓会亏多少"
   - `tradingagents portfolio risk --check` → 检查是否需要告警（大盘跌超阈值）
   - `tradingagents portfolio risk --push` → 推送风险评估报告
3. 风险指标计算：
   - Beta 暴露：从历史数据计算个股与大盘的相关性
   - VaR 估算：简单历史模拟法
   - 最大回撤：20日滚动窗口
   - 集中度：Herfindahl 指数

**TDD 测试用例（单元）**：
- `test_market_drop_impact` — 给定持仓和大盘跌幅，计算损益正确
- `test_concentration_risk` — 全部持仓一只股票时集中度最高
- `test_concentration_diversified` — 分散持仓时集中度低
- `test_drawdown_assessment` — 回撤计算正确
- `test_portfolio_risk_cli` — CLI 命令输出格式
- `test_portfolio_risk_push` — 推送内容包含风险汇总

## 待办事项

- [ ] **功能1：实时行情**
  - [ ] akshare.py: 新增 `get_real_time_quotes()`
  - [ ] cli/quote.py: 实现 quote 命令
  - [ ] tests/test_quote.py: TDD
- [ ] **功能2：条件单预警监控**
  - [ ] cli/monitor.py: 实现 monitor 轮询命令
  - [ ] cli/alerts.py: 扩展支持实时行情输入
  - [ ] tests/test_monitor.py: TDD
- [ ] **功能3：短线异动监控**
  - [ ] akshare.py: 新增涨停/跌停/炸板等 API 封装
  - [ ] dataflows/a_share_anomalies.py: 异动检测引擎
  - [ ] cli/alert_abnormal.py: CLI 命令
  - [ ] tests/test_alert_abnormal.py: TDD
- [ ] **功能4：公告快读**
  - [ ] akshare.py: 新增 `get_individual_notices()`
  - [ ] utils/summarization_prompts.py: 公告摘要 prompt
  - [ ] cli/notice.py: CLI 命令
  - [ ] tests/test_notice.py: TDD
- [ ] **功能5：分析师研报**
  - [ ] akshare.py: 新增 `get_research_reports()`
  - [ ] 研报正文抓取逻辑
  - [ ] utils/summarization_prompts.py: 研报摘要 prompt
  - [ ] cli/research_report.py: CLI 命令
  - [ ] tests/test_research_report.py: TDD
- [ ] **功能6：持仓风险监控**
  - [ ] dataflows/position_risk.py: 风险评估模块
  - [ ] cli/portfolio.py: 扩展 risk 子命令
  - [ ] tests/test_position_risk.py: TDD

## 成功标准

- [ ] 6 个新 CLI 命令全部可用，输出格式一致
- [ ] 所有 `@pytest.mark.unit` 测试通过（mocked，无网络依赖）
- [ ] 实时行情在 < 2秒内返回单只股票数据
- [ ] 公告快读：用户输入 `tradingagents notice 600519` 后 3 秒内看到摘要
- [ ] 异动监控：一次 `tradingagents alert-abnormal` 执行在 < 5 秒内完成
- [ ] LSP diagnostics 全部文件 0 error

## 风险与约束

- akshare 接口变更或服务器不稳定 → 所有命令需要 try/except + 友好错误消息
- 东方财富研报正文抓取可能需要反爬处理 → 备选方案：仅展示研报标题+评级，不抓取正文
- `stock_individual_notice_report` 返回纯文本公告内容，部分公告为 PDF 链接 → 仅处理文本类公告
- 实时行情频繁调用可能导致 akshare 限流 → 缓存层 + 最小轮询间隔 30 秒
- 推送频率控制：避免短时间内重复推送同一条预警
