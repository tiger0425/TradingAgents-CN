# 市场维度注入——股票分析上下文增强

## 摘要

> **核心目标**：将大盘状态、板块轮动、资金流向、市场宽度等市场维度数据系统性地注入 TradingAgents 多智能体分析管道，使各智能体在个股分析时感知整体市场环境。
>
> **交付物**：
> - `get_market_context()` 纯数据获取函数（akshare，零 LLM 调用）
> - Market Analyst 工具链扩展 + prompt 增强
> - Bull/Bear Researcher prompt 注入市场上下文
> - Portfolio Manager prompt 注入校准参考
> - `enable_market_context` 配置开关
>
> **预估工作量**：中等
> **并行执行**：是 — 3 个波次
> **关键路径**：数据函数 → 状态字段 → 工具注册 → Prompt 注入

---

## 背景

### 原始需求
用户观察：当前股票分析结果严重依赖个股数据值（技术指标、财务数据），没有考虑市场整体环境。例如，个股 RSI 低位 + MACD 死叉被当作做空信号，但在大盘强势突破、板块领涨时，这可能是洗盘而非做空时机。

### 讨论总结
**关键决策**：
- 不新增独立的"市场分析师"节点（避免额外 LLM 调用开销）
- 在市场数据模块用纯函数（无 LLM），复用 akshare API
- 一次性在 `_run_graph()` 中获取 market_context，存入 AgentState
- Market Analyst 增加 `get_market_context` 工具 + prompt 引用
- Bull/Bear 研究员、PM 的 prompt 注入结构化市场上下文
- 通过 `enable_market_context` 配置开关控制

### 研究结论
- **akshare 市场数据 API 已验证**：`stock_market_fund_flow`（大盘资金流）、`stock_sector_fund_flow_rank`（板块资金流排名）、`stock_sse_deal_daily`（上交所每日概况）、`stock_zh_index_daily`（已在用）均可用
- **架构匹配**：现有 AgentState 类型系统、工具注册模式、prompt 注入模式都可复用

### Metis 审查
**已采纳的缺口**：
- **缓存策略**：market_context 按日期缓存（`market_context_{date}.json`），同一天多股票复用
- **降级处理**：非交易日 / API 失败返回明确降级信息，不阻塞管道
- **Token 限制**：market_context 注入内容 ≤ 500 tokens
- **配置开关**：`enable_market_context`（默认 true），支持 A/B 测试
- **US Stock 兼容**：market_context 在美股模式下优雅降级

---

## 目标

### 核心目标
在 TradingAgents 分析管道中系统性注入市场环境维度，提升决策质量。

### 具体交付物
- `tradingagents/dataflows/market_context.py` — 新文件，纯数据获取模块
- `tradingagents/agents/utils/market_context_tools.py` — `get_market_context` 工具函数
- 修改 `tradingagents/graph/propagation.py` — AgentState 新增 `market_context` 字段
- 修改 `tradingagents/agents/utils/agent_states.py` — 类型定义
- 修改 `tradingagents/graph/trading_graph.py` — 工具注册 + 状态注入
- 修改 `tradingagents/agents/analysts/market_analyst.py` — 工具 + prompt
- 修改 `tradingagents/agents/researchers/bull_researcher.py` — prompt 注入
- 修改 `tradingagents/agents/researchers/bear_researcher.py` — prompt 注入
- 修改 `tradingagents/agents/managers/portfolio_manager.py` — prompt 注入
- 修改 `tradingagents/default_config.py` — 配置项

### 验收标准
- [ ] `get_market_context("2026-05-09")` 返回含指数状态、板块轮动、资金流向、市场宽度的格式化字符串
- [ ] 美股模式 (`market_type: "US_STOCK"`) 返回 `"Market context unavailable for US stocks"`
- [ ] `enable_market_context: false` 时，所有 prompt 中不含 market_context
- [ ] 完整管道 `ta.propagate("600519", "2026-05-09")` 不因注入而报错
- [ ] AgentState JSON 序列化成功（market_context 为 string）

### Must Have
- 零 LLM 调用的市场数据获取
- 按日期缓存，同一天多次分析复用
- 配置开关可关闭
- Token 限制 ≤ 500 tokens

