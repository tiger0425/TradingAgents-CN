> ⚠️ **本文档描述重构前（v0.2.16-cn）的架构。** `planner/`、`executor.py`、`dynamic_graph_builder.py`、`report_renderer.py`、`context_manager.py` 已在 v0.2.17-cn 图管线统一重构中删除。当前架构为 `TradingAgentsGraph.propagate()` 单一入口，详见 [docs/refactor-unified-graph-pipeline.md](refactor-unified-graph-pipeline.md)。

# 工具循环四层防护体系 (Tool Loop Prevention System)

> 版本：v0.2.11-cn | 日期：2026-06-03 | 关联 FIX：FIX-8（原始检测）+ FIX-11（根本治理）

---

## 一、问题根因分析

### 1.1 现象

在 v0.2.10 及之前版本中，分析师的工具调用频繁触发死循环检测上限：

| 分析师 | 工具数（修复前） | 触限次数 | 触发原因 |
|--------|:---:|:---:|------|
| fundamentals | 5 | 6 | 冗余工具 + 提示词矛盾 + ToolNode 不匹配 |
| market | 4 | 4~10 | LLM 反复重入工具循环 |
| news | 2~3 | 偶尔 5 | LLM 重入循环 |
| social | 4 | 偶尔 4~5 | LLM 重入循环 |

### 1.2 根因分解（10 项）

| # | 根因 | 严重度 | 文件 |
|---|------|:---:|------|
| 1 | `get_balance_sheet`/`get_cashflow`/`get_income_statement` 与 `get_fundamentals` 功能重叠，但均暴露给 LLM | 🔴 | `fundamentals_analyst.py:31-37` |
| 2 | `get_insider_transactions` 绑定给 fundamentals 但不存在于 fundamentals ToolNode → 调用必失败 | 🔴 | `fundamentals_analyst.py:36` vs `bootstrap.py:193-200` |
| 3 | 系统提示词明确要求使用全部 4 类工具 | 🔴 | `fundamentals_analyst.py:42` |
| 4 | `max_tool_calls_per_analyst=6` 太宽松（5 工具全调一次才 5 次） | 🟡 | `conditional_logic.py:22` |
| 5 | `sanitize_messages_for_deepseek` 截断上下文 → LLM 忘记已有数据 → 重复调用 | 🟡 | `agent_utils.py:149-222` |
| 6 | `route_to_vendor` 静默失败 → 空返回 → LLM 重试 | 🟡 | `interface.py:397-405` |
| 7 | `_detect_tool_loop` 的 `repeat_detected`/`alternating_no_progress` 返回 `"continue"` 但 graph 边映射中不存在该路由 | 🟡 | `conditional_logic.py:147` vs `setup.py:160-167` |
| 8 | DeepSeek thinking mode 禁用 → LLM 无推理空间做"数据已够"判断 | 🟢 | `openai_client.py:273-275` |
| 9 | `curr_date` 参数在 `get_fundamentals_a` 中未使用 → LLM 换日期重试得相同结果 | 🟢 | `a_stock_data.py:345` |
| 10 | `filter_valid_tool_calls` 过滤有效工具名但不检查 ToolNode 可用性 | 🟢 | `agent_utils.py:225-246` |

---

## 二、解决方案：四层防护体系

```
┌──────────────────────────────────────────────────────────┐
│                    Layer 1: 工具精简                       │
│         从源头消除 LLM 选择冗余 / ToolNode 不匹配           │
│   fundamentals: 5 tools → 1 tool (get_fundamentals)      │
│   移除: get_balance_sheet, get_cashflow,                  │
│         get_income_statement, get_insider_transactions     │
├──────────────────────────────────────────────────────────┤
│                  Layer 2: 智能断环                         │
│    每个分析师独立检测数据完备性 — 已够即停，不等上限          │
│   market: ≥3/4 | fundamentals: ≥2 calls |                 │
│   news: 2/2 | social: ≥3/4                                │
├──────────────────────────────────────────────────────────┤
│                 Layer 3: 定量上限 (per-analyst)            │
│      即使 Layer 2 失效，也不会超过定制上限                   │
│   f=2, m=8, n=5, s=5 | 全局默认=4                         │
├──────────────────────────────────────────────────────────┤
│                  Layer 4: 路由修复                         │
│    任何循环检测 → Msg Clear 强制终止（不再返回不存在路由）    │
│    repeat_detected → Msg Clear (修复前: "continue" bug)    │
└──────────────────────────────────────────────────────────┘
```

