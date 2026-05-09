# TradingAgents 股票助手改造 - 学习记录

## 项目约定
- 所有 A 股代码为 6 位数字，上海 `6xxxxx` → `shxxxxxx`，深圳 `0/3xxxxx` → `szxxxxxx`
- 纯计算工具函数风格参考 `a_share_constraints.py`：接受参数、返回结果、无副作用
- Prompt 上下文片段风格参考 `agent_utils.py:build_instrument_context()`：接受参数、返回格式化字符串、空输入返回空字符串
- 原子写入模式参考 `memory.py:161-163`：`tmp_path.write_text() + tmp_path.replace()`
- AgentState 字段声明风格：`Annotated[type, "description"] = default`
- 测试风格：pytest + tmp_path fixture + 参数化测试
- CLI 命令注册在 `cli/main.py` 的 `app = typer.Typer()` 上
- `--output json` 需确保所有字段可 JSON 序列化（处理 datetime、Decimal 等）

## 重要路径
- 持仓文件: `~/.tradingagents/memory/position_state.json`
- 配置目录: `~/.tradingagents/`
- 记忆日志: `~/.tradingagents/memory/trading_memory.md`

## cli/batch.py 实现记录 (2026-05-09)

### 架构决策
- 使用 `graph.propagate()` 而非手动编排（与 `cli/main.py` 不同）——`propagate()` 内部处理过去记忆上下文、持仓持久化加载、A 股涨跌停价计算、状态持久化、记忆更新和持仓自动更新，无需在 batch 命令中重复这些逻辑
- 自建 Typer app（而非挂到 `cli/main.py` 的 `app` 上）以保持文件自包含，通过 `python -m cli.batch` 运行

### 关键映射
- 分析师别名: `"technical"` → `"fundamentals"`（与 task spec 的 "technical" 名称兼容）
- JSON 输出键映射: `fundamentals` → `"technical"`（JSON 中对外暴露 "technical"）
- 评级方向映射: Buy/Overweight → buy, Hold → hold, Underweight/Sell → sell

### JSON 序列化策略
- 双层防护：`_sanitize_for_json()` 处理单个值 + `_deep_sanitize()` 递归遍历所有嵌套结构
- 处理类型：datetime/date → isoformat, bytes → decode, set/frozenset → list, complex → dict, Decimal → float, 其他 → str
- `BatchJSONEncoder` 作为兜底，用于 `json.dumps` 时捕获 `_deep_sanitize` 遗漏的类型

### 验证通过
- 语法检查 ✓, 编译检查 ✓, 导入检查 ✓
- CLI --help 正确展示所有选项
- `_parse_analysts('market,technical')` → `['market', 'fundamentals']`（别名生效）

## 实现记录 — WatchlistManager 与 CLI (2026-05-09)

### 新建文件
- `tradingagents/watchlist.py`：`WatchlistManager` 类
  - `add(ticker, name, priority, alerts)` — 添加/更新股票，重复 ticker 不创建新条目而是合并更新
  - `remove(ticker)` — 移除股票，返回 bool
  - `list()` — 按 priority 升序排序返回所有股票
  - `get(ticker)` — 获取单只股票，返回副本（防止外部修改内部状态）
  - `set_alert(ticker, alert_type, value)` — 设置告警条件
  - `remove_alert(ticker, alert_type)` — 移除告警条件
  - `get_all_tickers()` — 返回排序的 ticker 列表
  - 默认路径：`~/.tradingagents/watchlist.json`
  - 配置键：`watchlist_path`
  - 原子写入：`.tmp` + `os.replace()`
  - JSON 损坏/缺失文件优雅降级为空列表

- `cli/watchlist.py`：watchlist Typer 命令组
  - 自建 Typer app (`watchlist_app`)，非挂到 `cli/main.py` 的 `app`
  - 命令：`add`, `remove`, `list`, `get`, `set-alert`, `remove-alert`
  - `list` 和 `get` 支持 `--output json` 选项
  - 文本输出使用简单 `print()`，JSON 用 `json.dumps`
  - 错误处理：`typer.Exit(code=1)` + `err=True`

- `tests/test_watchlist.py`：`TestWatchlistManager` 类（30 个测试）
  - 覆盖：add/remove/list/get/set_alert/remove_alert/get_all_tickers
  - 边界：损坏 JSON、缺失文件、深层嵌套目录、空字符串名称、负优先级
  - 行为：重复添加不重复、get 返回副本、remove 持久化

### 关键发现
- `add()` 在 ticker 已存在时合并 alerts（`dict.update`），保留已有告警的同时更新新增项
- `get()` 返回 `dict(entry)` 副本，防止外部修改污染内部数据
- CLI 的 `set-alert --rsi-oversold` 等布尔告警无需传值，typer 自动识别为 flag
- `remove-alert` 的布尔 flag 只标记要移除的告警类型，不传递值
- 测试遵循已有模式：`tmp_path` fixture + `{"watchlist_path": str(path)}` 覆盖默认路径

