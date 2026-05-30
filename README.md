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

# TradingAgents：双层智能金融分析系统

> **⚡ 衍生声明**：本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 二次开发。主要变更：A 股数据源（akshare + 国信证券）、V1.3 双层调度架构（后台采集 + 事件驱动）、LLM Planner 智能编排、知识库驱动、HTTP API 服务、Docker Compose 部署。原始版权归属 [原作者](https://arxiv.org/abs/2412.20138)。

## News

- [2026-05] **V1.3 架构质量升级**：11 项架构缺陷修复，涵盖分析师并行化（-67% 延迟）、辩论路由枚举化、deep_llm fallback 机制、检查点恢复、上下文智能压缩、工具循环检测、并发安全锁、因果链追踪等。
- [2026-05] **V1.2 冒烟验证全部通过**：4 Collector（AkShare 真实数据）+ KB 时效管理 + Planner 覆盖率计算 + OHLCV 预取 + 对话录入持仓全部验证通过。
- [2026-05] **V1.2 双层智能架构上线**：后台采集层不间断研究并写入知识库；LLM Planner 收到消息后优先查 KB，只对缺失部分启动 Agent。
- [2026-05] **国信证券数据源接入**：`dataflows/guosen.py` 提供实时行情、财务三表、宏观经济、智能选股、基金对比、ETF 筛选等 13 个数据函数。
- [2026-05] **知识消费体系上线**：ContextAssembly 节点自动装配历史知识（CONFIRMED/SINGLE/CONFLICTING/STALE 置信度标签），统一 DataCache 缓存层，三重缓存检查链。
- [2026-05] **分析存档 + Wiki + MCP Server**：分析结果自动归档，按 ticker/日期/决策检索。Wiki 导航 + MCP 工具暴露 6 个知识查询接口。
- [2026-05] **a-stock-data 数据源接入**：`dataflows/a_stock_data.py` 基于 simonlin1212/a-stock-data V3.1，覆盖 A 股龙虎榜（个股+全市场）、融资融券、大宗交易、限售解禁、股东户数变化（筹码集中度）、分红送转、财联社快讯、巨潮公告等 9 个缺失端点。直连 HTTP API，全部免费无 Key。
- [2026-05] **a-stock-data 28 端点全面整合**：经过 Phase 1/2/3 三个阶段的递进替换，已完成 26/28（93%）端点直连覆盖，涵盖行情、研报、信号、资金、新闻、基础数据、公告 7 层。akshare 核心依赖从 10 个函数降至 4 个。

---

## V1.3 架构

TradingAgents V1.3 采用**双层智能系统**，模拟券商研究所的运作方式：

```
┌──────────────────────────────────────────────────────────┐
│                    接入层 — OpenClaw                       │
│  用户消息接收 / 报告推送                                    │
└────────────────────────┬─────────────────────────────────┘
                         │  POST /analyze
┌────────────────────────▼─────────────────────────────────┐
│              分析引擎层 — TradingAgents (FastAPI)           │
│                                                          │
│  🔄 后台采集层   市场(30min) 公告(1h) 政策(2h) 舆情(15min)  │
│         │ 持续写入                                        │
│  ┌──────▼─────────────────────────────────────           │
│  │  📚 知识库 (KB)  市场快照 / 公告摘要 / 政策简报           │
│  │      时效标签 FRESH → STALE → EXPIRED                  │
│  └──────┬─────────────────────────────────────           │
│         │ Planner 先查 KB                                 │
│  ┌──────▼─────────────────────────────────────           │
│  │  🧠 LLM Planner  KB查询 → 模板匹配 → 动态图构建          │
│  └──────┬─────────────────────────────────────           │
│         │                                                │
│  ┌──────▼─────────────────────────────────────           │
│  │  👥 Agent 执行层  13 Agent 按需调度（只跑缺失部分）       │
│  └────────────────────────────────────────────           │
│                                                          │
│  ⏰ 双层调度：采集层 interval / 事件层 cron                   │
└──────────────────────────────────────────────────────────┘
```

**核心差异**：事件触发时先查 KB，已有分析直接复用，大幅降低 LLM 调用成本（约 55%）。

| 场景 | V1.0（纯事件驱动） | V1.3（双层架构） |
|------|-------------------|-----------------|
| 晨会 | 每次采集外盘+公告 ($0.35) | KB 已有 30min 前快照 ($0.10) |
| 客户问个股 | 从零全流程 ($0.85) | KB 已有快照，只补辩论 ($0.30) |
| 盘中突发公告 | 不知道（无监控） | 后台采集已写入 KB |

### Agent 团队（13 Agent 按需调度）

| Agent | 中文名 | 适用场景 |
|-------|--------|---------|
| market_analyst | 技术面分析师 | 所有分析 |
| fundamentals_analyst | 基本面分析师 | 个股分析、选股 |
| news_analyst | 新闻分析师 | 持仓预警、政策 |
| social_analyst | 舆情分析师 | 个股分析 |
| macro_analyst | 宏观研究员 | 晨会、周选股 |
| bull_researcher / bear_researcher | 多/空方研究员 | 辩论 |
| research_manager | 研究主管 | 辩论汇总 |
| trader | 交易员 | 四方案/交易计划 |
| risk_aggressive/conservative/neutral | 三方风控 | 风控辩论 |
| portfolio_manager | 组合经理 | 最终决策 |

---

## 快速开始

### Docker Compose（推荐）

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
docker compose up
```

### HTTP API 使用

```bash
# 健康检查
curl http://localhost:8000/health
# → {"status":"ok","kb_entries":0,"user_count":1}

# 分析请求
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","message":"茅台最近走势分析","ticker":"600519"}'
```

**响应**：

```json
{
  "report": "## 最终分析报告\n\n...",
  "intent": "standard_analysis",
  "generation_mode": "template_exact",
  "template_id": "tpl_standard_analysis",
  "estimated_cost_usd": 0.30,
  "workflow_steps": 6
}
```

### 本地开发启动

```bash
python -m venv .venv && source .venv/bin/activate
pip install .
OPENAI_API_KEY=sk-xxx uvicorn tradingagents.api_server:app --host 0.0.0.0 --port 8000
```

### CLI 模式（兼容保留）

```bash
tradingagents                              # 交互式 CLI
tradingagents batch --ticker 600519 --output json  # 非交互式
```

### `POST /portfolio/chat` — 对话录入持仓

用自然语言管理持仓，LLM 自动解析股票代码、成本价、数量并写入 portfolio.yaml：

```bash
curl -X POST http://localhost:8000/portfolio/chat \
  -d "user_id=test&message=我买了600519茅台1000股成本1800"
# → {"action":"add_holding","ticker":"600519","name":"贵州茅台","cost_price":1800,"quantity":1000}
```

---

## 知识库（KB）

后台采集层不间断写入结构化研究数据：

| 分类 | 频率 | 内容 |
|------|------|------|
| 市场快照 | 30min | 指数、板块轮动、资金流、北向 |
| 公告扫描 | 1h | 全市场公告 + 自选股深度解读 |
| 政策监控 | 2h | 央行/证监会/产业政策 |
| 舆情报告 | 15min | 财经新闻 + 情感分析 |

数据存在 `~/.tradingagents/kb/`，市场数据所有用户共享，个股快照按用户生成。每日 09:00 自动预取持仓/自选股 60 日 OHLCV 到 KB，分析时无需等待数据拉取。

### 知识消费

```bash
tradingagents wiki generate          # 生成 Markdown 导航索引
tradingagents mcp serve              # 启动 MCP Server（6 个查询工具）
```

---

## 模板系统

LLM Planner 使用模板匹配优先策略，6 个核心模板：

| 模板 | 场景 | Agent | 辩论 |
|------|------|:---:|:---:|
| `morning_briefing` | 晨会 08:50 | 4 | ❌ |
| `midday_review` | 午评 12:00 | 3 | ❌ |
| `closing_review` | 收盘复盘 15:10 | 3 | ❌ |
| `standard_analysis` | 客户个股分析 | 12 | ✅ |
| `breakeven_recovery` | 解套方案 | 5 | ✅ |
| `weekly_screening` | 周日选股 | 3 | ❌ |

模板自动进化：根据成功率动态调整匹配权重。

---

## 配置

### 环境变量

```bash
# 首次启动自动从 .env.example 创建 .env
DEEPSEEK_API_KEY=sk-...        # DeepSeek（推荐，成本低）
OPENAI_API_KEY=sk-...          # OpenAI
GS_API_KEY=...                 # 国信证券（可选）
OPENCLAW_HOOK_TOKEN=...        # OpenClaw 推送令牌
```

### 默认配置

```python
DEFAULT_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "market_type": "A_SHARE",
    "benchmark_ticker": "000300",
    "output_language": "Chinese",
    "max_debate_rounds": 1,
    "data_vendors": {
        "core_stock_apis": "akshare",
        "macro_economic": "guosen",
        "stock_screening": "guosen",
        "specialty_data": "a_stock_data",
        "fundamental_data": "a_stock_data",  # 新增：腾讯财经PE/PB/市值
    },
}
```

---

## 多用户隔离

```
~/.tradingagents/users/
├── alice/portfolio/portfolio.yaml    # 持仓 + 自选
├── bob/...
└── shared/kb/                        # 共享知识库
```

持仓、自选股、分析历史、个性化模板按 `user_id` 隔离。市场快照和政策简报所有用户共享。

---

## 文档

- 📖 [OpenClaw 编排指南 →](docs/openclaw-operation-guide.md)
- 📖 [知识库系统指南 →](docs/knowledge-base-help.md)

---

## 引用

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

## 免责声明

本项目仅供**学术研究和技术学习**使用，不构成任何形式的投资建议。投资有风险，入市需谨慎。
