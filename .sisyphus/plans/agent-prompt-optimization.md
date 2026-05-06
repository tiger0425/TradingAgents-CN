# Agent 提示词全面优化计划

## 摘要

> **快速概览**：基于前序详细分析（13 个 agent，综合评分 6.7/10），对 TradingAgents 多智能体交易框架的所有提示词进行全面优化，修复 10 个已识别问题 + Metis 发现的 5 个额外缺陷，使整体评分提升至 8.5+/10。
>
> **交付物**：
> - 14 个 agent/模块文件的提示词优化（含新增社交媒体工具）
> - 5 个前置 bug 修复
> - 端到端流程验证报告
>
> **预估工作量**：中等
> **并行执行**：是 — 5 波次
> **关键路径**：Wave 0（前置修复）→ Wave 1（高优重构）→ Wave 2（中优提升）→ Wave 3（低优打磨）→ Wave FINAL（验证）

---

## 背景

### 原始需求
用户基于对 13 个 agent 提示词的详细分析报告（综合评分 6.7/10），要求按优先级全面优化所有提示词。

### 分析摘要
**已识别问题**（详见 `.sisyphus/drafts/agent-prompt-optimization.md`）：

| 级别 | 编号 | 问题 | 影响范围 |
|------|------|------|---------|
| 🔴 高 | ISSUE-1 | Social Media Analyst 名不副实（只有 get_news 工具） | 1 agent |
| 🔴 高 | ISSUE-2 | News Analyst 提示词过弱（仅 5 行） | 1 agent |
| 🔴 高 | ISSUE-3 | LangChain 基础模板污染所有分析师 | 4 agents |
| 🟡 中 | ISSUE-4 | Trader 提示词偏短且角色不清 | 1 agent |
| 🟡 中 | ISSUE-5 | Bull/Bear Researcher 首轮与反驳轮使用相同 prompt | 2 agents |
| 🟡 中 | ISSUE-6 | Portfolio Manager past_context 注入格式混乱 | 1 agent |
| 🟡 中 | ISSUE-7 | 中英文输出不一致（Trader + Research Manager 缺语言指令） | 4 agents |
| 🟠 低 | ISSUE-8 | Market Analyst 提示词过长（~1800 字符指标目录） | 1 agent |
| 🟠 低 | ISSUE-9 | 缺少通用降级策略（数据源返回空） | 所有 agents |
| 🟠 低 | ISSUE-10 | 辩论 agent 缺少轮次深度控制 + 上下文窗口风险 | 5 agents |

### Metis 评审发现（额外缺陷）

| 编号 | 发现 | 严重度 |
|------|------|--------|
| **BUG-1** | 分析师 report 赋值 bug：`if len(result.tool_calls) == 0: report = result.content`——当 LLM 调用工具时 report 为空字符串 | 🔴 |
| **BUG-2** | `get_limit_prices()` 硬编码 10% 涨跌停，未调用 `get_limit_rate()`，导致科创板/创业板/ST 约束错误 | 🔴 |
| **BUG-3** | `output_language` 为 None 时 `AttributeError`（`lang.strip().lower()` 调用在 None 上） | 🟡 |
| **BUG-4** | `past_context` 为 None 时未被默认值保护（`state.get("past_context", "")` 在 key 存在但值为 None 时返回 None） | 🟡 |
| **BUG-5** | Bull/Bear 及 Risk Debater 首轮 `current_response` 为空字符串，LLM 可能编造虚构论点 | 🟡 |
| **GAP-1** | `get_insider_transactions` 注册在 ToolNode 但未绑定到任何 agent | 🟠 |
| **GAP-2** | akshare 社交媒体 API 仅返回行为指标（关注人数/排名/意愿指数），非实际帖子内容或情感得分 | 🟡 |

---

## 目标

### 核心目标
基于分析报告和 Metis 评审，系统性优化所有 13 个 agent 的提示词质量，修复所有已识别的缺陷和 bug，使 agent 提示词系统的综合评分从 6.7/10 提升至 8.5+/10。

### 具体交付物
- 14 个 agent 文件提示词优化（含新增 `social_sentiment_tools.py`）
- 5 个 bug 修复（`dataflows/a_share_constraints.py`、`agent_utils.py`、4 个分析师文件等）
- 1 个新增 akshare 社交媒体数据聚合函数（`dataflows/akshare.py`，≤80 行）
- 端到端验证报告（`tradingagents analyze --ticker 600519 --date 2026-04-15`）

### 完成标准
- [x] 所有 5 个 bug 修复并验证无回归
- [x] 所有 10 个 ISSUE 对应优化完成
- [x] 端到端流程成功运行（600519 茅台 + 000001 平安银行两个样本）
- [x] Social Media Analyst 报告引用 akshare 社交媒体数据源
- [x] 分析师报告中不再出现 "FINAL TRANSACTION PROPOSAL"
- [x] 中文模式下 Trader + Research Manager 输出中文
- [x] 所有 agent 在数据为空时不崩溃

### 必须包含
- 所有 13 个 agent 的提示词优化
- 5 个前置 bug 修复
- 社交媒体工具添加
- 端到端验证

### 必须排除（护栏）
- 不改动 LangGraph 图拓扑结构（`setup.py`、`conditional_logic.py`）
- 不重构 `memory.py` 日志格式
- 不修改 `llm_clients/` 目录
- 不修改 `test.py` 和 `tests/` 目录（不添加单元测试）
- 不将提示词提取为外部模板文件
- 每个 agent 的 system prompt 控制在 ~1200 token（~5000 字符）内
- 不修改 `get_indicators` 等工具函数描述（Issue-8 仅精简 agent 提示词，不碰 `*_tools.py`）
- 中文输出仅限用户可见报告层，内部辩论 agent 保持英文

---

## 验证策略

### 测试决策
- **测试基础设施**：已有（`test.py`、`tests/`）
- **自动化测试**：无（不使用 TDD，不添加单元测试）
- **验证方式**：Agent-Executed QA — 每个波次后运行端到端流程验证

### QA 策略
每个波次完成后，运行完整的 `tradingagents analyze` 流程进行端到端验证：
- **API/CLI**：使用 Bash 执行 `python -m cli.main` 或直接调用 `TradingAgentsGraph`
- **证据**：保存到 `.sisyphus/evidence/` 目录

---

## 执行策略

### 并行执行波次