### Must NOT Have（护栏）
- **禁止**新增独立 Market Analyst 节点（不修改 `setup.py` 拓扑）
- **禁止**在非 LLM 代码中添加择时过滤逻辑
- **禁止**修改 News Analyst / Sentiment Analyst / Fundamentals Analyst
- **禁止**修改 AnalysisArchive schema
- **禁止**修改 ContextAssembly 的逻辑
- **禁止** market_context 数据进入 debate history（只注入 prompt，不追加到 history 字符串）

---

## 验证策略

> **零人工干预** — 所有验证由执行 agent 通过命令行工具完成。

### 测试决策
- **基础设施存在**：项目已有 `pytest` 基础设施（`pip install -e .[dev]`）
- **自动化测试**：测试后补（Tests-after）
- **框架**：pytest

### QA 策略
每个任务必须包含 agent 执行的 QA 场景。证据保存至 `.sisyphus/evidence/task-{N}-{scenario-slug}.log`。
- **后端/CLI**：使用 Bash（`python -c` 或 `pytest`）执行，验证输出
- **API/数据**：使用 Bash（`python -c`）直接调用函数，验证返回值

---

## 执行策略

### 并行执行波次

```
Wave 1（立即开始——基础设施）：
├── Task 1: market_context 数据模块 [quick]
├── Task 2: AgentState 类型 + 配置项 [quick]
└── Task 3: 工具函数 get_market_context [quick]

Wave 2（依赖 Wave 1——核心集成）：
├── Task 4: _run_graph 状态注入 + 缓存 [deep]
├── Task 5: Market Analyst 工具注册 + prompt [quick]
├── Task 6: Bull Researcher prompt 注入 [quick]
├── Task 7: Bear Researcher prompt 注入 [quick]
└── Task 8: Portfolio Manager prompt 注入 [quick]

Wave 3（依赖 Wave 2——验证与收尾）：
├── Task 9: 集成测试 + 端到端验证 [quick]
└── Task 10: 边界情况 + 回退测试 [quick]
```

关键路径：Task 1 → Task 3 → Task 4 → Task 9
并行加速：~60% 快于顺序执行
最大并发：3（Wave 1），5（Wave 2）

### Agent 调度摘要
- **Wave 1**：3 个 `quick` — 数据模块、类型定义、工具函数
- **Wave 2**：1 个 `deep` — 状态注入，4 个 `quick` — prompt 修改
- **Wave 3**：2 个 `quick` — 测试验证

---

## 待办事项

- [x] 1. 市场上下文数据模块：`tradingagents/dataflows/market_context.py`

  **任务内容**：
  - 创建新文件 `tradingagents/dataflows/market_context.py`
  - 实现 `fetch_market_context(trade_date, market_type)` 函数，包括：
    - **指数状态**：通过 `ak.stock_zh_index_daily(symbol="sh000001")` 获取上证指数 OHLCV，计算最近 5 日涨跌幅、当日涨跌幅
    - **板块轮动**：通过 `ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")` 获取板块资金流排名，提取前 3 领涨板块和后 3 领跌板块
    - **资金流向**：通过 `ak.stock_market_fund_flow()` 获取大盘主力资金净流入/流出
    - **市场宽度**：通过 `ak.stock_sse_deal_daily(date=...)` 获取上交所每日概况（涨跌家数、成交额）
  - 返回格式化字符串（Markdown），总长度 ≤ 800 字（约 500 tokens）
  - 美股模式下返回英文降级信息
  - 每个 akshare API 调用包裹 try/except，失败时返回 `"数据暂不可用"`

  **Must NOT 操作**：
  - 不调用任何 LLM（禁止 `from tradingagents.llm_clients`）
  - 不导入 `langchain` 或 `langgraph`
  - 不过滤或解释数据含义（只做格式化，不做归纳）

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：纯数据获取函数，无复杂逻辑
  - **技能**：`[]`
    - 无需特殊技能

  **并行化**：
  - **可并行**：是（WAVE 1，与 Task 2 并行）
  - **阻塞**：Task 3, Task 4
  - **依赖**：无

  **参考**：
  - `tradingagents/dataflows/akshare.py:154-211` — `get_stock_data()` 函数模式（try/except 包裹 + 格式化输出）
  - `tradingagents/dataflows/akshare.py:669-766` — `get_global_news()` 多 API 聚合模式 + 降级逻辑

  **验收标准**：
  - [ ] `fetch_market_context("2026-05-09", "A_SHARE")` 返回含 4 个 section 的格式化字符串
  - [ ] `fetch_market_context("2026-05-09", "US_STOCK")` 返回 `"Market context unavailable for US stocks"`
  - [ ] 任一 API 失败时函数不抛异常，对应 section 标注 `"数据暂不可用"`

  **QA 场景**：
  ```
  场景: A 股市场上下文正常获取
    Tool: Bash (python -c)
    Preconditions: akshare 已安装，网络可用
    Steps:
      1. 执行: python -c "from tradingagents.dataflows.market_context import fetch_market_context; print(fetch_market_context('2026-05-09', 'A_SHARE'))"
      2. 断言: 输出包含 "## 指数状态" "## 板块轮动" "## 资金流向" "## 市场宽度"
      3. 断言: 输出总字符数 ≤ 2000
    Expected Result: 4 个 section 均有数据或明确的降级标注
    Evidence: .sisyphus/evidence/task-1-market-context-fetch.log

  场景: 美股模式降级
    Tool: Bash (python -c)
    Steps:
      1. 执行: python -c "from tradingagents.dataflows.market_context import fetch_market_context; print(fetch_market_context('2026-05-09', 'US_STOCK'))"
      2. 断言: 输出包含 "Market context unavailable for US stocks"
    Evidence: .sisyphus/evidence/task-1-us-stock-fallback.log
  ```

  **提交**：是（独立提交）
  - Message: `feat(market): add market context data module`
  - Files: `tradingagents/dataflows/market_context.py`