---

## 三、实现细节

### 3.1 Layer 1 — 工具精简

**文件**: `tradingagents/agents/analysts/fundamentals_analyst.py`

```python
# 修复前
tools = [
    get_fundamentals,
    get_balance_sheet,      # 冗余: get_fundamentals 已包含
    get_cashflow,           # 冗余
    get_income_statement,   # 冗余
    get_insider_transactions,  # 错误: 不存在于 fundamentals ToolNode
]

# 修复后
tools = [get_fundamentals]
```

系统提示词同步更新：

```
修复前: "Use the available tools: `get_fundamentals` for comprehensive
         analysis, `get_balance_sheet`, `get_cashflow`, and
         `get_income_statement` for specific financial statements."

修复后: "TOOL USAGE: You have ONE tool: `get_fundamentals`. It returns
         real-time price + full balance sheet + income statement +
         cash flow statement in a SINGLE call. Call it once, then
         analyze the results and produce your report."
```

### 3.2 Layer 2 — 智能断环

**文件**: `tradingagents/graph/conditional_logic.py`

为每个分析师添加 `should_continue_*` 前置检测钩子。

#### 通用模式

```python
def should_continue_<analyst>(self, state):
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        # 前置：如果已获取足够数据，立即断环
        if self._<analyst>_data_fully_fetched(messages):
            self._inject_break_message(state, "all_data_retrieved")
            return "Msg Clear <Analyst>"
        # 否则：运行传统死循环检测
        is_loop, reason = self._detect_tool_loop(state, "<analyst>")
        if is_loop:
            self._inject_break_message(state, reason)
            return "Msg Clear <Analyst>"  # 修复: 不再返回 "continue"
        return "tools_<analyst>"
    return "Msg Clear <Analyst>"
```

#### 各分析师检测逻辑

| Helper | 检测条件 | 工具集 |
|--------|---------|--------|
| `_fundamentals_already_fetched` | `get_fundamentals` 被调用 ≥2 次（含当前调用） | `{get_fundamentals}` |
| `_market_data_fully_fetched` | 4 工具中 ≥3 个已调用 | `{get_current_price, get_stock_data, get_indicators, get_market_context}` |
| `_news_data_fully_fetched` | 2 工具全部调用 | `{get_news, get_global_news}` |
| `_social_data_fully_fetched` | 4 工具中 ≥3 个已调用 | `{get_social_sentiment_tool, get_news, get_cls_flash, get_hot_stock_reasons}` |

**设计原理**: fundamentals 只有 1 个工具，检测"调了几次"；market/news/social 各有多个独立工具，检测"调了哪些"。阈值设在 ≥3/4 而非 4/4，因为某些环境下个别工具可能不可用（如 `get_market_context`），严格全量匹配反而会放过循环。

### 3.3 Layer 3 — Per-Analyst 定量上限

**文件**: `tradingagents/graph/conditional_logic.py`

```python
# 初始化时加载（ConditionalLogic.__init__）
self._analyst_tool_limits: dict[str, int] = {
    "fundamentals": 2,   # 1 tool + 1 retry
    "market": 8,         # 4 tools + room for retries
    "news": 5,           # 2 tools + room for retries
    "social": 5,         # 4 tools + room for retries
}
# 全局兜底
self.max_tool_calls_per_analyst = 4

# 运行时读取（_detect_tool_loop）
max_allowed = self._analyst_tool_limits.get(
    analyst_type, self.max_tool_calls_per_analyst
)
if tool_msg_count >= max_allowed:
    return True, "limit_exceeded"
```

### 3.4 Layer 4 — 路由 Bug 修复

**文件**: `tradingagents/graph/conditional_logic.py`

4 个 `should_continue_*` 方法中 `repeat_detected` / `alternating_no_progress` 原先返回 `"continue"`，但 graph 边映射中不存在该路由：

