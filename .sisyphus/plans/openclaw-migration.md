# TradingAgents → OpenClaw 多 Agent 迁移方案

## 摘要

> **核心目标**：将现有基于 LangGraph 的 TradingAgents 交易框架完整迁移到 OpenClaw 原生多 Agent 架构，用 SOUL.md/AGENTS.md/MEMORY.md 替换 Python prompt 注入，用 MCP 服务器替换 LangChain @tool 绑定，用 sessions_spawn 并行扇出替换 LangGraph 顺序执行。
>
> **交付物**：
> - 1 个 akshare MCP 服务器（12 个工具）
> - 9 个 OpenClaw Agent 工作空间（各含 SOUL.md/AGENTS.md）
> - 1 个交易分析 SKILL.md 工作流
> - MEMORY.md 决策日志 + memory/ 每日日志
> - openclaw.json Gateway 配置（CLI + 飞书 + 微信）
> - 端到端验证通过（至少 3 只 A 股全流程分析）
>
> **预估工作量**：中等（8 个波段，约 4-5 周）
> **并行执行**：YES — 6 个波段
> **关键路径**：MCP Server → 分析师 Agent → PM 编排者 → 渠道集成 → 端到端验证

---

## 背景

### 源项目概况
TradingAgents 是基于 LangGraph 的多智能体金融交易框架（v0.2.4，基于 TauricResearch/TradingAgents 二次开发），目前特性：
- **13 个 Agent**：4 分析师（有工具绑定）+ 2 辩论研究员 + 1 研究经理 + 1 交易员 + 3 风险辩论者 + 1 PM + 1 消息清理器
- **LangGraph StateGraph** 编排：顺序分析师 → 循环辩论 → 研究经理 → 交易员 → 循环风险辩论 → PM
- **10 个 LLM 供应商**：通过工厂模式支持 OpenAI/Anthropic/Google/xAI/DeepSeek/Qwen/GLM/Azure/Ollama/OpenRouter
- **akshare 数据源**：10 个数据函数 + a_share_calendar + a_share_constraints
- **A 股适配**：涨跌停限制、T+1 规则、交易日历、沪深300 基准
- **持久化**：LangGraph SqliteSaver 检查点 + TradingMemoryLog Markdown 决策日志

### 当前架构瓶颈
1. **4 个分析师顺序执行**（先 Market → 再 Social → 再 News → 再 Fundamentals），每次都要等前一个完成
2. **LangGraph 共享状态**（AgentState 16+ 字段）让 agent 紧耦合，难以独立测试
3. **Python 代码中硬编码 prompt**，修改需要代码改动
4. **LangChain 工具绑定**依赖特定框架，不利于跨平台复用

### 目标架构（OpenClaw 原生）
采用 OpenClaw 的层级化 Agent 模型，将 9 个 Agent 组织为深度 0→1 的树形结构：

```
深度 0: 🧠 PM Orchestrator（主 Agent）
  │  sessions_spawn ×4 并行 ↓
  ├── 📊 analyst-market       (MCP: get_stock_data, get_indicators, get_current_price)
  ├── 💬 analyst-sentiment    (MCP: get_news)
  ├── 📰 analyst-news         (MCP: get_news, get_global_news, get_insider_transactions)
  └── 📈 analyst-fundamentals (MCP: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement)
  │  sessions_spawn ×2 顺序 ↓
  ├── 🐂 researcher-bull      (接收: 4 份报告摘要 → 输出: 看涨论点)
  └── 🐻 researcher-bear      (接收: 报告摘要 + 看涨观点 → 输出: 看跌论点)
  │  sessions_spawn ↓ (仅多轮辩论时)
  └── ⚖️ researcher-manager   (接收: 辩论记录 → 输出: ResearchPlan)
  │  sessions_spawn ↓
  └── 💹 trader               (接收: ResearchPlan → 输出: TraderProposal)
  │  PM 自身推理 ↓
  └── 3 方风险评估（激进/保守/中性）→ 最终 PortfolioDecision
       → 写入 trading_memory.md
```

### Metis 审查
**已解决的缺口**：
- MCP 工具确认 12 个（新增 `get_insider_transactions`、`get_trading_calendar`、`get_limit_prices`）
- 代理间数据传递方案：JSON 摘要（≤2000 token）嵌入 sessions_spawn task 参数
- 保留 akshare 数据回退逻辑（东方财富 → 新浪）
- 保留 TradingMemoryLog Markdown 格式，适配到 MEMORY.md + memory/YYYY-MM-DD.md
- 结构化 Pydantic 输出转换为 AGENTS.md 中的输出模板定义

**标记为待验证**：
- DeepSeek reasoning_content 在 OpenClaw 中的兼容性（在 Wave 7 验证）
- sessions_spawn 中 `model` 参数动态覆盖是否支持两层 LLM 切换

---

## 目标

### 核心目标
将 TradingAgents 从 LangGraph 紧耦合架构完全迁移到 OpenClaw 原生多 Agent 架构，实现：
1. **分析师并行化**：4 个分析师同时运行，整体分析耗时减少 60%+
2. **声明式 Agent 定义**：用 SOUL.md/AGENTS.md 替代 Python 硬编码 prompt
3. **MCP 工具标准化**：12 个 akshare 工具统一为 MCP 协议
4. **多渠道接入**：CLI + 飞书 + 微信，24/7 可用
5. **记忆持久化**：OPENCLAW MEMORY.md 替换 LangGraph 检查点

### 具体交付物
- `akshare-mcp-server/`：12 个 MCP 工具的 FastMCP 服务器
- `~/.openclaw/workspace/{agent_name}/SOUL.md` × 9
- `~/.openclaw/workspace/{agent_name}/AGENTS.md` × 9
- `~/.openclaw/workspace/pm_orchestrator/SKILL.md`：交易分析工作流
- `~/.openclaw/openclaw.json`：Gateway + 多渠道 + MCP 配置
- `trading_memory.md` + `memory/YYYY-MM-DD.md` 每日日志

### 必须包含
- [ ] 所有 4 个分析师可并行运行（sessions_spawn ×4）
- [ ] 辩论循环支持可配置轮次（默认 3）
- [ ] A 股涨跌停/T+1/交易日历约束保留
- [ ] 中文输出（所有 Agent 使用中文）
- [ ] 决策日志持久化（跨会话可检索）
- [ ] CLI/飞书/微信三种触发方式

### 必须不包含（防护规则）
- [ ] **不**开发回测引擎
- [ ] **不**集成 yfinance/alpha_vantage 数据供应商
- [ ] **不**实现自动交易执行
- [ ] **不**开发 Web 仪表板/GUI
- [ ] **不**添加第 10 个以上 Agent
- [ ] **不**开发自定义 OpenClaw 插件
- [ ] **不**涉及模型训练/微调
- [ ] **不**在 SOUL.md/AGENTS.md 中硬编码 API 密钥
- [ ] **不**支持多用户会话