- [x] 2. AgentState 类型扩展 + 配置项

  **任务内容**：
  - 在 `tradingagents/agents/utils/agent_states.py` 的 `AgentState` 中新增字段：
    ```python
    market_context: Annotated[str, "Market environment context for the analysis date"] = ""
    ```
  - 在 `tradingagents/graph/propagation.py` 的 `create_initial_state()` 中初始化：
    ```python
    "market_context": "",
    ```
  - 在 `tradingagents/default_config.py` 中新增配置项：
    ```python
    "enable_market_context": True,  # 市场上下文注入开关
    ```
  - 确保 `AgentState` 字段顺序一致（添加在 `market_report` 之后/附近）

  **Must NOT 操作**：
  - 不修改任何现有字段的类型或默认值

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：类型定义 + 配置项，简单修改

  **并行化**：
  - **可并行**：是（WAVE 1，与 Task 1 并行）
  - **阻塞**：Task 3, Task 4, Task 5, Task 6, Task 7, Task 8
  - **依赖**：无

  **参考**：
  - `tradingagents/agents/utils/agent_states.py:88-92` — 现有字段定义模式
  - `tradingagents/graph/propagation.py:57-60` — 状态初始化模式
  - `tradingagents/default_config.py` — 配置项添加位置

  **验收标准**：
  - [ ] `AgentState.__annotations__` 包含 `market_context` 键
  - [ ] `create_initial_state()` 返回字典含 `"market_context": ""`
  - [ ] `DEFAULT_CONFIG["enable_market_context"]` 为 `True`

  **QA 场景**：
  ```
  场景: 状态字段和配置项正确注册
    Tool: Bash (python -c)
    Steps:
      1. 执行: python -c "from tradingagents.agents.utils.agent_states import AgentState; print('market_context' in AgentState.__annotations__)"
      2. 断言: 输出 "True"
      3. 执行: python -c "from tradingagents.default_config import DEFAULT_CONFIG; print(DEFAULT_CONFIG.get('enable_market_context'))"
      4. 断言: 输出 "True"
    Evidence: .sisyphus/evidence/task-2-state-config-check.log
  ```

  **提交**：是（合并至 Task 1 提交或独立提交）
  - Message: `feat(market): add market_context state field and config flag`
  - Files: `tradingagents/agents/utils/agent_states.py`, `tradingagents/graph/propagation.py`, `tradingagents/default_config.py`