```
Wave 0（前置修复 — 独立并行，不依赖任何其他任务）：
├── Task 0.1: 修复 4 个分析师的 report 赋值 bug [quick]
├── Task 0.2: 修复 get_limit_prices() 硬编码 10% [quick]
├── Task 0.3: 修复 output_language None 处理 [quick]
├── Task 0.4: 修复 past_context None 处理 [quick]
└── Task 0.5: 修复首轮辩论空响应 + insider_transactions 绑定 [quick]

Wave 1（高优提示词重构 — 依赖 Wave 0 完成，内部可并行）：
├── Task 1.1: 重写 Social Media Analyst + 添加社交媒体工具 [deep]
├── Task 1.2: 重写 News Analyst 提示词 [quick]
└── Task 1.3: 剥离 4 个分析师的 LangChain 模板 [quick]

Wave 2（中优质量提升 — 依赖 Wave 1 完成，内部可并行）：
├── Task 2.1: 重写 Trader 提示词 [quick]
├── Task 2.2: Bull/Bear Researcher 轮次感知 [quick]
├── Task 2.3: 优化 Portfolio Manager past_context 注入 [quick]
├── Task 2.4: 统一中英文输出策略 [quick]
└── Task 2.5: 修复 Risk Debater 首轮空响应 [quick]

Wave 3（低优平滑打磨 — 依赖 Wave 2 完成，内部可并行）：
├── Task 3.1: 精简 Market Analyst 提示词 [quick]
├── Task 3.2: 添加通用降级策略 [quick]
└── Task 3.3: 辩论 depth 控制 + 上下文窗口保护 [quick]

Wave FINAL（端到端验证）：
├── Task F1: Plan 合规审计 (oracle)
├── Task F2: 代码质量审查
├── Task F3: 端到端 QA 执行
└── Task F4: 范围保真度检查
```

---

## 待办事项

- [x] 0.1. 修复 4 个分析师的 report 赋值 bug

  **What to do**：
  - 修改 `fundamentals_analyst.py`、`market_analyst.py`、`news_analyst.py`、`social_media_analyst.py` 中 report 赋值逻辑
  - 当前代码：`if len(result.tool_calls) == 0: report = result.content` — 改为无论是否调用工具，都捕获 LLM 最终响应的 content 作为 report
  - 正确逻辑：`report = result.content if result.content else ""`（或类似确保始终有值的方案）
  - 注意保留 `messages` state 中的工具调用结果——只修复 report 变量赋值

  **Must NOT do**：
  - 不改变 `state["messages"]` 的返回逻辑
  - 不改变工具绑定或 prompt 结构
  - 不改变返回字典中除 report 以外的任何字段

  **Recommended Agent Profile**：
  - **Category**：`quick` — 4 个文件相同的简单模式修改
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 0（与 Task 0.2、0.3、0.4、0.5 并行）
  - **Blocks**：Wave 1 所有任务
  - **Blocked By**：无

  **References**：
  - `tradingagents/agents/analysts/fundamentals_analyst.py:59-67` — 需修改的 report 赋值模式
  - `tradingagents/agents/analysts/market_analyst.py:80-88` — 同上
  - `tradingagents/agents/analysts/news_analyst.py:52-60` — 同上
  - `tradingagents/agents/analysts/social_media_analyst.py:47-55` — 同上

  **Acceptance Criteria**：
  - [ ] 4 个分析师文件的 report 赋值逻辑改为始终捕获 LLM 最终响应的 content
  - [ ] 当 LLM 调用工具时（`len(result.tool_calls) > 0`），report 不再为空字符串

  **QA Scenarios**：

  ```
  Scenario: 端到端运行后检查各 report 非空
    Tool: Bash
    Preconditions: Wave 1 优化完成后
    Steps:
      1. 运行: python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; from tradingagents.default_config import DEFAULT_CONFIG; c=DEFAULT_CONFIG.copy(); c['max_debate_rounds']=1; c['max_risk_rounds']=1; ta=TradingAgentsGraph(debug=True,config=c); _,d=ta.propagate('600519','2026-04-15'); print('FUND:', len(d.get('fundamentals_report',''))>0); print('MKT:', len(d.get('market_report',''))>0); print('NEWS:', len(d.get('news_report',''))>0); print('SENT:', len(d.get('sentiment_report',''))>0)"
      2. 验证 4 个输出均为 True
    Expected Result: 所有 4 个 report 非空
    Failure Indicators: 任一个为 False
    Evidence: .sisyphus/evidence/task-0-1-reports-nonempty.txt
  ```

  **Commit**：YES（与 0.2-0.5 合并一批）
  - Message: `fix(agents): report assignment bug — capture content even when LLM makes tool calls`
  - Files: `tradingagents/agents/analysts/fundamentals_analyst.py`, `market_analyst.py`, `news_analyst.py`, `social_media_analyst.py`

- [x] 0.2. 修复 `get_limit_prices()` 硬编码 10% 涨跌停比例

  **What to do**：
  - 修改 `tradingagents/dataflows/a_share_constraints.py` 中的 `get_limit_prices()` 函数
  - 当前硬编码 `limit_rate = 0.10`，改为调用同文件的 `get_limit_rate(symbol, name)` 获取正确比例
  - `get_limit_prices` 的签名需要增加 `symbol: str` 参数
  - 同时修改 `get_limit_rate()` 使其支持：
    - `68xxxx` → 科创板 20%
    - `30xxxx` → 创业板 20%
    - `8xxxxx`（6 位）→ 北交所 30%
    - 含 "ST" 或 "*ST" → 5%
    - 其他 → 10%

  **Must NOT do**：
  - 不改变 `format_limit_constraint()` 和 `format_t_plus_1_constraint()` 的函数签名
  - 不改变约束文本格式

  **Recommended Agent Profile**：
  - **Category**：`quick` — 单文件函数逻辑修复
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 0（与 Task 0.1、0.3、0.4、0.5 并行）
  - **Blocks**：Wave 1 Task 1.3（约束注入到分析师）
  - **Blocked By**：无

  **References**：
  - `tradingagents/dataflows/a_share_constraints.py:7-32` — `get_limit_prices()` + `get_limit_rate()` 函数
  - 调用点需检查：搜索 `get_limit_prices(` 的所有调用，更新参数传入 `symbol`

  **Acceptance Criteria**：
  - [ ] `get_limit_prices("688001", prev_close=100.0)` 返回 `(120.0, 80.0)`（20%）
  - [ ] `get_limit_prices("000001", prev_close=100.0)` 返回 `(110.0, 90.0)`（10%）
  - [ ] `get_limit_prices("000001", "ST公司", 100.0)` 返回 `(105.0, 95.0)`（5%）
  - [ ] 所有调用点传入正确的 symbol 参数

  **QA Scenarios**：

  ```
  Scenario: 验证涨跌停比例正确计算
    Tool: Bash (python REPL)
    Preconditions: 无
    Steps:
      1. python3 -c "from tradingagents.dataflows.a_share_constraints import get_limit_prices; print(get_limit_prices('688001', 100.0))"
      2. python3 -c "from tradingagents.dataflows.a_share_constraints import get_limit_prices; print(get_limit_prices('300001', 100.0))"
      3. python3 -c "from tradingagents.dataflows.a_share_constraints import get_limit_prices; print(get_limit_prices('000001', 100.0))"
      4. python3 -c "from tradingagents.dataflows.a_share_constraints import get_limit_prices; print(get_limit_prices('000001', '*ST公司', 100.0))"
    Expected Result: 依次输出 (120.0, 80.0), (120.0, 80.0), (110.0, 90.0), (105.0, 95.0)
    Failure Indicators: 科创板/创业板返回 10% 比例
    Evidence: .sisyphus/evidence/task-0-2-limit-prices.txt
  ```

  **Commit**：YES（与 0.1-0.5 合并一批）
  - Message: `fix(dataflows): get_limit_prices() now uses correct limit rate per board (20%/30%/5%)`
  - Files: `tradingagents/dataflows/a_share_constraints.py` + 所有调用点