```python
# 修复前 (bug)
if is_loop:
    ...
    if reason == "limit_exceeded":
        return "Msg Clear Market"
    return "continue"   # ← 不存在于 edge map → graph 路由错误

# 修复后
if is_loop:
    ...
    return "Msg Clear Market"   # 任何循环检测 → 正确终止
```

同时降低 `max_repeat_calls` 从 3→2，使重复检测更敏锐。

---

## 四、配套修复

### 4.1 API 报告完整性

**文件**: `tradingagents/graph/executor.py`

```python
# 修复前: 仅返回第一个非空字段（~700 chars）
def _extract_report(final_state):
    for field in ("final_trade_decision", "investment_plan", "trader_investment_plan"):
        report = final_state.get(field, "")
        if report:
            return report

# 修复后: 组装全部内容（~7000 chars）
def _extract_report(final_state):
    parts = []
    for title, content in [("Market Analyst", market_report), ...]:
        if content:
            parts.append(f"--- {title} ---

{content}")
    parts.append(investment_plan)
    parts.append(trader_plan)
    parts.append(final_decision)  # (if != investment_plan)
    return "

".join(parts)
```

### 4.2 辩论安全上限收窄

**文件**: `tradingagents/graph/conditional_logic.py`

| 参数 | 修复前 | 修复后 | 说明 |
|------|:---:|:---:|------|
| 安全上限公式 | `2*max_rounds+2` | `2*max_rounds+1` | 默认 2 轮：6→5 |
| 质量阈值 | 0.3 | 0.4 | 连续两轮低于阈值 → 提前终止 |
| 硬截止 | 无 | `count ≥ 2*max+1` | 无论质量如何，强行终止 |

### 4.3 Batch 输出修复

**文件**: `cli/batch.py`

| 问题 | 修复 |
|------|------|
| 报告截断 200 字符 | 移除所有 `_truncate_text()` 调用 |
| "Fundamentals Analyst" 显示为 "Technical Analyst" | 新增 `ANALYST_AGENT_NAMES` 字典，不再复用 `ANALYST_JSON_KEYS` |

---

## 五、验证结果

API 路径连续运行 600105 分析：

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| fundamentals 触限 | 6 calls | **0** ✅ |
| market 触限 | 4→10 calls | **0** ✅ |
| news 触限 | 偶尔 | **0** ✅ |
| social 触限 | 偶尔 | **0** ✅ |
| debate 轮次 | 6 | **5** ✅ |
| `final_report` 长度 | 702 chars | **7666 chars** ✅ |
| 报告结构 | 仅结论段落 | 4 分析师报告 + 投资计划 + 交易计划 ✅ |
| "continue" 路由 | 4 处 bug | **0** ✅ |

---

## 六、修改文件清单

| 文件 | 改动类型 | 行数变化 |
|------|---------|:---:|
| `tradingagents/agents/analysts/fundamentals_analyst.py` | imports 精简, tools 5→1, 提示词重写 | -7 / +1 |
| `tradingagents/agents/utils/fundamental_data_tools.py` | docstring 扩展 | +4 |
| `tradingagents/graph/conditional_logic.py` | 4 helpers, 4 should_continue 重写, limits, 路由修复 | +100 / -15 |
| `tradingagents/graph/executor.py` | `_extract_report` 完整报告 | +22 / -12 |
| `cli/batch.py` | 截断移除, `ANALYST_AGENT_NAMES` | +8 / -8 |

---

## 七、后续优化建议

1. **`sanitize_messages_for_deepseek` 重构** — 当前截断逻辑是 LLM 重入循环的主要助推器。考虑在消息清理时保留"已获取数据摘要"而非直接丢弃。

2. **ToolNode 统一** — `bootstrap.py:193-200` 和 `trading_graph.py:196-204` 的 fundamentals ToolNode 定义不一致（6 tools vs 4 tools）。建议统一为标准集合。

3. **结构化工具返回** — 为工具响应添加 `metadata.data_type` 标记，让 LLM 能明确判断"这个数据已获取过"。

4. **`route_to_vendor` 错误传播** — 当前静默 catch 所有异常，建议在研发环境保留详细日志。
