# 知识消费实施计划 — 经验记录

## 代码库模式

### 文件结构
- `tradingagents/dataflows/akshare.py` — 所有 A 股数据 API，含 `_load_ohlcv_akshare()` 缓存（~5年 OHLCV）
- `tradingagents/graph/trading_graph.py` — `propagate()` 主流程，`TradingAgentsGraph` 类
- `tradingagents/agents/utils/agent_states.py` — `AgentState` 定义（LangGraph MessageState）
- `tradingagents/agents/utils/memory.py` — `TradingMemoryLog` 类，memory 管理
- `tradingagents/analysis_archive.py` — `AnalysisArchive` 类，文件系统存档
- `tradingagents/default_config.py` — `DEFAULT_CONFIG` 字典
- `cli/` — 各个 CLI 命令

### AgentState 模式
- 扩展自 `MessagesState`（LangGraph）
- 使用 `Annotated[type, "description"]` 注解
- 通过 `state.get("field", default)` 安全访问

### prompt 注入模式
- Trader: `create_trader()` 中 `trader_node()`，注入 position_note 到 system message
- PM: `create_portfolio_manager()` 中 `portfolio_manager_node()` 直接拼接到 prompt
- RM: `create_research_manager()` 中 `research_manager_node()` 直接拼接到 prompt

### 缓存模式
- `_load_ohlcv_akshare()` 使用 CSV 文件缓存 ~5 年 OHLCV 数据
- `get_current_price()` 使用内存 TTL 缓存（30秒）
- 基准指数数据完全无缓存
- CLI 各命令独立调用 `ak.stock_zh_a_spot()`，不共享缓存

## Phase 0 — 统一缓存层 (DataCache)

### 实现记录 (2026-05-09)

**创建文件**: `tradingagents/dataflows/cache.py`

`DataCache` 类提供基于文件系统的命名空间缓存：
- `benchmark/`、`fundamentals/` — 磁盘（CSV/JSON），无 TTL 过期
- `spot/` — 内存（`_SpotCache` 内部类），默认 30 秒 TTL
- 使用 `tempfile.mkstemp` + `os.replace` 实现原子写入
- `_SpotCache` 使用 `threading.Lock` 保证线程安全
- DataFrame 写为 CSV（`index=False`），dict/list 写为 JSON（`ensure_ascii=False`）
- 损坏文件静默返回 `None`（视为缓存未命中）
- `invalidate(namespace, key=None)` 递归删除整个命名空间目录

**修改文件**: `tradingagents/default_config.py`

新增 18 个配置键，覆盖 Phase 0-5：
- 知识注入预算：`knowledge_token_budget: 25000`
- 去重与增量：`skip_if_analyzed_today`、`incremental_window_days`
- Phase 0 开关：`enable_context_assembly`、`enable_archive_first_cache`
- 置信度标签：`confidence_tags_enabled`、`confidence_threshold_inject: "CONFLICTING"`
- Graphify：`graphify_auto_sync`、`graphify_analysis_graph_path`
- MCP 服务：`mcp_server_enabled`、`mcp_server_port`
- Wiki：`wiki_output_dir`、`wiki_auto_generate`
- 存档目录：`analysis_archive_dir`（默认 `~/.tradingagents/analysis-archive`）

## Phase 0.2–0.4 — 缓存应用到代码库 (2026-05-09)

### Phase 0.2: 基准指数缓存

**修改文件**: `tradingagents/graph/trading_graph.py` → `_get_ashare_benchmark_close_series()`

- 使用 `DataCache.get_or_fetch()` 替换直接 `ak.stock_zh_index_daily()` 调用
- 命名空间 `"benchmark"`，key 格式 `{ticker}_{start}_{end}.csv`
- fetcher lambda 下载全量数据，缓存后按日期范围过滤
- DataFrame 从 CSV 读取后需 `pd.to_datetime()` 转换日期列（CSV 存为字符串）
- 返回类型保持 `df["close"].values`（numpy array）

### Phase 0.3: 消除 4 个冗余 akshare 调用