- [x] 0.3. 修复 `output_language` 为 None 时的 `AttributeError`

  **What to do**：
  - 修改 `tradingagents/agents/utils/agent_utils.py` 中的 `get_language_instruction()` 函数
  - 当前代码：`lang = get_config().get("output_language", "English")`；如果值为 None，`lang.strip().lower()` 会抛出 `AttributeError`
  - 修改为：`lang = (get_config().get("output_language") or "English")`

  **Must NOT do**：
  - 不改变函数返回格式
  - 不改变语言判断逻辑

  **Recommended Agent Profile**：
  - **Category**：`quick` — 单行修复
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 0
  - **Blocks**：Wave 1 Task 1.3（语言指令注入）
  - **Blocked By**：无

  **References**：
  - `tradingagents/agents/utils/agent_utils.py:31-35` — 需修改函数

  **Acceptance Criteria**：
  - [ ] 当 `output_language` 配置为 None 时，`get_language_instruction()` 不抛出异常
  - [ ] 返回空字符串（英文模式默认行为）

  **QA Scenarios**：

  ```
  Scenario: None 值不导致异常
    Tool: Bash (python REPL)
    Preconditions: 无
    Steps:
      1. python3 -c "from tradingagents.agents.utils.agent_utils import get_language_instruction; from tradingagents.dataflows.config import set_config; set_config({'output_language': None}); print(repr(get_language_instruction()))"
    Expected Result: 输出 ""（空字符串，无异常）
    Failure Indicators: AttributeError 异常
    Evidence: .sisyphus/evidence/task-0-3-language-none.txt
  ```

  **Commit**：YES（与 0.1-0.5 合并一批）
  - Message: `fix(agents): handle None output_language config gracefully`
  - Files: `tradingagents/agents/utils/agent_utils.py`

- [x] 0.4. 修复 `past_context` 为 None 时的边界情况

  **What to do**：
  - 修改 `tradingagents/agents/managers/portfolio_manager.py` 第 45 行附近
  - 当前代码：`past_context = state.get("past_context", "")` — 当 key 存在但值为 None 时返回 None 而非 ""
  - 修改为：`past_context = state.get("past_context") or ""`
  - 同时检查 `position_opened_date` 等类似字段是否有同类型问题

  **Must NOT do**：
  - 不改变 `lessons_line` 的格式逻辑
  - 不改变 `TradingMemoryLog.get_past_context()` 的返回值格式

  **Recommended Agent Profile**：
  - **Category**：`quick` — 防御性编程修复
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 0
  - **Blocks**：Wave 2 Task 2.3
  - **Blocked By**：无

  **References**：
  - `tradingagents/agents/managers/portfolio_manager.py:45-50` — 需修改处

  **Acceptance Criteria**：
  - [ ] 当 `state["past_context"]` 为 None 时，`lessons_line` 为空字符串
  - [ ] 当 `state["past_context"]` 为空字符串时，`lessons_line` 为空字符串
  - [ ] 当 `state["past_context"]` 有内容时，正常注入

  **QA Scenarios**：

  ```
  Scenario: None past_context 不导致异常
    Tool: Bash (python REPL)
    Preconditions: 无
    Steps:
      1. python3 -c "state={'past_context': None}; pc=state.get('past_context') or ''; print('OK:', repr(pc))"
    Expected Result: "OK: ''"
    Failure Indicators: 异常或非空输出
    Evidence: .sisyphus/evidence/task-0-4-past-context.txt
  ```

  **Commit**：YES（与 0.1-0.5 合并一批）
  - Message: `fix(agents): handle None past_context in Portfolio Manager`
  - Files: `tradingagents/agents/managers/portfolio_manager.py`

