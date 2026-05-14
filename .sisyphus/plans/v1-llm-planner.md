# V1.2 技术方案：LLM Planner 智能调度中心 + 知识库驱动 + Dashboard + 多用户

> **版本**: v1.2
> **日期**: 2026-05-13
> **状态**: 实施中（Phase 1-3 代码层完成，Phase 3-4 待环境）
> **位置**: `tradingagents-cn/`（主力开发仓库）
> **关联文档**: `../tradingagents-platform/docs/PRD-数字金融团队.md`、`../tradingagents-platform/docs/架构决策记录.md`

---

## 实施进度

| Phase | 状态 | 文件数 |
|-------|:---:|:---:|
| Phase 1 — 模块骨架 | ✅ 完成 | 23 个 |
| Phase 2 — 核心功能 | ✅ 完成 | KB/DynamicGraphBuilder/LLMPlanner/Collector/TemplateMatcher |
| Phase 3 — 代码层 | ✅ 完成 | 30 个文件（6模板+CostTracker+DataExporter+调度+多用户） |
| Phase 3 — 待环境 | 🚫 阻塞 | OpenClaw推送/对话录入/数据预取（需要 LLM Key + AkShare + OpenClaw） |
| Phase 4 — 验证 | 🚫 阻塞 | 端到端测试/模板进化验证（需要完整 docker compose 环境） |

---

## 一、摘要

当前 TradingAgents 有三大根本缺陷：
1. Agent 编排是**硬编码的单一管线**——无论什么意图都跑同一条流程
2. **没有后台研究能力**——每次分析从零采集数据、从零分析
3. **无用户界面**——只有 OpenClaw 消息推送，看不到 Agent 工作状态、KB 内容、成本

V1.2 目标：将 TradingAgents 改造为**双层智能系统 + 双 Dashboard + 多用户**——后台采集层不间断做市场研究并沉淀到知识库；事件驱动层优先从 KB 调取已有分析；LangRay 提供 Agent 执行可视化；自建业务看板提供持仓/KB/成本概览；按 user_id 数据隔离支持多用户。砍掉过度设计的 Paperclip 治理层。

---

## 二、背景

### 2.1 当前问题

| 问题 | 具体表现 |
|------|---------|
| **管线固定** | 所有分析请求走同一条 Agent 序列，不能按意图切换 |
| **每次从零采集** | 没有后台研究能力，客户问一个问题就要从头采集数据、从头分析 |
| **无关 Agent 也跑** | 晨会不需要辩论/风控，但管道写死全部跑一遍 |
| **无持仓感知** | 没有持仓/自选股管理，分析不通个性化 |
| **架构过重** | Paperclip + OpenClaw + TradingAgents = 3 项目、2 技术栈 |
| **无知识积累** | 每次分析从零开始，不沉淀研究数据 |

### 2.2 为什么是双层

真实券商研究所：

```
基础研究团队（持续工作）        高级分析师（事件驱动）
├─ 宏观研究员: 盯盘/读政策    ├─ 接到客户需求
├─ 行业研究员: 跟踪公告        ├─ 先查内部研究库
└─ 数据团队: 维护数据库        └─ 引用已有研究 + 补充专项分析
```

纯事件驱动（V1.0）只有"高级分析师"——每次从零采集。双层架构（V1.1）让后台采集层充当"基础研究团队"，事件层接到需求时优先从 KB 调取。

| 场景 | 纯事件驱动 | 双层架构 |
|------|-----------|---------|
| 晨会 | 每次采集隔夜外盘+扫公告 (~$0.35) | KB 已有 30 分钟前快照 (~$0.10) |
| 客户问个股 | 从零分析技术面+基本面+公告 (~$0.85) | KB 已有快照，只补四方案+辩论 (~$0.30) |
| 盘中突发公告 | 不知道（无监控） | 后台采集已写入 KB，晨会自然包含 |

### 2.3 瘦身决策

| 砍掉 | 原因 | 替代 |
|------|------|------|
| Paperclip | v1 不需要组织治理/预算审计 | APScheduler（双层） |
| 行业研究组 ×3 | 后台采集已覆盖行业跟踪 | 采集层按行业采集入 KB |
| 学习发展组独立 Agent | 模板进化 + KB 时效管理已覆盖 | 内置 |
| 五层知识库 | V1.1 结构化 KB 够用 | KB 模块 |
| Board 审批 | 无用户时不需 | 延迟至 v2 |

---

## 三、目标

### 3.1 核心目标

**建立"后台持续研究 + 事件按需调度"的双层智能系统——后台不间断做市场研究、公告扫描、政策监控并写入 KB；事件层接收需求时优先从 KB 调取已有分析，只对缺失部分启动 Agent。**

### 3.2 可衡量目标

| 目标 | V1.0 | V1.1 |
|------|------|------|
| **KB 覆盖率** | — | ≥80% 事件能从 KB 获取 ≥60% 所需分析 |
| **模板匹配率** | ≥70% | ≥85%（KB 上下文提升匹配精度） |
| **月总成本** | ~$150（每次从零跑） | ~$80（采集固定 + 事件缩减） |
| **信息全面性** | 仅分析被问到的 | 持续监控，不遗漏盘中突发 |
| **部署步骤** | `docker compose up -d` | 同 |

---

## 四、架构

### 4.1 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    接入层 — OpenClaw                          │
│  消息接收 / 报告推送（只做管道）                                │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│               分析引擎层 — TradingAgents (Python)              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  🔄 后台采集层 (Background Collectors)  ★新增         │    │
│  │  市场(30min) / 公告(1h) / 政策(2h) / 舆情(15min)     │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │ 持续写入                           │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │  📚 知识库 (KB)  ★新增                                │    │
│  │  市场快照 / 个股快照 / 公告摘要 / 政策简报 / 行业报告    │    │
│  │  向量检索 + 时效标签 (FRESH/STALE/EXPIRED)            │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │ Planner 先查 KB                   │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │  🧠 LLM Planner（事件驱动层）                          │    │
│  │  KB查询 → 模板匹配 → LLM补充 → 动态图构建               │    │
│  └───────────────────────┬─────────────────────────────┘    │
│                          │                                   │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │  👥 Agent 执行层（只跑 KB 缺失的）                     │    │
│  │  11 Agent 按需调度                                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ⏰ 双层调度                                           │    │
│  │  采集层: interval (15min/30min/1h/2h)                 │    │
│  │  事件层: cron (晨会08:50/午评12:00/复盘15:10/周日09:00)│    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 仓库改动

| 仓库 | 改动类型 | 说明 |
|------|---------|------|
| `tradingagents-cn/` | ★ 主力改动 | 新增 Collector / KB / Planner / Template / DynamicGraphBuilder / Portfolio / Scheduler |
| `tradingagents-platform/` | 精简 | 移除 Paperclip 配置、简化 docker-compose、保留 OpenClaw 配置 |

---

## 五、核心组件设计

### 5.1 目录结构