**修改文件**: `tradingagents/graph/trading_graph.py`

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| `_get_ashare_close_series()` | `ak.stock_zh_a_daily()` | `_load_ohlcv_akshare()` + 日期过滤 |
| `_run_graph()` prev_close 循环 | 最多 14 次 `ak.stock_zh_a_daily()` | `_load_ohlcv_akshare()` 一次 + `Date < trade_date` 过滤 |
| `_get_analysis_day_close()` | `ak.stock_zh_a_daily()` | `_load_ohlcv_akshare()` + `Date == target` 匹配 |

关键注意事项:
- `_load_ohlcv_akshare(symbol, curr_date)` 自动过滤 `Date <= curr_date`，所以找前一日收盘价需额外过滤 `Date < trade_date`
- `_load_ohlcv_akshare` 内部已有 CSV 文件缓存（5 年跨度），无需再次缓存
- 列名使用大写英文：`Date`, `Open`, `Close` 等（Sina 源英文字段名）
- 日期比较使用 `pd.Timestamp` 避免类型不匹配

### Phase 0.4: CLI 行情缓存统一

4 个 CLI 文件修改为使用 `get_current_price()`（含 30s TTL）:

| 文件 | 函数 | 修改方式 |
|------|------|----------|
| `cli/portfolio.py` | `_fetch_spot_prices()` | 接收 tickers 参数，逐个调用 `get_current_price()` 并解析 Markdown |
| `cli/scan.py` | `_get_spot_quote()` | 调用 `get_current_price()` 替代 `ak.stock_zh_a_spot()` |
| `cli/alerts.py` | `_get_spot_price()` | 调用 `get_current_price()` 并解析价格 |
| `cli/market_scan.py` | `_fetch_spot_df()` | 使用 `DataCache.get_or_fetch("spot", ...)` 30s TTL |

关键注意事项:
- `get_current_price()` 返回 Markdown 格式化字符串，CLI 需要解析提取结构化数据
- `market_scan.py` 需要完整 DataFrame（全市场排名），使用 DataCache.spot 内存缓存，和 get_current_price 的 `_spot_cache` 独立运作（两个 30s TTL 缓存）
- `portfolio.py` 需要 `List` 类型注解（已有 `from typing import List`）
- `scan.py` 的 `_get_close_price()` 保留直接 `ak.stock_zh_a_daily()` 调用（不在本次 scope 内）

## Phase 0.5 — Graphify 自动同步 (2026-05-09)

**修改文件**: `cli/batch.py`, `cli/scan.py`

创建 `_graphify_auto_sync(config)` 辅助函数在 `cli/batch.py`：
- 用 `subprocess.run(["graphify", "update", "."], timeout=60)` 执行
- 受 `config["graphify_auto_sync"]` 开关控制（默认 True）
- `FileNotFoundError` → `logger.info`（静默跳过，graphify 未安装）
- 其他异常 → `logger.warning`（不崩溃）
- 返回码非零 → `logger.warning`（记录 stderr）

调用点插入位置（均在成功存档之后、异常处理/输出之前）：
| 文件 | 函数 | 行号 |
|------|------|------|
| `cli/batch.py` | `batch()` | 在 `save_to_archive()` 与 `except` 之间 |
| `cli/scan.py` | `scan_watchlist()` | 在 archive 循环与 `if output_mode` 之间 |
| `cli/scan.py` | `morning_scan()` | 在 archive 循环与 `# --- Notification ---` 之间 |
| `cli/scan.py` | `evening_review()` | 在 archive 循环与 `# Calculate P&L` 之间 |

`cli/scan.py` 通过 `from cli.batch import _graphify_auto_sync` 复用辅助函数。

## Phase 1 — 知识注入流水线 (2026-05-09)

### 创建文件: `tradingagents/graph/context_assembly.py`