- [x] 3. 工具函数 `get_market_context`

  **任务内容**：
  - 创建 `tradingagents/agents/utils/market_context_tools.py`
  - 使用 `@tool` 装饰器定义 `get_market_context`：
    ```python
    @tool
    def get_market_context(
        trade_date: Annotated[str, "Current analysis date, yyyy-mm-dd"],
    ) -> str:
        """Retrieve market environment context including index status,
        sector fund flow, capital flow, and market breadth."""
        from tradingagents.dataflows.config import get_config
        from tradingagents.dataflows.market_context import fetch_market_context
        config = get_config()
        market_type = config.get("market_type", "A_SHARE")
        return fetch_market_context(trade_date, market_type)
    ```
  - 在 `tradingagents/agents/utils/agent_utils.py` 中导出 `get_market_context`
  - 在 `tradingagents/graph/trading_graph.py:163-198` 的 `_create_tool_nodes()` 中：
    - 在 `"market"` 的 `ToolNode` 列表中添加 `get_market_context`

  **Must NOT 操作**：
  - 不在 tool 函数内做数据格式化或归纳

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：薄包装层，逻辑极简

  **并行化**：
  - **可并行**：是（WAVE 1，与 Task 1, 2 并行）
  - **阻塞**：Task 5
  - **依赖**：Task 1（数据模块）, Task 2（配置项）

  **参考**：
  - `tradingagents/agents/utils/core_stock_tools.py:6-22` — `@tool` 装饰器 + `route_to_vendor` 模式
  - `tradingagents/graph/trading_graph.py:166-173` — `"market"` 的 `ToolNode` 列表添加模式

  **验收标准**：
  - [ ] `get_market_context("2026-05-09")` 返回非空字符串
  - [ ] `get_market_context` 在 `agent_utils.py` 中被导出
  - [ ] `_create_tool_nodes()["market"]` 的 ToolNode 列表中包含 `get_market_context`

  **QA 场景**：
  ```
  场景: 工具函数正常返回
    Tool: Bash (python -c)
    Steps:
      1. 执行: python -c "from tradingagents.agents.utils.market_context_tools import get_market_context; result = get_market_context.invoke({'trade_date': '2026-05-09'}); print(len(result) > 0)"
      2. 断言: 输出 "True"
    Evidence: .sisyphus/evidence/task-3-tool-check.log

  场景: 工具注册到 Market Analyst 节点
    Tool: Bash (python -c)
    Steps:
      1. 执行: python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; ta = TradingAgentsGraph(selected_analysts=['market']); node = ta.tool_nodes.get('market'); print(node is not None); print(len(node.tools))"
      2. 断言: node 存在且 tools 数量 ≥ 3（原 2 个 + get_market_context）
    Evidence: .sisyphus/evidence/task-3-tool-registration.log
  ```

  **提交**：是（与 Task 1 合并或独立）
  - Message: `feat(market): add get_market_context tool`
  - Files: `tradingagents/agents/utils/market_context_tools.py`, `tradingagents/agents/utils/agent_utils.py`, `tradingagents/graph/trading_graph.py`

- [x] 4. `_run_graph()` 中集成 market_context 获取与缓存

  **任务内容**：
  - 在 `tradingagents/graph/trading_graph.py` 的 `_run_graph()` 方法中（约第 483 行，`init_agent_state` 创建之前）：
    - 检查 `config.get("enable_market_context")` 是否为 `True`
    - 若是，调用 `fetch_market_context(trade_date, market_type)` 获取市场上下文
    - 将结果存入 `init_agent_state["market_context"]`
  - 实现缓存：在 `DataCache` 中新建 `market` 命名空间
    - 缓存键：`market_context_{date}.json`
    - 同一日期多次 propagation 直接读缓存，不重复调用 akshare
  - 添加日志：`logger.info("Market context assembled for %s", trade_date)`

  **Must NOT 操作**：
  - 不在 `propagate()` 中获取（必须在 `_run_graph()` 中，确保 `trade_date` 参数已解析）

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 理由：涉及缓存集成、异常处理、跨模块状态传递，需要全面理解数据流

  **并行化**：
  - **可并行**：否（阻塞 WAVE 2 其他任务）
  - **阻塞**：Task 5, Task 6, Task 7, Task 8
  - **依赖**：Task 1（数据模块）, Task 2（状态字段）

  **参考**：
  - `tradingagents/graph/trading_graph.py:461-489` — `_run_graph()` 中 `knowledge_context` 装配模式（参照实现 market_context 注入）
  - `tradingagents/dataflows/cache.py` — `DataCache.get_or_fetch()` 缓存模式

  **验收标准**：
  - [ ] `enable_market_context: True` 时，`init_agent_state["market_context"]` 非空
  - [ ] `enable_market_context: False` 时，`init_agent_state["market_context"]` 为空字符串
  - [ ] 同一天第二次调用直接从缓存读取（日志可见）
  - [ ] akshare API 失败时 `market_context` 包含降级信息，管道不中断

  **QA 场景**：
  ```
  场景: market_context 注入到 AgentState
    Tool: Bash (python -c)
    Preconditions: enable_market_context=True
    Steps:
      1. 执行: 编写测试脚本调用 ta.propagate("600519", "2026-05-09")，检查 final_state["market_context"] 非空
      2. 断言: market_context 字符串包含 "指数状态" 或降级信息
    Evidence: .sisyphus/evidence/task-4-state-injection.log

  场景: 缓存验证——同日期第二次调用
    Tool: Bash (grep 日志)
    Steps:
      1. 连续两次调用 propagate("600519", "2026-05-09")
      2. 检查日志中第二次调用是否出现 "Market context cached" 或跳过 akshare 调用的迹象
    Evidence: .sisyphus/evidence/task-4-cache-verification.log

  场景: 配置关闭
    Tool: Bash (python -c)
    Steps:
      1. 设置 enable_market_context=False，调用 propagate
      2. 断言: final_state["market_context"] 为空字符串 ""
    Evidence: .sisyphus/evidence/task-4-config-off.log
  ```

  **提交**：是（独立提交）
  - Message: `feat(market): integrate market_context fetch into _run_graph with cache`
  - Files: `tradingagents/graph/trading_graph.py`