```
tradingagents-cn/tradingagents/
├── api_server.py                # ★新增：FastAPI HTTP 服务 (OpenClaw ↔ Planner)

├── collector/                    # ★新增：后台采集模块
│   ├── market_collector.py       #   市场数据（每30分钟）
│   ├── announcement_collector.py #   公告扫描（每1小时）
│   ├── policy_collector.py       #   政策监控（每2小时）
│   └── sentiment_collector.py    #   舆情采集（每15分钟）

├── kb/                           # ★新增：知识库模块
│   ├── knowledge_base.py         #   存储/检索/时效管理
│   └── freshness.py              #   时效标签管理

├── planner/                      # ★新增：Planner 模块
│   ├── llm_planner.py            #   Planner 主逻辑（含 KB 查询）
│   ├── template_matcher.py       #   模板匹配引擎
│   └── template_evolver.py       #   模板进化管理

├── graph/
│   ├── trading_graph.py          # 现有（修改：接入 Planner）
│   ├── dynamic_graph_builder.py  # ★新增：动态 LangGraph 构建
│   ├── setup.py                  # 现有（将被 DynamicGraphBuilder 替代）
│   ├── conditional_logic.py      # 现有（保留工具循环/辩论轮数）
│   ├── propagation.py            # 现有（保留状态初始化）
│   └── context_assembly.py       # 现有（保留知识上下文注入）

├── dashboard/                    # ★新增：Dashboard 模块
│   ├── agent_viz.py               #   LangRay 集成（Agent 执行可视化）
│   └── user_dashboard.py          #   用户业务看板（FastAPI + HTML）
│
├── users/                        # ★新增：多用户数据隔离
│   └── user_manager.py           #   用户命名空间管理
│
├── portfolio/                    # ★新增：持仓管理
│   └── portfolio_manager.py
│
├── scheduler/                    # ★新增：双层调度
│   └── scheduler.py              #   APScheduler (采集层+事件层)

├── templates/                    # ★新增：模板存储
│   ├── tpl_morning_briefing.json
│   ├── tpl_midday_review.json
│   ├── tpl_closing_review.json
│   ├── tpl_standard_analysis.json
│   ├── tpl_breakeven_recovery.json
│   └── tpl_weekly_screening.json

└── agents/                       # 现有：保留全部 Agent
    ├── analysts/
    ├── researchers/
    ├── risk_mgmt/
    ├── managers/
    └── trader/
```

### 5.2 后台采集层（collector/）

**职责**：不间断采集市场数据、公告、政策、舆情，结构化后写入 KB。

**设计原则**：
- 每个采集器独立异步运行，互不阻塞
- 只用轻量 LLM（quick_thinking_llm），成本极低
- 采集失败不影响事件层（标记 STALE，优雅降级）
- 每个采集器有自己的频率

```python
class BackgroundCollector:
    def __init__(self, kb: KnowledgeBase, config: dict):
        self.kb = kb
        self.quick_llm = create_llm_client(model=config["quick_think_llm"])
        self.scheduler = AsyncIOScheduler()

    def start(self):
        self.scheduler.add_job(self._collect_market, 'interval', minutes=30)
        self.scheduler.add_job(self._scan_announcements, 'interval', hours=1)
        self.scheduler.add_job(self._monitor_policy, 'interval', hours=2)
        self.scheduler.add_job(self._collect_sentiment, 'interval', minutes=15)
        self.scheduler.start()

    async def _collect_market(self):
        raw = await self._fetch_market_raw()  # AkShare
        summary = await self.quick_llm.summarize(raw,
            prompt="汇总当前市场：指数、板块轮动、资金流向、北向，3-5条要点"
        )
        self.kb.save("market_snapshot", {
            "collected_at": now(), "freshness": "FRESH", "data": summary
        })

    async def _scan_announcements(self):
        raw = await self._fetch_announcements()
        for ticker in self.watchlist + self.hot_stocks:
            if ticker in raw:
                summary = await self.quick_llm.annotate(raw[ticker])
                self.kb.save("stock_snapshot", {
                    "ticker": ticker, "latest_announcements": summary
                })

    async def _monitor_policy(self):
        raw = await self._fetch_policy_news()
        if raw and self._is_new(raw):
            analysis = await self.quick_llm.analyze(raw)
            self.kb.save("policy_brief", {
                "source": raw["source"], "title": raw["title"],
                "data": analysis, "freshness": "FRESH"
            })
```

| 采集器 | 频率 | 内容 | 单次 LLM 成本 |
|--------|------|------|:---:|
| 市场数据 | 30min | 指数/板块/资金流/北向 | ~$0.01 |
| 公告扫描 | 1h | 全市场公告 + 自选股深度解读 | ~$0.03 |
| 政策监控 | 2h | 央行/证监会/产业政策 → 影响分析 | ~$0.02 |
| 舆情采集 | 15min | 财经新闻 + 情感分析 | ~$0.005 |

### 5.3 知识库（kb/）

**职责**：存储后台采集层的所有结构化研究，为事件层提供"先查后跑"。

```python
class KnowledgeBase:
    COLLECTIONS = {
        "market_snapshot": {"freshness_ttl": 1800, "stale_ttl": 7200},
        "stock_snapshot":  {"freshness_ttl": 3600, "stale_ttl": 14400},
        "policy_brief":    {"freshness_ttl": 7200, "stale_ttl": 86400},
        "sentiment_report":{"freshness_ttl": 900,  "stale_ttl": 3600},
    }

    def query_for_event(self, trigger, context) -> KBContext:
        """事件触发时查询相关知识"""
        results = []
        # 1. 市场快照（几乎所有事件都需要）
        market = self.get_latest("market_snapshot")
        if market: results.append(market)
        # 2. 个股快照
        if context.ticker:
            stock = self.get_latest("stock_snapshot", ticker=context.ticker)
            if stock: results.append(stock)
        # 3. 相关政策
        if context.industry:
            policies = self.query("policy_brief", industry=context.industry)
            results.extend(policies)
        # 4. 计算覆盖率
        coverage = self._calculate_coverage(results, trigger)
        return KBContext(results=results, coverage=coverage,
                        missing=self._identify_gaps(results, trigger))

    def maintain_freshness(self):
        """定期降级过期数据"""
        for name, cfg in self.COLLECTIONS.items():
            for entry in self._get_all(name):
                age = (now() - entry["collected_at"]).total_seconds()
                if age > cfg["stale_ttl"]: entry["freshness"] = "EXPIRED"
                elif age > cfg["freshness_ttl"]: entry["freshness"] = "STALE"
```

**存储**：`~/.tradingagents/kb/` — 每个 collection 一个 JSON 文件 + SQLite 索引。向量检索用 SQLite-vec。

### 5.4 LLM Planner（planner/llm_planner.py）— 先查 KB 版

**新增核心流程**：

```
输入: trigger + context (持仓/自选)
  │
  ├─→ KB.query_for_event()           # ★ 0. 先查知识库
  │     输出: coverage_score + missing_aspects
  │
  ├─→ coverage ≥ 0.7?
  │     ├─ 是 → KB 结果注入 Agent context
  │     │       只对缺失部分生成 sub-plan（模板或 LLM）
  │     └─ 否 → 完整规划（模板优先 + LLM 兜底）
  │
  └─→ DynamicGraphBuilder.build(plan) → 执行 → TemplateEvolver
```

**关键接口**：

