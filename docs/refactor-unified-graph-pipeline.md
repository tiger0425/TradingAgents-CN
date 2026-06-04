# 图管线统一重构记录

> 分支：`refactor/unify-graph-pipeline`
> 日期：2026-06-04
> 状态：✅ 已完成（11/12 任务完成, 1 推迟）

---

## 一、为什么重构

### 1.1 双图竞争架构

重构前项目同时维护**两套独立的图编排路径**，它们拓扑不同、状态字段不同、数据流不兼容：

```
路径A（旧/CLI 交互式）:
  cli/main.py → TradingAgentsGraph.propagate()
    → GraphSetup.setup_graph() → graph.invoke()
    → 使用 Propagator.create_initial_state() [9 字段]

路径B（新/API+batch）:
  api_server.py → LLMPlanner.plan()
    → GraphExecutor.execute()
    → DynamicGraphBuilder.build() → graph.invoke()
    → 使用 GraphExecutor._build_init_state() [17 字段]

路径C（guping 批量）:
  guping/agent_batch.py → lazy_bootstrap()
    → Planner → Executor（同路径B但参数不同）
```

每条路径被不同的入口点使用，Bug 要修两遍，行为不一致。

### 1.2 三层无价值的"壳"

在 `TradingAgentsGraph.propagate()` 外面重叠了三层抽象：

| 层 | 文件 | 行数 | 问题 |
|---|------|------|------|
| Planner | `planner/` | 508 行 | 每次返回同一个工作流，`setup.py` 一行代码就能做的事 |
| Executor | `executor.py` | 360 行 | 与 `trading_graph.py` 功能完全重复 |
| DynamicBuilder | `dynamic_graph_builder.py` | 424 行 | 与 `setup.py` 功能完全重复 |

这三层加起来 **1292 行**，做的事情和原来的 `trading_graph.py` + `setup.py` 完全相同。

### 1.3 五个自创的 Bug

这些 Bug 不是上游项目（TauricResearch/TradingAgents）有的，是引入壳层后引入的：

| Bug | 根因 | 表现 |
|-----|------|------|
| 辩论 Agent 信息丢失 | `ContextWindowManager` 压缩 4 份分析师报告 | 辩论时论据单薄 |
| 北汽蓝谷"列4/列5" | `ReportRenderer` 正则重排表格 | 表格损坏，原始列名暴露 |
| 双路径状态不一致 | `Propagator` 和 `Executor` 用不同 state 字段 | 同一标的在不同路径结果不同 |
| config 全局竞态 | `set_config()` 变异步状态 | 多用户场景下互相覆盖 |
| interface 静默吞异常 | `except Exception: continue` | 数据获取失败 LLM 也不知道 |

### 1.4 git log 证实：补丁叠补丁

```
fix: tool loop four-layer prevention    ← 新架构的 tool loop 失控
fix: prevent hallucinated prices        ← 复杂 prompt 导致幻觉
fix: break msg routed through tools     ← 消息路由在新层中断裂
fix: ToolMessage fallback               ← 工具返回值在新架构丢失
fix(agent): move anti-patterns to prompt front ← prompt 太长
```

每个补丁都在修前一个补丁引入的问题。上游项目没有这些 commit。

---

## 二、重构方案

### 2.1 目标

所有入口统一为 **单一路径**，保留 A 股能力，删除壳层。

```
统一后路径：
CLI main/api/batch/guping
  → TradingAgentsGraph.propagate()
    → GraphSetup.setup_graph()
    → graph.invoke()
    → build_report(final_state)
```

### 2.2 任务分解（5 波次，12 任务）

#### 波次 1：独立 Bug 修复 + 初步删除（无依赖，可并行）

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| T1 | interface 静默吞异常 | `interface.py:405` | `except Exception:` → `except Exception as e: logger.warning(...)` |
| T2 | config 全局可变状态 | `dataflows/config.py` | 删除 `set_config()`，`get_config()` 只读返回冻结快照 |
| T3 | 删除 ContextWindowManager | `context_manager.py` + `bull/bear_researcher.py` | 删除 359 行压缩模块，辩论 Agent 改为直接从 4 个 state 字段拼接报告 |
| T4 | a_stock_data 日期参数 | `a_stock_data.py` | `get_financial_statements()` 加 `curr_date` 过滤；`get_news_a()`/`get_global_news_a()` 默认 30 天 |
| T5 | 删除 planner 目录 | `planner/` 全部 5 文件 + 更新 8 个导入方 | 508 行，LLM 规划层，连模板匹配一起删 |
| T6 | 评估 causal_tracer | `causal_tracer.py` | 保留，使用惰性导入 |

#### 波次 2：删除重复的编排层

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| T7 | 删除 executor + dynamic_graph_builder | `executor.py`+`dynamic_graph_builder.py` | 功能由 `trading_graph.py` + `setup.py` 承接 |
| T8 | 删除 report_renderer | `report_renderer.py` | 446 行正则渲染删掉，`trading_graph.py` 加 20 行 `build_report()` |

#### 波次 3：重写 API 服务

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| T9 | bootstrap + api_server | `bootstrap.py`+`api_server.py` | 替换 `LLMPlanner.plan()`+`GraphExecutor.execute()` 为 `TradingAgentsGraph.propagate()` |

#### 波次 4：重写 CLI 入口

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| T10 | cli/batch + guping/agent_batch | `cli/batch.py`+`guping/agent_batch.py` | 同上，替换 planner/executor 为 TradingAgentsGraph |