- [x] 5. Market Analyst prompt 增强 + 上下文引用

  **任务内容**：
  - 修改 `tradingagents/agents/analysts/market_analyst.py`：
    - 在 `system_message` 末尾追加市场上下文引用指令：
      ```
      **Market Environment Context**:
      The current market environment data is available via the `get_market_context` tool.
      Call this tool at the START of your analysis to understand the broader market conditions
      (index trends, sector rotation, capital flows, market breadth) before interpreting
      individual stock technical indicators. Factor the market environment into your
      assessment of whether technical signals indicate genuine trends or market-driven noise.
      ```
    - 在 `prompt.partial()` 中注入预获取的 `market_context`（来自 state 字段），
      作为 prompt 的静态上下文（不等 agent 调用工具）
    - 读取 state 中的 `market_context` 字段（若为空则不注入）

  **Must NOT 操作**：
  - 不修改 tools 列表（已在 Task 3 中添加）
  - 不删除或覆盖已有的 `system_message` 内容

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：prompt 模板修改，逻辑简单

  **并行化**：
  - **可并行**：是（WAVE 2，与 Task 6, 7, 8 并行）
  - **依赖**：Task 3（工具注册）, Task 4（状态注入）

  **参考**：
  - `tradingagents/agents/analysts/market_analyst.py:25-39` — system_message 结构
  - `tradingagents/agents/analysts/market_analyst.py:42-54` — prompt 构建和 partial 注入模式

  **验收标准**：
  - [ ] system_message 包含 `get_market_context` 引用
  - [ ] prompt 中注入 `market_context` 字符串（当非空时）
  - [ ] `enable_market_context: False` 时 prompt 不含 market_context

  **QA 场景**：
  ```
  场景: Market Analyst prompt 包含市场上下文
    Tool: Bash (python -c)
    Steps:
      1. 编写脚本模拟 market_analyst_node 调用，检查生成的 prompt 内容
      2. 断言: prompt 中包含 "市场环境" 或 "Market Environment"
      3. 断言: 当 market_context 非空时，prompt 中包含市场数据片段
    Evidence: .sisyphus/evidence/task-5-market-analyst-prompt.log
  ```

  **提交**：与 Task 6/7/8 合并至一个 Prompt 提交
  - Message: `feat(market): inject market context into agent prompts`
  - Files: `tradingagents/agents/analysts/market_analyst.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`, `tradingagents/agents/managers/portfolio_manager.py`