```python
class LLMPlanner:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def plan(self, trigger, context) -> WorkflowPlan:
        kb_ctx = self.kb.query_for_event(trigger, context)
        if kb_ctx.coverage >= 0.7:
            sub_plan = self._plan_missing_only(kb_ctx.missing, trigger, context)
            return self._merge_kb_with_plan(kb_ctx, sub_plan)
        else:
            match = self.template_matcher.match(trigger, context)
            return self._plan_from_match(match, trigger, context)
```

### 5.5 动态图构建器（同 V1.0）

根据 Planner 输出的 workflow JSON 在运行时动态构建 LangGraph。现有 11 个 Agent 全部按需调度，辩论轮数由 Planner 通过 `max_debate_rounds` 控制。

### 5.6 持仓管理器（同 V1.0）

`~/.tradingagents/portfolio/portfolio.yaml` — 持仓/自选/风险偏好。支持对话录入。

### 5.7 双层调度（scheduler.py）

```python
class TradingAgentsScheduler:
    def __init__(self, kb, planner, portfolio, openclaw):
        self.collector = BackgroundCollector(kb)
        self.planner = planner
        self.event_scheduler = AsyncIOScheduler()

    def start(self):
        # ★ 第一层：后台采集（interval 持续运行）
        self.collector.start()

        # ★ 第二层：事件驱动（cron）
        self.event_scheduler.add_job(self._morning_briefing,
            'cron', day_of_week='mon-fri', hour=8, minute=50)
        self.event_scheduler.add_job(self._midday_review,
            'cron', day_of_week='mon-fri', hour=12, minute=0)
        self.event_scheduler.add_job(self._closing_review,
            'cron', day_of_week='mon-fri', hour=15, minute=10)
        self.event_scheduler.add_job(self._sunday_screening,
            'cron', day_of_week='sun', hour=9, minute=0)
        self.event_scheduler.add_job(self.collector.kb.maintain_freshness,
            'interval', hours=1)
        self.event_scheduler.start()
```

### 5.8 Agent 执行可视化 — LangRay（dashboard/agent_viz.py）★新增

**职责**：提供 Agent 内部执行过程的实时可视化，面向开发者调试。

**选型理由**：LangRay 是 MIT 许可的 LangGraph 专用可视化工具，一行代码接入，零外部依赖。比 Langfuse（需要 PG+CK+Redis+S3 四容器）轻量得多，比 LangSmith（SaaS 付费）自由得多。

```python
# 一行接入，开发环境自动开启
from langray import visualize

if config.get("debug_viz", False):
    graph = visualize(
        graph,
        port=8080,
        open_browser=True
    )

# 浏览器自动打开 http://localhost:8080
```

| 功能 | 说明 |
|------|------|
| 实时节点执行流 | 哪个 Agent 正在运行、耗时多少、状态变化 |
| 状态检查器 | 点击任意节点查看完整 State（持仓/上下文/中间报告） |
| Token 追踪 | 每次运行的输入/输出 token 消耗 |
| 运行历史 | 自动保存最近 50 次运行，可回放、比较 |
| 导出 Trace | JSON 格式，可作为 GEPA 学习循环的输入 |

### 5.9 用户业务看板（dashboard/user_dashboard.py + data_exporter.py）★新增

**职责**：面向最终用户的业务概览页面——持仓、KB 状态、分析历史、成本、模板健康度。

**数据流设计**：（借鉴 PRISM-INSIGHT 的静态 JSON 管道模式）
- 每次定时任务完成后 → `data_exporter.py` 生成 `dashboard_data.json`
- 前端只读静态 JSON → 零运行时数据库依赖
- FastAPI 服务静态文件，无需额外前端框架

**页面结构**：

```
┌──────────────────────────────────────────────────────────┐
│  📊 华创量化研究院                  用户: alice | 语言: 中文 │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  💼 持仓概览                              💰 本月成本      │
│  ┌─────────────────────────┐    ┌──────────────────────┐ │
│  │ 600519 茅台  成本1850    │    │ 采集层: ¥12.50       │ │
│  │ 现价1760  浮亏-4.8% 🟡  │    │ 事件层: ¥35.20       │ │
│  │ 000858 五粮液 成本152    │    │ 总计:   ¥47.70       │ │
│  │ 现价168  浮盈+10.5% 🟢  │    └──────────────────────┘ │
│  └─────────────────────────┘                             │
│                                                          │
│  👀 自选股状态                                            │
│  002594 比亚迪  等待回调 +3.2% 🟢                          │
│  601899 紫金矿业  继续等待 -0.5% 🟡                        │
│                                                          │
│  📚 知识库状态                                            │
│  市场快照: 14:30 (FRESH ✅)  公告扫描: 15:00 (15条)        │
│  政策简报: 12:00 (2条)      舆情报告: 14:45 (FRESH ✅)     │
│                                                          │
│  📊 模板健康度                                            │
│  tpl_breakeven   92% ✅   tpl_morning    88% ✅            │
│  tpl_weekly      62% ⚠️   tpl_auto_xxx   30% 🔴           │
│                                                          │
│  📋 最近分析                               全部历史 →     │
│  [05-13 08:50] 晨报 — 五粮液偏离成本需关注                 │
│  [05-12 15:10] 收盘复盘 — 茅台企稳，明日关注1700支撑        │
│  [05-12 14:22] 客户分析 — 五粮液解套方案                   │
└──────────────────────────────────────────────────────────┘
```

**技术实现**：FastAPI + 极简 HTML 模板（v1 无前端框架依赖）。v2 可升级为 Streamlit 或 Next.js。

```python
# tradingagents/dashboard/user_dashboard.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

class UserDashboard:
    def __init__(self, portfolio_mgr, kb, archive, cost_tracker):
        self.portfolio_mgr = portfolio_mgr
        self.kb = kb
        self.archive = archive
        self.cost_tracker = cost_tracker

    def register_routes(self, app: FastAPI):
        @app.get("/", response_class=HTMLResponse)
        async def dashboard(user_id: str = "default"):
            return self._render(user_id)

        @app.get("/api/status")
        async def api_status(user_id: str = "default"):
            return self._get_status(user_id)

    def _render(self, user_id: str) -> str:
        p = self.portfolio_mgr.load(user_id)
        kb_status = self.kb.get_freshness_summary()
        briefings = self.archive.list_recent(user_id, limit=20)
        costs = self.cost_tracker.get_monthly(user_id)

        return f"""
        <!DOCTYPE html>
        <html><head><title>华创量化研究院</title>
        <meta charset="utf-8"><style>
          body {{ font-family: system-ui; max-width: 900px; margin: auto; padding: 20px; }}
          .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 12px 0; }}
          .green {{ color: #22c55e; }} .red {{ color: #ef4444; }} .warn {{ color: #f59e0b; }}
          table {{ width: 100%; border-collapse: collapse; }}
          th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #eee; }}
        </style></head><body>
          <h1>📊 华创量化研究院</h1>

          <div class="card"><h2>💼 持仓概览</h2>
            {self._render_holdings_table(p.holdings)}
          </div>

          <div class="card"><h2>👀 自选股</h2>
            {self._render_watchlist(p.watchlist)}
          </div>

          <div class="card"><h2>📚 知识库状态</h2>
            <p>市场快照: {kb_status.market_age} 前 | {kb_status.market_freshness}</p>
            <p>公告扫描: {kb_status.announcement_count} 条</p>
            <p>政策简报: {kb_status.policy_count} 条</p>
          </div>

          <div class="card"><h2>📋 最近分析</h2>
            {self._render_briefings(briefings)}
          </div>

          <div class="card"><h2>💰 本月成本: ¥{costs.total:.2f}</h2>
            <p>采集层: ¥{costs.collector:.2f} | 事件层: ¥{costs.event:.2f}</p>
          </div>
        </body></html>"""
```

