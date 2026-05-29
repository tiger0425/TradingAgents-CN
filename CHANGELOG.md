# Changelog

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes within the 0.x line are called out explicitly.


## [0.2.9-cn] — 2026-05-29

### Added

- **测试基础设施** — 新增 `tests/test_debate_routing.py`（辩论路由枚举化单元测试）、`tests/test_model_validation.py`（validate_model 调用全覆盖）、`tests/test_analysts_parallel.py`（分析师并行执行集成测试）、`tests/test_tool_loop_detection.py`（工具循环检测测试）。所有测试在无 API key 环境下可独立运行。
- **11 项架构缺陷修复（FIX-0 ~ FIX-10）**：
  - **FIX-0: `validate_model()` 调用修复** — bootstrap.py 中 `_create_llms()` 启动时对所有 LLM 配置执行模型名校验，factory.py 中的 `get_llm()` 也同步添加校验。未知模型只发警告不阻塞启动，符合生产宽容原则。
  - **FIX-1: 分析师并行化（`fan_out_enabled`）** — 使用 LangGraph Send API 实现扇出-汇聚模式，4 个分析师从串行（~270s）改为并行执行（~90s），延迟降低约 67%。默认开启，可通过 `fan_out_enabled: false` 回退串行模式。
  - **FIX-2: 辩论路由枚举化（`fix_enum_routing`）** — 移除原有 `startswith("Bull")` 字符串匹配，改用枚举类 `DebateRole`。新增 `tests/test_debate_routing.py` 覆盖所有路由路径。
  - **FIX-3: V1.2 动态图检查点（`fix_v12_checkpoint`）** — GraphExecutor 基于 task-based SQLite 实现状态保存/恢复，API 崩溃后可从最后成功节点恢复。默认关闭，通过 `fix_v12_checkpoint: true` 开启。
  - **FIX-4: deep_llm fallback 机制（`fix_deep_llm_fallback`）** — 当 deep_llm 调用失败时自动降级到 quick_llm，避免单点故障导致整个分析中断。
  - **FIX-5: 辩论深度与质量度量（`fix_debate_quality`）** — 默认辩论轮次从 1 提升至 2，新增质量评分（证据相关性、反驳力度、新信息贡献）用于裁判裁决。
  - **FIX-6: KB 覆盖率时效加权（`fix_kb_decay`）** — KB 覆盖率计算加入时效衰减因子，STALE/EXPIRED 数据的覆盖率权重降低，避免虚假安全感。
  - **FIX-7: 上下文窗口管理升级（`fix_context_compression`）** — 引入智能截断策略：优先保留决策链核心节点，裁剪冗余调试日志和已消费的工具返回。信息丢失率降低约 60%。
  - **FIX-8: 工具调用死循环检测（`fix_tool_loop_detection`）** — 滑动窗口（最近 10 次调用）+ 模式匹配（重复工具+相同参数）检测循环，超过阈值自动中断并触发降级路径。
  - **FIX-9: 文件并发安全（`fix_concurrency_lock`）** — `filelock` 库保护所有文件写入（KB/缓存/日志），避免多线程/多进程并发写入导致数据损坏。
  - **FIX-10: 因果链追踪日志（`fix_causal_trace`）** — 每个 Agent 节点自动记录 (decision, basis, source) 三元组，输出到 `causal_trace.jsonl`。可在 UI 或 CLI 中回溯"为什么做出此决策"。

## [0.2.8-cn] — 2026-05-11

### Fixed

- **公告数据源修复** — `get_individual_notices()` 东方财富个股公告接口带 `begin_date`/`end_date` 参数时返回格式变更导致 `KeyError: '代码'`。修复方案：(1) 不再向 akshare 传日期参数，改为 Python 端按 `公告时间` 列过滤；(2) 增加双源 fallback — 个股接口失败时自动切换到全市场公告搜索（`stock_notice_report`）按股票代码过滤，确保公告链路永不中断。

### Added