`ContextAssembler` 类在运行开始时收集所有历史知识：
- 通过 `AnalysisArchive.list()` 查询存档分析（限制 5 条）
- 通过 `TradingMemoryLog.get_past_context()` 查询过往决策
- 通过 `AnalysisArchive.summary()` 查询信号分布（30 天）
- 从记忆日志条目中提取跨标的教训
- 通过 `DataCache` 快照缓存状态

置信度系统（纯规则，无 LLM 调用）：
- `CONFIRMED`：过去 30 天内 3 条以上同向信号
- `SINGLE`：仅发现 1 条分析
- `CONFLICTING`：最近有混合买入/卖出信号
- `STALE`：最新分析距今超过 90 天
- `DERIVED`：跨标的模式（保留供将来使用）

Token 预算控制：`_apply_budget()` 近似计算 1 token ≈ 4 字符，按优先级截断：
`cache_status → lessons → ticker_signals → past_decisions → archived_analyses`

### 修改文件: `tradingagents/agents/utils/agent_states.py`

新增 `knowledge_context: Annotated[dict, "..."] = {}` 字段，位于 `past_context` 之后。

### 修改文件: `tradingagents/graph/trading_graph.py`

在 `_run_graph()` 中，`create_initial_state()` 之前：
- 通过 `config["enable_context_assembly"]`（默认 True）控制的开关
- 实例化 `ContextAssembler(self.config)`，调用 `assembler.assemble()`
- 将结果传递给 `create_initial_state(knowledge_context=...)`
- 在异常时优雅降级（`logger.warning`）

### 修改文件: `tradingagents/graph/propagation.py`

`create_initial_state()` 新增 `knowledge_context: dict = None` 参数，
在返回的字典中设置 `"knowledge_context": knowledge_context or {}`。

### 修改文件: `tradingagents/agents/trader/trader.py`

在 `position_context` 之后注入历史交易经验：
- 从 `state.get("knowledge_context", {})` 中提取 `past_decisions`
- 格式化 **Historical Trading Experience** 章节
- 包含置信度标签摘要：整体、分布
- 注入到用户消息内容

### 修改文件: `tradingagents/agents/managers/research_manager.py`

新增 **Historical Context** 章节，包含来自 `knowledge_context` 的 `past_decisions`。

### 修改文件: `tradingagents/agents/managers/portfolio_manager.py`

新增 **Recent Analysis History** 章节，展示来自 `knowledge_context` 的已存档分析及其决策。

### 测试: `tests/test_context_assembly.py`（28 个测试）

涵盖：assemble() 结构、空存档、带数据的存档、Token 预算截断、
信号摘要、教训提取、置信度过滤、模块级辅助函数。

### 测试: `tests/test_confidence.py`（18 个测试）

涵盖：CONFIRMED/SINGLE/CONFLICTING/STALE 标签计算、
阈值过滤、标签映射、信号分布。

### 测试: `tests/test_knowledge_injection.py`（14 个测试）

涵盖：Trader/RM/PM 提示注入、空上下文的优雅降级、
AgentState knowledge_context 字段验证。

### 关键决策
- 置信度计算为纯规则驱动，无需 LLM 调用（测试更简单，速度更快）
- prompt 注入为**仅追加**——不修改现有提示，仅在章节后附加历史记录
- 所有新功能受配置开关控制（向后兼容）
- Token 预算约简为 1 token ≈ 4 字符（简单且可测试）
- 单条陈旧条目（>90d）会触发 STALE，而非 SINGLE

## Phase 2 — 三级缓存检查链 (2026-05-09)

### 实现文件: `tradingagents/graph/trading_graph.py`

在 `propagate()` 方法中实现三级缓存检查流水线：

**Level 1 — 同日同标的缓存跳过** (lines ~383-399):
- 受 `config["skip_if_analyzed_today"]` 控制（默认 False）
- 使用 `AnalysisArchive._build_entry_id()` 构建 "batch" 类型的条目 ID
- 缓存命中时直接返回 `(cached_state_dict, decision_string)`
- `cached_state_dict` 包含 `final_trade_decision`、`_cached=True` 等字段
- 返回类型与正常 `propagate()` 返回值兼容：`(dict, str)`

