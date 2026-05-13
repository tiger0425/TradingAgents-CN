# V1.2 收尾计划：剩余功能 + 冒烟验证

> **日期**：2026-05-13
> **范围**：P0（.env 创建 + 对话录入持仓）+ P1（OHLCV 预取 + 冒烟测试）
> **关联**：`.sisyphus/plans/v1-llm-planner.md`、`.sisyphus/plans/v1-gap-fix.md`
> **前序**：v1-gap-fix 已完成 → 4 Collector 接入 AkShare、DeepSeek 配置、freshness 维护

---

## 摘要

> **目标**：完成 V1.2 最后 4 个未实现项——创建运行环境（.env）、对话录入持仓（LLM 解析自然语言）、开盘前 OHLCV 预取、全链路冒烟验证。
> 
> **环境**：Docker Compose 已可用；DeepSeek API Key 已提供；4 Collector 已接入真实数据源。
> 
> **预估**：1.5-2 小时

---

## 背景

### 上轮完成状态

| 项目 | 状态 |
|------|:---:|
| DeepSeek v4-pro/flash 配置 | ✅ |
| 4 Collector 全接入 AkShare | ✅ |
| KB freshness.maintain() | ✅ |
| Phase 1-2 代码层 ($23$ 文件，2208 行) | ✅ |
| `.env` 文件 | 🔴 不存在 |
| 对话录入持仓 | 🔴 未实现 |
| OHLCV 数据预取 | 🔴 未实现 |
| 冒烟测试 | 🔴 未实施 |

### 后移项

| 后移 | 原因 |
|------|------|
| OpenClaw 推送集成 | 需 OpenClaw 实例，本期跳过 |
| tradingagents-platform 简化 | 外部仓库修改，独立处理 |
| 完整 e2e 测试 | 需大量 LLM 调用，成本不可控 |
| 模板进化验证 | 需多轮模拟，延迟 |
| Docker Compose 集成测试 | 已有 compose 文件但未包含 OpenClaw |

---

## 技术决策

### 对话录入持仓

- **方式**：新增 `POST /portfolio/chat` 端点，接收自然语言消息
- **解析**：LLM (`deepseek-v4-flash`) 提取 {action, ticker, name, cost_price, quantity}
- **写入**：调用 `PortfolioManager.add_holding()` / `remove_holding()` / `add_to_watchlist()`
- **降级**：LLM 失败时返回明确错误提示，不尝试正则解析

### OHLCV 数据预取

- **触发**：定时任务每日 09:00（开盘前 30 分钟）
- **范围**：持仓 + 自选的全部股票
- **数据**：`get_stock_data(symbol, start_date, end_date)` 获取 60 日 OHLCV
- **存储**：写入 KB 的 `stock_snapshot` collection
- **桥接**：`asyncio.to_thread()` 包裹同步 AkShare 调用

### 冒烟测试

- Collector 测试：每个 collector 的 `collect()` 不崩溃
- KB 完整性：写入→检索→新鲜度标签
- Planner 测试：传入触发词 → 返回有效 workflow plan
- 全部通过 Python 脚本执行，无需人工介入

---

## 执行策略

```
Wave 1: .env + 对话录入持仓（无依赖，立即开始）
   ├─ Task 1: .env 创建 + API Key 配置
   └─ Task 2: POST /portfolio/chat 端点

Wave 2: OHLCV 预取（依赖 Task 1 的 LLM 配置）
   └─ Task 3: BackgroundCollector._prefetch_watchlist_data()

Wave FINAL: 冒烟验证（ALL 完成后 — 3 并行验证）
   ├─ Task F1: Collector 冒烟测试
   ├─ Task F2: KB + Planner 集成测试
   └─ Task F3: 对话录入持仓验证
```

---

## 护栏（MUST NOT）

- ❌ 不修改 `akshare.py` 或 `market_context.py`
- ❌ 不修改 `scheduler.py` 核心调度（只在 collector 内加方法）
- ❌ 不新建 LLM 客户端
- ❌ 不做 OpenClaw 集成
- ❌ 不修改 `tradingagents-platform` 仓库

---

## TODO