- [x] 0.5. 修复首轮辩论空响应 + `get_insider_transactions` 绑定

  **What to do**：
  - **A. 首轮空响应修复**：修改 `bull_researcher.py` 和 `bear_researcher.py` 的首轮 prompt，当 `current_response` 为空时使用引导文案（如："(No argument yet — this is the opening round. Present your initial thesis.)"）
  - 同样处理 `aggressive_debator.py`、`conservative_debator.py`、`neutral_debator.py` 的首轮空响应
  - **B. insider_transactions 绑定**：在 `fundamentals_analyst.py` 的 tools 列表中添加 `get_insider_transactions`（当前第 8 行已导入但第 19-24 行 tools 列表中遗漏）

  **Must NOT do**：
  - 不改变辩论状态管理逻辑（`investment_debate_state` / `risk_debate_state`）
  - 不改变新增工具的函数签名
  - 不改变辩论轮次计数逻辑

  **Recommended Agent Profile**：
  - **Category**：`quick` — 两个独立小修复
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES
  - **Parallel Group**：Wave 0
  - **Blocks**：Wave 2 Task 2.2、2.5
  - **Blocked By**：无

  **References**：
  - `tradingagents/agents/researchers/bull_researcher.py:30` — `Last bear argument: {current_response}`
  - `tradingagents/agents/researchers/bear_researcher.py:32` — `Last bull argument: {current_response}`
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py:29` — `{current_conservative_response}` / `{current_neutral_response}`
  - `tradingagents/agents/risk_mgmt/conservative_debator.py:29` — 同上
  - `tradingagents/agents/risk_mgmt/neutral_debator.py:29` — 同上
  - `tradingagents/agents/analysts/fundamentals_analyst.py:8,19-24` — `get_insider_transactions` 导入但未绑定

  **Acceptance Criteria**：
  - [ ] 首轮辩论时，空 `current_response` 替换为引导文案
  - [ ] `get_insider_transactions` 出现在 fundamentals_analyst 的工具列表中

  **QA Scenarios**：

  ```
  Scenario: 首轮辩论引导文案生效
    Tool: Bash
    Preconditions: Wave 1-2 优化完成
    Steps:
      1. 运行端到端流程（600519, 2026-04-15）
      2. 检查 debate history 中 Bull Researcher 首轮输出不含虚构引用
    Expected Result: debate history 首轮无 "you said" / "you argued" 等对不存在论点的引用
    Failure Indicators: 首轮包含对不存在对手论点的虚构引用
    Evidence: .sisyphus/evidence/task-0-5-first-round.txt
  ```

  **Commit**：YES（与 0.1-0.5 合并一批）
  - Message: `fix(agents): empty first-round response guards + bind insider_transactions to fundamentals analyst`
  - Files: `bull_researcher.py`, `bear_researcher.py`, `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`, `fundamentals_analyst.py`

- [x] 1.1. 重写 Social Media Analyst + 添加社交媒体数据工具

  **What to do**：
  - **A. 新增工具**：在 `tradingagents/dataflows/akshare.py` 末尾新增 `get_social_sentiment(symbol: str) -> str` 函数（≤80 行），聚合 akshare 的行为指标：
    - `ak.stock_comment_em()` — 关注指数
    - `ak.stock_comment_detail_scrd_focus_em(symbol)` — 关注度历史（近 7 天）
    - `ak.stock_comment_detail_scrd_desire_em(symbol)` — 参与意愿指数
    - `ak.stock_hot_rank_detail_realtime_em()` — 实时人气排名
    - `ak.stock_hot_follow_xq(symbol)` — 雪球关注度
  - 函数返回格式化的 Markdown 文本（含指标表格 + 趋势解读提示），处理 akshare 不可用时的优雅降级
  - **B. 创建工具包装**：在 `tradingagents/agents/utils/` 新建 `social_sentiment_tools.py`（≤40 行），创建 `get_social_sentiment_tool()` LangChain tool wrapper
  - **C. 注册到 ToolNode**：修改 `tradingagents/graph/trading_graph.py`，在 social analyst 的 ToolNode 中注册新工具（参照现有 news analyst toolNode 模式）
  - **D. 重写 Prompt**：修改 `social_media_analyst.py` 的 system_message，诚实说明能力范围：
    - 角色："A 股社交媒体行为分析师"
    - 分析维度：投资者关注度变化趋势、参与意愿、人气排名、跨平台（雪球/东方财富）对比
    - 分析局限：坦诚说明数据为行为指标（非帖子内容），建议结合新闻分析交叉验证
    - 添加降级提示："若行为指标无显著变化，请标注并基于当前可用数据输出"
    - 保留 Markdown 表格要求 + 语言指令
  - **E. 剥离 LangChain 模板**：与 Task 1.3 协调，使用独立 system prompt（不包含协作模板）

  **Must NOT do**：
  - 不声称分析"what people are saying"——仅分析行为指标
  - 不添加 NLP 情感分析管道（超出范围）
  - `dataflows/akshare.py` 新增 ≤80 行
  - `social_sentiment_tools.py` ≤40 行
  - 不改变 `get_news` 工具绑定（保留作为辅助数据源）

  **Recommended Agent Profile**：
  - **Category**：`deep` — 涉及跨层（dataflows → agents/utils → graph → agent prompt）的新功能添加
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 1.2 并行）
  - **Parallel Group**：Wave 1（与 1.2、1.3 并行，但 1.2 和 1.3 之间无依赖）
  - **Blocks**：Wave 2 所有任务
  - **Blocked By**：Wave 0（必须完成所有 bug 修复）

  **References**：
  - `tradingagents/agents/analysts/social_media_analyst.py:6-57` — 当前 social analyst 完整代码
  - `tradingagents/dataflows/akshare.py` — 现有 akshare 数据流，了解添加新函数的模式
  - `tradingagents/agents/utils/news_data_tools.py` — 现有工具包装器模式参考
  - `tradingagents/graph/trading_graph.py:135-185` — ToolNode 注册位置
  - akshare 文档：`stock_comment_em`、`stock_comment_detail_scrd_focus_em` 等 API

  **Acceptance Criteria**：
  - [ ] `get_social_sentiment("600519")` 返回包含关注指数、关注度变化、排名信息的 Markdown 文本
  - [ ] 当 akshare 不可用时函数不抛出异常（返回降级提示文本）
  - [ ] Social Media Analyst 的 prompt 中不再出现 "social media posts"、"what people are saying" 等误导性描述
  - [ ] 端到端运行后 `sentiment_report` 引用 akshare 数据源（`grep -i 'akshare\|关注指数\|参与意愿'` 命中有内容）

  **QA Scenarios**：

  ```
  Scenario: 社交媒体工具返回有效数据（正常情况）
    Tool: Bash (python REPL)
    Preconditions: akshare 已安装
    Steps:
      1. python3 -c "from tradingagents.dataflows.akshare import get_social_sentiment; result = get_social_sentiment('600519'); print(result[:500]); assert len(result) > 100, 'Result too short'"
    Expected Result: 输出包含关注指数、关注度变化、排名的 Markdown 文本，>100 字符
    Failure Indicators: 空字符串、异常、"数据获取失败" 但无降级内容
    Evidence: .sisyphus/evidence/task-1-1-social-tool-ok.txt

  Scenario: akshare 不可用时的降级（网络断开或 API 异常）
    Tool: Bash
    Preconditions: 模拟 akshare 不可用
    Steps:
      1. python3 -c "from tradingagents.dataflows.akshare import get_social_sentiment; result = get_social_sentiment('INVALID___TICKER'); assert '无法获取' in result or '暂时不可用' in result, 'No degradation message'"
    Expected Result: 返回降级提示文本，不抛出异常
    Failure Indicators: 未捕获异常导致崩溃
    Evidence: .sisyphus/evidence/task-1-1-social-degradation.txt

  Scenario: 端到端 Social Media Analyst 报告包含 akshare 数据
    Tool: Bash
    Preconditions: Wave 1 全部完成
    Steps:
      1. 运行端到端流程（600519）
      2. grep -i 'akshare\|关注指数\|参与意愿\|人气排名' 在输出的 sentiment_report 中
    Expected Result: 至少 1 处命中
    Failure Indicators: 0 命中
    Evidence: .sisyphus/evidence/task-1-1-e2e-social.txt
  ```

  **Commit**：YES
  - Message: `feat(agents): rewrite Social Media Analyst with real akshare social sentiment tools`
  - Files: `dataflows/akshare.py`, `agents/utils/social_sentiment_tools.py`（新建）, `graph/trading_graph.py`, `agents/analysts/social_media_analyst.py`

- [x] 1.2. 重写 News Analyst 提示词

  **What to do**：
  - 修改 `news_analyst.py` 的 system_message，大幅增强提示词：
    1. 角色定位：明确为"新闻与宏观分析师"，区别于 Social Media Analyst 的"行为情绪分析师"
    2. 搜索策略：建议先 `get_global_news` 了解宏观环境 → 再 `get_news(query=股票名称+行业关键词)` 获取公司相关新闻
    3. 信源评估：提示按来源可信度分层（官方公告 > 权威财经媒体 > 自媒体），优先引用高可信度来源
    4. 交叉验证：当多源信息矛盾时，标注差异并建议以基本面数据为准
    5. 降级策略：若搜索返回空，标注并基于 `get_global_news` 的宏观背景提供有限分析
    6. 保留 Markdown 表格 + 语言指令
  - 剥离 LangChain 协作模板（与 Task 1.3 协调）

  **Must NOT do**：
  - 不新增工具（仍然使用 `get_news` + `get_global_news`）
  - 不改变输出格式（仍写入 `state["news_report"]`）
  - 提示词长度控制在 ~1000 字符内

  **Recommended Agent Profile**：
  - **Category**：`quick` — 单文件 prompt 重写
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 1.1 并行）
  - **Parallel Group**：Wave 1
  - **Blocks**：Wave 2
  - **Blocked By**：Wave 0

  **References**：
  - `tradingagents/agents/analysts/news_analyst.py:21-25` — 当前 system_message（5 行，需要重写）
  - `tradingagents/agents/analysts/social_media_analyst.py` — 参见 Task 1.1 的角色区分设计
  - `tradingagents/agents/utils/news_data_tools.py` — 了解 get_news 和 get_global_news 的参数形式

  **Acceptance Criteria**：
  - [ ] system_message 包含搜索策略指导（先宏观后微观）
  - [ ] system_message 包含信源可信度分层说明
  - [ ] system_message 包含降级策略（空数据时的处理）
  - [ ] 提示词总长度 ~800-1200 字符（不过度膨胀）

  **QA Scenarios**：

  ```
  Scenario: News Analyst 在端到端流程中调用多种工具类型
    Tool: Bash
    Preconditions: Wave 1 全部完成
    Steps:
      1. 运行端到端流程（600519），启用 debug 日志
      2. 检查调试日志：News Analyst 调用了 get_global_news 和 get_news 两种工具
    Expected Result: 两种工具均有调用记录
    Failure Indicators: 仅使用一种工具
    Evidence: .sisyphus/evidence/task-1-2-news-tool-diversity.txt

  Scenario: 无效查询返回降级而非幻觉
    Tool: Bash
    Preconditions: Wave 1 全部完成
    Steps:
      1. 运行端到端流程（stock="999999" 无效代码，date="2026-04-15"）
      2. 检查 news_report 内容：应包含 "无法获取" / "数据有限" 等降级表述，不虚构新闻内容
    Expected Result: 降级说明存在，无虚构新闻事件
    Failure Indicators: 编造具体的新闻标题、日期、内容
    Evidence: .sisyphus/evidence/task-1-2-news-degradation.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): enhance News Analyst prompt with search strategy, credibility tiers, and degradation`
  - Files: `tradingagents/agents/analysts/news_analyst.py`

- [x] 1.3. 剥离 4 个分析师的 LangChain 基础模板，定制独立 system prompt

  **What to do**：
  - 修改 4 个分析师文件（`fundamentals_analyst.py`、`market_analyst.py`、`news_analyst.py`、`social_media_analyst.py`）的 ChatPromptTemplate 结构
  - **移除**：`"You are a helpful AI assistant, collaborating with other assistants..."` 整个协作模板段落 + `FINAL TRANSACTION PROPOSAL` 停止信号逻辑
  - **保留并增强**：每个 agent 的专业 system_message 作为唯一的 system prompt
  - **新增**：每个 system prompt 末尾添加角色收尾语如 `"你是分析师团队的独立成员，专注于本领域分析。默认情况下你不是做出最终交易决策的人。"`（中文模式下）
  - 保持工具绑定结构不变（`prompt | llm.bind_tools(tools)`），仅改变 prompt 模板内容
  - 保持 `{tool_names}`、`{current_date}`、`{instrument_context}` 变量注入不变

  **Must NOT do**：
  - 不改变每个 analyst 的工具集或输出字段
  - 不改变 LangGraph 图结构中的节点连接方式
  - 不改变 ChatPromptTemplate 的基本结构（仍使用 from_messages）

  **Recommended Agent Profile**：
  - **Category**：`quick` — 4 个文件相同模式的模板清理
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 1.1、1.2 并行，但各自改不同文件）
  - **Parallel Group**：Wave 1
  - **Blocks**：Wave 2
  - **Blocked By**：Wave 0

  **References**：
  - `tradingagents/agents/analysts/fundamentals_analyst.py:33-53` — ChatPromptTemplate 结构（需修改）
  - `tradingagents/agents/analysts/market_analyst.py:54-69` — 同上
  - `tradingagents/agents/analysts/news_analyst.py:27-48` — 同上
  - `tradingagents/agents/analysts/social_media_analyst.py:21-42` — 同上

  **Acceptance Criteria**：
  - [ ] 4 个分析师文件的 system prompt 中不再包含 "collaborating with other assistants"
  - [ ] 4 个文件的 system prompt 中不再包含 "FINAL TRANSACTION PROPOSAL"
  - [ ] 每个 agent 有独立的专业角色收尾语
  - [ ] 端到端运行后，分析师报告中不出现 "FINAL TRANSACTION PROPOSAL" 文本

  **QA Scenarios**：

  ```
  Scenario: 分析师报告不含停止信号
    Tool: Bash
    Preconditions: Wave 1 全部完成
    Steps:
      1. 运行端到端流程（600519）
      2. grep -c 'FINAL TRANSACTION PROPOSAL' 在 fundamentals_report / market_report / news_report / sentiment_report 中
    Expected Result: 4 个报告均为 0
    Failure Indicators: 任一报告 >0
    Evidence: .sisyphus/evidence/task-1-3-no-stop-signal.txt

  Scenario: 每个分析师有独立角色收尾语
    Tool: Bash (grep)
    Preconditions: Wave 1 全部完成
    Steps:
      1. 运行端到端流程（000001）
      2. 检查 4 份报告的末尾：各有角色特征性收尾（基本面="财务分析"、技术="技术指标"等）
    Expected Result: 4 份报告的角色收尾语不雷同
    Failure Indicators: 4 份报告收尾高度相似
    Evidence: .sisyphus/evidence/task-1-3-role-distinction.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): strip LangChain collaboration template from all analysts, use tailored per-agent system prompts`
  - Files: `tradingagents/agents/analysts/fundamentals_analyst.py`, `market_analyst.py`, `news_analyst.py`, `social_media_analyst.py`

- [x] 2.1. 重写 Trader 提示词

  **What to do**：
  - 修改 `trader.py` 的 system message（当前仅 4 行），大幅增强：
    1. 角色区分：明确 Trader 与 Research Manager 的职责边界 — Research Manager 做方向建议，Trader 负责具体的交易执行（时机、价格、仓位规模）
    2. 信号冲突处理：当多份分析师报告给出矛盾信号时，按权重优先级排序：基本面分析师（长期）> 技术分析师（中短期）> 新闻/情绪（短期噪音）；当冲突严重时，选择 Hold 并标注原因
    3. 价格约束遵守：明确要求 entry_price 必须在涨跌停范围内
    4. 添加 `get_language_instruction()` 调用，确保中文模式下输出中文
  - 保持结构化输出（`TraderProposal` schema）不变
  - 保持 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 输出标记

  **Must NOT do**：
  - 不改变 `TraderProposal` schema 字段定义
  - 不增加新工具（Trader 仍基于文字分析做决策）
  - 不改变 function signature 或节点返回格式

  **Recommended Agent Profile**：
  - **Category**：`quick` — 单文件 prompt 重写
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 2.2-2.5 并行）
  - **Parallel Group**：Wave 2
  - **Blocks**：Wave 3
  - **Blocked By**：Wave 1

  **References**：
  - `tradingagents/agents/trader/trader.py:19-67` — 完整 trader 代码
  - `tradingagents/agents/schemas.py:109-163` — TraderProposal schema 和 renderer
  - `tradingagents/agents/managers/research_manager.py` — Research Manager 角色定义（区分参考）

  **Acceptance Criteria**：
  - [ ] Trader system message 包含信号冲突处理优先级
  - [ ] Trader system message 包含价格约束遵守要求
  - [ ] Trader 在中文模式下输出中文推理内容
  - [ ] 端到端运行后 trader_investment_plan 的 reasoning 字段为中文（中文模式下）

  **QA Scenarios**：

  ```
  Scenario: Trader 中文输出（中文模式）
    Tool: Bash
    Preconditions: config["output_language"] = "Chinese"
    Steps:
      1. 运行端到端流程（600519, 2026-04-15, output_language=Chinese）
      2. 检查 trader_investment_plan：reasoning 字段应为中文
    Expected Result: reasoning 字段主要是中文（英文词 < 10%）
    Failure Indicators: reasoning 全英文
    Evidence: .sisyphus/evidence/task-2-1-trader-chinese.txt

  Scenario: 矛盾信号下的 Hold 决策
    Tool: Bash
    Preconditions: 选择一支多空分歧明显的股票
    Steps:
      1. 运行端到端流程（可选 ticker: 000001, 近 30 日波动较大的日期）
      2. 检查 Trader action：如果多空信号矛盾严重，应为 Hold 并标注原因
    Expected Result: 若矛盾明显则 Hold + 标注冲突原因
    Failure Indicators: 矛盾信号下仍输出 Buy/Sell 且无冲突说明
    Evidence: .sisyphus/evidence/task-2-1-trader-conflict.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): enhance Trader prompt with role distinction, signal conflict handling, and Chinese output`
  - Files: `tradingagents/agents/trader/trader.py`

- [x] 2.2. Bull/Bear Researcher 添加轮次感知 prompt

  **What to do**：
  - 修改 `bull_researcher.py` 和 `bear_researcher.py` 的 prompt 模板
  - **首轮**（`count == 0`）：专注独立分析 — "This is the opening round. Present your comprehensive initial thesis based on the analyst reports. Do NOT reference opponent arguments (none exist yet)."
  - **反驳轮**（`count >= 1`）：专注反驳 — "This is a rebuttal round. Focus on countering the opponent's last argument with specific data and reasoning. Introduce at least ONE new piece of evidence not previously cited. Be conversational — speak as if you're in a live debate."
  - 通过 `count` 变量（来自 `investment_debate_state`）在 f-string 中做条件分支
  - 限制上下文：仅在 prompt 中保留最近 2 轮辩论历史（防止上下文窗口溢出）

  **Must NOT do**：
  - 不改变 `investment_debate_state` 的数据结构
  - 不改变 LangGraph 的辩论路由逻辑
  - 不改变输出格式（仍为 `Bull Analyst: ...` / `Bear Analyst: ...`）

  **Recommended Agent Profile**：
  - **Category**：`quick` — 两个文件相同的条件分支模式
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 2.3、2.4 并行）
  - **Parallel Group**：Wave 2
  - **Blocks**：Wave 3
  - **Blocked By**：Wave 1

  **References**：
  - `tradingagents/agents/researchers/bull_researcher.py:3-48` — 完整代码
  - `tradingagents/agents/researchers/bear_researcher.py:3-48` — 完整代码
  - `tradingagents/graph/propagation.py:28-34` — InvestDebateState 的 count 字段初始化

  **Acceptance Criteria**：
  - [ ] 首轮 prompt 包含 "opening round" / "do NOT reference opponent" 指导
  - [ ] 反驳轮 prompt 包含 "rebuttal" / "counter" / "introduce new evidence" 指导
  - [ ] 辩论历史仅保留最近 2 轮（防止上下文溢出）
  - [ ] 端到端运行后，首轮 debate 输出不含 "you argued" / "your point" 等引用

  **QA Scenarios**：

  ```
  Scenario: 首轮不含虚构引用
    Tool: Bash
    Preconditions: config["max_debate_rounds"] >= 2
    Steps:
      1. 运行端到端流程（600519, max_debate_rounds=2）
      2. 检查 Bull 首轮输出：不含 "you argued" / "Bear" 引用
    Expected Result: Bull 首轮为独立分析，无对 Bear 的引用
    Failure Indicators: 首轮包含 "Bear Analyst mentioned" / "as you said" 等
    Evidence: .sisyphus/evidence/task-2-2-first-round-clean.txt

  Scenario: 反驳轮引入新证据
    Tool: Bash
    Preconditions: config["max_debate_rounds"] >= 2
    Steps:
      1. 运行端到端流程（000001, max_debate_rounds=2）
      2. 检查第 2 轮 Bear 输出：应引入第 1 轮未出现的新数据点或新角度
    Expected Result: 反驳轮有新证据或新分析角度
    Failure Indicators: 回应与首轮完全相同，无新增内容
    Evidence: .sisyphus/evidence/task-2-2-rebuttal-new-evidence.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): add round-aware prompts to Bull/Bear researchers with context window protection`
  - Files: `tradingagents/agents/researchers/bull_researcher.py`, `bear_researcher.py`

- [x] 2.3. 优化 Portfolio Manager 的 past_context 注入格式

  **What to do**：
  - 修改 `portfolio_manager.py` 中 `lessons_line` 的格式
  - 当前：`"- Lessons from prior decisions and outcomes:\n{past_context}\n"` — past_context 可能是嵌套大段文本
  - 优化为结构化格式：
    ```
    **历史经验教训**（来自过往决策）：
    同一股票（{ticker}）最近分析：
    {same_ticker_lessons}

    跨股票通用教训：
    {cross_ticker_lessons}
    ```
  - 新增辅助函数 `format_past_context(past_context: str) -> str` 在 `agent_utils.py` 中，负责格式化 past_context
  - 当 past_context 为空时，`lessons_line` 输出空字符串（保持当前行为）

  **Must NOT do**：
  - 不重构 `memory.py` 的 `_format_full()` / `_format_reflection_only()` 方法
  - 不改变 Portfolio Manager 的核心决策逻辑
  - 不修改 `PortfolioDecision` schema

  **Recommended Agent Profile**：
  - **Category**：`quick` — prompt 格式优化
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 2.2、2.4、2.5 并行）
  - **Parallel Group**：Wave 2
  - **Blocks**：Wave 3
  - **Blocked By**：Wave 1

  **References**：
  - `tradingagents/agents/managers/portfolio_manager.py:45-50` — 当前 lessons_line 构造
  - `tradingagents/agents/utils/memory.py:284-298` — `_format_full()` 和 `_format_reflection_only()` 的输出格式
  - `tradingagents/agents/utils/agent_utils.py` — 新增辅助函数的放置位置

  **Acceptance Criteria**：
  - [ ] past_context 注入格式包含分节标题（同一股票 vs 跨股票）
  - [ ] 历史经验与当前分析上下文有清晰分隔
  - [ ] 端到端运行后 PM 决策中提到历史经验时有可追溯的标注

  **QA Scenarios**：

  ```
  Scenario: 历史经验注入格式清晰
    Tool: Bash
    Preconditions: 至少有 1 次历史运行记录（trading_memory.md 有内容）
    Steps:
      1. 新建 memory 条目：手动写入一条历史决策到 trading_memory.md
      2. 再次运行同一 ticker 端到端流程
      3. 检查 PM 的 investment_thesis：应引用历史教训且有可追溯格式
    Expected Result: PM 输出包含结构化的历史经验引用
    Failure Indicators: 历史经验以原始嵌套方式出现在输出中
    Evidence: .sisyphus/evidence/task-2-3-past-context-format.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): improve Portfolio Manager past_context injection format with section headers`
  - Files: `tradingagents/agents/managers/portfolio_manager.py`, `tradingagents/agents/utils/agent_utils.py`

- [x] 2.4. 统一中英文输出策略

  **What to do**：
  - **A. 扩展语言指令范围**：在以下 agent 中添加 `get_language_instruction()` 调用：
    - `trader.py` 的 system message（已在 Task 2.1 中处理）
    - `research_manager.py` 的 prompt 末尾
  - **B. Schema 字段描述多语言**：修改 `schemas.py` 的 `Field(description=...)` — 当 `output_language == "Chinese"` 时在 render 函数中追加中文标签，或将 schema 描述改为中英双语
  - **C. 验证无遗漏**：检查所有面向用户输出的 agent 都有语言指令调用

  **Must NOT do**：
  - 不给内部辩论 agent（Bull/Bear、Risk Debater）添加中文输出——保持英文以保证推理质量
  - 不改变 Pydantic schema 的 enum 值（Buy/Hold/Sell 保持不变）

  **Recommended Agent Profile**：
  - **Category**：`quick` — 语言指令传播
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 2.2、2.3、2.5 并行）
  - **Parallel Group**：Wave 2
  - **Blocks**：Wave 3
  - **Blocked By**：Wave 1

  **References**：
  - `tradingagents/agents/utils/agent_utils.py:24-35` — `get_language_instruction()` 定义
  - `tradingagents/agents/managers/research_manager.py:22-48` — Research Manager prompt（需添加语言指令）
  - `tradingagents/agents/trader/trader.py:33-49` — Trader prompt（Task 2.1 中处理）
  - `tradingagents/agents/schemas.py:61-101, 109-163, 171-228` — 三个 schema 的 Field description 和 render 函数

  **Acceptance Criteria**：
  - [ ] Research Manager 输出中文（中文模式下）
  - [ ] Trader 输出中文（中文模式下，Task 2.1 覆盖）
  - [ ] Schema 字段在中文模式下有对应中文标签
  - [ ] 内部辩论 agent（Bull/Bear/Risk）仍输出英文

  **QA Scenarios**：

  ```
  Scenario: 中文模式全链路中文输出
    Tool: Bash
    Preconditions: config["output_language"] = "Chinese"
    Steps:
      1. 运行端到端流程（600519, output_language=Chinese）
      2. 检查 Research Manager 的 investment_plan 推荐理由：应为中文
      3. 检查 Trader 的 reasoning：应为中文
      4. 检查 PM 的 executive_summary：应为中文
    Expected Result: 所有面向用户的决策节点输出中文
    Failure Indicators: Research Manager 或 Trader 输出英文
    Evidence: .sisyphus/evidence/task-2-4-all-chinese.txt

  Scenario: 英文模式全链路英文输出
    Tool: Bash
    Preconditions: config["output_language"] = "English"
    Steps:
      1. 运行端到端流程（NVDA, output_language=English, market_type=US_STOCK）
      2. 验证 Research Manager + Trader + PM 输出英文
    Expected Result: 英文模式正常输出
    Failure Indicators: 任何 agent 混入中文
    Evidence: .sisyphus/evidence/task-2-4-all-english.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): unify Chinese output across Research Manager, Trader, and schema labels`
  - Files: `tradingagents/agents/managers/research_manager.py`, `tradingagents/agents/schemas.py`

- [x] 2.5. 修复 Risk Debater 首轮空响应（与 Task 0.5.A 协调）

  **What to do**：
  - 确保 Task 0.5.A 的首轮空响应修复正确覆盖了所有 3 个 risk debater
  - **额外优化**（本 task）：
    - 首轮 prompt 增加："This is the opening round. Present your initial risk assessment without referencing other analysts (no arguments from them exist yet)."
    - 反驳轮 prompt 增加："Focus on countering the specific points raised by the aggressive/conservative/neutral analyst. Introduce risk metrics or data the opponent overlooked."
  - 验证 `aggressive_debator.py`、`conservative_debator.py`、`neutral_debator.py` 的 prompt 均已正确处理首轮/反驳轮区分

  **Must NOT do**：
  - 不重复 Task 0.5.A 的修复（先检查是否已完成）
  - 不改变风险辩论的 tri-agent 拓扑

  **Recommended Agent Profile**：
  - **Category**：`quick` — 验证 + 小额增强
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 2.2、2.3、2.4 并行）
  - **Parallel Group**：Wave 2
  - **Blocks**：Wave 3
  - **Blocked By**：Wave 1 + Task 0.5 完成

  **References**：
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py:19-31` — 需检查的 prompt
  - `tradingagents/agents/risk_mgmt/conservative_debator.py:19-31`
  - `tradingagents/agents/risk_mgmt/neutral_debator.py:19-31`

  **Acceptance Criteria**：
  - [ ] 3 个 risk debater 的首轮 prompt 均包含 "opening round" / "no arguments from other analysts exist yet" 指导
  - [ ] 反驳轮 prompt 包含 "countering specific points" 指导
  - [ ] 端到端运行后首轮无虚构引用

  **QA Scenarios**：

  ```
  Scenario: Risk 首轮输出不含对不存在的对手论点的引用
    Tool: Bash
    Preconditions: config["max_risk_rounds"] >= 2
    Steps:
      1. 运行端到端流程（600519, max_risk_rounds=2）
      2. 检查 Aggressive 首轮：不含 "Conservative analyst mentioned" / "Neutral said" 等
    Expected Result: 首轮为独立风险评估，无对手引用
    Failure Indicators: 首轮引用不存在的对手论点
    Evidence: .sisyphus/evidence/task-2-5-risk-first-round.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): add round-aware guard to risk debater first-round prompts`
  - Files: `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`

