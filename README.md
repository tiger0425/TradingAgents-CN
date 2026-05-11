<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents：多智能体 LLM 金融交易框架

> **⚡ 衍生声明**：本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 进行二次开发，原始项目采用 Apache 2.0 许可证。主要变更包括：将数据源替换为 **akshare** 以支持 A 股市场分析，新增涨跌停限制与 T+1 交割规则约束，添加交易日历模块，并全面适配中文输出。原始版权归属 [TradingAgents 原作者](https://arxiv.org/abs/2412.20138) 所有。

## News

- [2026-05] **国信证券数据源接入**：新增 `dataflows/guosen.py` 模块，基于国信证券专业接口提供实时行情、财务三表、宏观经济、智能选股、基金对比、ETF筛选等 13 个数据函数。需配置 `GS_API_KEY` 环境变量（限制 50 次/Key）。
- [2026-05] **每日自动投研管线上线**：新增 `tradingagents daily --push` 一键串行宏观上下文→预警检查→组合风险评估→推送晨报。新增 `macro_context.py` 接入美股/汇率/商品/VIX/北向资金6路外围数据；Bull/Bear 辩论增加"核心证据锚定"双方输出单条最硬事实供裁判对比；组合层面新增相关性矩阵和对冲关系识别。Market Context 非交易日自动回退到最近交易日数据。
- [2026-05] **A股助手功能上线**：新增 6 个 CLI 工具——实时行情 (`quote`)、条件单价格预警 (`monitor`)、短线异动检测 (`alert-abnormal`，涨停/跌停/炸板/天地板/连板)、公告 LLM 快读 (`notice`)、研报抓取摘要 (`research-report`)、持仓风险评估 (`portfolio-risk`)，全部支持 `--push` 推送和 `--output json`。
- [2026-05] **分析存档系统（AnalysisArchive）**：每次 CLI 分析（batch / morning-scan / evening-review / scan-watchlist）自动持久化完整结果到 `~/.tradingagents/analysis-archive/`，支持按 ticker、日期、决策方向检索。新增 `tradingagents archive` 命令组：list/search/summary/delete。存档结构与 TradingMemoryLog 互补——memory 存决策+反思给 LLM 注入，archive 存完整分析上下文给人+AI 查询
- [2026-05] **知识消费体系上线**：新增 ContextAssembly 节点自动装配历史知识（含 CONFIRMED/SINGLE/CONFLICTING/STALE 置信度标签），Trader/Research Manager/Portfolio Manager prompt 注入历史决策与存档分析摘要，消除 trading_graph 中冗余 akshare 调用（14+ → ≤2 次/run），统一 DataCache 缓存层、三重缓存检查链（同天跳过/增量模式/全量分析）
- [2026-05] **Wiki 导航 + MCP Server**：新增 `tradingagents wiki generate` 自动生成 Markdown 知识导航索引（index.md + 个股详情 + lessons），新增 `tradingagents mcp serve` 启动 MCP Server 暴露 6 个知识查询工具（query_analysis / get_ticker_signals / search_patterns / get_lessons / get_confidence / get_graph_neighbors），支持 Graph Merge 合并代码图与分析图
- [2026-05] **A 股日历与指标 Bug 修复**：修复交易日历类型比较（`pd.Timestamp` → `.date()`），优化技术指标缺失值提示（区分"交易日数据未到"与"非交易日"）
- [2026-05] **A 股适配增强**：新增实时行情工具（基于 Sina `stock_zh_a_spot`），历史数据切换至 Sina 源（`stock_zh_a_daily`，英文字段名），`_fetch_returns()` 接入 akshare 计算 A 股收益与 Alpha，`akshare` 加入项目依赖
- [2026-05] **可编排化 CLI 与自动化升级**：新增非交互式 batch 模式、自选股池管理（watchlist）、批量扫描、盘前/盘后日报、预警条件检查、全市场扫描、持仓组合概览与简化回测，以及飞书/微信通知推送。所有命令支持 `--output json`，可供 OpenClaw 等 AI 编排系统调用。
- [2026-05] **持仓跟踪与操作指导**：新增成本价和数量输入，系统自动计算浮动盈亏并注入 Trader 和 Portfolio Manager prompt，实现盈亏分析、止盈止损建议、加仓减仓指导和风险调整四合一操作指导。持仓数据跨运行持久化，支持模拟自动更新。
- [2026-04] **TradingAgents v0.2.4** 发布，新增结构化输出智能体（Research Manager、Trader、Portfolio Manager）、LangGraph 检查点恢复、持久化决策日志、DeepSeek/Qwen/GLM/Azure 供应商支持、Docker 及 Windows UTF-8 编码修复。详见 [CHANGELOG.md](CHANGELOG.md)。
- [2026-03] **TradingAgents v0.2.3** 发布，新增多语言支持、GPT-5.4 系列模型、统一模型目录、回测日期准确性和代理支持。
- [2026-03] **TradingAgents v0.2.2** 发布，新增 GPT-5.4/Gemini 3.1/Claude 4.6 模型覆盖、五级评分体系、OpenAI Responses API、Anthropic effort 控制和跨平台稳定性。
- [2026-02] **TradingAgents v0.2.0** 发布，新增多供应商 LLM 支持（GPT-5.x、Gemini 3.x、Claude 4.x、Grok 4.x）并改进系统架构。
- [2026-01] **Trading-R1** [技术报告](https://arxiv.org/abs/2509.11420) 发布，[Terminal](https://github.com/TauricResearch/Trading-R1) 即将发布。

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **TradingAgents** 正式发布！我们收到了大量关于这项工作的询问，在此感谢社区的热情支持。
>
> 因此我们决定将框架完全开源。期待与大家一起打造有影响力的项目！

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## TradingAgents Framework

TradingAgents 是一个多智能体交易框架，模拟了真实交易公司的运作方式。通过部署由 LLM 驱动的专业智能体（从基本面分析师、情绪专家、技术分析师到交易员和风险管理团队），该平台协同评估市场状况并做出交易决策。此外，这些智能体还会进行动态讨论以确定最优策略。

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents 框架仅供研究用途。交易表现可能因多种因素而异，包括所选的基础语言模型、模型温度、交易周期、数据质量及其他非确定性因素。[不构成财务、投资或交易建议。](https://tauric.ai/disclaimer/)

我们的框架将复杂的交易任务分解为专业化的角色，确保系统在市场分析和决策中实现稳健、可扩展的方法。

### Analyst Team

- 基本面分析师（Fundamentals Analyst）：评估公司财务和业绩指标，识别内在价值和潜在风险信号。
- 情绪分析师（Sentiment Analyst）：通过情绪评分算法分析社交媒体和公众情绪，衡量短期市场情绪。
- 新闻分析师（News Analyst）：监控全球新闻和宏观经济指标，解读事件对市场状况的影响。
- 技术分析师（Technical Analyst）：利用技术指标（如 MACD 和 RSI）识别交易模式并预测价格走势。

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team

- 由看涨和看空研究员组成，他们批判性地评估分析师团队提供的见解。通过结构化辩论，在潜在收益与固有风险之间取得平衡。

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent

- 综合分析师和研究员的研究报告做出明智的交易决策。基于全面的市场洞察，确定交易的时机和规模。

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager

- 通过评估市场波动性、流动性及其他风险因素，持续评估投资组合风险。风险管理团队评估并调整交易策略，向投资组合经理（Portfolio Manager）提供评估报告以供最终决策。
- 投资组合经理批准或拒绝交易提案。若获批，订单将被发送至模拟交易所并执行。

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

克隆 TradingAgents：

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

使用任意偏好的环境管理器创建虚拟环境：

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

安装包及其依赖：

```bash
pip install .
```

### Docker

或者，使用 Docker 运行：

```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

使用 Ollama 运行本地模型：

```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents 支持多种 LLM 供应商。为所选供应商设置 API 密钥：

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen (Alibaba DashScope)
export ZHIPU_API_KEY=...           # GLM (Zhipu)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

对于企业级供应商（如 Azure OpenAI、AWS Bedrock），将 `.env.enterprise.example` 复制为 `.env.enterprise` 并填写您的凭据。

对于本地模型，在配置中将 Ollama 设置为 `llm_provider: "ollama"`。

或者，将 `.env.example` 复制为 `.env` 并填写您的密钥：

```bash
cp .env.example .env
```

### CLI Usage

启动交互式 CLI：

```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```

您将看到一个界面，您可以在其中选择所需的股票代码、分析日期、LLM 供应商、研究深度等选项。
在分析师选择之后，新增了可选的持仓成本价、持股数量和开仓日期输入步骤（按 Enter 跳过，仅使用纯市场分析）。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

界面将实时显示加载中的结果，让您跟踪智能体的运行进度。

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

我们使用 LangGraph 构建了 TradingAgents，以确保灵活性和模块化。该框架支持多种 LLM 供应商：OpenAI、Google、Anthropic、xAI、DeepSeek、Qwen（阿里 DashScope）、GLM（智谱）、OpenRouter、用于本地模型的 Ollama 以及用于企业级的 Azure OpenAI。

### Python Usage

要在代码中使用 TradingAgents，您可以导入 `tradingagents` 模块并初始化一个 `TradingAgentsGraph()` 对象。`.propagate()` 函数将返回一个决策。您可以运行 `main.py`，以下是一个快速示例：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 前向传播
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

```python
# 带持仓成本价和数量 — 系统自动计算浮动盈亏并注入操作指导
_, decision = ta.propagate("600519", "2026-05-06", cost_price=1580.0, quantity=100)
print(decision)
```

您还可以调整默认配置，自定义 LLM 选择、辩论轮次等参数。

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # 可选：openai, google, anthropic, xai, deepseek, qwen, glm, openrouter, ollama, azure
config["deep_think_llm"] = "gpt-5.4"     # 用于复杂推理的模型
config["quick_think_llm"] = "gpt-5.4-mini" # 用于快速任务的模型
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

所有配置选项请参阅 `tradingagents/default_config.py`。

### 数据供应商

TradingAgents 支持可插拔数据供应商，通过 `data_vendors` 配置切换：

| 供应商 | 模块 | 说明 | 环境变量 |
|--------|------|------|----------|
| **akshare**（默认） | `dataflows/akshare.py` | A 股数据，基于 akhare + Sina 源 | 无需额外配置 |
| **guosen** | `dataflows/guosen.py` | 国信证券专业接口，支持行情/财务/宏观/选股/基金/ETF | `GS_API_KEY` 等 3 个（限 50 次/Key） |
| alpha_vantage | 内置 | 美股数据 | `ALPHA_VANTAGE_API_KEY` |
| yfinance | 内置 | 美股数据（免费） | 无需额外配置 |

数据商分工（默认）：
- `core_stock_apis` → akshare（guosen 可选备选）
- `technical_indicators` → akshare（guosen 不支持）
- `fundamental_data` → akshare（guosen 可选备选）
- `news_data` → akshare（guosen 不支持）
- **`macro_economic`** → guosen（宏观经济，仅 guosen 支持）
- **`stock_screening`** → guosen（选股/排行/资金流/ETF/基金，仅 guosen 支持）

```python
config["data_vendors"] = {
    "core_stock_apis": "guosen",       # 切换为 guosen
    "technical_indicators": "akshare",
    "fundamental_data": "guosen",
    "news_data": "akshare",
}
```

或直接在代码中调用：

```python
from tradingagents.dataflows.guosen import get_real_time_quote, screen_stocks

print(get_real_time_quote("600519"))
print(screen_stocks("市盈率小于20的银行股"))
```

## Persistence and Recovery

TradingAgents 跨运行持久化两种状态。

### Decision log

决策日志始终开启。每次运行完成后将决策追加到 `~/.tradingagents/memory/trading_memory.md`。下次对同一股票代码运行时，TradingAgents 会获取已实现收益（原始收益和相对 SPY 的 Alpha 收益），生成一段反思，并将最近的同股票代码决策以及跨股票代码的经验教训注入到投资组合管理器（Portfolio Manager）的提示中，使每次分析都能继承过去有效和无效的经验。

可通过 `TRADINGAGENTS_MEMORY_LOG_PATH` 覆盖路径。

### Checkpoint resume

检查点恢复通过 `--checkpoint` 选项启用。启用后，LangGraph 会在每个节点后保存状态，从而使崩溃或中断的运行从上一个成功步骤处恢复，无需重新开始。恢复运行时，您将在日志中看到 `Resuming from step N for <TICKER> on <date>`；新运行时将看到 `Starting fresh`。成功完成后检查点会自动清除。

每个股票代码的 SQLite 数据库位于 `~/.tradingagents/cache/checkpoints/<TICKER>.db`（可通过 `TRADINGAGENTS_CACHE_DIR` 覆盖基础路径）。使用 `--clear-checkpoints` 可在运行前重置所有检查点。

```bash
tradingagents analyze --checkpoint           # enable for this run
tradingagents analyze --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

## 分析存档系统（AnalysisArchive）

从 v0.2.6 起，每次 CLI 分析的结果自动持久化到结构化存档中，形成跨运行的累积知识库。

### 存档目录结构

```
~/.tradingagents/analysis-archive/
├── index.json                          # 全量倒排索引（ticker/日期/决策）
├── 2026/
│   └── 05/
│       ├── index.json                  # 月索引
│       └── 09/
│           ├── morning-scan_600519.json
│           ├── batch_600519.json
│           ├── evening-review_600519.json
│           └── 2026-05-09_summary.md   # 当日汇总
└── ...
```

### 存档内容

每次分析结果保存为标准 JSON，包含：

| 字段 | 内容 |
|------|------|
| `_meta` | 版本号、时间戳、来源命令 |
| `request` | ticker、日期、分析师配置、LLM 供应商 |
| `market_context` | 实时行情快照、涨跌停价 |
| `analysis` | 各分析师信号汇总 + 最终决策 + 推理过程 |
| `tags` | 自动提取的关键标签（用于搜索） |

### CLI 命令

```bash
# 查询存档（支持 ticker/日期/决策方向筛选）
tradingagents archive list --ticker 600519 --limit 10

# 获取某次分析的完整内容
tradingagents archive get 2026/05/09/batch_600519

# 全文搜索历史分析
tradingagents archive search "放量突破"

# 信号分布汇总
tradingagents archive summary 600519 --days 90

# 删除条目
tradingagents archive delete 2026/05/09/batch_600519

# 重建索引（数据损坏时）
tradingagents archive rebuild-index
```

### 与 TradingMemoryLog 的关系

分析存档与 TradingMemoryLog 互补而非替代：

| 维度 | TradingMemoryLog | AnalysisArchive |
|------|-----------------|----------------|
| 存储内容 | 决策结果 + 反思（精简） | 完整分析上下文（行情+报告+推理） |
| 消费对象 | LLM agent prompt 注入 | 人和 AI 通过 CLI/MCP 查询 |
| 条目管理 | LRU 裁剪（最近 N 条） | 持久保留，手工管理 |
| 路径 | `~/.tradingagents/memory/trading_memory.md` | `~/.tradingagents/analysis-archive/` |

### 自动存档

以下命令在成功执行后自动将结果写入存档：

- `tradingagents batch` — 单股票全量分析
- `tradingagents morning-scan` — 盘前扫描
- `tradingagents evening-review` — 收盘复盘
- `tradingagents scan-watchlist` — 批量扫描

存档写入失败不影响主流程（静默跳过）。

## 可编排化 CLI 与自动化

从 v0.2.5 开始，TradingAgents 提供完整的非交互式 CLI 接口，支持通过命令行参数驱动所有分析流程，输出结构化 JSON，可被 OpenClaw 等 AI 编排系统直接调用。

### 架构概览

```
OpenClaw / 定时任务 / AI 编排
    │ 调用 CLI 命令 (--output json)
    ▼
TradingAgents CLI (可编排模式)
    ├── batch             非交互式单股票分析
    ├── scan-watchlist    批量扫描自选股
    ├── morning-scan      盘前快速扫描
    ├── evening-review    收盘复盘
    ├── check-alerts      预警条件检查
    ├── market-scan       全市场扫描
    ├── portfolio         持仓组合概览
    ├── backtest          简化回测
    ├── watchlist         自选股管理
    ├── notify            飞书/微信通知
    ├── archive           存档管理（查询/搜索/删除）
    ├── wiki              Wiki 知识导航生成
    └── mcp               MCP Server 启动
```

### Batch 模式

非交互式单股票分析，所有参数通过命令行传入：

```bash
tradingagents batch \
  --ticker 600519 \
  --date 2026-05-09 \
  --analysts market,news,technical \
  --llm openai \
  --output json
```

支持 `--output json` / `--output text` / `--output silent` 三种输出模式。

### 自选股管理

通过 `tradingagents watchlist` 子命令管理 `~/.tradingagents/watchlist.json`：

```bash
tradingagents watchlist add 600519 --name "贵州茅台" --priority 1 --price-above 1600
tradingagents watchlist remove 600519
tradingagents watchlist list --output json
tradingagents watchlist set-alert 600519 --rsi-oversold
```

每只股票可配置独立预警条件（price_above、price_below、rsi_oversold、rsi_overbought、volume_surge、ma_cross）。

### 批量扫描

读取自选股池，按优先级排序后逐只分析，汇总输出：

```bash
tradingagents scan-watchlist --date 2026-05-09 --output json
tradingagents morning-scan --date 2026-05-09 --output json
tradingagents evening-review --date 2026-05-09 --output json
```

- **morning-scan**：获取实时行情快照 + 轻量分析（市场 + 技术面，1 轮辩论）
- **evening-review**：获取收盘价，基于持仓计算浮动盈亏，更新决策日志

### 预警与市场扫描

```bash
# 检查自选股预警条件
tradingagents check-alerts --date 2026-05-09 --output json

# 全市场扫描（涨幅/跌幅/成交量排行）
tradingagents market-scan --top 20 --output json
```

### 持仓组合

基于 `position_state.json` 的多股票持仓管理：

```bash
tradingagents portfolio --output json
```

输出组合概况：总市值、总盈亏、各持仓明细、仓位集中度。

### 通知推送

支持飞书机器人和微信（Server酱 / PushPlus）通知渠道：

```bash
# 配置方式（环境变量或 default_config.py）
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
export SERVER_CHAN_KEY="xxx"

# 手动发送通知
tradingagents notify feishu --title "今日信号" --content "600519: Buy"
tradingagents notify all --markdown --title "晨报" --content "$(cat report.md)"

# morning-scan 和 evening-review 完成后自动发送通知
```

### 简化回测

```bash
tradingagents backtest \
  --ticker 600519 \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --output json
```

逐日运行 LLM 分析流水线，输出决策分布、胜率和平均收益统计。

## 知识消费与历史注入

TradingAgents 从 v0.2.6 起新增知识消费体系，让 AI agent 在每次分析时自动感知历史知识，减少重复计算，提升决策质量。

### 统一缓存层 (DataCache)

系统级磁盘 + 内存双层缓存，消除冗余数据源调用：

| 命名空间 | 存储方式 | TTL |
|---------|---------|-----|
| `ohlcv/` | CSV 文件 | 持久化 |
| `benchmark/` | CSV 文件 | 持久化（新增，消除基准指数重复下载） |
| `fundamentals/` | CSV/JSON 文件 | 持久化（新增） |
| `spot/` | 内存 | 30 秒 |

```python
from tradingagents.dataflows.cache import DataCache

cache = DataCache("~/.tradingagents/cache")
# 缓存优先：命中返回，未命中调用 fetcher 并自动缓存
df = cache.get_or_fetch("benchmark", "000300_2026-05-09.csv", fetcher=fetch_fn)
```

**效果**：基准指数数据不再每次 propagate() 重新下载，trading_graph.py 中 akshare 调用从 14+ 次/run 降至 ≤2 次/run。

### ContextAssembly 节点

在每次分析启动时自动装配所有可用历史知识，位于 `tradingagents/graph/context_assembly.py`：

```
propagate(ticker, date)
  │
  ├── 1. 缓存检查（DataCache）
  ├── 2. 三重缓存检查链（同天跳过 / 增量模式 / 全量）
  ├── 3. ContextAssembly ← 新增
  │     ├── AnalysisArchive → 历史分析（含置信度标签）
  │     ├── TradingMemoryLog → 历史交易决策与盈亏
  │     ├── 信号分布统计（过去 30 天）
  │     ├── Lessons（跨标的洞察）
  │     └── Token 预算控制（默认 25K tokens）
  │
  └── 4-6. Agent 执行（注入历史知识）
```

### Confidence 标签体系

每次历史结论自动标注置信度，AI agent 据此加权参考：

| 标签 | 含义 | 加权 |
|------|------|------|
| `CONFIRMED` | 多次独立分析验证（3+ 同向信号） | 最高 |
| `SINGLE` | 单次分析结论 | 中 |
| `DERIVED` | 跨标的推理结论 | 中低 |
| `CONFLICTING` | 多次分析分歧 | 低 |
| `STALE` | 超过 90 天未更新 | 最低 |

可通过 `confidence_threshold_inject` 配置注入阈值（默认：CONFLICTING 及以上的结论才注入 prompt）。

### Agent Prompt 注入

| 智能体 | 注入内容 |
|--------|---------|
| **Trader** | 历史交易决策 + 盈亏结果 + Confidence 标签 |
| **Research Manager** | 历史决策上下文 |
| **Portfolio Manager** | 存档分析摘要 + 历史 lessons |

### 三重缓存检查链

在 `propagate()` 中实现三级递进检查：

```python
config = DEFAULT_CONFIG.copy()
config["skip_if_analyzed_today"] = True    # Level 1：同天跳过
config["incremental_window_days"] = 3      # Level 2：3 天内增量
```

- **Level 1**：同 ticker 同天已分析 → 直接返回存档结果
- **Level 2**：近 N 天有分析 → 增量模式（减少完整分析开销）
- **Level 3**：无历史 → 全量分析，完成后自动写入存档

## 知识库导航与 MCP Server

分析存档累积后，AI agent 需要高效途径发现和查询历史知识。TradingAgents 提供两种互补通道。

### 通道 A：Wiki 导航（被动发现）

自动为分析存档生成 agent 可爬取的 Markdown 导航索引：

```bash
# 全量生成 Wiki
tradingagents wiki generate

# 单 ticker 增量更新
tradingagents wiki generate --ticker 600519

# 查看个股详情页
tradingagents wiki show 600519

# 列出所有页面
tradingagents wiki list
```

生成产物位于 `~/.tradingagents/wiki/`：

| 文件 | 内容 |
|------|------|
| `index.md` | 全量索引：所有 ticker 的分析次数、最近信号、置信度 |
| `{ticker}.md` | 个股详情：信号时间线、置信度标签、经验教训 |
| `lessons.md` | 跨标的经验教训汇总（7 天去重） |

零外部依赖（纯 Markdown），AI agent 读 index.md 即可了解知识库全貌。

### 通道 B：MCP Server（主动查询）

通过 [Model Context Protocol](https://modelcontextprotocol.io) 将分析知识库暴露为 AI agent 可直接调用的工具：

```bash
# 启动 MCP Server（stdio 模式）
tradingagents mcp serve
```

**6 个 MCP 工具：**

| 工具 | 功能 | 适用场景 |
|------|------|---------|
| `query_analysis` | 按 ticker/日期/关键词查询 | "查一下 600519 近期所有分析" |
| `get_ticker_signals` | 信号分布 + 趋势 + 置信度 | "茅台最近信号是否一致看多？" |
| `search_patterns` | 搜索反复出现的市场模式 | "历史上缩量突破后怎么走？" |
| `get_lessons` | 跨标的经验教训 | "其他股票的教训能否参考？" |
| `get_confidence` | 某 ticker 当前信号可信度 | "当前 Buy 信号可信吗？" |
| `get_graph_neighbors` | 知识图谱关联节点 | "茅台和哪些行业龙头有关联？" |

**Claude Desktop / OpenClaw 配置示例：**
```json
{
  "mcpServers": {
    "trading-knowledge": {
      "command": "python",
      "args": ["-m", "tradingagents.knowledge.mcp_server"],
      "env": {
        "TRADINGAGENTS_ARCHIVE_DIR": "~/.tradingagents/analysis-archive"
      }
    }
  }
}
```

### 存档管理

```bash
# 查询存档（支持 ticker/日期/决策筛选）
tradingagents archive list --ticker 600519 --limit 10

# 全文搜索
tradingagents archive search "放量突破"

# 查看信号分布
tradingagents archive summary 600519 --days 90

# 删除条目
tradingagents archive delete 2026/05/09/batch_600519
```

### Graph Merge

将代码知识图谱与分析知识图谱合并为统一查询层：

```bash
python -m tradingagents.knowledge.mcp_server --merge-graphs \
  graphify-out/graph.json \
  graphify-out/analysis-graph.json \
  --output graphify-out/unified-graph.json
```

### 知识消费双通道

```
┌─────────────────────────────────────────────────────────────┐
│                   知识消费双通道                             │
├─────────────────────────┬───────────────────────────────────┤
│  通道 A: Wiki 导航       │  通道 B: MCP 工具调用             │
│  （被动，低成本）         │  （主动，按需）                   │
│                          │                                   │
│  agent 读 Markdown       │  agent 通过 function calling 调用 │
│  → 了解知识库全貌         │  → 精确获取所需信息              │
│  适合：每次分析的前置      │  适合：深度回溯、跨标的查询       │
│  token 成本：~2K/page    │  token 成本：按需付费             │
└─────────────────────────┴───────────────────────────────────┘
```

## Contributing

我们欢迎社区的贡献！无论是修复 Bug、改进文档还是建议新功能，您的参与都能帮助这个项目变得更好。如果您对此研究方向感兴趣，请考虑加入我们的开源金融 AI 研究社区 [Tauric Research](https://tauric.ai/)。

过往贡献，包括代码、设计反馈和 Bug 报告，均按版本记录在 [`CHANGELOG.md`](CHANGELOG.md) 中。

## Citation

如果您觉得 *TradingAgents* 对您有所帮助，请引用我们的工作 :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```

---

## A-Share Market Support (A 股支持)

TradingAgents 通过 **akshare** 数据供应商支持 A 股（中国股票市场）分析。数据源基于新浪财经（Sina Finance），通过两个 API 通道获取：`stock_zh_a_daily`（历史日线 OHLCV，前复权，英文字段名）和 `stock_zh_a_spot`（实时行情快照，30 秒缓存）。所有现有智能体工作流无需修改即可在 A 股数据上运行。

### Installation

```bash
pip install akshare
```

### Data Sources（数据源）

A 股行情数据通过两个 Sina 源的 akshare API 获取：

| API | 功能 | 说明 |
|-----|------|------|
| `stock_zh_a_daily` | 历史日线 OHLCV | 前复权价格，英文字段名（date, open, high, low, close, volume） |
| `stock_zh_a_spot` | 实时行情快照 | 最新价、涨跌幅、成交量、成交额，30 秒本地缓存 |

6 位数字代码自动转换为 Sina 格式：上海 `6xxxxx` → `shxxxxxx`，深圳 `0/3xxxxx` → `szxxxxxx`，由 `_to_sina_symbol()` 统一处理。

### Configuration

默认配置已设置为 A 股模式。您可以通过 `default_config.py` 切换市场：

```python
# 在 tradingagents/default_config.py 或您的配置字典中：
config = {
    # 数据供应商 — "akshare" 用于 A 股，"yfinance" 用于美股
    "data_vendors": {
        "core_stock_apis": "akshare",       # 可选：akshare, yfinance, alpha_vantage
        "technical_indicators": "akshare",
        "fundamental_data": "akshare",
        "news_data": "akshare",
    },
    # 基准指数
    "benchmark_ticker": "000300",          # CSI 300（沪深300）
    "benchmark_name": "沪深300",

    # 市场类型影响约束注入（涨跌停、T+1）
    # "A_SHARE" 启用 A 股特定规则
    # "US_STOCK" 禁用这些规则以保持向后兼容
    "market_type": "A_SHARE",

    # 输出语言 — "Chinese" 输出中文报告，"English" 输出英文报告
    "output_language": "Chinese",

    # 知识消费配置
    "knowledge_token_budget": 25000,
    "skip_if_analyzed_today": False,
    "incremental_window_days": 0,
    "enable_context_assembly": True,
    "enable_archive_first_cache": True,
    "confidence_tags_enabled": True,
    "confidence_threshold_inject": "CONFLICTING",
    "graphify_auto_sync": True,
    "wiki_auto_generate": False,
    "mcp_server_enabled": False,
}
```

### Basic Usage

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
# 默认已设置为 A 股模式

ta = TradingAgentsGraph(config=config)

# A 股股票代码使用 6 位数字代码
_, decision = ta.propagate("600519", "2026-01-15")
print(decision)

# 切换回美股：
config["market_type"] = "US_STOCK"
config["data_vendors"] = {k: "yfinance" for k in config["data_vendors"]}
config["benchmark_ticker"] = "SPY"
config["benchmark_name"] = "S&P 500"
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

### Real-time Quotes（实时行情）

**Market Analyst** 智能体配备了 `get_current_price` 工具，可通过 Sina `stock_zh_a_spot` 获取 A 股实时行情快照：

```python
from tradingagents.dataflows.akshare import get_current_price

# 获取贵州茅台实时行情
quote = get_current_price("600519")
print(quote)
# Real-time Quote for 600519 (贵州茅台)
# Current Price: 1580.00
# Change: -5.00 (-0.32%)
# Open: 1585.00   High: 1592.00   Low: 1576.00
# Previous Close: 1585.00
# Volume: 2850000   Turnover: 4523000000
# Data source: akshare (Sina, real-time)
```

该工具已注册到智能体工具链，LLM 可在分析过程中按需调用。

### Market Rules

当 `market_type: "A_SHARE"` 时，系统自动强制执行以下规则：

| 规则 | 实现方式 |
|------|---------------|
| **涨跌停限制**（±10%/20%/30%/5%） | 注入到交易员和投资组合管理器的提示中作为价格约束 |
| **T+1 交割** | 今日开仓的仓位需在下一个交易日才能卖出 |
| **交易日历** | 通过 akshare 使用新浪财经日历（`is_trade_day()` 等） |
| **6 位代码** | 上海：`.SS` 后缀 / `sh` 前缀（Sina）；深圳：`.SZ` 后缀 / `sz` 前缀（Sina） |

### Position Tracking（持仓跟踪）

从 2026-05 起支持输入持仓成本价和数量，系统自动将持仓盈亏状态注入决策智能体的 prompt，生成个性化的操作指导。

#### Python API 使用

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(config=DEFAULT_CONFIG.copy())

# 不传持仓参数 — 纯市场分析，与之前行为一致（向后兼容）
_, decision = ta.propagate("600519", "2026-05-06")

# 传持仓参数 — 系统结合持仓盈亏给出操作指导
_, decision = ta.propagate("600519", "2026-05-06",
                           cost_price=1580.0,
                           quantity=100,
                           position_opened_date="2026-01-15")
print(decision)
```

#### CLI 交互输入

分析流程中新增 3 个可选步骤（在分析师选择之后）：

| 步骤 | 提示 | 校验规则 |
|------|------|---------|
| Step 4.5 | 输入当前持仓成本价 | 必须为正浮点数，Enter 跳过 |
| Step 4.6 | 输入当前持仓股数 | 必须为正整数，Enter 跳过 |
| Step 4.7 | 输入开仓日期 YYYY-MM-DD | 格式合法且不晚于分析日期，Enter 跳过 |

所有步骤均为可选，按 Enter 跳过即降级为纯市场分析模式。

#### 操作指导内容

当提供持仓数据后，系统在以下环节注入持仓上下文：

| 智能体 | 注入内容 |
|--------|---------|
| **Trader** | 当前持仓成本价、股数，提示因子化现有持仓做出交易方案 |
| **Portfolio Manager** | 详细持仓盈亏分析，含浮盈超 10% 止盈提示、浮亏超 10% 止损评估、震荡区间观望建议及风险立场调整 |

#### 模拟持仓自动更新

系统分析完成后，根据 Portfolio Manager 的最终决策自动更新模拟持仓：

| 决策 | 自动操作 |
|------|---------|
| Buy / Overweight | 以分析日收盘价开仓 100 股（仅当无持仓时） |
| Sell / Underweight | 以分析日收盘价平仓（受 T+1 约束检查保护） |
| Hold | 持仓不变 |

自动更新具有幂等性：同一 ticker 同一天不会重复更新。

#### 持仓持久化

持仓数据存储于 `~/.tradingagents/memory/position_state.json`，使用原子写入防止文件损坏。下次分析时自动加载上次的持仓信息，无需重复输入。

### What's Not Yet Supported

- 分钟级 K 线数据（实时行情快照已支持）
- 北向资金流向分析
- 板块轮动策略
- 分批建仓的 FIFO/LIFO 成本追踪
- 多股票组合持仓管理
- 真实券商 API 对接

### 文档

- 📖 [知识库系统使用指南 →](docs/knowledge-base-help.md) — 分析存档、搜索查询、Wiki 导航、MCP Server 配置等知识库功能详解
- 📖 [OpenClaw 编排指南 →](docs/openclaw-operation-guide.md) — 面向 AI 编排系统的 CLI 命令参考、JSON 输出格式、典型工作流

---

## 免责声明

本项目仅供 **学术研究和技术学习** 使用，不构成任何形式的投资建议、理财建议或交易指令。

- 本系统基于历史数据和 LLM 预测模型生成分析，**不保证**任何交易策略的盈利能力
- A 股市场存在涨跌停、T+1 等特殊制度约束，实际交易结果可能与模拟结果存在显著差异
- 使用本系统产生的任何交易盈亏，开发者**不承担**任何责任
- 投资有风险，入市需谨慎。请勿将本系统用于实际资金交易决策