### 验证结果
- 30/30 测试通过 ✅
- 导入验证通过 ✅
- CLI --help 全部 6 个子命令正常 ✅
- 端到端集成测试 7/7 通过 ✅

## 实现记录 — cli/scan.py (2026-05-09)

### 新建文件
- `cli/scan.py`：批量扫描 Typer 命令组
  - `scan_app = typer.Typer(name="scan")` — 自建 Typer app
  - 三个命令：`scan-watchlist`, `morning-scan`, `evening-review`
  - 所有命令共享选项：`--date`, `--output`, `--llm`, `--deep-model`, `--quick-model`, `--debate-rounds`

### 辅助函数
- `_group_signals(results)` → `Dict[str, List[str]]`：按决策评级分类到 5 个信号桶（buy/overweight/hold/underweight/sell），跳过含 error 字段的结果
- `_build_scan_json_output(date, results, signals, scanned, total, **extra)` → `dict`：构建标准 JSON 输出结构，可通过 extra_fields 注入 quotes/positions/holdings/total_pnl
- `_format_scan_text_header(title, date, scanned, total)` → `str`：通用文本表头
- `_format_scan_text_signals(signals, indent)` → `str`：信号摘要文本格式化
- `_truncate_text(text, max_len=100)` → `str`：截断文本
- `_format_signal_line(label, tickers)` → `str`：单行信号格式化
- `_get_spot_quote(ticker)` → `Optional[dict]`：通过 akshare stock_zh_a_spot 获取实时行情
- `_get_close_price(ticker, date)` → `Optional[float]`：通过 akshare stock_zh_a_daily 获取收盘价
- `_run_single_analysis(ticker, date, config, selected_analysts)` → `dict`：单股票分析，不抛异常
- `_run_scan(tickers, date, config, selected_analysts, position_states)` → `(results, scanned)`：批量分析，错误不中断

### 关键设计决策
- 复用 `cli/batch.py` 的 `build_config()`, `_parse_analysts()`, `ANALYST_ORDER`, `RATING_DIRECTION_MAP`, `BatchJSONEncoder`, `_deep_sanitize`
- 不调用 batch CLI 入口，直接导入 graph 组件（`TradingAgentsGraph` + `DEFAULT_CONFIG`）
- `scan-watchlist`：完整 4 个分析师 + 按优先级排序
- `morning-scan`：仅市场 + 技术面（`_parse_analysts("market,technical")` → `["market", "fundamentals"]`），附加实时行情数据
- `evening-review`：完整分析师 + 持仓 P&L 计算（通过 `PositionStateManager` 获取持仓，`_get_close_price` 获取收盘价，`calc_position_pnl` 计算盈亏）
- 错误处理：单只股票失败不中断整个扫描，结果中标记 `"error"` 字段
- akshare 懒加载：`try/except ImportError` + `_AKSHARE_AVAILABLE` 标志
- 无 Rich UI：所有文本输出使用 `typer.echo()` + `print()` 风格

### 测试覆盖 (tests/test_scan.py)
- 29 个测试，6 个测试类：
  - `TestTruncateText` (5 tests)：截断、空值、边界
  - `TestFormatSignalLine` (3 tests)：信号行格式化
  - `TestGroupSignals` (6 tests)：分类、去重、错误跳过、未知决策降级
  - `TestBuildScanJsonOutput` (7 tests)：JSON 结构、详情、错误结果、extra_fields、序列化
  - `TestFormatScanTextHeader` (3 tests)：文本表头
  - `TestFormatScanTextSignals` (3 tests)：信号文本、缩进
  - `TestSIGNALKEYS` (2 tests)：常量验证

### 验证结果
- 29/29 测试通过 ✅
- 语法检查通过 ✅
- 导入验证通过 ✅
- 3 个命令已注册到 scan_app ✅

## 通知系统实现记录 (2026-05-09)

### 新建文件
- `tradingagents/notifier.py`：通知抽象层
  - `Notifier` ABC：`send_text(title, content)` 和 `send_markdown(title, content)` 接口
  - `FeishuNotifier`：飞书自定义机器人 webhook，支持完整 URL 或 hook ID，config key `"feishu_webhook"`，env var `FEISHU_WEBHOOK`
  - `ServerChanNotifier`：Server酱微信推送，config key `"server_chan_key"`，env var `SERVER_CHAN_KEY`
  - `PushPlusNotifier`：PushPlus 多通道推送，config key `"pushplus_token"`，env var `PUSHPLUS_TOKEN`
  - `create_notifier(config)` 工厂函数：根据配置中存在的 key 创建对应 notifier 列表
  - 所有 HTTP 调用用 `requests.post()`，异常通过 `try/except requests.RequestException` 处理
  - `configured` 属性判断渠道是否已配置