- [x] 3.1. 精简 Market Analyst 提示词

  **What to do**：
  - 修改 `market_analyst.py` 的 system_message，将内联的 ~1800 字符指标目录（第 25-49 行）精简为：
    - 保留：指标类别概览（MA / MACD / RSI / Bollinger / ATR / VWMA）及其一句话用途
    - 移除：每个指标的详细 "Usage" 和 "Tips" 段落（移至末尾参考资料区或完全移除）
    - 添加：`"完整指标说明请参见工具函数的参数描述。选择指标时优先考虑互补性，避免冗余（如不同时选 RSI 和 StochRSI）。"`
  - 保留所有的工具调用指导（先 `get_stock_data` 再 `get_indicators`）
  - 保留 Markdown 表格要求 + 语言指令

  **Must NOT do**：
  - 不修改 `technical_indicators_tools.py` 或其工具描述
  - 不删除任何指标的种类名称（确保 agent 仍知道有哪些可选指标）

  **Recommended Agent Profile**：
  - **Category**：`quick` — prompt 精简
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 3.2、3.3 并行）
  - **Parallel Group**：Wave 3
  - **Blocks**：Wave FINAL
  - **Blocked By**：Wave 2

  **References**：
  - `tradingagents/agents/analysts/market_analyst.py:24-52` — 当前 system_message，包含 ~1800 字符的指标目录

  **Acceptance Criteria**：
  - [ ] system_message 长度减少 ≥30%（约 ≤1200 字符）
  - [ ] 所有指标类别名称保留（agent 仍知道可选范围）
  - [ ] 工具调用指导保留完整

  **QA Scenarios**：

  ```
  Scenario: Market Analyst 仍能正确选择指标
    Tool: Bash
    Preconditions: Wave 3 完成
    Steps:
      1. 运行端到端流程（600519）
      2. 检查 market_report：应包含 RSI、MACD、Bollinger 等指标分析
    Expected Result: 报告包含多种技术指标分析，质量不低于优化前
    Failure Indicators: 指标种类明显减少或分析质量下降
    Evidence: .sisyphus/evidence/task-3-1-market-quality.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): trim Market Analyst prompt — move detailed indicator docs out of system message`
  - Files: `tradingagents/agents/analysts/market_analyst.py`