- [x] 1. `.env` 文件创建 + DeepSeek API Key 配置

  **推荐 Agent**：`quick` | **并行**：是（与 Task 2 并行）

  **做什么**：
  - 复制 `.env.example` → `.env`
  - 将 `.env` 中的 `DEEPSEEK_API_KEY=` 替换为 `DEEPSEEK_API_KEY=sk-3c86ef0170b24156b293a731225fb6e5`
  - 确认文件存在且包含 API Key

  **不做**：不修改 .env.example

  **QA**：
  ```
  Scenario: .env 存在且含 API Key
    Tool: Bash
    Steps:
      1. grep "DEEPSEEK_API_KEY=sk-" .env
    Expected: 匹配 1 行
    Evidence: .sisyphus/evidence/task-1-env.txt
  ```

  **提交**：否（.env 不应提交到 git）

- [x] 2. `POST /portfolio/chat` 对话录入持仓端点

  **推荐 Agent**：`unspecified-high` | **并行**：否（依赖 Task 1 的 LLM 配置）

  **做什么**：

  ### 2.1 在 `api_server.py` 中新增端点

  ```python
  @app.post("/portfolio/chat")
  async def portfolio_chat(user_id: str = "default", message: str = ""):
  ```

  功能：
  - 接收自然语言消息（如「我买了茅台1000股成本1800」）
  - 调用 LLM (`deepseek-v4-flash`) 解析为结构化数据
  - 调用 `PortfolioManager.add_holding()` 写入 portfolio.yaml
  - 返回解析结果和确认消息

  ### 2.2 LLM Prompt 模板

  ```python
  PORTFOLIO_PARSE_PROMPT = """
  从用户消息中提取持仓操作，输出严格JSON：
  {
    "action": "add_holding" | "remove_holding" | "add_watchlist" | "unknown",
    "ticker": "6位代码",
    "name": "股票名称",
    "cost_price": 成本价(float),
    "quantity": 数量(int, 股),
    "entry_date": "YYYY-MM-DD",
    "notes": "备注"
  }
  消息: {message}
  """
  ```

  ### 2.3 降级处理

  - LLM 解析失败 → 返回 `{"error": "无法解析持仓信息", "message": "请提供股票代码和成本价，例如：我买了600519茅台1000股成本1800"}`
  - JSON 解析失败 → 返回错误提示
  - PortfolioManager 写入失败 → 返回错误信息

  ### 2.4 响应格式

  ```json
  {
    "action": "add_holding",
    "ticker": "600519",
    "name": "贵州茅台",
    "cost_price": 1800,
    "quantity": 1000,
    "confirmation": "已添加持仓：600519 贵州茅台，成本1800元，1000股"
  }
  ```

  **不做**：不新增前端页面、不实现 remove_from_watchlist、不添加 CLI 命令

  **参考**：
  - `tradingagents/api_server.py:25-29` → AnalyzeRequest 模型（参考 Pydantic 用法）
  - `tradingagents/portfolio/portfolio_manager.py:40-56` → `add_holding()` 方法签名
  - `tradingagents/planner/llm_planner.py:119-127` → `_fallback_plan()` LLM 降级模式

  **验收**：
  - [ ] `POST /portfolio/chat` 返回 200 并成功写入 portfolio.yaml
  - [ ] 不完整消息返回明确错误提示
  - [ ] LLM 不可用时降级为错误提示

  **QA**：
  ```
  Scenario: 对话录入茅台持仓成功
    Tool: Bash (curl)
    Steps:
      1. curl -s -X POST http://localhost:8000/portfolio/chat \
           -d 'user_id=test&message=我买了600519茅台1000股成本1800'
      2. 检查响应含 "action": "add_holding"
      3. 检查响应含 "ticker": "600519"
      4. 检查响应含 "cost_price": 1800
    Expected: 200, JSON 含正确持仓数据
    Evidence: .sisyphus/evidence/task-2-portfolio-chat.json

  Scenario: 不完整消息提示错误
    Tool: Bash (curl)
    Steps:
      1. curl -s -X POST http://localhost:8000/portfolio/chat \
           -d 'user_id=test&message=今天天气真好'
      2. 检查响应含 "error" 字段
    Expected: 200, JSON action="unknown" 或含 error
    Evidence: .sisyphus/evidence/task-2-portfolio-error.json
  ```

  **提交**：`feat(api): add POST /portfolio/chat for natural language portfolio entry` — `tradingagents/api_server.py`