### 5.10 多用户支持（users/）★新增

**设计原则**：以 user_id 为命名空间，持仓/自选/分析存档按用户隔离，知识库市场数据共享。

**数据目录结构**：

```
~/.tradingagents/
├── users/
│   ├── alice/                          # 用户 alice
│   │   ├── portfolio/
│   │   │   └── portfolio.yaml          # 持仓 + 自选
│   │   ├── templates/                  # 用户专属模板
│   │   ├── analysis-archive/           # 分析历史
│   │   ├── memory/                     # 决策记忆
│   │   └── preferences.yaml            # 风险偏好、推送偏好
│   │
│   ├── bob/
│   │   └── ...
│   │
│   └── _default/                       # 匿名用户（未登录时的默认用户）
│
├── shared/                             # ★ 所有用户共享
│   ├── kb/
│   │   ├── market_snapshots/           # 市场数据
│   │   ├── policy_briefs/              # 政策简报
│   │   └── sentiment_reports/          # 舆情报告
│   └── templates/                      # 共享模板库
│
└── config.yaml
```

**隔离规则**：

| 数据 | 隔离？ | 说明 |
|------|:---:|------|
| 持仓/自选 | ❌ 隔离 | 每个人的持仓不同 |
| 分析历史 | ❌ 隔离 | 每个人的决策记录 |
| 个性化模板 | ❌ 隔离 | 从个人使用中演化 |
| **市场快照** | ✅ 共享 | 大盘数据所有人一样 |
| **政策简报** | ✅ 共享 | 政策解读所有人一样 |
| **个股快照** | 🔀 混合 | 持仓股/自选股专属生成；热门股共享 |

**Planner 按用户加载**：

```python
class LLMPlanner:
    def plan(self, trigger, context):
        kb_ctx = self.kb.query_for_event(
            trigger, context,
            user_id=context.user_id    # ★ 按用户过滤
        )
        portfolio = self.portfolio_mgr.load(context.user_id)
        templates = self.template_matcher.for_user(context.user_id)
        ...
```

**定时任务遍历用户**：

```python
async def _morning_briefing(self):
    for user_id in self.get_active_users():
        portfolio = self.portfolio_mgr.load(user_id)
        plan = self.planner.plan(
            Trigger(type="scheduled", task="晨会"),
            Context(user_id=user_id, portfolio=portfolio)
        )
        report = await self.executor.execute(plan)
        await self.openclaw.push(report, user_id=user_id)
```

**OpenClaw user_id 透传**：

```yaml
# config/openclaw/channels.yaml
channels:
  - platform: wechat
    route_to:
      default: advisor
    # OpenClaw 自动将微信 OpenID 映射为 user_id
    user_id_field: "openid"
```

### 5.11 OpenClaw ↔ TradingAgents 交互机制（api_server.py） ★新增

**当前问题**：TradingAgents 以 `tail -f /dev/null` 运行，OpenClaw 通过系统 CLI 调用 `tradingagents batch --ticker X --date Y --output json`。CLI 模式只能传结构化参数，无法传自然语言消息，完全不兼容 LLM Planner。

**目标**：TradingAgents 启动 FastAPI 服务，OpenClaw 通过 HTTP POST 透传用户消息和 user_id。

**交互架构**：

```
用户消息 ──→ OpenClaw ──→ POST /analyze ──→ TradingAgents
                     {user_id, message, platform}    │
                                                    ├─ Planner 规划
                                                    ├─ KB 查询
                                                    ├─ 动态图执行
                                                    └─ 返回报告
                         ←── HTTP Response ─────────┘

定时报告 ──→ TradingAgents(APScheduler) ──→ POST OpenClaw /push ──→ 用户
```

**TradingAgents 侧 — api_server.py**：

```python
from fastapi import FastAPI
from pydantic import BaseModel
from .planner.schemas import Trigger, Context

app = FastAPI(title="TradingAgents API")

class AnalyzeRequest(BaseModel):
    user_id: str = "default"
    message: str
    platform: str = "unknown"

class PushToOpenclawRequest(BaseModel):
    user_id: str
    report: str
    report_type: str = "analysis"

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    trigger = Trigger(type="customer_message", message=req.message)
    context = Context(user_id=req.user_id,
                      portfolio_summary=portfolio.summary_for_planner(req.user_id))
    plan = planner.plan(trigger, context)
    graph = dynamic_builder.build(plan)
    result = graph.invoke(init_state)
    cost_tracker.record(req.user_id, "planner", model, 
                        tokens_in, tokens_out, cost, "event")
    return {"report": result.get("final_trade_decision", ""),
            "cost_usd": plan.get("estimated_cost_usd", 0),
            "plan_intent": plan.get("intent", ""),
            "generation_mode": plan.get("_generation_mode", "")}

@app.get("/health")
async def health():
    return {"status": "ok", "kb_entries": kb.count_all()}
```

**OpenClaw 侧变更 — Advisor Agent 改为 HTTP 调用**：

在 OpenClaw Advisor Agent 的配置中，不再用系统命令调用 CLI，而是 HTTP POST：

```yaml
# OpenClaw Advisor Agent 配置
tools:
  - name: call_tradingagents_analyze
    description: "将用户消息发送到 TradingAgents 分析引擎"
    http:
      method: POST
      url: "http://tradingagents:8000/analyze"
      headers:
        Content-Type: "application/json"
      body:
        user_id: "{{session.user_id}}"
        message: "{{input}}"
        platform: "{{session.platform}}"
```

**TradingAgents 主动推送报告到 OpenClaw**：

OpenClaw 原生支持 Webhook API。在 `openclaw.json` 中启用：

```json5
{ hooks: { enabled: true, token: "shared-secret", path: "/hooks" } }
```

**方式 A — `/hooks/agent`（推荐）**：触发隔离 Agent 任务，Agent 将报告投递到用户渠道。

```python
async def push_report(report: str, channel: str, target: str, report_name: str = "报告"):
    payload = {
        "message": report,
        "name": report_name,
        "deliver": True,
        "channel": channel,
        "to": target,
        "wakeMode": "now",
        "idempotencyKey": f"{report_name}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    }
    resp = await httpx.post(
        "http://openclaw:18789/hooks/agent",
        headers={"Authorization": f"Bearer {config['openclaw_hook_token']}"},
        json=payload, timeout=30
    )
    return resp.json()  # {"ok": true, "runId": "..."}
```

**方式 B — `/hooks/wake`**：轻量唤醒 Main Agent（适合简短通知）。

```python
async def wake_agent(text: str):
    await httpx.post(
        "http://openclaw:18789/hooks/wake",
        headers={"Authorization": f"Bearer {config['openclaw_hook_token']}"},
        json={"text": text, "mode": "now"}, timeout=10
    )
```

