> ⚠️ **本文档描述重构前（v0.2.16-cn）的架构。** `planner/`、`executor.py`、`dynamic_graph_builder.py`、`report_renderer.py`、`context_manager.py` 已在 v0.2.17-cn 图管线统一重构中删除。当前架构为 `TradingAgentsGraph.propagate()` 单一入口，详见 [docs/refactor-unified-graph-pipeline.md](refactor-unified-graph-pipeline.md)。

# TradingAgents LangGraph 辩论架构设计

> 版本: v1.2 | 日期: 2026-05-28 | 状态: 当前架构

---

## 目录

1. [架构总览](#一架构总览)
2. [图拓扑结构](#二图拓扑结构)
3. [AgentState 状态管理](#三agentstate-状态管理)
4. [分析师 Agent 设计](#四分析师-agent-设计)
5. [投资辩论流程](#五投资辩论流程)
6. [交易节点](#六交易节点)
7. [风险辩论流程](#七风险辩论流程)
8. [条件路由机制](#八条件路由机制)
9. [V1.2 双层架构集成](#九v12-双层架构集成)
10. [数据流全景](#十数据流全景)
11. [检查点/恢复机制](#十一检查点恢复机制)
12. [关键设计决策](#十二关键设计决策)

---

## 一、架构总览

TradingAgents 基于 LangGraph 的 `StateGraph` 构建了一个**三阶段辩论 pipeline**：

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 0: 图前装配 (trading_graph.py _run_graph)             │
│  ├─ ContextAssembler → 历史知识注入                           │
│  ├─ Market Context → 大盘环境                                 │
│  └─ A 股约束计算 → 涨跌停价格                                 │
├─────────────────────────────────────────────────────────────┤
│  Phase 1: 分析师链 (4 分析师 串行)                            │
│  Market → Social → News → Fundamentals                      │
│  每个分析师: Agent ↔ ToolNode 循环 → 消息清除 → 下一个        │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: 投资辩论 + 交易                                     │
│  Bull Researcher ↔ Bear Researcher (最多 N 轮)                │
│     → Research Manager (裁判) → investment_plan              │
│     → Trader → trader_investment_plan                        │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: 风险辩论                                            │
│  Aggressive → Conservative → Neutral (循环, 最多 N 轮)        │
│     → Portfolio Manager (裁判) → final_trade_decision        │
└─────────────────────────────────────────────────────────────┘
```

**核心设计原则**：
- 分析师负责**数据收集**（绑定工具，读取外部数据）
- 辩论 Agent 负责**观点碰撞**（纯 LLM，无工具，仅读取分析师报告）
- 管理层 Agent 负责**结构化决策**（Pydantic schema 约束输出）
- 所有决策可追溯（每条决定记录到 TradingMemoryLog）

---

## 二、图拓扑结构

### 2.1 节点定义

图在 `tradingagents/graph/setup.py` 的 `GraphSetup.setup_graph()` 中构建（第 29-182 行）。

使用 `StateGraph(AgentState)` 作为图基类，添加以下节点：

| 节点名 | 创建函数 | LLM | 工具 |
|--------|---------|:---:|------|
| Market Analyst | `create_market_analyst()` | quick | `get_stock_data`, `get_indicators`, `get_market_context` |
| Social Media Analyst | `create_social_media_analyst()` | quick | `get_social_sentiment_tool`, `get_news` |
| News Analyst | `create_news_analyst()` | quick | `get_news`, `get_global_news`, `get_insider_transactions` |
| Fundamentals Analyst | `create_fundamentals_analyst()` | quick | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` |
| Bull Researcher | `create_bull_researcher()` | quick | 无（纯 prompt） |
| Bear Researcher | `create_bear_researcher()` | quick | 无（纯 prompt） |
| Research Manager | `create_research_manager()` | **deep** | 无（使用 `with_structured_output`） |
| Trader | `create_trader()` | quick | 无（使用 `with_structured_output`） |
| Aggressive Analyst | `create_aggressive_debator()` | quick | 无（纯 prompt） |
| Conservative Analyst | `create_conservative_debator()` | quick | 无（纯 prompt） |
| Neutral Analyst | `create_neutral_debator()` | quick | 无（纯 prompt） |
| Portfolio Manager | `create_portfolio_manager()` | **deep** | 无（使用 `with_structured_output`） |

每个分析师还有两个辅助节点：
- `tools_{type}`: ToolNode（绑定 LLM 工具调用）
- `Msg Clear {Type}`: 消息清除节点（防止上下文溢出）

### 2.2 边连接

```
START
  │
  ▼
Market Analyst ←──┐
  │ 条件           │
  ├──► tools_market ──┘ (工具循环)
  │
  ▼
Msg Clear Market
  │
  ▼
Social Media Analyst ←──┐
  │ 条件                  │
  ├──► tools_social ──────┘
  │
  ▼
Msg Clear Social
  │
  ▼
News Analyst ←──┐
  │ 条件          │
  ├──► tools_news ──┘
  │
  ▼
Msg Clear News
  │
  ▼
Fundamentals Analyst ←──┐
  │ 条件                  │
  ├──► tools_fundamentals ──┘
  │
  ▼
Msg Clear Fundamentals
  │
  ▼
┌─ Bull Researcher ◄───────────┐
│    │ 条件 (should_continue_debate)  │
│    ▼                          │
│  Bear Researcher ─────────────┘
│    │ 条件
│    ▼
│  Research Manager
│    │
│    ▼
│  Trader
│    │
│    ▼
│  Aggressive Analyst ◄──────────────────┐
│    │ 条件 (should_continue_risk_analysis)│
│    ▼                                    │
│  Conservative Analyst ─────────────────┤
│    │ 条件                                │
│    ▼                                    │
│  Neutral Analyst ───────────────────────┘
│    │ 条件
│    ▼
│  Portfolio Manager
│    │
│    ▼
│  END
```

### 2.3 分析师顺序

分析师始终按固定顺序串行执行：`Market → Social → News → Fundamentals`。这由 `setup_graph()` 第 112-134 行的循环控制。每个分析师完成工具循环并清除消息后，硬边连接到下一个。

---

## 三、AgentState 状态管理

定义在 `tradingagents/agents/utils/agent_states.py`。

### 3.1 AgentState（继承 MessagesState）

```python
class AgentState(MessagesState):
    # === 上下文信息 ===
    company_of_interest: str          # 股票代码
    trade_date: str                   # 分析日期
    sender: str                       # 消息发送方标识
    
    # === 分析师报告 (Phase 1 产出) ===
    market_report: str                # Market Analyst 写入
    sentiment_report: str             # Social Media Analyst 写入
    news_report: str                  # News Analyst 写入
    fundamentals_report: str          # Fundamentals Analyst 写入
    market_context: str               # 大盘环境文本 (图前注入)
    
    # === 投资辩论 (Phase 2 读写) ===
    investment_debate_state: InvestDebateState   # Bull/Bear/RM 共享子状态
    investment_plan: str             # Research Manager 写入
    
    # === 交易 (Phase 2 产出) ===
    trader_investment_plan: str       # Trader 写入
    
    # === 风险辩论 (Phase 3 读写) ===
    risk_debate_state: RiskDebateState  # 三方风控共享子状态
    final_trade_decision: str         # Portfolio Manager 写入 (最终输出)
    
    # === 知识注入 ===
    past_context: str                 # 历史决策上下文 (TradingMemoryLog)
    knowledge_context: dict           # 结构化知识 (ContextAssembler)
    
    # === A 股特有 ===
    market_type: str                  # "A_SHARE" | "US_STOCK"
    benchmark_ticker: str             # 基准指数 (默认 "000300")
    limit_up_price: float             # 涨停价
    limit_down_price: float           # 跌停价
    position_opened_date: str         # 开仓日期
    
    # === 持仓状态 ===
    cost_price: float                 # 成本价
    quantity: int                     # 持仓数量
    position_pnl: float               # 浮动盈亏
    position_pnl_pct: Optional[float] # 浮动盈亏百分比
```

### 3.2 InvestDebateState（投资辩论子状态）

```python
class InvestDebateState(TypedDict):
    bull_history: str          # Bull 独家发言记录
    bear_history: str          # Bear 独家发言记录
    history: str               # 完整辩论记录
    current_response: str      # 最新发言 (用于路由: 以 "Bull..." 开头 → Bear)
    judge_decision: str        # Research Manager 最终判定
    count: int                 # 发言轮次计数器
```

### 3.3 RiskDebateState（风险辩论子状态）

```python
class RiskDebateState(TypedDict):
    aggressive_history: str           # Aggressive 独家发言
    conservative_history: str         # Conservative 独家发言
    neutral_history: str              # Neutral 独家发言
    history: str                      # 完整辩论记录
    latest_speaker: str               # 最近发言者 (用于路由: Agr→Cons→Neut→Agr)
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str               # Portfolio Manager 最终判定
    count: int                        # 发言轮次计数器
```

---

## 四、分析师 Agent 设计

### 4.1 Market Analyst（技术面分析师）

**文件**: `tradingagents/agents/analysts/market_analyst.py`

| 维度 | 内容 |
|------|------|
| LLM | `quick_thinking_llm` |
| 工具 | `get_stock_data()`, `get_indicators()`, `get_market_context()` |
| 摄入 | `trade_date`, `company_of_interest`, `messages`, `market_context` |
| 产出 | `market_report` (写入 state) |
| 核心职责 | K线形态、均线系统、MACD/RSI/BOLL 等技术指标分析 |

**执行模式**: Agent → 调用 `get_stock_data` 获取日K线 → 调用 `get_indicators` 计算技术指标 → 生成 Markdown 格式报告。工具调用循环由条件路由控制：如果 LLM 返回 `tool_calls`，路由到 `tools_market`，执行后返回 Agent 继续。

**Prompt 特点**:
- 选最多 8 个互补指标（MA/MACD/RSI/Boll/ATR/VWMA）
- 要求先 `get_stock_data` 再 `get_indicators`
- 调用 `get_market_context` 了解大盘环境
- 末尾要求 Markdown 表格
- 声明"你不是最终交易决策者"

### 4.2 Fundamentals Analyst（基本面分析师）

**文件**: `tradingagents/agents/analysts/fundamentals_analyst.py`

| 维度 | 内容 |
|------|------|
| LLM | `quick_thinking_llm` |
| 工具 | `get_fundamentals()`, `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()`, `get_insider_transactions()` |
| 产出 | `fundamentals_report` |

**核心职责**: PE/PB/ROE/毛利率/净利率等财务指标 + 三大报表 + 股东增减持。

### 4.3 News Analyst（新闻分析师）

**文件**: `tradingagents/agents/analysts/news_analyst.py`

| 维度 | 内容 |
|------|------|
| 工具 | `get_news()`, `get_global_news()`, `get_insider_transactions()` |
| 产出 | `news_report` |

**核心职责**: 公告解读、新闻事件影响、行业政策跟踪。

**Prompt 特点**:
- 搜索策略两步走：先 `get_global_news` 后 `get_news`
- 三级信源可信度：官方公告 > 权威财经媒体 > 一般新闻
- 要求交叉验证和降级策略

### 4.4 Social Media Analyst（舆情分析师）

**文件**: `tradingagents/agents/analysts/social_media_analyst.py`

| 维度 | 内容 |
|------|------|
| 工具 | `get_social_sentiment_tool()`, `get_news()` |
| 产出 | `sentiment_report` |

**核心职责**: A 股散户行为指标——关注指数、参与意愿度、实时热度排名、雪球/东财跨平台对比。

**数据来源**: 行为指标（非帖子内容），来自 akshare 的 `stock_comment_em`、`stock_hot_rank_detail_realtime_em` 等接口。

---

## 五、投资辩论流程

### 5.1 辩论拓扑

```
Bull Researcher ──► Bear Researcher
      ▲                   │
      │    条件路由         │ 条件路由
      └───────────────────┘
              │ (count ≥ 2×max_debate_rounds)
              ▼
       Research Manager
```

### 5.2 Bull Researcher（多方研究员）

**文件**: `tradingagents/agents/researchers/bull_researcher.py`

| 维度 | 内容 |
|------|------|
| LLM | `quick_thinking_llm`（纯 prompt，无工具） |
| 摄入 | 4 份分析师报告 + `market_context` + `investment_debate_state` |
| 产出 | 更新 `bull_history`, `history`, `current_response`, `count` |

**轮次感知机制**:
- **首轮** (`count == 0`): 独立分析，提示词注入 `"No argument yet — this is the opening round"`
- **驳斥轮** (`count > 0`): 引用对手论点，提示词注入 `"Last bear argument: {current_response}"`

**强制输出格式**: 每轮必须输出 `**本轮核心证据:**` 段落（1-2 句话，引用具体数字）。

**上下文保护**: 历史超过 20 行时截断为最近 20 行（约 2 轮），防止 prompt 膨胀。

### 5.3 Bear Researcher（空方研究员）

**文件**: `tradingagents/agents/researchers/bear_researcher.py`

与 Bull Researcher 完全对称：
- 相同的轮次感知 + 强制输出格式 + 上下文保护
- 驳斥轮注入 `"Last bull argument: {current_response}"`

### 5.4 Research Manager（研究主管 / 裁判）

**文件**: `tradingagents/agents/managers/research_manager.py`

| 维度 | 内容 |
|------|------|
| LLM | `deep_thinking_llm` |
| 结构化输出 | `ResearchPlan` (Pydantic) |
| 评级 | Buy / Overweight / Hold / Underweight / Sell |
| 产出 | `investment_plan` (写入 state) |

**证据锚定规则**（核心创新）:
```
1. 提取 Bull 的"本轮核心证据"
2. 提取 Bear 的"本轮核心证据"
3. 比较: 可验证性、时效性、与价格方向的相关性
4. 裁决必须引用哪一方更有说服力
```

**回退机制**: 若 LLM 不支持 `with_structured_output`（如 DeepSeek），回退到自由文本 + `render_research_plan()` 渲染。

### 5.5 辩论轮次控制

默认配置 `max_debate_rounds=1`：

| 轮次 | 发言者 | count 值 | 路由 |
|:---:|------|:---:|------|
| 1 | Bull (首轮) | 1 | → Bear |
| 2 | Bear (驳斥) | 2 | count ≥ 2*1=2 → Research Manager |

若 `max_debate_rounds=2`，则 Bull→Bear→Bull→Bear→Research Manager。

---

## 六、交易节点

### Trader（交易员）

**文件**: `tradingagents/agents/trader/trader.py`

| 维度 | 内容 |
|------|------|
| LLM | `quick_thinking_llm` |
| 结构化输出 | `TraderProposal` (Pydantic): `action`(Buy/Hold/Sell), `reasoning`, `entry_price`, `stop_loss`, `position_sizing` |
| 产出 | `trader_investment_plan` |

**核心职责**: 将 Research Manager 的方向性建议转化为具体交易操作。

**信号冲突解决规则**:
- 基本面分析 > 技术面分析 > 新闻/舆情
- 矛盾严重时选择 Hold 并标注原因

**价格约束**: entry_price 必须在涨跌停范围内（`limit_up_price` / `limit_down_price`）。

---

## 七、风险辩论流程

### 7.1 辩论拓扑

```
Aggressive ──► Conservative ──► Neutral
    ▲                              │
    │       条件路由                 │ 条件路由
    └──────────────────────────────┘
                   │ (count ≥ 3×max_risk_discuss_rounds)
                   ▼
            Portfolio Manager
```

### 7.2 三个风控角色

| 角色 | 文件 | 立场 |
|------|------|------|
| Aggressive | `risk_mgmt/aggressive_debator.py` | 积极寻找高回报机会，挑战保守派过度谨慎 |
| Conservative | `risk_mgmt/conservative_debator.py` | 保护资产、最小化波动，质疑激进派过度乐观 |
| Neutral | `risk_mgmt/neutral_debator.py` | 平衡视角，同时挑战两方极端观点 |

三个角色共享相同的结构模式：
- LLM: `quick_thinking_llm`（纯 prompt，无工具）
- 轮次感知 + 对手引用 + 强制新证据 + 上下文截断
- 趋同认可：如果关键维度达成共识，坦诚承认而非强行制造分歧

### 7.3 Portfolio Manager（组合经理 / 裁判）

**文件**: `tradingagents/agents/managers/portfolio_manager.py`

| 维度 | 内容 |
|------|------|
| LLM | `deep_thinking_llm` |
| 结构化输出 | `PortfolioDecision` (Pydantic): `rating`, `executive_summary`, `investment_thesis`, `price_target`, `time_horizon` |
| 产出 | `final_trade_decision`（最终输出） |

**摄入信息**（最全面的上下文）:
- 4 份分析师报告
- 投资辩论结果 (Bull/Bear history + Research Manager 判定)
- Trader 交易方案
- 风险辩论全部历史
- A 股约束（涨跌停/T+1）
- 历史经验教训 (past_context)
- 存档分析摘要 (knowledge_context)
- 大盘市场环境 (market_context)

### 7.4 风险辩论轮次控制

默认 `max_risk_discuss_rounds=1`：

| 轮次 | 发言者 | latest_speaker | 路由 |
|:---:|------|------|------|
| 1 | Aggressive (首轮) | "Aggressive" | → Conservative |
| 2 | Conservative (驳斥) | "Conservative" | → Neutral |
| 3 | Neutral (驳斥) | "Neutral" | count ≥ 3*1=3 → Portfolio Manager |

---

## 八、条件路由机制

定义在 `tradingagents/graph/conditional_logic.py`。

### 8.1 分析师工具循环

```python
def should_continue_market(state):
    if last_message.tool_calls:
        return "tools_market"       # 继续工具调用
    return "Msg Clear Market"       # 分析完成，清除消息
```

四个分析师使用相同的模式（`should_continue_market/social/news/fundamentals`）。

### 8.2 投资辩论路由

```python
def should_continue_debate(state) -> str:
    debate = state["investment_debate_state"]
    if debate["count"] >= 2 * self.max_debate_rounds:
        return "Research Manager"           # 辩论结束
    if debate["current_response"].startswith("Bull"):
        return "Bear Researcher"            # Bull 刚发完 → 轮到 Bear
    return "Bull Researcher"                # Bear 刚发完 → 轮到 Bull
```

**路由原理**: 依赖 `current_response` 的文本前缀。Bull 发言以 `"Bull Analyst: ..."` 开头 → 路由到 Bear；Bear 发言以 `"Bear Analyst: ..."` 开头 → 路由到 Bull。

### 8.3 风险辩论路由

```python
def should_continue_risk_analysis(state) -> str:
    risk = state["risk_debate_state"]
    if risk["count"] >= 3 * self.max_risk_discuss_rounds:
        return "Portfolio Manager"               # 辩论结束
    if risk["latest_speaker"].startswith("Aggressive"):
        return "Conservative Analyst"            # Aggressive → Conservative
    if risk["latest_speaker"].startswith("Conservative"):
        return "Neutral Analyst"                 # Conservative → Neutral
    return "Aggressive Analyst"                  # Neutral → Aggressive
```

**路由原理**: 依赖显式的 `latest_speaker` 状态字段，强制固定旋转 `Aggressive → Conservative → Neutral → Aggressive`。

### 8.4 轮次配置

| 参数 | 默认值 | 含义 | 所在位置 |
|------|:---:|------|------|
| `max_debate_rounds` | 1 | 投资辩论 Bull↔Bear 来回次数 | `default_config.py` |
| `max_risk_discuss_rounds` | 1 | 风控辩论 3 方循环次数 | `default_config.py` |

默认配置下：Bull→Bear→RM（2次发言），Aggressive→Conservative→Neutral→PM（3次发言）。

---

## 九、V1.2 双层架构集成

### 9.1 架构概览

V1.2 在 V1.0 静态图的**上层**增加了双层调度：

```
┌─────────────────────────────────────────────────┐
│  接入层 — OpenClaw / HTTP API                     │
├─────────────────────────────────────────────────┤
│  分析引擎层                                       │
│                                                  │
│  🔄 后台采集层 (Scheduler)                        │
│  ├─ MarketDataCollector (30min)                   │
│  ├─ SentimentCollector (15min)                    │
│  ├─ AnnouncementCollector (1h)                    │
│  ├─ PolicyCollector (2h)                          │
│  └─ PrefetchManager (09:00 开盘前)                │
│         │ 持续写入                                │
│  ┌──────▼──────────────────────────────┐         │
│  │  📚 知识库 (KB)                       │         │
│  │  时效标签: FRESH → STALE → EXPIRED    │         │
│  └──────┬──────────────────────────────┘         │
│         │                                         │
│  ┌──────▼──────────────────────────────┐         │
│  │  🧠 LLM Planner                       │         │
│  │  KB 查询 → 模板匹配 → LLM 生成         │         │
│  └──────┬──────────────────────────────┘         │
│         │                                         │
│  ┌──────▼──────────────────────────────┐         │
│  │  ⚙️ DynamicGraphBuilder               │         │
│  │  按 Plan 动态装配 LangGraph            │         │
│  └──────┬──────────────────────────────┘         │
│         │                                         │
│  ┌──────▼──────────────────────────────┐         │
│  │  👥 Agent 执行层 (LangGraph 辩论)      │         │
│  │  12 LLM Agent 按需调度                 │         │
│  └──────────────────────────────────────┘         │
└─────────────────────────────────────────────────┘
```

### 9.2 LLM Planner 三级决策策略

**文件**: `tradingagents/planner/llm_planner.py`

```
Level 1: KB 覆盖率 ≥ 70% → 仅调 portfolio_manager（$0.10）
Level 2: 模板精确/模糊匹配 → 按模板 workflow 执行
Level 3: 全部失败 → LLM 生成 Plan / fallback
```

### 9.3 六模板系统

定义在 `tradingagents/templates/tpl_*.json`：

| 模板 | 场景 | Agent 数量 | 含辩论 | KB 覆盖率阈值 |
|------|------|:---:|:---:|:---:|
| `morning_briefing` | 晨会 08:50 | 4 | ❌ | 0.6 |
| `midday_review` | 午评 12:00 | 3 | ❌ | 0.5 |
| `closing_review` | 收盘复盘 15:10 | 2 | ❌ | 0.5 |
| `standard_analysis` | 个股分析 | 12 | ✅ 投资+风控 | 0.7 |
| `breakeven_recovery` | 解套方案 | 8 | ✅ 投资 | 0.6 |
| `weekly_screening` | 周日选股 | 4 | ❌ | 0.5 |

### 9.4 DynamicGraphBuilder

**文件**: `tradingagents/graph/dynamic_graph_builder.py`

根据 Plan 的 `workflow` 步骤列表动态组装 LangGraph 节点和边：
- 每个步骤的 `agent` 字段通过 `_agent_factory()` 映射到对应创建函数
- `research_manager` 和 `portfolio_manager` 使用 `deep_llm`，其余使用 `quick_llm`
- 根据 `depends_on` 列表建立步骤间的有向边
- 为分析师 agent 自动创建工具循环边

### 9.5 ContextAssembler

**文件**: `tradingagents/graph/context_assembly.py`

在图执行前装配历史知识到 `knowledge_context`：

| 数据源 | 获取方式 | 限制 |
|------|---------|:---:|
| 历史分析存档 | `AnalysisArchive.list(ticker, limit=5)` | 最近 30 天 |
| 过往交易决策 | `TradingMemoryLog.get_past_context(n_same=5, n_cross=3)` | 同标 5 条 + 跨标 3 条 |
| 信号摘要 | `_summarize_signals(ticker)` | 30 天 |
| 经验教训 | `_extract_lessons()` | 最多 10 条 |
| 置信度标签 | `_compute_confidence(ticker)` | CONFIRMED/SINGLE/CONFLICTING/STALE/DERIVED |

**置信度规则**:
- `CONFIRMED`: 近 30 天 ≥3 个同方向信号
- `SINGLE`: 仅 1 条分析记录
- `CONFLICTING`: 近 30 天同时有买/卖信号
- `STALE`: 最后分析 > 90 天前
- `DERIVED`: 跨标推导（预留）

---

## 十、数据流全景

### 10.1 从触发到最终决策的完整链路

```
1. 触发 (Trigger)
   ├─ customer_message: "茅台最近走势分析"  ← POST /analyze
   └─ scheduled: 晨会/午评/收盘             ← Scheduler cron

2. Context 构建
   ├─ user_id, ticker, portfolio_summary
   └─ market_context (fetch_market_context + 缓存)

3. Planner (LLMPlanner.plan)
   ├─ KB.query_for_event() → coverage_score
   ├─ TemplateMatcher.match() → exact/fuzzy/no_match
   └─ → WorkflowPlan { steps: [...] }

4. Executor (GraphExecutor.execute)
   ├─ ContextAssembler.assemble() → knowledge_context
   ├─ Propagator.create_initial_state() → AgentState
   │   ├─ InvestDebateState { count=0, ... }
   │   ├─ RiskDebateState { count=0, ... }
   │   ├─ knowledge_context (结构化历史知识)
   │   ├─ past_context (TradingMemoryLog 文本)
   │   ├─ A 股约束 (limit_up_price, limit_down_price)
   │   └─ 持仓上下文 (cost_price, quantity)
   └─ DynamicGraphBuilder.build(plan) → compiled graph

5. 图执行 (graph.invoke)
   │
   ├── 分析师并行 (Phase 1)
   │   ├─ Market Analyst → market_report
   │   ├─ Fundamentals → fundamentals_report
   │   ├─ News Analyst → news_report
   │   └─ Social Analyst → sentiment_report
   │
   ├── 投资辩论 (Phase 2)
   │   ├─ Bull Researcher → bear (路由)
   │   ├─ Bear Researcher → bull (路由)
   │   ├─ ... (最多 N 轮)
   │   └─ Research Manager → investment_plan
   │
   ├── 交易 (Phase 2)
   │   └─ Trader → trader_investment_plan
   │
   ├── 风险辩论 (Phase 3)
   │   ├─ Aggressive → conservative (路由)
   │   ├─ Conservative → neutral (路由)
   │   ├─ Neutral → aggressive (路由)
   │   ├─ ... (最多 N 轮)
   │   └─ Portfolio Manager → final_trade_decision
   │
   └── 最终输出: final_trade_decision

6. 后处理
   ├─ SignalProcessor.parse_rating() → "Buy"/"Hold"/"Sell"
   ├─ save_to_archive() → AnalysisArchive
   ├─ store_decision() → TradingMemoryLog
   └─ _auto_update_position() (A 股模式)
```

### 10.2 各阶段关键状态字段流向

```
Phase 0 (图前):
  ContextAssembler ──► knowledge_context ──► AgentState
  fetch_market_context ──► market_context ──► AgentState
  get_limit_prices ──► limit_up/down ──► AgentState

Phase 1 (分析师):
  Market Analyst ──► market_report ──► AgentState
  Social Analyst ──► sentiment_report ──► AgentState
  News Analyst ──► news_report ──► AgentState
  Fundamentals ──► fundamentals_report ──► AgentState

Phase 2 (投资辩论):
  Bull ──► investment_debate_state { bull_history, current_response, count++ }
  Bear ──► investment_debate_state { bear_history, current_response, count++ }
  RM ──► investment_debate_state { judge_decision }
       ──► investment_plan ──► AgentState

Phase 2 (交易):
  Trader ──► trader_investment_plan ──► AgentState

Phase 3 (风险辩论):
  Aggressive ──► risk_debate_state { aggressive_history, latest_speaker, count++ }
  Conservative ──► risk_debate_state { conservative_history, latest_speaker, count++ }
  Neutral ──► risk_debate_state { neutral_history, latest_speaker, count++ }
  PM ──► risk_debate_state { judge_decision }
      ──► final_trade_decision ──► AgentState (最终输出)
```

---

## 十一、检查点/恢复机制

### 11.1 架构

**文件**: `tradingagents/graph/checkpointer.py`

```
每个 ticker → 独立 SQLite 数据库
  ~/.tradingagents/cache/checkpoints/{TICKER}.db

thread_id = sha256("{TICKER}:{DATE}")[:16]
→ 同 ticker+date 始终对应同一 thread_id
```

### 11.2 启用方式

在 config 中设置 `checkpoint_enabled: true`，并在 `propagate()` 中：

```python
# trading_graph.py:416-431
if self.config.get("checkpoint_enabled"):
    with get_checkpointer(data_dir, ticker) as saver:
        self.graph = self.workflow.compile(checkpointer=saver)
        step = checkpoint_step(data_dir, ticker, date)
        # step 非 None → 从上次中断节点恢复
```

### 11.3 恢复原理

LangGraph 内置机制：`graph.invoke()` 如果检测到已有检查点，自动从上次成功节点之后恢复，跳过已执行节点。

### 11.4 生命周期

1. 启用 → 每次 `propagate()` 调用时重新编译图（带 `SqliteSaver`）
2. 执行 → LangGraph 自动在每步后写入检查点
3. 成功完成 → `clear_checkpoint()` 清除 SQLite 记录
4. 崩溃 → 下次同 ticker+date 调用自动恢复

### 11.5 限制

- 仅在 V1.0 静态图模式 (`propagate()`) 中可用
- V1.2 动态图模式 (`GraphExecutor`) 未集成检查点
- 需要 `langgraph-checkpoint-sqlite` 包
- 缺失时回退到 `MemorySaver`（无持久化）

---

## 十二、关键设计决策

### 12.1 两级 LLM 策略

| LLM 级别 | 使用场景 | 原因 |
|---------|---------|------|
| `deep_thinking_llm` | Research Manager, Portfolio Manager | 需要复杂推理和结构化决策 |
| `quick_thinking_llm` | 所有其他 Agent | 成本优化，快速响应 |

### 12.2 消息清除机制

每个分析师完成后清除非系统消息，防止上下文膨胀：
- `create_msg_delete()` 使用 LangGraph 的 `RemoveMessage`
- 仅保留 `market_context` 等系统注入消息

### 12.3 结构化输出 + 回退

三个管理层 Agent 支持 Pydantic 结构化输出（`with_structured_output`）：
- OpenAI/Anthropic: 原生支持
- DeepSeek: 回退到自由文本 + 确定性解析
- 通过 `parse_rating()` 提取 5 级评级（无需额外 LLM 调用）

### 12.4 上下文窗口保护

所有辩论 Agent 实施相同的上下文保护策略：
- 历史超过 20 行 → 截断为最近 20 行（约 2 轮辩论）
- 首轮不引用不存在的对手论点（避免幻觉）

### 12.5 A 股特化

- 涨跌停约束注入 Trader 和 Portfolio Manager
- T+1 规则注入 Portfolio Manager
- 交易日历感知（非交易日自动跳过调度）
- 科创板/创业板/北交所差异化涨跌停比例

---

## 附录：文件索引

| 模块 | 文件 | 行数 | 职责 |
|------|------|:---:|------|
| 图拓扑 | `graph/setup.py` | 182 | GraphSetup, 节点+边定义 |
| 图编排 | `graph/trading_graph.py` | 738 | TradingAgentsGraph, 初始化+执行 |
| 路由 | `graph/conditional_logic.py` | 67 | 7 个条件路由方法 |
| 状态传播 | `graph/propagation.py` | 81 | 初始状态构造 |
| 知识装配 | `graph/context_assembly.py` | ~400 | ContextAssembler, 置信度标签 |
| 动态图 | `graph/dynamic_graph_builder.py` | ~170 | Plan→LangGraph 动态组装 |
| 执行器 | `graph/executor.py` | ~260 | Plan→Graph 执行桥梁 |
| 信号处理 | `graph/signal_processing.py` | 31 | 5 级评级提取 |
| 检查点 | `graph/checkpointer.py` | 106 | SQLite 检查点/恢复 |
| 反思 | `graph/reflection.py` | 54 | 延迟复盘反思 |
| Planner | `planner/llm_planner.py` | ~150 | 三级决策管线 |
| Schema | `planner/schemas.py` | ~60 | Trigger/Context/WorkflowPlan |
| 模板匹配 | `planner/template_matcher.py` | 113 | 关键词+KB 增强匹配 |
| 模板进化 | `planner/template_evolver.py` | ~70 | 成功率动态加权 |
| API | `api_server.py` | 254 | FastAPI 端点 |
| 引导 | `bootstrap.py` | ~100 | 启动装配+DI |
| KB | `kb/knowledge_base.py` | 206 | 5 集合 KB + 覆盖率计算 |
| 时效 | `kb/freshness.py` | 103 | FRESH→STALE→EXPIRED |
| 调度 | `scheduler/scheduler.py` | ~200 | 双层调度 (interval+cron) |
| 状态 | `agents/utils/agent_states.py` | 93 | AgentState + 2 子状态 |
| 工具 | `agents/utils/agent_utils.py` | ~120 | 工具重导出+语言+降级策略 |
| Schema | `agents/schemas.py` | 242 | ResearchPlan/TraderProposal/PortfolioDecision |
| 多头 | `agents/researchers/bull_researcher.py` | 96 | Bull 辩论 Agent |
| 空头 | `agents/researchers/bear_researcher.py` | 98 | Bear 辩论 Agent |
| 研究主管 | `agents/managers/research_manager.py` | 85 | 投资辩论裁判 |
| 交易员 | `agents/trader/trader.py` | 124 | 交易方案生成 |
| 组合经理 | `agents/managers/portfolio_manager.py` | 147 | 最终决策 |
| 激进风控 | `agents/risk_mgmt/aggressive_debator.py` | 81 | 激进风控方 |
| 保守风控 | `agents/risk_mgmt/conservative_debator.py` | 83 | 保守风控方 |
| 中性风控 | `agents/risk_mgmt/neutral_debator.py` | 81 | 中性风控方 |