- [x] 3.2. 添加通用降级策略到所有 agent

  **What to do**：
  - 为所有面向用户的 agent（4 个分析师 + Research Manager + Trader + Portfolio Manager）在 prompt 末尾添加统一的降级提示：
    - `"降级策略：若数据源返回空或不可用，请在报告中明确标注数据局限性，并基于已有信息提供有限分析。不得编造数据或虚构未获取到的信息。若关键数据缺失导致无法形成有效结论，应坦诚告知并建议延后决策。"`（中文模式下）
  - 修改 `agent_utils.py` 的 `get_language_instruction()` 旁边新增 `get_degradation_instruction()` 辅助函数（返回降级提示文本）
  - 在以下文件的 system_message 末尾调用此函数：
    - `fundamentals_analyst.py`、`market_analyst.py`、`news_analyst.py`、`social_media_analyst.py`
    - `trader.py`、`research_manager.py`、`portfolio_manager.py`

  **Must NOT do**：
  - 不给内部辩论 agent（Bull/Bear/Risk）添加降级提示（它们的输入来自上游报告，不需要数据降级）
  - 不改变 tool 函数的异常处理逻辑（仅在 prompt 层添加降级指导）

  **Recommended Agent Profile**：
  - **Category**：`quick` — 统一模式传播
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 3.1、3.3 并行）
  - **Parallel Group**：Wave 3
  - **Blocks**：Wave FINAL
  - **Blocked By**：Wave 2

  **References**：
  - `tradingagents/agents/utils/agent_utils.py:24-35` — `get_language_instruction()` 模式（新增函数仿照）
  - `tradingagents/agents/analysts/fundamentals_analyst.py:30` — `get_language_instruction()` 调用点，新增降级指令同样位置
  - 其他 agent 的类似调用点

  **Acceptance Criteria**：
  - [ ] `get_degradation_instruction()` 函数存在且根据语言返回中文/英文降级提示
  - [ ] 7 个面向用户 agent 的 system message 中包含降级提示
  - [ ] 降级提示包含"不得编造数据"的明确禁止

  **QA Scenarios**：

  ```
  Scenario: 无效 ticker 不导致崩溃或幻觉
    Tool: Bash
    Preconditions: Wave 3 完成
    Steps:
      1. 运行端到端流程（ticker="999999", date="2026-04-15"）
      2. 验证流程正常完成（不抛出异常）
      3. 检查各报告：包含 "数据有限"/"无法获取" 等降级表述，不包含虚构数据
    Expected Result: 流程完成，无异常，无虚构内容
    Failure Indicators: 崩溃、异常、或编造具体的数据/价格
    Evidence: .sisyphus/evidence/task-3-2-invalid-ticker.txt

  Scenario: 非交易日运行降级
    Tool: Bash
    Preconditions: Wave 3 完成
    Steps:
      1. 运行端到端流程（ticker="600519", date="2026-04-05"（周日））
      2. 验证市场分析师能识别非交易日并降级处理
    Expected Result: 降级提示或最近交易日数据
    Failure Indicators: 崩溃、或对空数据无处理
    Evidence: .sisyphus/evidence/task-3-2-non-trading-day.txt
  ```

  **Commit**：YES
  - Message: `feat(agents): add universal degradation strategy to all user-facing agents`
  - Files: `tradingagents/agents/utils/agent_utils.py`, 7 个 agent 文件的 system_message 部分