- `cli/notify.py`：直接通知 CLI 命令
  - `notify_app = typer.Typer(name="notify")`，注册到 `cli/main.py`
  - 三个子命令：`feishu`（仅飞书）、`wechat`（Server酱+PushPlus）、`all`（全部已配置）
  - 选项：`--title`（必填）、`--content`（必填）、`--markdown`（可选，默认 False）
  - 无 Rich UI，纯 `typer.echo()` 输出

- `tests/test_notifier.py`：41 个单元测试
  - 6 个测试类：`TestFeishuNotifier`（12 tests）、`TestServerChanNotifier`（9 tests）、`TestPushPlusNotifier`（10 tests）、`TestCreateNotifier`（8 tests）、`TestNotifierABC`（2 tests）
  - 使用 `unittest.mock.patch` 模拟 `requests.post`
  - 覆盖：配置解析（参数字面量 > config dict > env var）、发送成功/失败/无配置/网络异常、工厂创建

### 修改文件
- `cli/scan.py`：
  - 新增 import: `from tradingagents.notifier import create_notifier`
  - 新增 `_notify_scan_results(scan_type, date, signals, scanned, total, config, **extra)` 辅助函数
  - 在 `morning_scan()` 中调用：`_notify_scan_results("晨间扫描", date, signals, scanned, total, config)`
  - 在 `evening_review()` 中调用：`_notify_scan_results("晚间复盘", date, signals, scanned, total, config, total_pnl=total_pnl, holdings=holdings_count)`
  - 通知失败不影响扫描（try/except 静默吞掉）
  - 仅在 notifier 已配置时才发送（`create_notifier(config)` 返回非空列表时）

- `cli/main.py`：
  - 新增 import: `from cli.notify import notify_app`
  - 新增注册: `app.add_typer(notify_app, name="notify")`

### 关键设计决策
- 所有 notifier 的 `send_*` 方法返回 `bool`（成功/失败），不抛异常
- 飞书 post 格式的 markdown 以文本段落形式发送（飞书 post 类型的富文本内容）
- PushPlus 的 `send_text` 使用 `template="txt"`，`send_markdown` 使用 `template="markdown"`
- Server酱 的 `send_markdown` 与 `send_text` 复用同一方法（Server酱原生支持 markdown）
- 通知内容使用中文标签（买入/增持/持有/减持/卖出）
- 晚间复盘的 markdown 内容在信号汇总前插入持仓盈亏段落

### 验证结果
- 41/41 new tests passed ✅（notifier）
- 29/29 existing scan tests passed ✅（无回归）
- 语法检查所有文件通过 ✅
- 导入验证通过 ✅

## Phase 3 — 市场扫描与告警系统 (2026-05-09)

### 新建文件
- `cli/alerts.py`：告警条件检查器
  - `check_alerts(date, output)` Typer 命令
  - 6 种告警类型：price_above, price_below, rsi_oversold, rsi_overbought, volume_surge, ma_cross
  - 纯逻辑检查函数 `_check_price()` / `_check_rsi()` / `_check_volume_surge()` / `_check_ma_cross()`
  - RSI 和成交量检查需要历史数据（`_load_ohlcv_akshare`），价格检查使用实时行情（`stock_zh_a_spot`）
  - 均线交叉检测使用最近两行数据判断金叉/死叉，支持可配置 MA 周期（5/20）
  - 布尔告警阈值自动使用默认值：RSI 30/70，成交量 2x 均量
  - 所有数据获取包裹在 try/except 中，单只股票失败不影响整体

- `cli/market_scan.py`：市场快照扫描器
  - `market_scan(top, output)` Typer 命令
  - 通过 akshare `stock_zh_a_spot()` 获取全市场快照
  - 四个榜单：涨幅榜、跌幅榜、成交量榜、板块表现
  - 板块表现通过 `stock_board_industry_name_em()` 获取
  - 文本输出使用格式化表格（代码/名称/现价/涨跌幅），成交量自动转换单位（亿/万/手）
  - `_build_stock_entry()` 统一处理 sh/sz/bj 前缀代码剥离

### 注册
- `cli/main.py` 新增 `check-alerts` 和 `market-scan` 命令注册
- 注册模式：`app.command(name="check-alerts")(check_alerts)`

### 测试覆盖
- `tests/test_alerts.py`：37 个测试，8 个测试类
  - TestCheckPrice (5 tests)：价格触发/不触发、等值边界
  - TestCheckRSI (8 tests)：超买超卖默认/自定义阈值、等值边界
  - TestCheckVolumeSurge (5 tests)：激增触发、默认倍数、零均量、等值
  - TestCheckMACross (7 tests)：金叉/死叉/无交叉、字符串/布尔类型配置、行数不足、缺少 MA 列
  - TestCheckStockAlerts (7 tests)：集成测试、无告警、无效类型跳过、无数据时优雅降级
  - TestAlertConstants (3 tests)：常量验证
  - TestCLIRegistration (2 tests)：命令注册烟雾测试