---

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| MCP 框架 | FastMCP（Python） | 原生 Python 支持，可直接复用现有 akshare 代码 |
| 工具命名规范 | `akshare_{action}_{resource}` | 遵循 OpenClaw MCP 约定，如 `akshare_get_stock_history` |
| Agent 间数据格式 | JSON 摘要（≤2000 token） | 避免上下文溢出，可比结构化 Markdown 更易解析 |
| 辩论终止条件 | maxDebateRounds=3 或双方重复率 >80% | 平衡分析深度与成本 |
| 风险3方 → PM 内推理 | 不生成子 Agent | 减少深度 2 嵌套，降低复杂度 |
| LLM 层级 | 分析师/辩论用 cheap 模型，PM/Trader 用 premium | 继承当前 quick/deep 两级策略 |
| 数据回退 | 东方财富 → 新浪 fallback | 保留当前 `route_to_vendor()` 逻辑 |
| 输出格式 | 所有 MCP 工具返回 JSON | 统一当前混合格式（CSV/Markdown/Text） |
| 飞书集成 | `openclaw channels login --channel feishu` | 官方支持，WebSocket 长连接 |
| 微信集成 | `@tencent-weixin/openclaw-weixin` 插件 | 社区插件，QR 登录 |

---

## 验证策略

> **零人工干预** — 所有验证由 Agent 自动执行。无例外。

### 测试决策
- **基础设施**：无现有测试框架（OpenClaw 生态）
- **自动化测试**：Agent 执行 QA 为主
- **框架**：Bash（curl/dev command）+ 文件断言

### QA 策略
每个任务包含 Agent 执行 QA 场景（见 TODO 模板）。证据保存到 `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`。

- **MCP 工具**：curl 测试端点 + JSON schema 验证
- **Agent 行为**：检查 SOUL.md/AGENTS.md 文件完整性 + 输出格式验证
- **端到端**：执行完整分析流程，检查所有中间输出和最终决策
- **渠道**：Gateway 状态检查 + 消息发送/接收验证

---

## 执行策略

### 并行执行波段

> 最大化吞吐量：相同波段内的独立任务并行执行。
> 目标：每波段 3-6 个任务。少于 3 个任务（除最终波段外）= 拆分不足。

```
波段 1（立即开始 — MCP 基础设施）：
├── 任务 1: akshare MCP Server 项目骨架 [quick]
├── 任务 2: 行情数据 MCP 工具（3个） [quick]
├── 任务 3: 基本面 MCP 工具（4个） [quick]
├── 任务 4: 新闻 MCP 工具（3个） [quick]
├── 任务 5: 日历+约束 MCP 工具（2个） [quick]
└── 任务 6: MCP Server 集成测试 [quick]

波段 2（波段 1 完成后 — 4 个分析师 Agent，最大并行）：
├── 任务 7: Market Analyst Agent [quick]
├── 任务 8: Sentiment Analyst Agent [quick]
├── 任务 9: News Analyst Agent [quick]
└── 任务 10: Fundamentals Analyst Agent [quick]

波段 3（波段 2 完成后 — 辩论 + 裁决 Agent）：
├── 任务 11: Bull Researcher Agent [quick]
├── 任务 12: Bear Researcher Agent [quick]
└── 任务 13: Research Manager Agent [quick]

波段 4（波段 3 完成后 — 交易 + 编排 Agent）：
├── 任务 14: Trader Agent [quick]
└── 任务 15: PM Orchestrator Agent + SKILL.md [deep]

波段 5（波段 4 完成后 — 记忆 + 配置）：
├── 任务 16: MEMORY.md 决策日志系统 [quick]
├── 任务 17: openclaw.json Gateway 配置 [quick]
└── 任务 18: CLI 触发入口 [quick]

波段 6（波段 5 完成后 — 渠道集成）：
├── 任务 19: 飞书渠道集成 [quick]
└── 任务 20: 微信渠道集成 [quick]

波段 7（波段 6 完成后 — 端到端验证）：
├── 任务 21: 单只 A 股全流程验证 [deep]
├── 任务 22: 多类型 A 股批量测试 [deep]
└── 任务 23: 边缘场景测试 [deep]

波段 FINAL（全部任务完成后 — 4 个并行审查，然后用户确认）：
├── 任务 F1: 计划合规审计 (oracle)
├── 任务 F2: 代码质量审查 (unspecified-high)
├── 任务 F3: 实际手动 QA (unspecified-high + playwright)
└── 任务 F4: 范围一致性检查 (deep)
→ 呈现结果 → 获取用户明确确认
```

**关键路径**：任务 1 → 任务 2-5 → 任务 6 → 任务 7-10 → 任务 11-12 → 任务 13 → 任务 14 → 任务 15 → 任务 16-17 → 任务 19-20 → 任务 21 → F1-F4

**并行加速比**：波段 1 可并行 6 个任务，波段 2 可并行 4 个任务。分析师并行化使分析阶段从顺序 ~120s 降至 ~35s（约 70% 加速）。

### Agent 调度摘要

- **波段 1**：**6** — T1-T6 → `quick`
- **波段 2**：**4** — T7-T10 → `quick`
- **波段 3**：**3** — T11-T13 → `quick`
- **波段 4**：**2** — T14 → `quick`，T15 → `deep`
- **波段 5**：**3** — T16-T18 → `quick`
- **波段 6**：**2** — T19-T20 → `quick`
- **波段 7**：**3** — T21-T23 → `deep`
- **FINAL**：**4** — F1 → `oracle`，F2 → `unspecified-high`，F3 → `unspecified-high`，F4 → `deep`

---

## 待办事项

> 实现 + 测试 = 一个任务。不可分离。
> 每个任务必须包含：推荐 Agent 画像 + 并行化信息 + QA 场景。
> **缺少 QA 场景的任务是不完整的。无一例外。**

### 波段 1：akshare MCP Server（基础设施）