- [x] 3.3. 辩论 agent 添加轮次深度控制 + 上下文窗口保护

  **What to do**：
  - **A. 轮次深度控制**：在 `bull_researcher.py`、`bear_researcher.py` 和 3 个 risk debater 的反驳轮 prompt 中添加：
    - `"At least ONE new piece of evidence or analytical angle must be introduced this round. Do not repeat arguments from previous rounds."`
    - `"If you find yourself agreeing with the opponent on all points, acknowledge the convergence and suggest moving to decision."`
  - **B. 上下文窗口保护**：
    - 在 debate prompt 中限制历史长度：仅保留最近 2 轮（已在 Task 2.2 中处理 Researcher）
    - 对 Risk Debater 同样添加历史截断：当 `history` 超过 ~4000 字符时，仅保留最近 2 轮
    - 在 3 个 risk debater 的 f-string 中添加 `{history_truncated}` 变量替代全量 `{history}`，其中 `history_truncated` 为最近 2 轮

  **Must NOT do**：
  - 不修改 `conditional_logic.py` 的轮次计数逻辑
  - 不改变 debate state 的数据结构
  - 截断逻辑仅截取用于 prompt 显示的文本，不修改持久化的 state

  **Recommended Agent Profile**：
  - **Category**：`quick` — prompt 级截断 + 深度控制
  - **Skills**：`[]`

  **Parallelization**：
  - **Can Run In Parallel**：YES（与 Task 3.1、3.2 并行）
  - **Parallel Group**：Wave 3
  - **Blocks**：Wave FINAL
  - **Blocked By**：Wave 2

  **References**：
  - `tradingagents/agents/researchers/bull_researcher.py:15-32` — 当前 prompt（已含 `{history}`）
  - `tradingagents/agents/researchers/bear_researcher.py:15-34`
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py:19-31` — 当前 prompt（已含 `{history}`）
  - `tradingagents/agents/risk_mgmt/conservative_debator.py:19-31`
  - `tradingagents/agents/risk_mgmt/neutral_debator.py:19-31`

  **Acceptance Criteria**：
  - [ ] 反驳轮 prompt 包含 "new evidence or analytical angle" 要求
  - [ ] Prompt 中仅使用最近 2 轮辩论历史（而非全量 history）
  - [ ] 各 agent 的 max prompt 长度 ≤5000 字符（粗略估算）

  **QA Scenarios**：

  ```
  Scenario: 多轮辩论不重复观点
    Tool: Bash
    Preconditions: config["max_debate_rounds"] >= 3
    Steps:
      1. 运行端到端流程（600519, max_debate_rounds=3）
      2. 检查 debate history：每轮应有新数据点或新分析角度
    Expected Result: 3 轮各有新内容
    Failure Indicators: 轮 2-3 与轮 1 内容高度重复
    Evidence: .sisyphus/evidence/task-3-3-no-repeat.txt
  ```

  **Commit**：YES
  - Message: `refactor(agents): add debate depth control and context window protection for all debate agents`
  - Files: `tradingagents/agents/researchers/bull_researcher.py`, `bear_researcher.py`, `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`

---

## 最终验证波次

---

## 提交策略

---

## 成功标准