**Level 2 — 增量模式窗口检查** (lines ~401-410):
- 受 `config["incremental_window_days"]` 控制（默认 0，禁用）
- 使用 `archive.list(ticker=..., date_from=..., limit=1)` 查询最近分析
- 找到时设置 `self._incremental_mode = True` 和 `self._recent_analyses`
- 每次 `propagate()` 调用时重置标志（lines 379-381）

**Level 3 — 分析后存档保存** (lines ~433-444):
- 受 `config["enable_archive_first_cache"]` 控制（默认 True）
- 在 `_run_graph()` 成功后调用 `save_to_archive()`（来自 `cli/archive.py`）
- 异常时 `logger.warning` 静默降级

**增量模式注入** (lines ~491-495):
- 在 `_run_graph()` 中，如 `_incremental_mode` 为 True，将 `_incremental_mode` 和 `_recent_analyses` 注入 `init_agent_state`

### 测试文件: `tests/test_cache_chain.py` (17 个测试)

涵盖：
- Level 1: skip_if_analyzed_today 开关、缓存命中、不同标的、顶层 decision 字段
- Level 2: 窗口禁用、窗口启用有/无近期分析、标志重置
- 存档保存: 成功后保存、异常处理、禁用后不保存
- 配置默认值: 所有键存在、默认值安全
- 向后兼容: 默认行为不变、propagate 返回类型不变、Level 1 返回类型匹配

### 关键决策
- `save_to_archive` 的 result dict 使用 `{"decision": ..., "summary": ..., "analysts": ["batch"]}`
- 存档中缓存的条目按 `request/analysis/final_decision` 路径查找（非顶层 `decision`）
- `AnalysisArchive.list()` 的 `date_from` 使用 `>=` 过滤——查找的是分析日期 >= trade_date 的条目
- 所有 import 使用延迟导入（函数内 `from ... import ...`），避免启动时循环依赖
- 每次 `propagate()` 开始时重置 `_incremental_mode` / `_recent_analyses` 标志

## Phase 4 — MCP Server + Graph Merge (2026-05-09)

### 实现记录

**创建文件**: `tradingagents/knowledge/mcp_server.py`

`KnowledgeMCPServer` 类通过 stdio JSON-RPC 2.0 暴露分析知识库为 6 个 MCP 工具：
- `query_analysis`: 按 ticker/日期/关键词查询分析记录
- `get_ticker_signals`: 信号分布 + 置信度评估
- `search_patterns`: 关键词搜索并按决策方向分组
- `get_lessons`: 从 TradingMemoryLog 提取跨标的教训
- `get_confidence`: 使用 ContextAssembler._compute_confidence 计算置信度标签
- `get_graph_neighbors`: 引用加载的知识图谱 JSON，查找相邻节点

**关键设计决策**：
- MCP 传输：stdio 模式（非 HTTP/TCP），一行 JSON-RPC 请求 → 一行 JSON-RPC 响应
- 无外部依赖：MCP 协议是纯 JSON-RPC，无需 `mcp` 库
- `tool_get_lessons` 内部创建独立的 `TradingMemoryLog()` 实例（不依赖 config）
- `tool_get_confidence` 延迟创建 `ContextAssembler` 实例复用规则引擎
- `tool_get_graph_neighbors` 仅支持 depth=1（一阶邻居）
- 未知工具返回 `isError: True`；未知方法返回 `{"error": ...}`

**Graph Merge 工具** (`merge_graphs`):
- 按节点 ID 去重合并两个 graphify JSON 文件
- 共享节点标记 `merged_from: ["code", "analysis"]`
- 边按 (source, target, type) 三元组去重
- 输出包含 `_meta` 元数据

**安装文件**: `cli/mcp.py`
- `serve()` 函数从环境变量 `TRADINGAGENTS_ARCHIVE_DIR` 或配置中读取存档目录
- 在 `cli/main.py` 中以 `app.command(name="mcp")(mcp_serve)` 注册