- [ ] 1. akshare MCP Server 项目骨架

  **做什么**：
  - 在项目根创建 `akshare-mcp-server/` 目录
  - 使用 FastMCP 搭建基础服务器框架
  - 定义 `pyproject.toml`（依赖：fastmcp, akshare>=1.14.0, pandas）
  - 创建 `server.py` 主入口（端口 8000，health 端点）
  - 注册 FastMCP 实例，声明服务器元信息（名称：akshare-mcp，版本：1.0.0）
  - 测试 health 端点是否正常响应

  **禁止做**：
  - 不要在这个任务中实现任何具体工具函数
  - 不要引入 yfinance 或 alpha_vantage 依赖

  **推荐 Agent 画像**：
  - **分类**：`quick` — 标准项目脚手架搭建
  - **技能**：无特殊要求

  **并行化**：
  - **可并行**：NO（所有后续 MCP 工具依赖此骨架）
  - **阻止**：任务 2、3、4、5

  **参考**：
  - 模式参考：zwldarren/akshare-one-mcp（GitHub）的 FastMCP 项目结构
  - 外部参考：FastMCP 官方文档 `https://gofastmcp.com/getting-started/welcome`

  **验收标准**：
  - [ ] `akshare-mcp-server/` 目录存在
  - [ ] `akshare-mcp-server/pyproject.toml` 含 fastmcp + akshare 依赖
  - [ ] `akshare-mcp-server/server.py` 可启动（`python server.py`）
  - [ ] `curl http://localhost:8000/health` 返回 `{"status": "ok"}`

  **QA 场景**：
  ```
  场景：MCP Server 健康检查
    工具：Bash (curl)
    步骤：
      1. 启动 server：`cd akshare-mcp-server && python server.py &`
      2. 等待 3 秒
      3. `curl -s http://localhost:8000/health`
    预期结果：HTTP 200，响应体包含 "status": "ok"
    失败指示：连接拒绝或非 200 状态码
    证据：.sisyphus/evidence/task-1-health.json
  ```

  **提交**：YES（独立提交）
  - 消息：`feat(mcp): akshare MCP server project scaffold`
  - 文件：`akshare-mcp-server/`

- [ ] 2. 行情数据 MCP 工具（3 个）

  **做什么**：
  - 在 `akshare-mcp-server/tools/market.py` 中实现 3 个工具：
    - `akshare_get_stock_history(symbol, start_date, end_date)` → 历史 OHLCV（前复权），JSON 格式
    - `akshare_get_indicators(symbol, indicator_names)` → 技术指标时间序列，JSON 格式
    - `akshare_get_current_price(symbol)` → 实时行情快照（30 秒缓存），JSON 格式
  - 每个工具使用 `@mcp.tool()` 装饰器注册
  - 参数使用 Annotated 类型 + Field(description) 提供中文说明
  - 输出统一为 `{"status": "ok", "data": [...], "source": "sina"}` JSON
  - 复用现有 `dataflows/akshare.py` 的数据获取逻辑
  - OHLCV 缓存逻辑保留（`_load_ohlcv_akshare()` 模式，5 年窗口）

  **禁止做**：
  - 不要返回 CSV/Markdown 格式（统一 JSON）
  - 不要在工具中打印日志（使用 logger）

  **推荐 Agent 画像**：
  - **分类**：`quick` — Python 数据函数封装
  - **技能**：无特殊要求

  **并行化**：
  - **可并行**：YES（与任务 3、4、5 并行）
  - **并行组**：波段 1（与任务 3、4、5）
  - **被阻止**：任务 1

  **参考**：
  - 数据源参考：现有 `tradingagents/dataflows/akshare.py` 中的 `get_stock_data()`、`get_indicators()`、`get_current_price()`
  - MCP 模式参考：FastMCP 工具注册 `@mcp.tool()` 装饰器

  **验收标准**：
  - [ ] `akshare-mcp-server/tools/market.py` 存在
  - [ ] `akshare_get_stock_history("600519", "2026-01-01", "2026-01-15")` 返回 ≥10 条 OHLCV 记录
  - [ ] `akshare_get_indicators("600519", "rsi,macd")` 返回含 rsi 和 macd 字段的 JSON
  - [ ] `akshare_get_current_price("600519")` 返回实时价格且带 source 字段

  **QA 场景**：
  ```
  场景：获取 A 股历史行情（正常路径）
    工具：Bash (curl MCP endpoint)
    步骤：
      1. 调用 MCP 工具 endpoint：curl 发送 tools/call 请求
      2. 参数：symbol="600519", start_date="2026-01-05", end_date="2026-01-15"
    预期结果：返回 JSON 数组，每项含 date/open/high/low/close/volume，至少 5 条记录
    证据：.sisyphus/evidence/task-2-stock-history.json

  场景：获取不存在的股票代码（异常路径）
    工具：Bash (curl)
    步骤：
      1. 调用 ak_share_get_stock_history("999999", "2026-01-01", "2026-01-15")
    预期结果：返回 {"status": "error", "message": "数据不可用"} 而非崩溃
    证据：.sisyphus/evidence/task-2-invalid-symbol.json
  ```

  **提交**：YES（与任务 3、4、5 一起提交）
  - 消息：`feat(mcp): market data tools (stock history, indicators, real-time price)`

- [ ] 3. 基本面 MCP 工具（4 个）

  **做什么**：
  - 在 `akshare-mcp-server/tools/fundamentals.py` 中实现 4 个工具：
    - `akshare_get_fundamentals(symbol)` → 综合财务指标（PE/PB/ROE/毛利率等），JSON
    - `akshare_get_balance_sheet(symbol)` → 资产负债表，JSON
    - `akshare_get_cashflow(symbol)` → 现金流量表，JSON
    - `akshare_get_income_statement(symbol)` → 利润表，JSON
  - 复用现有 `dataflows/akshare.py` 中 4 个基本面方法
  - 保留 akshare 双源（新浪 + 东方财富）fallback 逻辑
  - 输出统一为 JSON 格式，含 `source` 字段标识数据来源

  **禁止做**：
  - 不要返回原始 CSV 文本

  **推荐 Agent 画像**：
  - **分类**：`quick`
  - **技能**：无特殊要求

  **并行化**：
  - **可并行**：YES（与任务 2、4、5 并行）
  - **并行组**：波段 1

  **参考**：
  - 现有实现：`tradingagents/dataflows/akshare.py` 中的 `get_fundamentals()`、`get_balance_sheet()` 等

  **验收标准**：
  - [ ] 4 个工具均可正常调用（使用 600519 测试）
  - [ ] 返回 JSON 格式，含财务字段名
  - [ ] `akshare_get_fundamentals("600519")` 返回 ≥5 个财务指标

  **QA 场景**：
  ```
  场景：获取贵州茅台基本面数据
    工具：Bash (curl)
    步骤：
      1. 调用 ak_share_get_fundamentals("600519")
    预期结果：返回 JSON 含 PE、PB、ROE、净利润增长率等字段
    证据：.sisyphus/evidence/task-3-fundamentals.json

  场景：数据源 fallback（东方财富 → 新浪）
    工具：Bash
    步骤：
      1. 模拟东方财富不可用（环境变量 MOCK_EASTMONEY_DOWN=1）
      2. 调用 ak_share_get_fundamentals("600519")
    预期结果：返回数据且 source="sina_fallback"
    证据：.sisyphus/evidence/task-3-fallback.json
  ```

  **提交**：YES（与任务 2、4、5 一起提交）

- [ ] 4. 新闻 MCP 工具（3 个）

  **做什么**：
  - 在 `akshare-mcp-server/tools/news.py` 中实现 3 个工具：
    - `akshare_get_news(symbol)` → 个股新闻，JSON
    - `akshare_get_global_news(look_back_days)` → 全球宏观新闻，JSON
    - `akshare_get_insider_transactions(symbol)` → 大股东增减持，JSON
  - 复用现有 `dataflows/akshare.py` 中对应方法
  - `akshare_get_news` 支持东方财富个股新闻源
  - `akshare_get_global_news` 支持多源回退（东方财富 → 上交所）

  **禁止做**：
  - 不要在工具内做新闻情感分析（留给 Agent）

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 2、3、5 并行）
  - **并行组**：波段 1

  **验收标准**：
  - [ ] 3 个工具均可正常调用
  - [ ] `akshare_get_news("600519")` 返回 ≥3 条新闻
  - [ ] `akshare_get_insider_transactions("600519")` 返回增减持数据

  **QA 场景**：
  ```
  场景：获取个股新闻
    工具：Bash (curl)
    步骤：调用 ak_share_get_news("600519")
    预期结果：返回 JSON 数组，每项含 title/date/content 字段，至少 3 条
    证据：.sisyphus/evidence/task-4-news.json

  场景：获取宏观新闻（无股票代码）
    工具：Bash
    步骤：调用 ak_share_get_global_news(3)
    预期结果：返回近 3 天全球宏观新闻列表
    证据：.sisyphus/evidence/task-4-global-news.json
  ```

  **提交**：YES（与任务 2、3、5 一起提交）

- [ ] 5. 日历 + 约束 MCP 工具（2 个）

  **做什么**：
  - 在 `akshare-mcp-server/tools/calendar.py` 中实现：
    - `akshare_get_trading_calendar(date)` → 返回 {is_trading_day, last_trading_day, next_trading_day}，JSON
  - 在 `akshare-mcp-server/tools/constraints.py` 中实现：
    - `akshare_get_limit_prices(symbol)` → 返回 {limit_up, limit_down, market_type}，JSON
  - 复用现有 `dataflows/a_share_calendar.py` 和 `dataflows/a_share_constraints.py`
  - 日历工具自动处理中国节假日（春节、国庆等）

  **禁止做**：
  - 不要在约束工具中注入交易建议

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 2、3、4 并行）
  - **并行组**：波段 1

  **验收标准**：
  - [ ] `akshare_get_trading_calendar("2026-02-01")` 正确判断是否为交易日
  - [ ] `akshare_get_limit_prices("600519")` 返回涨跌停价格
  - [ ] ST 股票（如 000585）返回 5% 而非 10% 涨跌停

  **QA 场景**：
  ```
  场景：判断周六为非交易日
    工具：Bash (curl)
    步骤：调用 ak_share_get_trading_calendar("2026-01-10")（周六）
    预期结果：is_trading_day=false, last_trading_day=2026-01-09, next_trading_day=2026-01-12
    证据：.sisyphus/evidence/task-5-calendar-saturday.json

  场景：ST 股票 5% 涨跌停
    工具：Bash
    步骤：调用 ak_share_get_limit_prices("000585")
    预期结果：涨跌停幅度为 5%（非 10%）
    证据：.sisyphus/evidence/task-5-st-limit.json
  ```

  **提交**：YES（与任务 2、3、4 一起提交）

- [ ] 6. MCP Server 集成测试

  **做什么**：
  - 编写 `akshare-mcp-server/test_integration.py`
  - 测试所有 12 个工具的端到端调用
  - 验证统一 JSON 输出格式（`status`、`data`、`source` 字段）
  - 验证错误处理（无效股票代码、网络超时、空数据）
  - 验证数据回退逻辑（东方财富 → 新浪 fallback）
  - 运行 `python test_integration.py` 确保全部通过

  **禁止做**：
  - 不要在此任务中添加新工具

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：NO（依赖任务 2-5 全部完成）
  - **被阻止**：任务 2、3、4、5

  **验收标准**：
  - [ ] `test_integration.py` 存在
  - [ ] 全部 12 个工具测试通过
  - [ ] 至少 3 个异常场景测试通过（无效代码、网络错误、空数据）

  **QA 场景**：
  ```
  场景：全部 12 个 MCP 工具可调用
    工具：Bash (python)
    步骤：
      1. cd akshare-mcp-server && python test_integration.py
    预期结果：12/12 tests passed，输出 "All integration tests passed"
    证据：.sisyphus/evidence/task-6-integration-test.txt
  ```

  **提交**：YES
  - 消息：`test(mcp): integration tests for all 12 akshare MCP tools`
  - 文件：`akshare-mcp-server/test_integration.py`

### 波段 2：分析师 Agent 工作空间（全部可并行）

- [ ] 7. Market Analyst Agent（技术面分析）

  **做什么**：
  - 创建 `~/.openclaw/workspace/analyst-market/` 工作空间
  - 编写 `SOUL.md`：定义为技术面分析师，专注 K 线形态、技术指标、趋势判断
  - 编写 `AGENTS.md`：
    - 工具白名单：`akshare_get_stock_history`, `akshare_get_indicators`, `akshare_get_current_price`
    - 输出模板：Markdown 报告格式（技术指标综述 + 趋势判断 + 支撑/阻力位 + Markdown 表格）
    - 行为约束：必须先用 get_stock_history 再 get_indicators；最多选 8 个互补指标
    - 语言：中文（"Write entire response in Chinese"）
  - 从现有 `tradingagents/agents/analysts/market_analyst.py` 移植系统 prompt 核心内容

  **禁止做**：
  - 不要在 SOUL.md/AGENTS.md 中硬编码 API 密钥
  - 不要引用其他分析师的数据

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 8、9、10 并行）
  - **并行组**：波段 2
  - **被阻止**：任务 6

  **参考**：
  - Prompt 来源：`tradingagents/agents/analysts/market_analyst.py` L25-51（system_message 内容）
  - 工具来源：`tradingagents/agents/utils/agent_utils.py` L4-7（工具导入）

  **验收标准**：
  - [ ] `~/.openclaw/workspace/analyst-market/SOUL.md` 存在
  - [ ] `~/.openclaw/workspace/analyst-market/AGENTS.md` 存在且含工具白名单 + 输出模板
  - [ ] SOUL.md 中定义的角色与现有 market_analyst 系统 prompt 一致

  **QA 场景**：
  ```
  场景：Agent 工作空间文件完整性
    工具：Bash (test)
    步骤：
      1. test -f ~/.openclaw/workspace/analyst-market/SOUL.md
      2. test -f ~/.openclaw/workspace/analyst-market/AGENTS.md
      3. grep "akshare_get_stock_history" ~/.openclaw/workspace/analyst-market/AGENTS.md
      4. grep "Chinese" ~/.openclaw/workspace/analyst-market/SOUL.md
    预期结果：所有检查通过（文件存在，含关键字）
    证据：.sisyphus/evidence/task-7-market-agent.txt
  ```

  **提交**：YES（与任务 8、9、10 一起提交）

- [ ] 8. Sentiment Analyst Agent（情绪分析）

  **做什么**：
  - 创建 `~/.openclaw/workspace/analyst-sentiment/` 工作空间
  - 编写 `SOUL.md`：定义为社交媒体情绪分析师，专注市场舆情和公众情绪
  - 编写 `AGENTS.md`：
    - 工具白名单：`akshare_get_news`
    - 输出模板：情绪综述 + 舆情热度评分（1-10）+ 正面/负面关键词 + Markdown 表格
    - 行为约束：关注最近 7 天舆情变化趋势
    - 语言：中文
  - 从现有 `tradingagents/agents/analysts/social_media_analyst.py` 移植核心 prompt

  **禁止做**：
  - 不要自行进行基本面或技术面分析

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 7、9、10 并行）

  **验收标准**：
  - [ ] `~/.openclaw/workspace/analyst-sentiment/SOUL.md` 存在
  - [ ] AGENTS.md 含 `akshare_get_news` 工具白名单
  - [ ] SOUL.md 含中文语言指令

  **QA 场景**：
  ```
  场景：Sentiment Agent 工作空间完整性
    工具：Bash
    步骤：
      1. test -f ~/.openclaw/workspace/analyst-sentiment/SOUL.md
      2. grep "舆情\|sentiment\|情绪" ~/.openclaw/workspace/analyst-sentiment/SOUL.md
    预期结果：文件存在，含情绪分析关键词
    证据：.sisyphus/evidence/task-8-sentiment-agent.txt
  ```

  **提交**：YES（与任务 7、9、10 一起提交）

- [ ] 9. News Analyst Agent（新闻分析）

  **做什么**：
  - 创建 `~/.openclaw/workspace/analyst-news/` 工作空间
  - 编写 `SOUL.md`：定义为新闻分析师，专注全球宏观新闻和行业动态
  - 编写 `AGENTS.md`：
    - 工具白名单：`akshare_get_news`, `akshare_get_global_news`, `akshare_get_insider_transactions`
    - 输出模板：宏观环境综述 + 行业影响分析 + 公司层面新闻摘要 + Markdown 表格
    - 行为约束：先全局再个股，区分宏观和微观影响
    - 语言：中文
  - 从现有 `tradingagents/agents/analysts/news_analyst.py` 移植核心 prompt

  **禁止做**：
  - 不要做技术面分析

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 7、8、10 并行）

  **验收标准**：
  - [ ] 工作空间完整（SOUL.md + AGENTS.md）
  - [ ] 工具白名单含 3 个 MCP 工具
  - [ ] 输出模板含宏观/行业/公司三层结构

  **QA 场景**：
  ```
  场景：News Agent 工作空间完整性
    工具：Bash
    步骤：
      1. grep "akshare_get_global_news" ~/.openclaw/workspace/analyst-news/AGENTS.md
      2. grep "akshare_get_insider_transactions" ~/.openclaw/workspace/analyst-news/AGENTS.md
    预期结果：两个工具名均出现
    证据：.sisyphus/evidence/task-9-news-agent.txt
  ```

  **提交**：YES（与任务 7、8、10 一起提交）

- [ ] 10. Fundamentals Analyst Agent（基本面分析）

  **做什么**：
  - 创建 `~/.openclaw/workspace/analyst-fundamentals/` 工作空间
  - 编写 `SOUL.md`：定义为基本面分析师，专注财务数据、估值和公司治理
  - 编写 `AGENTS.md`：
    - 工具白名单：`akshare_get_fundamentals`, `akshare_get_balance_sheet`, `akshare_get_cashflow`, `akshare_get_income_statement`
    - 输出模板：财务健康度评分 + 估值分析 + 成长性指标 + 风险提示 + Markdown 表格
    - 行为约束：至少覆盖 PE/PB/ROE/毛利率/净利润增长率 5 项指标
    - 语言：中文
  - 从现有 `tradingagents/agents/analysts/fundamentals_analyst.py` 移植核心 prompt

  **禁止做**：
  - 不要做技术面分析

  **推荐 Agent 画像**：
  - **分类**：`quick`

  **并行化**：
  - **可并行**：YES（与任务 7、8、9 并行）

  **验收标准**：
  - [ ] 工作空间完整
  - [ ] 工具白名单含 4 个 MCP 工具
  - [ ] 输出模板含 5 项必要财务指标

  **QA 场景**：
  ```
  场景：Fundamentals Agent 完整配置验证
    工具：Bash
    步骤：
      1. test -f ~/.openclaw/workspace/analyst-fundamentals/AGENTS.md
      2. grep -c "akshare_" ~/.openclaw/workspace/analyst-fundamentals/AGENTS.md
    预期结果：至少 4 个工具引用
    证据：.sisyphus/evidence/task-10-fundamentals-agent.txt
  ```

  **提交**：YES（与任务 7、8、9 一起提交）

### 波段 3：辩论 + 裁决 Agent

- [ ] 11. Bull Researcher Agent（看涨研究员）

  **做什么**：
  - 创建 `~/.openclaw/workspace/researcher-bull/` 工作空间
  - 编写 `SOUL.md`：看涨研究员，坚定持多头立场
  - 编写 `AGENTS.md`：
    - 输入：PM 传入的 4 份报告 JSON 摘要 + 熊方上轮论点
    - 输出模板：`**Bull Thesis**` + `**Supporting Evidence**(≥3条)` + `**Rebuttal to Bear**` + `**Confidence Score**(1-10)`
    - 语言：推理用英文，对外输出用中文
  - 从 `tradingagents/agents/researchers/bull_researcher.py` 移植核心辩论 prompt

  **禁止做**：不使用 MCP 工具（纯推理 Agent）

  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 12 并行），被阻止：任务 7-10
  **验收标准**：工作空间完整，输出模板含 Bull Thesis / Evidence / Rebuttal / Confidence Score

  **QA 场景**：
  ```
  场景：Bull Agent 输出模板验证
    工具：Bash
    步骤：
      1. grep "Bull Thesis" ~/.openclaw/workspace/researcher-bull/AGENTS.md
      2. grep "Supporting Evidence" ~/.openclaw/workspace/researcher-bull/AGENTS.md
    预期结果：全部关键词存在
    证据：.sisyphus/evidence/task-11-bull-agent.txt
  ```

  **提交**：YES（与任务 12、13 一起提交）

- [ ] 12. Bear Researcher Agent（看跌研究员）

  **做什么**：
  - 创建 `~/.openclaw/workspace/researcher-bear/` 工作空间
  - 编写 `SOUL.md`：看跌研究员，坚定持空头立场
  - 编写 `AGENTS.md`：
    - 输入：4 份报告摘要 + 牛方上轮论点
    - 输出模板：`**Bear Thesis**` + `**Risk Factors**(≥3条)` + `**Critique of Bull**` + `**Risk Score**(1-10)`
    - 语言：推理用英文，对外输出用中文
  - 从 `tradingagents/agents/researchers/bear_researcher.py` 移植核心 prompt

  **禁止做**：不使用 MCP 工具
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 11 并行）
  **验收标准**：工作空间完整，输出模板含 Bear Thesis / Risk Factors / Critique / Risk Score

  **QA 场景**：
  ```
  场景：Bear Agent 输出模板验证
    工具：Bash
    步骤：grep "Risk Factors\|Bear Thesis\|Critique" ~/.openclaw/workspace/researcher-bear/AGENTS.md
    预期结果：全部关键词存在
    证据：.sisyphus/evidence/task-12-bear-agent.txt
  ```

  **提交**：YES（与任务 11、13 一起提交）

- [ ] 13. Research Manager Agent（研究经理 / 辩论裁决者）

  **做什么**：
  - 创建 `~/.openclaw/workspace/researcher-manager/` 工作空间
  - 编写 `SOUL.md`：辩论裁决者，综合牛熊双方论点裁决
  - 编写 `AGENTS.md`：
    - 输出模板：`**Recommendation**: Buy/Overweight/Hold/Underweight/Sell` + `**Rationale**` + `**Strategic Actions**`
    - 评级指南：Buy（多头优势明显）、Hold（势均力敌）、Sell（空头优势明显）
    - 语言：中文
  - 从 `tradingagents/agents/managers/research_manager.py` 移植结构化输出逻辑

  **禁止做**：不引入新分析数据，不使用 MCP 工具
  **推荐 Agent 画像**：`quick`
  **并行化**：NO（依赖任务 11、12 完成）
  **验收标准**：工作空间完整，含 5 级评级量表

  **QA 场景**：
  ```
  场景：Research Manager 评级验证
    工具：Bash
    步骤：grep "Buy\|Overweight\|Hold\|Underweight\|Sell" ~/.openclaw/workspace/researcher-manager/AGENTS.md
    预期结果：全部 5 个评级关键词存在
    证据：.sisyphus/evidence/task-13-research-mgr.txt
  ```

  **提交**：YES（与任务 11、12 一起提交）

### 波段 4：交易 + 编排 Agent

- [ ] 14. Trader Agent（交易员）

  **做什么**：
  - 创建 `~/.openclaw/workspace/trader/` 工作空间
  - 编写 `SOUL.md`：交易员角色，基于研究计划生成具体交易提案
  - 编写 `AGENTS.md`：
    - 输出模板：`**Action**: Buy/Hold/Sell` + `**Entry Price**` + `**Stop Loss**` + `**Position Sizing**` + `**Reasoning**`
    - A 股约束感知：涨跌停价格检测（从 MCP 获取），标记不可执行价格
    - 安全声明：`⚠️ 本建议仅供研究参考，不构成投资建议。不会自动执行任何交易。`
    - 语言：中文
  - 从 `tradingagents/agents/trader/trader.py` 移植结构化输出逻辑

  **禁止做**：**绝对不要**建议或触发实际交易执行；不要遗漏安全声明
  **推荐 Agent 画像**：`quick`
  **并行化**：NO（依赖任务 13）
  **验收标准**：工作空间完整，输出模板含 Action/Entry Price/Stop Loss/Position Sizing，安全声明存在

  **QA 场景**：
  ```
  场景：Trader 安全声明验证
    工具：Bash
    步骤：grep -i "不构成\|仅供参考\|not.*advice" ~/.openclaw/workspace/trader/SOUL.md ~/.openclaw/workspace/trader/AGENTS.md
    预期结果：至少匹配 1 处安全声明
    证据：.sisyphus/evidence/task-14-trader-safety.txt
  ```

  **提交**：YES（与任务 15 一起提交）

- [ ] 15. PM Orchestrator Agent + SKILL.md（投资组合经理 / 编排者）

  **做什么**：
  - 创建 `~/.openclaw/workspace/pm_orchestrator/` 工作空间
  - 编写 `SOUL.md`：PM 编排者，最终决策者，负责协调整个分析流程
  - 编写 `AGENTS.md`：
    - 编排规则：sessions_spawn ×4 并行启动分析师 → 收集报告（压缩为 ≤2000 token JSON 摘要）→ 顺序启动辩论 → 启动交易员 → 自身 3 方风险评估 → 生成 PortfolioDecision
    - 子 Agent 配置：`runtime: "subagent"`, `runTimeoutSeconds: 300`, `announce: "parent"`
    - 辩论控制：`maxDebateRounds: 3`，重复率 >80% 提前终止
    - 3 方风险评估：激进视角（高风险高回报）、保守视角（最大回撤）、中性视角（风险收益平衡）
    - A 股约束：涨跌停 + T+1 + 交易日历检查
  - 编写 `SKILL.md`：5 步交易分析工作流（触发→分析师并行→辩论→交易→决策）
  - 最终决策模板：`**Rating**` + `**Executive Summary**` + `**Investment Thesis**` + `**Price Target**` + `**Time Horizon**`
  - 决策后写入 `trading_memory.md` + `memory/YYYY-MM-DD.md`
  - 从现有 PM、风控、约束模块移植逻辑

  **禁止做**：不要让子 Agent 结果直接返回用户；不要省略超时配置
  **推荐 Agent 画像**：`deep` — 系统最复杂 Agent，需深度推理
  **并行化**：NO（依赖任务 11-14 全部完成）
  **验收标准**：工作空间完整（SOUL.md+AGENTS.md+SKILL.md），SKILL.md 含 5 步工作流，AGENTS.md 含 sessions_spawn ×4 并行指令和 3 方风险评估

  **QA 场景**：
  ```
  场景：PM Orchestrator 编排能力验证
    工具：Bash
    步骤：
      1. grep "sessions_spawn" ~/.openclaw/workspace/pm_orchestrator/AGENTS.md
      2. grep "announce.*parent" ~/.openclaw/workspace/pm_orchestrator/AGENTS.md
      3. test -f ~/.openclaw/workspace/pm_orchestrator/SKILL.md
    预期结果：全部 3 项通过
    证据：.sisyphus/evidence/task-15-pm-orchestrator.txt

  场景：3 方风险评估逻辑验证
    工具：Bash
    步骤：grep "激进\|保守\|中性" ~/.openclaw/workspace/pm_orchestrator/AGENTS.md
    预期结果：全部 3 个视角被描述
    证据：.sisyphus/evidence/task-15-risk-perspectives.txt
  ```

  **提交**：YES（与任务 14 一起提交）

### 波段 5：记忆 + 配置 + CLI

- [ ] 16. MEMORY.md 决策日志系统

  **做什么**：
  - 在 PM Orchestrator 工作空间创建 `trading_memory.md`：存储结构化决策记录
  - 创建 `memory/` 目录：`memory/YYYY-MM-DD.md` 每日日志
  - 决策记录格式：`## [日期] [股票代码]` + Rating + Summary + Raw Return + Alpha Return + Reflection
  - 保留现有 `TradingMemoryLog` 的反思模式：每次新分析时读取历史决策，LLM 生成 2-4 句反思注入 PM prompt
  - 在 PM SKILL.md 中添加"读取记忆 → 注入上下文 → 分析 → 写入记忆"循环

  **禁止做**：不要在 MEMORY.md 中存储 API 密钥或敏感信息
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 17、18 并行）
  **验收标准**：trading_memory.md 模板存在，memory/ 目录结构定义完成

  **QA 场景**：
  ```
  场景：MEMORY.md 模板验证
    工具：Bash
    步骤：
      1. test -f ~/.openclaw/workspace/pm_orchestrator/trading_memory.md
      2. grep "Rating\|Summary\|Reflection" ~/.openclaw/workspace/pm_orchestrator/trading_memory.md
    预期结果：模板存在，含关键字段
    证据：.sisyphus/evidence/task-16-memory-template.txt
  ```

  **提交**：YES（与任务 17、18 一起提交）