**方式 C — WebSocket JSON-RPC `send`**：直接推送消息到渠道，绕过 Agent。

```python
async def send_direct(target: str, message: str, channel: str = "telegram"):
    async with websockets.connect("ws://openclaw:18789") as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":0,"method":"connect",
            "params":{"role":"control","auth":{"token":config['gateway_token']}}}))
        await ws.recv()
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"send",
            "params":{"to":target,"message":message,"channel":channel,
                      "idempotencyKey":str(uuid4())}}))
```

**渠道与接收者格式**：

| 渠道 | `channel` 值 | `to` 格式 | 示例 |
|------|-------------|----------|------|
| Telegram 私聊 | `telegram` | 数字 chat ID | `"123456789"` |
| Telegram 群组 | `telegram` | 负数 chat ID | `"-1001234567890"` |
| 微信 | `wechat` | 微信 OpenID | `"oXXXX..."` |
| Discord | `discord` | `channel:ID` 或 `user:ID` | `"channel:123456"` |
| Slack | `slack` | `channel:ID` | `"channel:C12345"` |

**docker-compose 变更**：

```yaml
# V1.2 精简版
services:
  openclaw:
    image: ghcr.io/openclaw/openclaw:latest
    ports: ["18789:18789"]
    volumes: ["./config/openclaw:/app/config:ro"]

  tradingagents:
    build: {context: ../tradingagents-cn}
    ports: ["8000:8000"]   # ★ FastAPI
    command: ["python", "-m", "uvicorn", "tradingagents.api_server:app",
              "--host", "0.0.0.0", "--port", "8000"]
    environment:
      - OPENCLAW_URL=http://openclaw:18789
      - OPENCLAW_HOOK_TOKEN=${OPENCLAW_HOOK_TOKEN}  # ★ Webhook 认证令牌
    volumes: ["tradingagents_data:/root/.tradingagents"]
```

**交互对比**：

| | 当前（CLI） | V1.2（HTTP API） |
|---|---|---|
| TradingAgents 启动 | `tail -f /dev/null` 被动等待 | `uvicorn api_server:app` 主动服务 |
| 客户消息 | `tradingagents batch --ticker X` | `POST /analyze {message: "原文"}` |
| Planner 介入 | ❌ 不可行（只有 ticker+date） | ✅ 自然语言消息→语义理解→规划 |
| KB 查询 | ❌ 不可行 | ✅ Planner 先查 KB |
| 多用户 | ❌ 无法区分 | ✅ user_id 透传 |
| 报告推送 | `tradingagents notify feishu` | HTTP POST 到 OpenClaw `/push` |
| 调度 | 外部 cron 调 CLI | APScheduler 内置 |

---

## 六、V1.2 初始模板库

人工编写 6 个核心模板：

| 模板 | 场景 | 触发 | 核心 Agent | 辩论 | 风控 |
|------|------|------|-----------|:---:|:---:|
| `tpl_morning_briefing` | 晨会 | 定时 08:50 | KB快照 → market(预警) → pm | ❌ | ❌ |
| `tpl_midday_review` | 午评 | 定时 12:00 | KB快照 → market(异动) → risk(偏离) → pm | ❌ | ❌ |
| `tpl_closing_review` | 收盘复盘 | 定时 15:10 | KB快照 → market(归因) → pm(预案) | ❌ | ❌ |
| `tpl_standard_analysis` | 标准分析 | 客户消息 | KB快照 → 4 Analyst → Bull/Bear → Trader → Risk×3 → PM | ✅ | ✅ |
| `tpl_breakeven_recovery` | 解套方案 | 客户消息 | KB快照 → Trader(四方案) → Bull/Bear聚焦 → PM | ✅ | ❌ |
| `tpl_weekly_screening` | 周选股 | 周日 09:00 | KB快照 → sector(扫描) → fundamentals(确认) → pm | ❌ | ❌ |

---

## 七、执行流程对比

### 场景：客户问"五粮液最近跌了，怎么看？"

```
纯事件驱动（V1.0）:                 知识库驱动（V1.1）:

① Market Analyst                    ① KB 查询
   采集K线/计算指标   $0.15/3次LLM       ✅ 技术面快照（30分钟前）
② Fundamentals Analyst                  ✅ 基本面快照（1小时前）
   查财报/估值        $0.10/2次LLM       ✅ 公告摘要（1小时前）
③ News Analyst                            覆盖率: 0.85 → 只补缺失
   搜公告/新闻        $0.10/2次LLM    
④ Trader 四方案      $0.05/1次LLM    ② Trader 四方案      $0.05
⑤ Bull/Bear 辩论     $0.10/2次LLM    ③ Bull/Bear 辩论     $0.10
⑥ PM 最终方案        $0.05/1次LLM    ④ PM 最终方案        $0.05

合计: $0.55 / 11次LLM / 3分钟          合计: $0.20 / 4次LLM / 45秒
```

### 场景：晨会

```
V1.0:                                V1.1:

① Macro 隔夜外盘     $0.10          ① KB 已有 30 分钟前市场快照 + 1 小时前公告
② News 扫描公告      $0.10          ② Market 基于 KB 做持仓预警  $0.05
③ Market 持仓技术面   $0.05          ③ PM 汇总晨报              $0.05
④ PM 汇总            $0.05                
                                    合计: $0.10 （vs V1.0 $0.35）
合计: $0.35 / 6次LLM                
```

---

## 八、成本估算

```
后台采集层（固定成本，每日 8 小时交易时段）:
  市场数据: 16次 × $0.01 = $0.16
  公告扫描:  8次 × $0.03 = $0.24
  政策监控:  4次 × $0.02 = $0.08
  新闻舆情: 32次 × $0.005 = $0.16
  ─────────────────────────────
  采集层日计: ≈$0.64 → 月计 ≈$19

事件驱动层（假设 100 次客户请求 + 80 次定时任务/月）:
  有KB支撑 (110次): 110 × $0.15 = $16.50
  需完整分析 (40次): 40 × $0.40 = $16.00
  无KB支撑 (30次):   30 × $0.55 = $16.50
  ─────────────────────────────
  事件层月计: ≈$49

V1.1 总计: ≈$68/月
V1.0 总计: ≈$150+/月
节省: ≈55%
```

---

## 九、实施计划

### Phase 1 — 基础设施（第 1-2 周）

| 任务 | 描述 | 估时 |
|------|------|------|
| 1.1 | 创建 `kb/` 模块（knowledge_base.py + freshness.py） | 1 天 |
| 1.2 | 创建 `collector/` 模块骨架（4 个采集器） | 1 天 |
| 1.3 | 创建 `planner/` 模块（llm_planner + template_matcher + template_evolver + schemas） | 1 天 |
| 1.4 | 创建 `portfolio/` 模块 | 0.5 天 |
| 1.5 | 创建 `scheduler/` 模块（双层调度） | 0.5 天 |
| 1.5 | 创建 `dashboard/` 模块（agent_viz.py + user_dashboard.py） | 0.5 天 |
| 1.6 | 创建 `users/` 模块（user_manager.py + 目录结构） | 0.5 天 |
| 1.7 | 创建 `graph/dynamic_graph_builder.py` | 1 天 |
| 1.8 | 创建 `api_server.py`（FastAPI /analyze + /health 端点骨架） | 0.5 天 |