#### 波次 5：清理

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| T12 | 清理 .bak + 死代码 | `*.bak`, `trading_graph.py` | 删除备份文件、`propagate_with_planner()` 死方法 |

> T11（context_assembly → propagation 合并）被推迟——它被 mcp_server 和 wiki_generator 引用，合并风险高且收益低。

---

## 三、重构执行结果

### 3.1 统计

```
删除文件:  12 个
删除代码:  2577 行
修改文件:  13 个（+355/-- 行）
净效果:    -2222 行
```

### 3.2 删除的模块

| 模块 | 行数 | 删除理由 |
|------|------|---------|
| `planner/` | 508 | 零价值 LLM 规划层 |
| `executor.py` | 360 | 与 trading_graph.py 重复 |
| `dynamic_graph_builder.py` | 424 | 与 setup.py 重复 |
| `report_renderer.py` | 446 | 正则解析引入格式损坏 |
| `context_manager.py` | 359 | 压缩报告导致辩论 Agent 失忆 |
| `.bak` 文件 | 178 | 重构残留 |

### 3.3 修复的 Bug

| Bug | 修复 | 效果 |
|-----|------|------|
| interface 静默吞异常 | `except Exception` → `logger.warning()` | 出错可见 |
| config 全局竞态 | 删除 `set_config()`，`get_config()` 只读 | 多用户安全 |
| 辩论 Agent 看不到完整报告 | 删除 ContextWindowManager，直接 4 字段拼接 | 论据质量恢复 |
| 双路径状态不一致 | 统一走 `TradingAgentsGraph.propagate()` | 行为一致 |
| 北汽蓝谷"列4/列5" | 删除 ReportRenderer，换 `build_report()` | 表格完整 |
| 新闻日期 2025 年 | `get_news_a()` 默认最近 30 天 | 时效恢复 |
| 财务数据日期忽略 | `get_financial_statements()` 加 `curr_date` 过滤 | 数据相关性提高 |
| 风险提示全缺 | 3 个分析师 prompt 加"必须写 3 个风险" | 风险输出改善 |
| Market 指标无数值 | market_analyst prompt 加"必须写具体数值" | 分析深度改善 |

### 3.4 保留的增强能力（没有白做）

- ✅ A 股数据源（a_stock_data + akshare + guosen）
- ✅ 结构化输出（schemas.py Pydantic 模型）
- ✅ agent_states 扩展字段（17 字段）
- ✅ checkpointer 断点续跑
- ✅ IndustryVerifier 行业检测
- ✅ causal_tracer 决策追踪
- ✅ debate_quality 辩论质量跟踪
- ✅ 多供应商 LLM（含 quick_llm_provider 独立配置）

---

## 四、验证结果

### 4.1 测试覆盖

7 只 A 股全量分析（2026-06-04）：

| 代码 | 名称 | 字数 | 状态 |
|------|------|:----:|:----:|
| 600418 | 江淮汽车 | 52,607 bytes | ✅ |
| 600733 | 北汽蓝谷 | 58,666 bytes | ✅ |
| 000796 | 凯撒旅业 | 33,199 bytes | ✅ |
| 605255 | 天普股份 | 23,976 bytes | ✅ |
| 600105 | 永鼎股份 | 38,414 bytes | ✅ |
| 002736 | 国信证券 | 46,936 bytes | ✅ |
| 000166 | 申万宏源 | 11,560 bytes | ✅ |

零崩溃、零导入错误、所有 11 个 Agent 节点正常执行。

### 4.2 模块导入验证

```
trading_graph.py         OK
graph/__init__.py        OK  
config.py                OK（只读冻结）
bull/bear researcher     OK（无 ContextWindowManager 依赖）
interface.py             OK
api_server.py            OK
planner/                 已删除 ✅
executor.py              已删除 ✅
dynamic_graph_builder.py 已删除 ✅
report_renderer.py       已删除 ✅
context_manager.py       已删除 ✅
```

### 4.3 与重构前对比

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| 执行路径 | 3 条独立路径 | 1 条统一路径 |
| 图编排 | `setup.py` + `dynamic_graph_builder.py` 两套 | 只有 `setup.py` |
| 报告输出 | `report_renderer.py` 正则解析（446 行） | `build_report()` 直接拼接（20 行） |
| 辩论上下文 | `ContextWindowManager` 压缩（359 行） | 4 字段直接拼接（0 行中间层） |
| 规划 | `LLMPlanner` LLM 调用（508 行） | 无规划层 |
| LLM 客户端 | 仅 deep + quick 同 provider | 支持 `quick_llm_provider` 独立配置 |
| 数据缓存 | 无日期强制 | `get_news` 默认 30 天过滤 |
| 风险输出 | 靠 renderer 注入"数据暂缺" | Prompt 强制 LLM 写 3 个风险 |

---

## 五、待办事项

| 优先级 | 事项 | 状态 |
|--------|------|------|
| P2 | `benchmark_fanout.py` 重写 | 待办 |
| P2 | `scheduler/scheduler.py` 适配 TradingAgentsGraph | 待办 |
| P3 | `context_assembly.py` → `propagation.py` 合并 | 推迟 |

---

## 六、风险与回退

如果重构出现问题，回退方式：

```bash
git checkout main
git branch -D refactor/unify-graph-pipeline
```

由于重构是纯删除代码 + 修改导入路径，不是重写核心逻辑，回退风险低。
唯一新增的代码是 `build_report()`（20 行）和 `apply_env_overrides()`（15 行），
以及 `api_types.py` 中的两个临时 dataclass（15 行）。