- [ ] 17. openclaw.json Gateway 配置

  **做什么**：
  - 创建 `~/.openclaw/openclaw.json` 配置文件
  - 定义 9 个 Agent（`agents.list`）：
    - 每 Agent 含 `id`、`identity`、`workspace`、`model`（PM/Trader 用 premium，其余用 cheap）
  - 定义 MCP 服务器配置：`mcp.servers.akshare` 指向 localhost:8000
  - 定义 per-agent 工具权限：分析师仅可访问其领域 MCP 工具（白名单模式）
  - 配置文件结构参考 OpenClaw 官方多 Agent 示例

  **禁止做**：不要在配置文件中硬编码 API 密钥（使用环境变量 `env` 字段）
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 16、18 并行）
  **验收标准**：openclaw.json 存在，含 9 个 Agent 定义 + MCP 配置 + per-agent 工具白名单

  **QA 场景**：
  ```
  场景：Gateway 配置完整性验证
    工具：Bash
    步骤：
      1. test -f ~/.openclaw/openclaw.json
      2. python3 -c "import json; cfg=json.load(open('~/.openclaw/openclaw.json')); print(len(cfg['agents']['list']))"
    预期结果：输出 9（9 个 Agent 已配置）
    证据：.sisyphus/evidence/task-17-gateway-config.txt
  ```

  **提交**：YES（与任务 16、18 一起提交）