### Phase 2 — 核心功能（第 3-4 周）

| 任务 | 描述 | 估时 |
|------|------|------|
| 2.1 | 实现 BackgroundCollector（4 个采集器 + LLM 摘要） | 2 天 |
| 2.2 | 实现 KnowledgeBase（存储/检索/时效/向量索引） | 2 天 |
| 2.3 | 实现 TemplateMatcher（结合 KB 上下文的匹配打分） | 1 天 |
| 2.4 | 实现 LLMPlanner（KB 查询 + 覆盖率判断 + 补充规划） | 2 天 |
| 2.5 | 实现 DynamicGraphBuilder | 1 天 |
| 2.6 | 实现 TemplateEvolver | 1 天 |
| 2.7 | 改造 trading_graph.py（接入 Planner + KB） | 1 天 |

### Phase 3 — 集成（第 5 周）

| 任务 | 描述 | 估时 |
|------|------|------|
| 3.1 | 集成双层调度（采集层 interval + 事件层 cron） | 1 天 |
| 3.2 | 集成 PortfolioManager（与 Planner 和 KB 对接） | 0.5 天 |
| 3.3 | 集成 OpenClaw 推送（HTTP POST 到 OpenClaw /push，替代 CLI notify） | 0.5 天 |
| 3.4 | **实现 api_server.py**（FastAPI /analyze + /health 端点） | 1 天 |
| 3.4 | 对话录入持仓 | 1 天 |
| 3.5 | 集成 LangRay Agent 可视化（一行 wrap + 端口暴露） | 0.5 天 |
| 3.6 | 集成用户 Dashboard（FastAPI :8000 + HTML 页面） | 1 天 |
| 3.7 | Dashboard 静态 JSON 数据管道（data_exporter.py + crontab） | 0.5 天 |
| 3.8 | 成本追踪器（CostTracker + Dashboard 成本卡片） | 0.5 天 |
| 3.9 | 多用户数据隔离（user_id 命名空间 + KB 合并逻辑） | 1.5 天 |
| 3.10 | 用户识别透传（OpenClaw session → user_id） | 0.5 天 |
| 3.11 | 自选股数据预取（开盘前预取 OHLCV 到本地缓存） | 1 天 |
| 3.12 | 简化 tradingagents-platform（移除 Paperclip、更新 docker-compose） | 0.5 天 |
| 3.13 | 编写 6 个初始模板 JSON | 0.5 天 |

### Phase 4 — 验证（第 6 周）

| 任务 | 描述 | 估时 |
|------|------|------|
| 4.1 | 端到端测试：KB 采集 → 事件触发 → Planner 先查 KB → 补充执行 | 1 天 |
| 4.2 | 验证模板进化：模拟消息 → 新模板自动保存 → 下次精确匹配 | 1 天 |
| 4.3 | 成本测试 + 覆盖率统计 | 0.5 天 |
| 4.4 | 文档更新 | 0.5 天 |

---

## 十、风险与约束

| 风险 | 缓解 |
|------|------|
| KB 数据过期导致分析不准 | 时效标签自动降级，Planner 检测 STALE/EXPIRED 时触发重新采集 |
| 采集层 LLM 调用成本超预期 | 每个采集器可独立调整频率或关闭 |
| 动态图构建出错 | JSON Schema 校验 + 单元测试覆盖所有 Agent 组合 |
| A 股交易日历误判 | AkShare 交易日历接口 + 双重校验 |

---

## 十一、成功标准

| 标准 | V1.1 目标 |
|------|---------|
| **KB 覆盖率** | ≥80% 事件能从 KB 获取 ≥60% 所需分析 |
| **模板匹配率** | ≥85% 精确匹配 |
| **月总成本** | <$80 |
| **晨会推送** | 每个交易日 08:50 ± 2 分钟 |
| **信息全面性** | 后台持续监控，盘中突发不遗漏 |
| **Agent 可视化** | LangRay 一行接入，实时看 Agent 执行状态 |
| **用户 Dashboard** | `http://localhost:8000` 持仓/KB/成本/简报一览 |
| **多用户隔离** | 按 user_id 数据隔离，KB 共享，互不干扰 |
| **部署步骤** | `docker compose up -d` |

---

## 附录 A：Agent 能力清单

| Agent | 中文名 | 工具 | 适用场景 |
|-------|--------|------|---------|
| market_analyst | 技术面分析师 | OHLCV、MACD/RSI/BOLL | 所有分析 |
| fundamentals_analyst | 基本面分析师 | ROE/财报/估值 | 个股分析、选股 |
| news_analyst | 新闻分析师 | 公告、新闻 | 持仓预警、政策 |
| social_analyst | 舆情分析师 | 社媒情绪 | 个股分析（可选） |
| macro_analyst | 宏观研究员 | 指数、汇率、北向 | 晨会、周选股 |
| bull_researcher | 多方研究员 | 无（纯推理） | 辩论 |
| bear_researcher | 空方研究员 | 无（纯推理） | 辩论 |
| research_manager | 研究主管 | 无（纯推理） | 辩论汇总 |
| trader | 交易员 | 无（纯推理） | 四方案/交易计划 |
| risk_aggressive | 激进风控 | 无（纯推理） | 风控辩论 |
| risk_conservative | 保守风控 | 无（纯推理） | 风控辩论 |
| risk_neutral | 中立风控 | 无（纯推理） | 风控辩论 |
| portfolio_manager | 组合经理 | 无（纯推理） | 最终决策 |

## 附录 B：核心 Prompt

### B.1 Planner System Prompt

```
你是华创量化研究院的所长。职责：理解客户需求，查阅知识库，规划分析流程。

## 知识库已有内容
{KB_CONTEXT}

## 可调用的研究员
{AGENT_CATALOG}

## 规划原则
1. 优先使用知识库中已有的分析（FRESH 标记），不要重复采集
2. 仅规划和调度 KB 中缺失或已过期的分析
3. 晨会(08:50) 仅做持仓预警，不超过 3 个 Agent
4. 午评(12:00) 仅做异动和偏离度检查，不超过 2 个 Agent
5. 个股分析需要深度，解套需要四方案模拟
6. 输出严格 JSON
```

## 附录 C：PRISM-INSIGHT 借鉴清单 ★新增

基于对 PRISM-INSIGHT 项目（`dragon1086/prism-insight`）及其实时 Dashboard（`analysis.stocksimulation.kr`）的深度代码分析，以下是 6 个可直接融入本方案的借鉴点：

### C.1 数据管道模式 — Dashboard 静态 JSON 驱动

**PRISM-INSIGHT 做法**：Python `generate_dashboard_json.py` 通过 crontab 定时生成 JSON 文件，Next.js 前端只读静态文件，不连接数据库。

**借鉴实现**：