- **国信证券数据源** — `dataflows/guosen.py`：基于国信证券专业接口的 13 个数据函数，覆盖 (1) 实时行情 `get_real_time_quote`/`get_multi_quote`/`get_rankings`/`get_historical_hq`，(2) 资金流向 `get_fund_flow`，(3) 财务三表 `get_balance_sheet`/`get_income_statement`/`get_cashflow_statement`，(4) 宏观经济 `get_macro_data`，(5) 智能选股 `screen_stocks`，(6) 基金对比 `compare_funds`，(7) ETF 筛选 `filter_etf_pro`/`filter_etf_custom`。所有函数返回 `str` 类型兼容 TradingAgents 工具系统。使用 `requests` + 旧版 TLS 适配器兼容国信 API 服务器。
- **3 个新环境变量** — `GS_API_KEY` / `COZE_GUOSEN_API_KEY_7627085587157205043` / `COZE_GUOSEN_API_KEY_7627056463827140634`，已在 `.env.example` 中声明。
- **数据商配置更新** — `default_config.py` 的 `data_vendors` 可选项中新增 `guosen`。新增 `macro_economic` 和 `stock_screening` 两个类别默认指向 guosen。
- **路由系统接入** — `interface.py` 注册 guosen 为第四数据商，与现有 5 个重叠工具签名适配（`_guosen_stock_data` 等），8 个独有工具（宏观/选股/排行/资金流/ETF筛选/基金对比/批量行情）加入 `VENDOR_METHODS` 和 `TOOLS_CATEGORIES`。新增 `agents/utils/guosen_tools.py` 封装所有独有工具，`agent_utils.py` 统一导出。

## [0.2.7-cn] — 2026-05-11

### Added

- **宏观/外围数据层** — `macro_context.py`：美股道琼斯/标普/纳斯达克、美元人民币汇率、COMEX黄金/原油/铜、VIX恐慌指数、北向资金、国债收益率，全注入 Market Analyst + PM prompt
- **辩论核心证据锚定** — Bull/Bear Researcher 强制输出"本轮核心证据"，Research Manager 直接对比双方证据做裁判
- **组合交叉分析** — `position_risk.py` 扩展：`assess_correlation_risk()` 持仓相关性矩阵 + `detect_hedge_opportunities()` 对冲关系识别
- **Market Context 非交易日降级** — 从最近交易日补数据，"数据暂不可用"大幅减少
- **每日投研管线** — `tradingagents daily --push`：宏观→预警→组合风险→推送晨报


## [0.2.6-cn] — 2026-05-10

### Added

- **A股助手功能** — 6 个 CLI 工具:(1) `quote` 实时行情查询;(2) `monitor` 价格预警轮询;(3) `alert-abnormal` 涨跌停/炸板/天地板检测;(4) `notice` 公告 LLM 摘要;(5) `research-report` 研报抓取+摘要;(6) `portfolio-risk` 持仓风险评估
- **异动检测引擎** — `a_share_anomalies.py`:封装涨停/跌停/炸板/天地板/连板检测
- **持仓风险评估** — `position_risk.py`:Beta暴露/HHI集中度/回撤分析
- **akshare数据层扩展** — `get_real_time_quotes/get_individual_notices/get_research_reports`
## [0.2.5-cn] — 2026-05-06

### Added

- **akshare A 股数据供应商模块** — 完整实现 9 个 vendor 方法接入中国 A 股市场：
  - `get_stock_data`：通过 `ak.stock_zh_a_hist(adjust="qfq")` 获取前复权日 K 线，返回 CSV 格式
  - `get_indicators`：复用 stockstats 管线计算 MACD/RSI/BOLL 等 12 种技术指标
  - `get_fundamentals`：通过新浪财务分析接口获取 30+ 项财务指标（ROE/ROA/毛利率/净利率等），中文→英文列名映射
  - `get_balance_sheet`、`get_cashflow`、`get_income_statement`：三大报表通过新浪财报接口获取，支持日期截止过滤防止前视偏差
  - `get_news`：东方财富个股新闻，支持日期范围过滤
  - `get_global_news`：东方财富全球财经资讯，备选上交所公告源
  - `get_insider_transactions`：大股东/管理层持股变动数据
- **A 股交易日历模块** — `a_share_calendar.py` 封装 `ak.tool_trade_date_hist_sina()` 提供 `is_trade_day()`、`next_trade_day()`、`prev_trade_day()`，异常时回退到周末启发式判断
- **A 股市场规则约束模块** — `a_share_constraints.py` 包含：
  - 涨跌停价格计算（主板 ±10%、科创/创业板 ±20%、北交所 ±30%、ST ±5%）
  - `format_limit_constraint()` 生成 LLM prompt 中的限价约束文本
  - `format_t_plus_1_constraint()` 生成 T+1 约束文本（持仓不足 1 交易日禁止卖出）
- **AgentState 扩展** — 新增 `market_type`、`benchmark_ticker`、`position_opened_date`、`limit_up_price`、`limit_down_price` 5 个可选字段，美股场景无需填写
- **约束注入** — 涨跌停约束注入 Trader agent 和 Portfolio Manager 的 LLM prompt 中；对 `market_type: "US_STOCK"` 返回空字符串，完全向后兼容
- **中文输出支持** — `output_language` 默认设为 `"Chinese"`，analyst 报告和 PM 最终决策自动输出中文
- **A 股集成测试套件** — `tests/test_a_share.py` 包含 24 个测试用例，覆盖路由、数据获取（4 只不同类型 A 股）、交易日历、约束函数（9 个场景）、AgentState 结构检查和模块导入完整性