- [x] 6. Bull Researcher prompt 注入市场上下文

  **任务内容**：
  - 修改 `tradingagents/agents/researchers/bull_researcher.py`：
    - 从 `state` 中读取 `market_context` 字段
    - 在 `prompt` 末尾追加（在 `{opponent_reference}` 之后）：
      ```
      **Current Market Environment:**
      {market_context}
      
      Factor the above market environment into your analysis.
      A strong bull thesis should acknowledge and explain why positive
      signals persist despite any negative market backdrop, or why the
      market tailwind amplifies bullish signals.
      ```
    - 只在 `market_context` 非空且 `enable_market_context` 为 True 时注入

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：prompt 模板修改

  **并行化**：
  - **可并行**：是（WAVE 2，与 Task 5, 7, 8 并行）
  - **依赖**：Task 4（状态注入）

  **参考**：
  - `tradingagents/agents/researchers/bull_researcher.py:40-60` — prompt 构建模式

  **验收标准**：
  - [ ] Bull Researcher prompt 中包含 `**Current Market Environment:**` section
  - [ ] market_context 为空时不注入
  - [ ] 注入的 market_context 不被追加到 `history` 字符串（只注入 prompt，不存储到 debate state）

  **QA 场景**：
  ```
  场景: Bull prompt 包含市场上下文
    Tool: Bash (python -c)
    Steps:
      1. 模拟 bull_researcher 调用，检查 prompt 内容
      2. 断言: prompt 中包含 "Current Market Environment"
      3. 断言: 当 market_context 包含 "上证" 时，prompt 中包含对应片段
    Evidence: .sisyphus/evidence/task-6-bull-prompt.log
  ```

  **提交**：合并至 Task 5 的 Prompt 提交

- [x] 7. Bear Researcher prompt 注入市场上下文

  **任务内容**：
  - 与 Task 6 对称实现，修改 `tradingagents/agents/researchers/bear_researcher.py`
  - 尾部追加：
    ```
    **Current Market Environment:**
    {market_context}
    
    Factor the above market environment into your risk assessment.
    A strong bear thesis should identify how negative signals are
    amplified by adverse market conditions, or acknowledge when
    bearish signals contradict a bullish market backdrop.
    ```

  **推荐 Agent 配置**：
  - **类别**：`quick`

  **并行化**：
  - **可并行**：是（WAVE 2，与 Task 5, 6, 8 并行）
  - **依赖**：Task 4（状态注入）

  **参考**：
  - `tradingagents/agents/researchers/bear_researcher.py:40-62` — prompt 构建模式

  **验收标准**：
  - [ ] Bear Researcher prompt 中包含 `**Current Market Environment:**` section

  **QA 场景**：
  ```
  场景: Bear prompt 包含市场上下文
    Tool: Bash (python -c)
    Steps:
      1. 模拟 bear_researcher 调用，检查 prompt 内容
      2. 断言: prompt 中包含 "Current Market Environment"
    Evidence: .sisyphus/evidence/task-7-bear-prompt.log
  ```

  **提交**：合并至 Task 5 的 Prompt 提交

- [x] 8. Portfolio Manager prompt 注入市场校准参考

  **任务内容**：
  - 修改 `tradingagents/agents/managers/portfolio_manager.py`：
    - 从 `state` 中读取 `market_context` 字段
    - 在 `prompt` 中（`{format_t_plus_1_constraint(...)}` 之前）追加：
      ```python
      market_context = state.get("market_context", "")
      if market_context:
          prompt += f"""
      **Market Calibration Reference:**
      {market_context}
      
      Use this market context to calibrate your final decision:
      - In strongly bullish market conditions, modest stock-level bearish signals may warrant Hold rather than Sell
      - In strongly bearish market conditions, even strong stock-level bullish signals warrant caution
      - If market and stock signals align, increase conviction; if they conflict, explain the tension
      """
      ```
    - 只在 `market_context` 非空且 `enable_market_context` 为 True 时注入
    - 确保注入内容在 `format_limit_constraint` 之前，在 `{lessons_line}` 之后

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：prompt 模板修改

  **并行化**：
  - **可并行**：是（WAVE 2，与 Task 5, 6, 7 并行）
  - **依赖**：Task 4（状态注入）

  **参考**：
  - `tradingagents/agents/managers/portfolio_manager.py:80-105` — prompt 构建模式

  **验收标准**：
  - [ ] PM prompt 中包含 `**Market Calibration Reference:**` section
  - [ ] 校准指令涵盖"牛市中弱做空信号 → Hold"和"熊市中强做多信号 → 谨慎"两个方向
  - [ ] market_context 为空时不注入

  **QA 场景**：
  ```
  场景: PM prompt 包含市场校准参考
    Tool: Bash (python -c)
    Steps:
      1. 模拟 portfolio_manager_node 调用，检查生成的 prompt
      2. 断言: prompt 中包含 "Market Calibration Reference"
      3. 断言: prompt 中包含市场校准指令文本
    Evidence: .sisyphus/evidence/task-8-pm-prompt.log
  ```

  **提交**：合并至 Task 5 的 Prompt 提交