- [x] 3. 自选股 OHLCV 数据预取

  **推荐 Agent**：`unspecified-high` | **并行**：否

  **做什么**：

  ### 3.1 新增 `tradingagents/collector/prefetch.py`

  ```python
  class PrefetchManager:
      def __init__(self, portfolio_mgr, kb, config=None): ...
      async def prefetch_all(self):
          """预取持仓/自选全部股票 60 日 OHLCV 到 KB。"""
          from ..dataflows.akshare import get_stock_data
          import asyncio
          tickers = self._gather_all_tickers()
          for ticker in tickers:
              ohlcv = await asyncio.to_thread(get_stock_data, ticker, start, end)
              if "No data" not in ohlcv:
                  self.kb.save("stock_snapshot", {"ticker": ticker, "data": ohlcv, "ohlcv_cached": True})
      def _gather_all_tickers(self):
          """从 PortfolioManager 收集所有持仓/自选 ticker。"""
  ```

  ### 3.2 在 `scheduler.py` 注册 cron job

  在 `_start_events()` 末尾添加：
  ```python
  from ..collector.prefetch import PrefetchManager
  self.prefetch = PrefetchManager(self.portfolio_mgr, self.kb)
  self.event_scheduler.add_job(
      self.prefetch.prefetch_all,
      'cron', day_of_week='mon-fri', hour=9, minute=0,
  )
  ```

  **不做**：不预取财务/公告数据、不修改现有调度频率

  **参考**：
  - `tradingagents/dataflows/akshare.py:155` → `get_stock_data(symbol, start_date, end_date)` signature
  - `tradingagents/collector/announcement_collector.py:63-95` → PortfolioManager 集成模式
  - `tradingagents/scheduler/scheduler.py:52-71` → `_start_events()` 添加新 cron job

  **验收**：prefetch 读取持仓+自选列表 → 逐股调用 get_stock_data → 写入 KB → 无股票时 skip

  **QA**：
  ```
  Scenario: 预取持仓 OHLCV 不崩溃
    Tool: Bash (python3 -c)
    Steps:
      创建 test 持仓 → asyncio.run(PrefetchManager(...).prefetch_all())
    Expected: 无异常，打印 "PREFETCH DONE"
    Evidence: .sisyphus/evidence/task-3-prefetch.txt
  ```

  **提交**：`feat(collector): add OHLCV prefetch for watchlist before market open` — `tradingagents/collector/prefetch.py`, `tradingagents/scheduler/scheduler.py`

- [x] F1. **Collector 冒烟测试** — `unspecified-high`
  4 个 collector 全部 `collect()` 验证：无崩溃、无 None（交易日），或合法 None（非交易日）。

- [x] F2. **KB + Planner 集成测试** — `unspecified-high`
  KB 写入→检索→Planner 覆盖率计算。验证 Planner 生成合法 workflow plan。

- [x] F3. **对话录入持仓验证** — `unspecified-high`
  `POST /portfolio/chat {"user_id":"test","message":"我买了茅台1000股成本1800"}` → 写入 portfolio.yaml → 验证。

---

## 提交策略

- **T1**: `chore: create .env from .env.example with DeepSeek API key` — .env
- **T2**: `feat(api): add POST /portfolio/chat endpoint` — api_server.py
- **T3**: `feat(collector): add OHLCV prefetch for watchlist` — collector/prefetch.py, scheduler/scheduler.py
- **FINAL**: `test: smoke verification of all V1.2 components` — evidence files

---

## 成功标准

- [x] `.env` 文件存在并正确配置 DEEPSEEK_API_KEY
- [x] `POST /portfolio/chat` 能将「我买了茅台1000股成本1800」正确写入 PortfolioManager
- [x] 每日 09:00 自动预取所有持仓/自选股 60 日 OHLCV
- [x] 4 Collector 冒烟全部通过
- [x] KB → Planner 链路不崩溃