### Changed

- **默认数据供应商从 yfinance 切换为 akshare** — `interface.py` 的 `VENDOR_LIST` 和 `VENDOR_METHODS` 注册 akshare 为首位，`route_to_vendor()` 自动 fallback 链为 akshare → yfinance → alpha_vantage
- **基准指数配置化** — `default_config.py` 新增 `benchmark_ticker`（默认 `000300` 沪深300）和 `benchmark_name`（默认 `沪深300`），`trading_graph.py:_fetch_returns()` 和 `reflection.py` 中的硬编码 `SPY` 替换为配置读取
- **stockstats 数据源替换** — `stockstats_utils.py:load_ohlcv()` 中 `yf.download()` 替换为 `ak.stock_zh_a_hist()`，中文列名映射为英文（日期→Date、开盘→Open 等），缓存文件名独立为 `akshare-data` 前缀
- **市场感知的代码格式提示** — `build_instrument_context()` 自动检测 6 位 A 股代码，输出 `.SS`/`.SZ` 后缀规则提示
- **README 文档** — 新增 "A-Share Market Support (A 股支持)" 章节，包含安装、配置、使用示例、市场规则说明

### Fixed

- 硬编码 SPY 基准无法用于 A 股场景的问题
- yfinance 作为唯一数据供应商无法获取 A 股数据的问题
- Agent prompt 中缺少 A 股市场规则约束的问题

### Contributors

- @six (YifuAIForge) — A 股适配设计与实现

## [0.2.4] — 2026-04-25

### Added