- [x] 9. 集成测试：端到端管道验证

  **任务内容**：
  - 编写测试脚本验证完整管道：
    - `enable_market_context: True` 时运行 `ta.propagate("600519", "2026-05-09")`
    - 检查 `final_state["market_context"]` 非空且包含有效数据
    - 检查 `final_state["market_report"]` 中包含市场上下文引用
    - 检查 `final_state["final_trade_decision"]` 非空
  - 验证 JSON 序列化：`json.dumps(final_state)` 成功
  - 验证 `_log_state()` 写入的 JSON 文件包含 `market_context` 字段且可解析
  - 验证 `enable_market_context: False` 时管道正常运行且 `market_context` 为空
  - 测试 `market_type: "US_STOCK"` 时管道不报错

  **Must NOT 操作**：
  - 不提交测试文件到仓库（测试脚本放 `/tmp`）

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：测试脚本，逻辑简单

  **并行化**：
  - **可并行**：是（WAVE 3，与 Task 10 并行）
  - **依赖**：Task 4, 5, 6, 7, 8

  **参考**：
  - `tradingagents/graph/trading_graph.py:347-452` — `propagate()` 完整调用流程
  - `tradingagents/graph/trading_graph.py:571-611` — `_log_state()` JSON 写入模式

  **验收标准**：
  - [ ] `propagate()` 完整运行不报错，返回有效决策
  - [ ] `_log_state()` JSON 文件包含 `market_context` 字段
  - [ ] 美股模式不报错

  **QA 场景**：
  ```
  场景: 端到端 A 股管道
    Tool: Bash (python -c)
    Steps:
      1. 创建临时 Python 脚本，配置 enable_market_context=True，调用 ta.propagate("600519", "2026-05-09")
      2. 检查返回值 final_state 不报错
      3. 断言: final_state["market_context"] 非空
      4. 断言: final_state["final_trade_decision"] 非空
    Evidence: .sisyphus/evidence/task-9-e2e-ashare.log

  场景: 配置关闭管道
    Tool: Bash (python -c)
    Steps:
      1. enable_market_context=False，调用 propagate
      2. 断言: market_context 为空，管道不报错
    Evidence: .sisyphus/evidence/task-9-e2e-disabled.log

  场景: 美股兼容性
    Tool: Bash (python -c)
    Steps:
      1. market_type="US_STOCK"，调用 propagate("NVDA", "2026-01-15")
      2. 断言: 管道不报错
    Evidence: .sisyphus/evidence/task-9-e2e-us-stock.log
  ```

  **提交**：否（测试文件不提交）

- [x] 10. 边界情况测试

  **任务内容**：
  编写脚本测试以下边界情况：
  - **非交易日**：`trade_date="2026-05-01"`（劳动节），验证 `fetch_market_context` 返回降级信息而非抛异常
  - **akshare API 限流/失败**：mock 某个 akshare API 返回 None/Exception，验证降级逻辑
  - **缓存一致性**：同一天两次 propagate 不同股票，验证 `market_context` 内容相同（来自同一缓存）
  - **Token 预算**：检查 `market_context` 字符串长度 ≤ 2000 字符（约 500 tokens）
  - **空数据**：market_context 所有 section 均为"数据暂不可用"时，管道正常运行

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 理由：边界测试，逻辑简单

  **并行化**：
  - **可并行**：是（WAVE 3，与 Task 9 并行）
  - **依赖**：Task 1（数据模块）, Task 4（缓存集成）

  **验收标准**：
  - [ ] 非交易日返回降级信息
  - [ ] API 失败不抛异常
  - [ ] 多股票同天 market_context 一致
  - [ ] market_context 长度 ≤ 2000 字符

  **QA 场景**：
  ```
  场景: 非交易日降级
    Tool: Bash (python -c)
    Steps:
      1. 执行: python -c "from tradingagents.dataflows.market_context import fetch_market_context; print(fetch_market_context('2026-05-01', 'A_SHARE'))"
      2. 断言: 输出包含 "非交易日" 或 "数据暂不可用"，不抛异常
    Evidence: .sisyphus/evidence/task-10-non-trading-day.log

  场景: 同天多股票缓存一致性
    Tool: Bash (python -c)
    Steps:
      1. propagate("600519", "2026-05-09") 和 propagate("000001", "2026-05-09")
      2. 断言: 两次 market_context 内容相同
    Evidence: .sisyphus/evidence/task-10-cache-consistency.log
  ```

  **提交**：否（测试文件不提交）

---