- [ ] 18. CLI 触发入口

  **做什么**：
  - 创建 `cli/analyze.sh`：命令行触发脚本
  - 功能：接收股票代码和日期参数 → 通过 OpenClaw CLI 发送分析指令到 PM Orchestrator
  - 用法：`./cli/analyze.sh 600519 2026-01-15`
  - 实现方式：`openclaw message send --agent pm_orchestrator "分析 {股票} 在 {日期} 的交易机会"`
  - 输出：等待并显示 PM 返回的 PortfolioDecision

  **禁止做**：不要在脚本中嵌入复杂的分析逻辑
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 16、17 并行）
  **验收标准**：`cli/analyze.sh` 存在且可执行

  **QA 场景**：
  ```
  场景：CLI 脚本语法验证
    工具：Bash
    步骤：
      1. test -x cli/analyze.sh
      2. bash -n cli/analyze.sh
    预期结果：脚本存在、可执行、语法正确
    证据：.sisyphus/evidence/task-18-cli-syntax.txt
  ```

  **提交**：YES（与任务 16、17 一起提交）

### 波段 6：渠道集成

- [ ] 19. 飞书渠道集成

  **做什么**：
  - 在 `openclaw.json` 添加飞书渠道配置：`channels.feishu`
  - 配置 bindings：飞书消息 → 路由到 `pm_orchestrator` Agent
  - 配置群聊 mention 模式：@Agent 触发分析
  - 执行 `openclaw channels login --channel feishu` 完成认证
  - 测试：通过飞书发送 "分析 600519" → 验证收到分析结果

  **禁止做**：不要在配置中共享飞书 App Secret
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 20 并行）
  **验收标准**：openclaw.json 含飞书渠道 + binding；Gateway 状态显示 feishu: connected

  **QA 场景**：
  ```
  场景：飞书渠道配置验证
    工具：Bash
    步骤：grep "feishu" ~/.openclaw/openclaw.json
    预期结果：匹配飞书配置项
    证据：.sisyphus/evidence/task-19-feishu-config.txt
  ```

  **提交**：YES（与任务 20 一起提交）

