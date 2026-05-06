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

- [2026-05] **A 股日历与指标 Bug 修复**：修复交易日历类型比较（`pd.Timestamp` → `.date()`），优化技术指标缺失值提示（区分"交易日数据未到"与"非交易日"）
- [2026-05] **A 股适配增强**：新增实时行情工具（基于 Sina `stock_zh_a_spot`），历史数据切换至 Sina 源（`stock_zh_a_daily`，英文字段名），`_fetch_returns()` 接入 akshare 计算 A 股收益与 Alpha，`akshare` 加入项目依赖
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

### What's Not Yet Supported

- 分钟级 K 线数据（实时行情快照已支持）
- 北向资金流向分析
- 板块轮动策略
- A 股数据完整回测框架

---

## 免责声明

本项目仅供 **学术研究和技术学习** 使用，不构成任何形式的投资建议、理财建议或交易指令。

- 本系统基于历史数据和 LLM 预测模型生成分析，**不保证**任何交易策略的盈利能力
- A 股市场存在涨跌停、T+1 等特殊制度约束，实际交易结果可能与模拟结果存在显著差异
- 使用本系统产生的任何交易盈亏，开发者**不承担**任何责任
- 投资有风险，入市需谨慎。请勿将本系统用于实际资金交易决策