```python
# tradingagents/dashboard/data_exporter.py
class DashboardDataExporter:
    """每次定时任务完成后，自动导出 Dashboard 所需数据为静态 JSON"""
    
    def export_all(self, user_id: str):
        data = {
            "portfolio": self.portfolio_mgr.load(user_id).to_dict(),
            "kb_status": self.kb.get_freshness_summary(),
            "recent_briefings": self.archive.list_recent(user_id, limit=20),
            "costs": self.cost_tracker.get_monthly(user_id),
            "template_stats": self.template_evolver.get_stats(user_id),
            "updated_at": datetime.now().isoformat()
        }
        path = f"~/.tradingagents/users/{user_id}/dashboard_data.json"
        json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)

# 在 scheduler.py 中注册：每次晨会/午评/复盘后自动触发
self.event_scheduler.add_job(
    self._export_dashboard_data,
    'cron', day_of_week='mon-fri', hour=8, minute=55  # 晨会后 5 分钟
)
```

**收益**：Dashboard 前端零后端运行时依赖，任何静态文件服务器都能托管。

### C.2 运营成本追踪卡片

**PRISM-INSIGHT 做法**：在 README 和 Dashboard 中公开展示月度运营成本（按 API/基础设施分列）。

**借鉴实现**：在用户 Dashboard 中增加成本卡片

```python
class CostTracker:
    """追踪每次 LLM 调用的 token 和费用"""
    
    def __init__(self):
        self.db = sqlite3.connect("~/.tradingagents/costs.db")
        self.db.execute("""CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            timestamp TEXT,
            agent TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,
            category TEXT  -- 'collector' | 'event'
        )""")
    
    def record(self, user_id, agent, model, input_tokens, output_tokens, cost, category):
        self.db.execute("INSERT INTO costs ...", ...)
    
    def get_monthly(self, user_id) -> dict:
        """按类别汇总月度成本"""
        return {
            "collector": self._sum(user_id, "collector"),
            "event": self._sum(user_id, "event"),
            "total": self._sum(user_id, None)
        }
```

**Dashboard 展示**：

```
💰 本月成本: ¥68.50
├── 采集层 (市场/公告/政策/舆情): ¥19.20
├── 事件层 (客户分析/定时报告): ¥42.30
└── 规划层 (LLM Planner): ¥7.00
```

### C.3 信号/模板可靠性追踪

**PRISM-INSIGHT 做法**：`trigger-reliability-card.tsx` 追踪每个异动检测信号的最终准确率。

**借鉴实现**：在我们的 `TemplateEvolver` 基础上增加 Dashboard 可视化

```python
class TemplateEvolver:
    def get_stats(self, user_id: str) -> list:
        """返回所有模板的可靠性统计"""
        stats = []
        for tpl in self.templates.for_user(user_id):
            stats.append({
                "template_id": tpl["template_id"],
                "description": tpl["match_patterns"]["description"],
                "use_count": tpl["use_count"],
                "success_rate": tpl["success_rate"],
                "status": tpl["status"],  # verified / unverified / deprecated
                "last_used": tpl["last_used"]
            })
        return sorted(stats, key=lambda s: s["use_count"], reverse=True)
```

**Dashboard 展示**：

```
📊 模板可靠性
✅ tpl_breakeven_recovery  使用 15 次  准确率 92%  verified
✅ tpl_morning_briefing    使用 42 次  准确率 88%  verified
⚠️ tpl_weekly_screening   使用 8 次   准确率 62%  unverified
🗑️ tpl_auto_20260514      使用 3 次   准确率 25%  deprecated
```

### C.4 多语言配置

**PRISM-INSIGHT 做法**：`cores/language_config.py`（15KB），支持 5 种语言的完整翻译包。

**借鉴实现**（简化版，适合 A 股场景）：

```python
# tradingagents/config/lang.py
LANG = {
    "zh": {
        "dashboard.title": "华创量化研究院",
        "briefing.morning": "晨报",
        "briefing.midday": "午评",
        "briefing.closing": "收盘复盘",
        "portfolio.holdings": "持仓概览",
        "portfolio.watchlist": "自选股",
        "kb.status": "知识库状态",
        "kb.fresh": "新鲜",
        "kb.stale": "过时",
        "costs.monthly": "本月成本",
    },
    "en": {
        "dashboard.title": "Huachuang Quant Research",
        "briefing.morning": "Morning Briefing",
        "briefing.midday": "Midday Review",
        "briefing.closing": "Closing Review",
        "portfolio.holdings": "Portfolio",
        "portfolio.watchlist": "Watchlist",
        "kb.status": "Knowledge Base",
        "kb.fresh": "Fresh",
        "kb.stale": "Stale",
        "costs.monthly": "Monthly Costs",
    }
}

def t(key: str, lang: str = "zh") -> str:
    return LANG.get(lang, LANG["zh"]).get(key, key)
```

**使用**：Dashboard HTML 模板和 Telegram 推送消息中统一使用 `t("briefing.morning")`，语言由用户偏好决定。

### C.5 自选股数据预取

**PRISM-INSIGHT 做法**：`cores/data_prefetch.py`（12KB），在分析启动前预加载所有目标股票的 OHLCV 数据到本地缓存。

**借鉴实现**：在 `BackgroundCollector` 中增加预取逻辑

```python
class BackgroundCollector:
    async def _prefetch_watchlist_data(self):
        """开盘前预取自选股+持仓股的完整数据到本地缓存"""
        for ticker in self.watchlist + self.holdings:
            # 预取 OHLCV（60 日）
            await self._fetch_and_cache_ohlcv(ticker, days=60)
            # 预取财务数据
            await self._fetch_and_cache_financials(ticker)
            # 预取公告
            await self._fetch_and_cache_announcements(ticker)
    
    # 在 scheduler 中注册
    self.scheduler.add_job(
        self._prefetch_watchlist_data,
        'cron', day_of_week='mon-fri', hour=8, minute=30  # 开盘前 1 小时
    )
```

**收益**：客户消息触发的分析不再需要等待数据拉取，直接从本地缓存读取，分析延迟从 3 秒降到 <500ms。

### C.6 自改进闭环（已内置于 TemplateEvolver，增加 Dashboard 可视化）

PRISM-INSIGHT 的 Trading Journal 胜率反馈机制与本方案的 `TemplateEvolver` 概念完全一致。借鉴的是其**透明度设计**——不仅内部使用胜率数据，而且将每个信号的可靠性公开展示在 Dashboard 上，让用户建立信任。

**本方案已有的对应实现**：

| PRISM-INSIGHT | 本方案 V1.2 |
|---------------|------------|
| Trading Journal (SQLite) | TemplateEvolver + MemoryLog |
| trigger_reliability | template.success_rate |
| Dashboard 公开胜率 | 附录 C.3 的模板可靠性卡片 |
| 交易日志反馈决策权重 | Planner 优先匹配高 success_rate 模板 |

### C.7 借鉴点总结

| 借鉴点 | 新增/增强 | 估时 | 优先级 |
|--------|:---:|------|:---:|
| 数据管道模式（静态 JSON） | 增强 Dashboard | 0.5 天 | P0 |
| 成本追踪卡片 | 新增 | 0.5 天 | P0 |
| 模板可靠性可视化 | 增强 Dashboard | 0.5 天 | P1 |
| 多语言配置 | 新增 | 0.5 天 | P2 |
| 自选股数据预取 | 增强 Collector | 0.5 天 | P1 |
| 自改进透明度 | 已内置 | — | ✅ 已有 |