- [ ] 20. 微信渠道集成

  **做什么**：
  - 在 `openclaw.json` 添加微信渠道配置：`channels.wechat`
  - 安装 `@tencent-weixin/openclaw-weixin` 插件
  - 配置 bindings：微信消息 → `pm_orchestrator`
  - 配置 QR 登录

  **禁止做**：N/A
  **推荐 Agent 画像**：`quick`
  **并行化**：YES（与任务 19 并行）
  **验收标准**：openclaw.json 含微信渠道 + binding 配置

  **QA 场景**：
  ```
  场景：微信渠道配置验证
    工具：Bash
    步骤：grep "wechat" ~/.openclaw/openclaw.json
    预期结果：匹配微信配置项
    证据：.sisyphus/evidence/task-20-wechat-config.txt
  ```

  **提交**：YES（与任务 19 一起提交）

### 波段 7：端到端验证

- [ ] 21. 单只 A 股全流程验证

  **做什么**：
  - 使用 PM Orchestrator 完整分析 `600519`（贵州茅台）
  - 验证所有 9 个 Agent 被正确调用（通过 Gateway 日志）
  - 验证 4 个分析师并行执行（通过时间戳对比）
  - 验证辩论循环正常工作（输出含 Bull Thesis + Bear Thesis + Research Plan）
  - 验证 Trader 输出含安全声明
  - 验证 PM 最终输出 PortfolioDecision（含 Rating + Summary + Thesis）
  - 验证决策写入 trading_memory.md

  **禁止做**：不要跳过任何验证步骤
  **推荐 Agent 画像**：`deep` — 需要分析日志和输出质量
  **并行化**：NO（依赖任务 1-20 全部完成）
  **验收标准**：全流程无报错，最终输出含 5 级 Rating，trading_memory.md 已更新

  **QA 场景**：
  ```
  场景：600519 全流程分析
    工具：Bash (CLI + curl)
    步骤：
      1. ./cli/analyze.sh 600519 2026-01-15
      2. 检查输出含 "**Rating**:"
      3. curl MCP health 确认工具可用
    预期结果：全流程 300 秒内完成，输出含评级和中文摘要
    证据：.sisyphus/evidence/task-21-e2e-600519.txt
  ```

  **提交**：YES（与任务 22、23 一起提交）