- `tests/test_market_scan.py`：30 个测试，7 个测试类
  - TestSanitizeFloat (9 tests)：各种输入类型的 float 转换
  - TestBuildStockEntry (4 tests)：sh/sz/bj 代码剥离，缺失字段
  - TestDetermineMarketStatus (3 tests)：空 DF、无时间戳、有效时间戳
  - TestGetTopGainers (5 tests)：Top N、超额、空 DF、缺失列、NaN 值
  - TestGetTopLosers (3 tests)：跌幅排序、空 DF、缺失列
  - TestGetTopVolume (4 tests)：成交量排序、空 DF、缺失列、NaN 值
  - TestCLIRegistration (2 tests)：命令注册烟雾测试

### 验证结果
- 67/67 new tests passed ✅
- 59/59 existing tests passed ✅（无回归）
- 语法检查通过 ✅
- 导入验证通过 ✅
- CLI 命令注册验证通过 ✅

## Phase 4 — 持仓组合与回测命令 (2026-05-09)

### 新建文件
- `cli/portfolio.py`：持仓组合概览命令
  - `portfolio(date, output)` Typer 命令
  - `_fetch_spot_prices()` — 通过 akshare `stock_zh_a_spot()` 获取全市场实时行情，返回 `Dict[str, dict]`，key 为 6 位代码（自动剥离 sh/sz/bj 前缀）
  - `_build_portfolio_json()` + `_format_portfolio_text()` — JSON 和文本两种输出格式
  - 持仓数据通过 `PositionStateManager.get_all()` 读取
  - 盈亏计算复用 `calc_position_pnl()`
  - 集中度分析：top1_weight + top3_weight
  - 空持仓时返回完整 JSON 结构（非错误）

- `cli/backtest.py`：简化回测命令
  - `backtest(ticker, start_date, end_date, llm, deep_model, quick_model, debate_rounds, output)` Typer 命令
  - `_get_trading_days()` — 获取交易日列表，优先使用 A 股交易日历（`a_share_calendar.is_trade_day`），失败降级为工作日判断，日历调用异常时二次降级为工作日过滤
  - `_compute_performance()` — 计算胜率（买入信号占比）、累积收益率、平均持仓收益率
  - `_build_backtest_json()` + `_format_backtest_text()` — 两种输出格式
  - 逐日运行 `TradingAgentsGraph.propagate()`，错误不中断（continue 到下一日）
  - API 费用警告提示（⚠️ 警告消息）
  - 决策归一化：case-insensitive（Buy/buy/Hold/hold 等）

### 注册
- `cli/main.py` 新增 `portfolio` 和 `backtest` 命令注册
- 注册模式：`app.command(name="portfolio")(portfolio)`

### 测试覆盖
- `tests/test_portfolio.py`：17 个测试，3 个测试类
  - TestBuildPortfolioJson (5 tests)：空持仓、单持仓、多持仓、JSON可序列化、pnl_pct None 处理
  - TestFormatPortfolioText (5 tests)：空持仓、单持仓、多持仓、集中度、零价格
  - TestFetchSpotPrices (7 tests)：akshare 不可用、返回None/空DF/有效数据、缺失字段、异常、非数字代码过滤

- `tests/test_backtest.py`：19 个测试，6 个测试类
  - TestGetTradingDays (5 tests)：工作日范围、周末排除、单日、日期顺序、日历不可用降级
  - TestComputePerformance (5 tests)：空结果、全买入、混合决策、无returns字段、零返回值过滤
  - TestBuildBacktestJson (4 tests)：基础输出、含错误、JSON可序列化、决策大小写不敏感
  - TestFormatBacktestText (4 tests)：基础输出、含错误、全卖出、绩效段落
  - TestCLIRegistration (1 test)：命令注册烟雾测试

### 关键设计决策
- akshare 懒加载：`try/except ImportError` + `_AKSHARE_AVAILABLE` 标志
- 回测交易日获取三层降级：日历成功→工作日过滤→日历函数异常→工作日过滤
- 回测绩效指标为简化估算（无未来价格数据，占位符 raw_return=0.0）
- JSON 输出使用 `round()` 精度控制，确保可序列化
- 文本输出使用简单 `print()` 格式化表格，无 Rich UI
- `typer.Exit(code=1)` 用于参数验证错误

### 验证结果
- 36/36 新测试通过 ✅
- 361/361 已有测试通过 ✅（无回归）
- 语法检查通过 ✅
- 导入验证通过 ✅
- CLI --help 正确展示 ✅