**测试**: `tests/test_mcp_server.py` (26 个测试)
- TestMCPServerInit (3): 仅 archive、带 graph path、不存在的 graph path
- TestMCPTools (16): query_analysis x5、ticker_signals x2、search_patterns x2、lessons x2、confidence x2、graph_neighbors x3
- TestGraphMerge (2): 合并两个图、空图合并
- TestStdIOServe (5): tools/list 路由、initialize、tool_call、tool_call_error、unknown_method

### 关键决策
- CLI 命令为 `tradingagents mcp --archive-dir ... --graph-path ...`（单命令，非子命令组）
- MCP 服务读取 stdin 直到 EOF（适合 MCP 客户端进程管理）
- `TradingMemoryLog()` 无参实例化使用默认 memory log 路径

## Phase 3 — Wiki 导航 + Lessons 回路 (2026-05-09)

### 创建文件: `tradingagents/knowledge/__init__.py`

空的包初始化文件。

### 创建文件: `tradingagents/knowledge/wiki_generator.py`

`WikiGenerator` 类提供从分析存档生成 agent 可导航 Markdown 索引的功能：

- `generate(ticker=None)` — 全量或单股票生成
- `incremental_update(new_entries)` — 增量更新
- `_build_index(entries)` — 构建 index.md
- `_build_ticker_page(ticker, entries)` — 构建单股票详情页
- `_build_lessons_page(lessons)` — 构建跨股票经验页
- `_deduplicate_lessons(lessons)` — 7 天窗口去重
- `_compute_confidence_tag(ticker, entries)` — 简化的置信度标签计算
- `_extract_all_lessons(entries)` — 从存档提取 lessons
- `_extract_patterns(entries)` — 从 tags 提取反复出现的模式

### 创建文件: `cli/wiki.py`

三个 CLI 命令：
- `tradingagents wiki generate [--ticker] [--output-dir]`
- `tradingagents wiki show <TICKER> [--output-dir]`
- `tradingagents wiki list [--output-dir]`

使用 Typer 子命令模式，与 `cli/archive.py` 一致。

### 修改文件: `cli/main.py`

添加 `from cli.wiki import wiki_app` 和 `app.add_typer(wiki_app, name="wiki")`。

### 创建文件: `tests/test_wiki.py` (28 个测试)

涵盖：
- `_build_index`: 空归档、单词条、多 ticker、表格格式、置信度标签、已知名称、未知名称、按数量排序、命令提示
- `_build_ticker_page`: 基本结构、信号时间线表格、置信度摘要、信号分布、最近 5 条、返回链接
- `generate()`: 创建索引文件、创建股票页、创建 lessons 页、空归档优雅处理、单股票生成、返回路径
- `incremental_update`: 无新条目、新条目更新、重新生成索引
- `_compute_confidence_tag`: 空条目、单条目、CONFIRMED、CONFLICTING、STALE
- `_compute_signal_distribution`: 基本分布计算

### 创建文件: `tests/test_lessons.py` (17 个测试)

涵盖：
- `_extract_all_lessons`: 提取reasoning、提取tags、空归档、跳过无内容条目、按日期排序
- `_deduplicate_lessons`: 同ticker 7天内去重、超7天保留、不同ticker保留、空列表、无ticker保留
- `_build_lessons_page`: 空lessons、单条lesson、多条lesson、长文本截断、评级显示、返回链接

### 关键决策
- WikiGenerator 纯规则驱动，零 LLM 调用
- Markdown 直接用 f-string 构建，不使用模板引擎（如 jinja2）
- 置信度计算复用 `CONFIDENCE_LEVELS`（从 context_assembly 导入），逻辑简化
- 已知 A 股名称硬编码在 `_get_ticker_name()` 中（可扩展）
- Lessons 去重使用 7 天窗口，遵循 ADR-010 设计
- WikiGenerator 与 AnalysisArchive 解耦，可独立测试
- 所有测试使用临时目录（tmp_path），不污染真实数据
- 总计 45 个测试，全部通过