- [ ] 22. 多类型 A 股批量测试

  **做什么**：
  - 测试至少 5 只不同类型 A 股：
    - 蓝筹：600519（茅台）
    - 成长：300750（宁德时代）
    - 金融：601398（工商银行）
    - 中小板：002415（海康威视）
    - ST 股票：000585（*ST东电）
  - 验证每只均完成分析且返回合理决策
  - 验证 ST 股票自动应用 5% 涨跌停限制
  - 记录每只分析耗时

  **禁止做**：不要对结果正确性做主观判断（仅验证流程完成）
  **推荐 Agent 画像**：`deep`
  **并行化**：NO（依赖任务 21）
  **验收标准**：5/5 只股票全流程无报错，ST 股票含 5% 涨跌停标注

  **QA 场景**：
  ```
  场景：ST 股票特殊规则验证
    工具：Bash
    步骤：./cli/analyze.sh 000585 2026-01-15
    预期结果：输出含 "5%" 或 "风险警示" 标注
    证据：.sisyphus/evidence/task-22-st-stock.txt
  ```

  **提交**：YES（与任务 21、23 一起提交）

- [ ] 23. 边缘场景测试

  **做什么**：
  - 测试非交易日分析：周六触发分析，验证输出含"非交易日"标注
  - 测试新股数据不足：分析上市 <60 天的股票，验证降级处理
  - 测试子 Agent 超时：设置短超时（5s），验证 PM 正确记录超时并降级
  - 测试数据源回退：模拟东方财富不可用，验证 fallback 到新浪
  - 测试辩论终止：设置 maxDebateRounds=1，验证单轮后正确终止

  **禁止做**：不要修改生产配置来进行测试（使用测试配置副本）
  **推荐 Agent 画像**：`deep`
  **并行化**：NO（依赖任务 21、22）
  **验收标准**：全部 5 个边缘场景正确处理，无崩溃

  **QA 场景**：
  ```
  场景：非交易日标记验证
    工具：Bash
    步骤：./cli/analyze.sh 600519 2026-01-10（周六）
    预期结果：输出含 "非交易日" 或 "盘后参考" 标记
    证据：.sisyphus/evidence/task-23-non-trading-day.txt
  ```

  **提交**：YES（与任务 21、22 一起提交）