## 附录 C：PRISM-INSIGHT 借鉴清单

> 分析来源：`https://github.com/dragon1086/prism-insight` + 在线 Dashboard `https://analysis.stocksimulation.kr/`

### C.1 数据管道模式

**PRISM-INSIGHT 做法**：Dashboard 不直连数据库，Python 脚本 `generate_dashboard_json.py` 定时（每日 11:05/17:05 crontab）生成静态 JSON，Next.js 只读文件。

**借鉴到我们**：

```python
# tradingagents/dashboard/data_exporter.py
# 每次晨会/午评/复盘后自动运行
def export_dashboard_data():
    json.dump({
        "portfolio": portfolio_mgr.load(),
        "kb_status": kb.get_freshness_summary(),
        "recent_briefings": archive.list_recent(limit=20),
        "costs": cost_tracker.get_monthly(),
        "template_health": template_evolver.get_health_report(),
        "updated_at": datetime.now().isoformat()
    }, open("~/.tradingagents/dashboard/dashboard_data.json", "w"))
```

**收益**：零后端运行时依赖，前端一个 HTML 文件 + JS 读取 JSON 即可渲染。v1 不需要 Next.js/React。

---

### C.2 运营成本透明化（Operating Costs Card）

**PRISM-INSIGHT 做法**：在 README 公开月度成本明细（OpenAI $235 / Anthropic $11 / 基础设施 $30），Dashboard 有 `operating-costs-card.tsx` 组件。

**借鉴到我们的用户 Dashboard**：

```
┌──────────────────────────────────┐
│  💰 本月成本                      │
│                                  │
│  采集层:  ¥12.50                 │
│  ├─ 市场数据   ¥4.80              │
│  ├─ 公告扫描   ¥3.20              │
│  ├─ 政策监控   ¥2.40              │
│  └─ 新闻舆情   ¥2.10              │
│                                  │
│  事件层:  ¥35.20                 │
│  ├─ 客户分析   ¥22.00 (45次)     │
│  └─ 定时任务   ¥13.20 (80次)     │
│                                  │
│  📊 总计: ¥47.70 / $6.80        │
│  📈 预估月费: ~¥68              │
└──────────────────────────────────┘
```

**实现**：在 `CostTracker` 中按类别/Agent 记录每次 LLM 调用的 token 和费用，Dashboard 按日/周/月聚合展示。

---

### C.3 信号可靠性可视化（Trigger Reliability）

**PRISM-INSIGHT 做法**：`trigger-reliability-card.tsx` 追踪每个买卖信号的最终准确率，标记"可靠/不可靠"。

**借鉴到我们的 TemplateEvolver**：

```
Dashboard 展示:

  模板健康度
  ┌─────────────────────────────────────────────┐
  │ tpl_breakeven_recovery  v2  使用15次         │
  │ 最近10次准确率: ████████░░ 80%  ✅ verified   │
  │                                              │
  │ tpl_standard_analysis  v1  使用32次           │
  │ 最近10次准确率: ██████░░░░ 60%  ⚠️ stable     │
  │                                              │
  │ tpl_auto_20260514  v1  使用3次                │
  │ 最近10次准确率: ███░░░░░░░ 30%  🔴 degraded   │
  │ → 自动暂停加载，等待人工复审                    │
  └─────────────────────────────────────────────┘
```

**实现**：`TemplateEvolver.periodic_review()` 已设计 success_rate 自动审查，Dashboard 只需读取模板元数据并可视化。

---

### C.4 数据预取到缓存（Data Prefetch）

**PRISM-INSIGHT 做法**：`cores/data_prefetch.py` 在分析启动前预加载股票数据到本地缓存。

**借鉴到我们的 BackgroundCollector**：

```python
class BackgroundCollector:
    # ★ 新增：开盘前预取自选股数据
    async def prefetch_watchlist_data(self):
        """每个交易日 09:00 预取自选股 + 热门股 OHLCV 数据"""
        for ticker in self.watchlist + self.hot_stocks:
            if not self.kb.has_fresh(ticker, "ohlcv"):
                data = await self._fetch_ohlcv(ticker)
                self.kb.save("stock_snapshot", {
                    "ticker": ticker,
                    "ohlcv_cached": True,
                    "cached_at": now()
                })
```

**收益**：Agent 分析时不再等网络请求，直接从本地缓存读取 OHLCV 数据。响应时间从 3-5 秒降到 <100ms。

---

### C.5 多语言报告模板（Language Config）

**PRISM-INSIGHT 做法**：`cores/language_config.py`（14KB）支持韩/英/日/中/西 5 种语言。

**借鉴到我们**（简化版，v1 只需中英）：

```python
# tradingagents/language_config.py
LANG = {
    "morning_briefing": {
        "zh": "晨报", "en": "Morning Briefing"
    },
    "holdings_alert": {
        "zh": "⚠️ {ticker} 偏离成本线 {pct}%，需关注",
        "en": "⚠️ {ticker} deviated {pct}% from cost, attention needed"
    },
    "dashboard": {
        "title": {"zh": "华创量化研究院", "en": "Huachuang Quant Research"},
        "portfolio": {"zh": "持仓概览", "en": "Portfolio"},
        "kb_status": {"zh": "知识库状态", "en": "Knowledge Base"},
        "monthly_cost": {"zh": "本月成本", "en": "Monthly Cost"},
    }
}

def t(key: str, lang: str = "zh", **kwargs) -> str:
    """翻译指定 key，支持 {变量} 替换"""
    text = LANG.get(key, {}).get(lang, key)
    return text.format(**kwargs) if kwargs else text
```

---

### C.6 自改进的胜率反馈闭环

**PRISM-INSIGHT 做法**：Trading Journal 记录每次买卖信号的实际结果，反馈到下一次决策（`docs/TRADING_JOURNAL.md`）。

**借鉴到我们的系统**（已在 TemplateEvolver 中设计，加强可视化）：

```
PRISM-INSIGHT 做法              我们的做法 (V1.2 已设计)
─────────────────────          ──────────────────────────
交易信号 → 实际结果              执行计划 → N天后复盘
→ 更新信号触发器胜率             → 模板 success_rate 更新
→ 低胜率降低权重                 → 匹配时优先高胜率模板
                                 → Dashboard 可视化健康度

增强点:
  ✅ 模板版本管理（PRISM 无）
  ✅ 自动 degraded 暂停（PRISM 无）
  ✅ 跨用户共享优质模板（PRISM 无）
```

### C.7 借鉴实施清单

| 借鉴点 | 实现位置 | 估时 | 优先级 |
|--------|---------|------|:---:|
| 数据管道（静态 JSON） | `dashboard/data_exporter.py` | 0.5 天 | P0 |
| 成本透明卡 | `dashboard/user_dashboard.py` + `CostTracker` | 0.5 天 | P0 |
| 信号可靠性可视化 | `dashboard/user_dashboard.py` → 模板健康表 | 1 天 | P1 |
| 数据预取 | `collector/` → `prefetch_watchlist_data()` | 1 天 | P1 |
| 多语言模板 | `language_config.py` | 0.5 天 | P2 |
| 胜率反馈闭环 | `TemplateEvolver` 加强 | 已设计 | — |