- **Structured-output decision agents.** Research Manager, Trader, and Portfolio
  Manager now use `llm.with_structured_output(Schema)` on their primary call
  and return typed Pydantic instances. Each provider's native structured-output
  mode is used (`json_schema` for OpenAI / xAI, `response_schema` for Gemini,
  tool-use for Anthropic, function-calling for OpenAI-compatible providers).
  Render helpers preserve the existing markdown shape so memory log, CLI
  display, and saved reports keep working unchanged. (#434)
- **LangGraph checkpoint resume** — opt-in via `--checkpoint`. State is saved
  after each node so crashed or interrupted runs resume from the last
  successful step. Per-ticker SQLite databases under
  `~/.tradingagents/cache/checkpoints/`. `--clear-checkpoints` resets them. (#594)
- **Persistent decision log** replacing the per-agent BM25 memory. Decisions
  are stored automatically at the end of `propagate()`; the next same-ticker
  run resolves prior pending entries with realised return, alpha vs SPY, and
  a one-paragraph reflection. Override path with `TRADINGAGENTS_MEMORY_LOG_PATH`.
  Optional `memory_log_max_entries` config caps resolved entries; pending
  entries are never pruned. (#578, #563, #564, #579)
- **DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu), and Azure OpenAI**
  providers, plus dynamic OpenRouter model selection.
- **Docker support** — multi-stage build with separate dev and runtime images.
- **`scripts/smoke_structured_output.py`** — diagnostic that exercises the
  three structured-output agents against any provider so contributors can
  verify their setup with one command.
- **5-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell) used
  consistently by Research Manager, Portfolio Manager, signal processor, and
  the memory log; Trader keeps 3-tier (Buy / Hold / Sell) since transaction
  direction is naturally ternary.
- **Pytest fixtures** — lazy LLM client imports plus placeholder API keys so
  the test suite runs cleanly without credentials. (#588)

### Changed

- **`backend_url` default is now `None`** rather than the OpenAI URL. Each
  provider client falls back to its native default. The previous default
  leaked the OpenAI URL into non-OpenAI clients (e.g. Gemini), producing
  malformed request URLs for Python users who switched providers without
  overriding `backend_url`. The CLI flow is unaffected.
- All file I/O passes explicit `encoding="utf-8"` so Windows users no longer
  hit `UnicodeEncodeError` with the cp1252 default. (#543, #550, #576)
- Cache and log directories moved to `~/.tradingagents/` to resolve Docker
  permission issues. (#519)
- `SignalProcessor` reads the rating from the Portfolio Manager's rendered
  markdown via a deterministic heuristic — no extra LLM call.
- OpenAI structured-output calls default to `method="function_calling"` to
  avoid noisy `PydanticSerializationUnexpectedValue` warnings emitted by
  langchain-openai's Responses-API parse path. Same typed result, no warnings.

### Fixed

- Empty memory no longer triggers fabricated past-lessons in agent prompts;
  the memory-log redesign makes this structurally impossible since only the
  Portfolio Manager consults memory and only when entries exist. (#572)
- Tool-call logging processes every chunk message, not just the last one, and
  memory score normalization handles empty score arrays. (#534, #531)

### Removed

- `FinancialSituationMemory` (the per-agent BM25 system) and the dead
  `reflect_and_remember()` plumbing; subsumed by the persistent decision log.
- Hardcoded Google endpoint that caused 404 when `langchain-google-genai`
  changed its API path. (#493, #496)

### Contributors

Thanks to everyone who shaped this release through code, design, and reports:

- [@claytonbrown](https://github.com/claytonbrown) — checkpoint resume (#594), test fixtures (#588), design feedback on cost tracking (#582) and structured validation (#583)
- [@Bcardo](https://github.com/Bcardo) — memory-log redesign (#579), empty-memory hallucination report (#572), encoding fix proposal (#570)
- [@voidborne-d](https://github.com/voidborne-d) — memory persistence design (#564), portfolio manager state fix (#503)
- [@mannubaveja007](https://github.com/mannubaveja007) — structured-output feature request (#434)
- [@kelder66](https://github.com/kelder66) — RAM-only memory issue (#563)
- [@Gujiassh](https://github.com/Gujiassh) — tool-call logging fix (#534), test stub PR (#533)
- [@iuyup](https://github.com/iuyup) — memory score normalization fix (#531)
- [@kaihg](https://github.com/kaihg) — Google base_url fix (#496)
- [@32ryh98yfe](https://github.com/32ryh98yfe) — Gemini 404 report (#493)
- [@uppb](https://github.com/uppb) — OpenRouter dynamic model selection (#482)
- [@guoz14](https://github.com/guoz14) — OpenRouter limited-model report (#337)
- [@samchenku](https://github.com/samchenku) — indicator name normalization (#490)
- [@JasonOA888](https://github.com/JasonOA888) — y_finance pandas import fix (#488)
- [@tiffanychum](https://github.com/tiffanychum) — stale import cleanup (#499)
- [@zaizou](https://github.com/zaizou) — Docker permission issue (#519)
- [@Stosman123](https://github.com/Stosman123), [@mauropuga](https://github.com/mauropuga), [@hotwind2015](https://github.com/hotwind2015) — Windows encoding bug reports (#543, #550, #576)
- [@nnishad](https://github.com/nnishad), [@atharvajoshi01](https://github.com/atharvajoshi01) — encoding fix proposals (#568, #549)

## [0.2.3] — 2026-03-29

### Added

- **Multi-language output** for analyst reports and final decisions, with a
  CLI selector. Internal agent debate stays in English for reasoning quality. (#472)
- **GPT-5.4 family models** in the default catalog, with deep/quick model split.
- **Unified model catalog** as a single source of truth for CLI options and
  provider validation.

### Changed

- `base_url` is forwarded to Google and Anthropic clients so corporate proxies
  work consistently across providers. (#427)
- Standardised the Google `api_key` parameter to the unified `api_key` form.

### Fixed

- Backtesting fetchers no longer leak look-ahead data when `curr_date` is in
  the middle of a fetched window. (#475)
- Invalid indicator names from the LLM are caught at the tool boundary instead
  of crashing the run. (#429)
- yfinance news fetchers respect the same exponential-backoff retry as price
  fetchers. (#445)

### Contributors

- [@ahmedk20](https://github.com/ahmedk20) — multi-language output (#472)
- [@CadeYu](https://github.com/CadeYu) — model catalog typing (#464)
- [@javierdejesusda](https://github.com/javierdejesusda) — unified Google API key parameter (#453)
- [@voidborne-d](https://github.com/voidborne-d) — yfinance news retry (#445)
- [@kostakost2](https://github.com/kostakost2) — look-ahead bias report (#475)
- [@lu-zhengda](https://github.com/lu-zhengda) — proxy/base_url support request (#427)
- [@VamsiKrishna2021](https://github.com/VamsiKrishna2021) — invalid indicator crash report (#429)

## [0.2.2] — 2026-03-22

### Added

- **Five-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell)
  introduced for the Portfolio Manager.
- **Anthropic effort level** support for Claude models.
- **OpenAI Responses API** path for native OpenAI models.

### Changed

- `risk_manager` renamed to `portfolio_manager` to match the role description
  shown in the CLI display.
- Exchange-qualified tickers (e.g. `7203.T`, `BRK.B`) preserved across all
  agent prompts and tool calls.
- Process-level UTF-8 default attempted for cross-platform consistency
  (note: this approach did not actually take effect; replaced in v0.2.4 with
  explicit per-call `encoding="utf-8"` arguments).

### Fixed

- yfinance rate-limit errors are retried with exponential backoff. (#426)
- HTTP client SSL customisation is supported for environments that need
  custom certificate bundles. (#379)
- Report-section writes handle list-of-string content gracefully.

### Contributors

- [@CadeYu](https://github.com/CadeYu) — exchange-qualified ticker preservation (#413)
- [@yang1002378395-cmyk](https://github.com/yang1002378395-cmyk) — HTTP client SSL customisation (#379)

## [0.2.1] — 2026-03-15

### Security

- Patched `langchain-core` vulnerability (LangGrinch). (#335)
- Removed `chainlit` dependency affected by CVE-2026-22218.

### Added

- `pyproject.toml` build-system configuration; the project now installs via
  modern packaging tooling.

### Removed

- `setup.py` — dependencies consolidated to `pyproject.toml`.

### Fixed

- Risk manager reads the correct fundamental report source. (#341)
- All `open()` calls receive an explicit UTF-8 encoding (initial pass).
- `get_indicators` tool handles comma-separated indicator names from the LLM. (#368)
- `Propagation` initialises every debate-state field so risk debaters never
  see missing keys.
- Stock data parsing tolerates malformed CSVs and NaN values.
- Conditional debate logic respects the configured round count. (#361)

### Contributors

- [@RinZ27](https://github.com/RinZ27) — `langchain-core` security patch (#335)
- [@Ljx-007](https://github.com/Ljx-007) — risk manager fundamental-report fix (#341)
- [@makk9](https://github.com/makk9) — debate-rounds config issue (#361)

## [0.2.0] — 2026-02-04

This is the largest release since the initial public version. The framework
moved from single-provider to a multi-provider architecture and grew several
production-ready surfaces.

### Added

- **Multi-provider LLM support** (OpenAI, Google, Anthropic, xAI, OpenRouter,
  Ollama) via a factory pattern, with provider-specific thinking configurations.
- **Alpha Vantage** integration as a configurable primary data provider, with
  yfinance as a community-stability fallback.
- **Footer statistics** in the CLI: real-time tracking of LLM calls, tool
  calls, and token usage via LangChain callbacks.
- **Post-analysis report saving** — the framework writes per-section markdown
  files (analyst reports, debate transcripts, final decision) when a run
  completes.
- **Announcements panel** — fetches updates from `api.tauric.ai/v1/announcements`
  for the CLI welcome screen.
- **Tool fallbacks** so a single vendor outage does not stop the pipeline.

### Changed

- Risky / Safe risk debaters renamed to **Aggressive / Conservative** for
  consistency with the displayed agent labels.
- Default data vendor switched to balance reliability and quota across
  community deployments.
- Ollama and OpenRouter model lists updated; default endpoints clarified.

### Fixed

- Analyst status tracking and message deduplication in the live display.
- Infinite-loop guard in the agent loop; reflection and logging hardened.
- Various data-vendor implementation bugs and tool-signature mismatches.

### Contributors

This release is the first with substantial outside contributions; many community
PRs from late 2025 also landed here.

- [@luohy15](https://github.com/luohy15) — Alpha Vantage data-vendor integration (#235)
- [@EdwardoSunny](https://github.com/EdwardoSunny) — yfinance fetching optimisations (#245)
- [@Mirza-Samad-Ahmed-Baig](https://github.com/Mirza-Samad-Ahmed-Baig) — infinite-loop guard, reflection, and logging fixes (#89)
- [@ZeroAct](https://github.com/ZeroAct) — saved results path support (#29)
- [@Zhongyi-Lu](https://github.com/Zhongyi-Lu) — `.env` gitignore (#49)
- [@csoboy](https://github.com/csoboy) — local Ollama setup (#53)
- [@chauhang](https://github.com/chauhang) — initial Docker support attempt (#47, later reverted; the merged Docker support shipped in v0.2.4)

## [0.1.1] — 2025-06-07

### Removed

- Static site assets that had been bundled with v0.1.0; the public site now
  lives separately.

## [0.1.0] — 2025-06-05

### Added

- **Initial public release** of the TradingAgents multi-agent trading
  framework: market / sentiment / news / fundamentals analysts; bull and bear
  researchers; trader; aggressive, conservative, and neutral risk debaters;
  portfolio manager. LangGraph orchestration, yfinance data, per-agent
  BM25 memory, single-provider OpenAI integration, interactive CLI.

[0.2.4]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TauricResearch/TradingAgents/releases/tag/v0.1.0