---

## 最终验证波段

> 4 个审查 Agent 并行运行。全部必须 APPROVE。向用户呈现合并结果，获取明确确认后才能标记完成。
> **在获得用户确认之前，不要将 F1-F4 标记为已完成。**

- [ ] F1. **计划合规审计** — `oracle`
  从头到尾阅读计划。对每个"必须包含"：验证实现存在（读文件、curl 端点、运行命令）。对每个"必须不包含"：搜索代码库中的禁止模式——如发现则标注 `文件:行号` 并 REJECT。检查 `.sisyphus/evidence/` 中证据文件是否存在。对比交付物与计划。
  输出：`Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **代码质量审查** — `unspecified-high`
  运行 `python -c "import ast; ..."` 检查 Python 语法。审查所有更改文件：硬编码密钥、空异常捕获、未使用的导入。检查 AI 冗余：过度注释、过度抽象、通用命名（data/result/item/temp）。
  输出：`Syntax [PASS/FAIL] | MCP Tools [N/N] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **实际手动 QA** — `unspecified-high`
  从干净状态开始。执行每个任务的 QA 场景——遵循确切步骤，捕获证据。测试跨任务集成（功能协同工作，而非孤立）。测试边缘情况：空状态、无效输入、快速操作。保存到 `.sisyphus/evidence/final-qa/`。
  输出：`Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **范围一致性检查** — `deep`
  对每个任务：读取"做什么"，读取实际 diff（git log/diff）。验证 1:1——规范中所有内容均已构建（无遗漏），超出规范的内容均未构建（无蔓延）。检查"禁止做"合规性。检测跨任务污染：任务 N 触及任务 M 的文件。标记未计入的更改。
  输出：`Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## 提交策略

- **波段 1 完成**：`feat(mcp): akshare MCP server with 12 tools` — akshare-mcp-server/
- **波段 2 完成**：`feat(agents): 4 analyst agent workspaces` — workspaces/analyst-*/
- **波段 3 完成**：`feat(agents): debate researchers + research manager` — workspaces/researcher-*/
- **波段 4 完成**：`feat(agents): trader + PM orchestrator with SKILL.md` — workspaces/trader, pm_orchestrator
- **波段 5 完成**：`feat(memory): decision log + gateway config` — memory/, openclaw.json
- **波段 6 完成**：`feat(channels): feishu + wechat integration` — openclaw.json
- **波段 7 完成**：`test(e2e): full workflow verification` — evidence/

---

## 成功标准

### 验证命令
```bash
# SC-1: MCP Server 运行正常
curl http://localhost:8000/health
# 预期：{"status": "ok", "tools": 12}

# SC-2: 9 个 Agent 工作空间文件完整
for a in analyst-market analyst-sentiment analyst-news analyst-fundamentals \
         researcher-bull researcher-bear researcher-manager trader pm_orchestrator; do
  test -f ~/.openclaw/workspace/$a/SOUL.md && test -f ~/.openclaw/workspace/$a/AGENTS.md \
    && echo "$a: OK" || echo "$a: MISSING"
done
# 预期：9 个 agent 全部 OK

# SC-3: Gateway 启动，渠道在线
openclaw gateway status
# 预期：running + channels 含 feishu: connected

# SC-4: 端到端分析完成（3 只 A 股）
# 运行分析 600519（茅台）、000858（五粮液）、300750（宁德时代）
# 预期：每只返回 PortfolioDecision，含 Buy/Overweight/Hold/Underweight/Sell 评级 + 中文说明

# SC-5: 并行分析耗时 < 120 秒
# 预期：4 个分析师并行完成时间 < 120s（对比当前顺序 ~280s）
```

### 最终检查清单
- [ ] 全部 12 个 MCP 工具返回合法 JSON
- [ ] 全部 9 个 Agent 拥有 SOUL.md + AGENTS.md
- [ ] PM Orchestrator SKILL.md 可正确触发完整分析流程
- [ ] 决策日志持久化到 trading_memory.md
- [ ] CLI/飞书/微信三种渠道均可触发分析
- [ ] A 股涨跌停/T+1/交易日历约束正确注入
- [ ] 所有"必须不包含"项确认不存在