## 最终验证波次（全部实现任务完成后）

> 4 个审查 agent 并行运行。全部 APPROVE 后，汇总结果提交给用户，等待显式 "okay" 确认。
>
> **未获得用户批准前，不要标注 F1-F4 为完成。** 如发现缺陷 → 修复 → 重新运行 → 再次提交 → 等待确认。

- [x] F1. **计划合规审计** — `oracle`
  读取计划全文，逐条检查：
  - Must Have：`get_market_context` 为纯函数（零 LLM 调用）、缓存按日期、开关可关闭、Token ≤ 500
  - Must NOT Have：无新增 Analyst 节点（`setup.py` 未变）、无择时过滤逻辑、无 AnalysisArchive schema 修改
  - 证据：读取 `tradingagents/dataflows/market_context.py`、`tradingagents/graph/setup.py`、`tradingagents/analysis_archive.py`
  输出：`Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **代码质量审查** — `unspecified-high`
  - 运行 `python -c "from tradingagents.dataflows.market_context import fetch_market_context; print(fetch_market_context('2026-05-09', 'A_SHARE'))"` 验证可运行
  - 检查所有修改文件：`as any`/`@ts-ignore`、空 catch、裸 print/console、注释掉的代码、未使用的 import
  - 检查 AI slop：过度注释、过度抽象、占位命名（data/result/item/temp）
  输出：`Build [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **手工 QA 执行** — `unspecified-high`
  执行所有 10 个任务的 QA 场景：
  - 逐条按照精确步骤、精确选择器、精确断言执行
  - 捕获证据到 `.sisyphus/evidence/`
  - 测试跨任务集成（market_context 从数据模块 → 状态注入 → prompt 展现的完整链路）
  - 测试边界：空数据、非交易日、美股模式、配置关闭
  输出：`Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **范围合规检查** — `deep`
  逐任务：读 "任务内容"，读实际 diff（`git diff`）。
  - 验证 1:1 —— spec 中的每项都已构建，spec 之外的没有添加
  - 检查 "Must NOT 操作" 合规性
  - 检测跨任务污染：Task N 触碰了 Task M 的文件
  - 标记未计入的改动
  输出：`Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## 提交策略

| 提交 | 描述 | 文件 |
|------|------|------|
| 1 | `feat(market): add market context data module and config` | `tradingagents/dataflows/market_context.py`, `tradingagents/agents/utils/agent_states.py`, `tradingagents/graph/propagation.py`, `tradingagents/default_config.py` |
| 2 | `feat(market): add get_market_context tool and integrate into pipeline` | `tradingagents/agents/utils/market_context_tools.py`, `tradingagents/agents/utils/agent_utils.py`, `tradingagents/graph/trading_graph.py` |
| 3 | `feat(market): inject market context into analyst and debate prompts` | `tradingagents/agents/analysts/market_analyst.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`, `tradingagents/agents/managers/portfolio_manager.py` |

---

## 成功标准

### 验证命令
```bash
# 1. 数据模块可独立运行
python -c "from tradingagents.dataflows.market_context import fetch_market_context; print(fetch_market_context('2026-05-09', 'A_SHARE'))"

# 2. 工具函数可通过 LLM 绑定
python -c "from tradingagents.agents.utils.market_context_tools import get_market_context; print(get_market_context.invoke({'trade_date': '2026-05-09'}))"

# 3. 完整管道不报错
python -c "
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
config = DEFAULT_CONFIG.copy()
config['enable_market_context'] = True
ta = TradingAgentsGraph(config=config, selected_analysts=['market'])
state, decision = ta.propagate('600519', '2026-05-09')
print('market_context length:', len(state.get('market_context', '')))
print('decision:', decision)
"

# 4. 配置关闭
python -c "
config = DEFAULT_CONFIG.copy()
config['enable_market_context'] = False
ta = TradingAgentsGraph(config=config, selected_analysts=['market'])
state, _ = ta.propagate('600519', '2026-05-09')
assert state.get('market_context') == '', 'market_context should be empty when disabled'
print('PASS: market_context disabled')
"
```

### 最终检查清单
- [ ] 所有 "Must Have" 已实现
- [ ] 所有 "Must NOT Have" 未违反
- [ ] 端到端管道 A 股模式运行成功
- [ ] 端到端管道美股模式不受影响
- [ ] 配置开关有效
- [ ] 缓存机制生效

---

## 提交策略

---

## 成功标准
