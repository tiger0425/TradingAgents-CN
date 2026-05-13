# V1.2 缺口修复计划

> **日期**：2026-05-13
> **范围**：P0（Collector 数据源接入 + DeepSeek 配置）+ P3（freshness.maintain()）
> **关联文档**：`.sisyphus/plans/v1-llm-planner.md`、`.sisyphus/drafts/v1-gap-fix.md`
> **Metis 审查**：已完成 — 6 类缺口中 4 类被限定修复范围，2 类后移

---

## 摘要

> **目标**：修复 V1.2 代码层中 4 个 Collector 的数据源桩问题（接入 AkShare），配置 DeepSeek 作为 LLM 提供商，完善 KB 新鲜度维护——使系统能端到端运转。
> 
> **范围约束**：只修 P0（数据源+LLM配置）+ P3 item 8（freshness.maintain()）。不修 P1（测试）、P2（OpenClaw/LMM摘要——与 P0 重复）、P3 item 9（Docker Compose）。
> 
> **预估工作量**：4-5 小时
> **执行策略**：顺序+部分并行

---

## 背景

### 上轮审计的核心发现

1. 4 个 Collector 的 `_fetch_*` 方法全部返回 `None`（桩），`_summarize` 返回空字符串 —— KB 永远为空
2. Planner、动态图构建、双层调度等 18 个模块已达生产级，但数据源断裂导致系统无法运转
3. DeepSeek LLM 客户端已存在于 `llm_clients/openai_client.py`（`DeepSeekChatOpenAI`），只需改默认模型名
4. AkShare 数据函数（14 个公开+6 个内部）已存在于 `dataflows/akshare.py`，只待被 Collector 调用

### Metis 审查的关键纠偏

| 误判点 | 纠正 |
|--------|------|
| scheduler `_push_report()` 是 try/except 框架 | 实际已完整实现 OpenClaw 推送 |
| P2 item 7 与 P0 item 2 是独立任务 | 它们是同一个任务，合并 |
| 需要新建 DeepSeek LLM 客户端 | 已存在于 `DeepSeekChatOpenAI` |
| PolicyCollector 无 bug | 它有重复的 `set_llm` 方法 |

### 关于范围后移

| 后移项 | 原因 |
|--------|------|
| P1 单元测试（planner/kb/graph/api） | 测试框架需另外讨论，本期先让系统跑通 |
| P2 OpenClaw 推送验证 | scheduler 已实现，需完整 docker 环境 |
| P3 Docker Compose 集成 | 大工程，独立处理 |

---

## 技术决策

### 护栏（MUST NOT）

- ❌ **不修改** `dataflows/akshare.py`（只 import 和调用）
- ❌ **不修改** `bootstrap.py` 核心逻辑（只改 default_config）
- ❌ **不修改** `scheduler.py` 的调度配置
- ❌ **不重构** Collector 为异步（本期只加 `asyncio.to_thread()` 包装）
- ❌ **不重构** `interface.py` 路由层
- ❌ **不新建** DeepSeek LLM 客户端类
- ❌ **不为无关模块写测试**

### 技术方案

- **数据源接入**：Collector 直接 `from tradingagents.dataflows.akshare import ...`，参考 `agents/utils/social_sentiment_tools.py` 的模式
- **同步/异步桥接**：AkShare 全部同步，Collector 用 `asyncio.to_thread()` 包装避免阻塞事件循环
- **LLM 配置**：`default_config.py` 中 `deep_think_llm="deepseek-v4-pro"`，`quick_think_llm="deepseek-v4-flash"`
- **摘要降级**：LLM 调用失败时回退到规则引擎生成文本摘要
- **非交易日处理**：Collector 开头添加交易日检测

---

## 验证策略

- **冒烟验证**：每个 Collector 修复后用本地脚本验证 `collect()` 能获取真实数据并写入 KB
- **配置验证**：bootstrap 后确认 `deep_llm.model_name == "deepseek-v4-pro"` 和 `quick_llm.model_name == "deepseek-v4-flash"`
- **KB 写入验证**：数据写入 KB 后能用 `kb.query()` 检索到
- **Agent QA**：每个任务包含 curl 或 Python 脚本验证场景

---

## 执行策略

### 顺序执行（存在前置依赖）

```
Wave 1: DeepSeek 配置 + PolicyCollector bugfix（无依赖，立即开始）
   ├─ Task 1: DeepSeek 配置（default_config + .env）
   └─ Task 2: PolicyCollector 重复 set_llm 修复

Wave 2: MarketDataCollector（最高频率，影响最广）
   └─ Task 3: MarketDataCollector _fetch_raw + _summarize

Wave 3: SentimentCollector（第二高频）
   └─ Task 4: SentimentCollector _fetch_sentiment_raw + _analyze

Wave 4: AnnouncementCollector（需解决 watchlist 参数注入）
   └─ Task 5: AnnouncementCollector _fetch_announcements + _annotate

Wave 5: PolicyCollector + freshness.maintain()
   ├─ Task 6: PolicyCollector _fetch_policy_news + _analyze
   └─ Task 7: kb/freshness.py maintain() 实现

Wave FINAL: 冒烟验证（ALL 完成后 — 4 并行验证）
   ├─ Task F1: 配置验证
   ├─ Task F2: Collector 冒烟验证
   ├─ Task F3: KB 数据完整性验证
   └─ Task F4: 代码质量审查
```

> **注意**：该修复以顺序为主（Collector 间经验可迁移，先做简单者建立模式）。但 Wave 内部的 task 如无依赖可并行。

---

## TODO

- [x] 1. DeepSeek 模型配置

  **推荐 Agent**：`quick`
  **并行**：是（与 Task 2 并行）

  **做什么**：
  - 修改 `tradingagents/default_config.py` 的 `DEFAULT_CONFIG`：
    - `"deep_think_llm": "deepseek-v4-pro"`
    - `"quick_think_llm": "deepseek-v4-flash"`
  - 检查 `tradingagents/llm_clients/openai_client.py` 中 `DeepSeekChatOpenAI` 已存在，确认不需要修改
  - 更新 `.env.example`，确保 `DEEPSEEK_API_KEY=` 占位符存在（不是必填项标注）

  **不做**：
  - 不新建 DeepSeek client 类
  - 不修改 bootstrap.py 的核心逻辑

  **参考文件**：
  - `tradingagents/default_config.py:1-50` — DEFAULT_CONFIG 当前值（定位修改点）
  - `tradingagents/llm_clients/openai_client.py` — 确认 DeepSeekChatOpenAI 存在（验证不需要额外工作）
  - `tradingagents/bootstrap.py:69-78` — `_apply_env_overrides()` 了解 DEEPSEEK_API_KEY 检测逻辑

  **验收标准**：
  - [ ] `DEFAULT_CONFIG["deep_think_llm"] == "deepseek-v4-pro"`
  - [ ] `DEFAULT_CONFIG["quick_think_llm"] == "deepseek-v4-flash"`
  - [ ] `.env.example` 含 `DEEPSEEK_API_KEY=`

  **QA 场景**：

  ```
  Scenario: 默认配置验证
    Tool: Bash (python -c)
    Steps:
      1. python -c "from tradingagents.default_config import DEFAULT_CONFIG; assert DEFAULT_CONFIG['deep_think_llm']=='deepseek-v4-pro'; assert DEFAULT_CONFIG['quick_think_llm']=='deepseek-v4-flash'; print('PASS')"
    Expected Result: 输出 "PASS"，无 AssertionError
    Evidence: .sisyphus/evidence/task-1-config-check.txt

  Scenario: .env.example 含 DeepSeek 占位符
    Tool: Bash (grep)
    Steps:
      1. grep -c "DEEPSEEK_API_KEY" .env.example
    Expected Result: 返回 ≥1 的行数
    Evidence: .sisyphus/evidence/task-1-env-check.txt
  ```

  **提交**：是
  - 消息：`config(deepseek): set deepseek-v4-pro/flash as default models`
  - 文件：`tradingagents/default_config.py`, `.env.example`

- [x] 2. PolicyCollector 重复 `set_llm` 方法修复

  **推荐 Agent**：`quick`
  **并行**：是（与 Task 1 并行）

  **做什么**：
  - 读取 `tradingagents/collector/policy_collector.py`
  - 找到第 17 行和第 20 行（约）两个相同的 `def set_llm(self, llm): self._llm = llm` 方法
  - 删除第二个（保留第一个 `__init__` 紧后面的那个）

  **不做**：
  - 不修改其他 collector 文件
  - 不修改 PolicyCollector 的其他逻辑

  **参考文件**：
  - `tradingagents/collector/policy_collector.py:1-30` — 确认 `set_llm` 重复位置
  - `tradingagents/collector/market_collector.py:25-26` — 正常模式的 `set_llm`（参考）

  **验收标准**：
  - [ ] `policy_collector.py` 中只有一个 `set_llm` 方法定义
  - [ ] `python -c "from tradingagents.collector.policy_collector import PolicyCollector; print('PASS')"` 成功

  **QA 场景**：

  ```
  Scenario: 只有一个 set_llm 方法
    Tool: Bash (grep)
    Steps:
      1. grep -c "def set_llm" tradingagents/collector/policy_collector.py
    Expected Result: 返回 1
    Evidence: .sisyphus/evidence/task-2-dup-fix.txt
  ```

  **提交**：是
  - 消息：`fix(collector): remove duplicate set_llm in PolicyCollector`
  - 文件：`tradingagents/collector/policy_collector.py`

- [x] 3. MarketDataCollector 接入 AkShare + LLM 摘要

  **推荐 Agent**：`unspecified-high`
  **并行**：否（依赖 Task 1 的 LLM 配置）

  **做什么**：
  - 在 `_fetch_raw()` 中调用 AkShare 获取实时市场数据：
    - `get_market_context()` — 获取指数、板块轮动、资金流向、北向
    - `get_stock_data("000300", "2026-05-13")` — 获取沪深300基准数据
  - 将 AkShare 返回的原始数据打包成 `dict` 返回
  - 在 `_summarize()` 中用 `self._llm.invoke(prompt)` 生成 3-5 条中文摘要要点：
    - 如果 LLM 调用失败（try/except），回退到规则引擎摘要（格式："今日沪指收于{close}，涨跌幅{change}%，{sector}板块领涨"）
  - 在 `collect()` 开头添加交易日检测：用 AkShare 交易日历或日期法（周一至周五非假日）
  - 确保 `_fetch_raw()` 失败时整个 `collect()` 优雅返回 `None`（不崩溃）

  **不做**：
  - 不修改 AkShare 函数的签名
  - 不修改 scheduler 中该 collector 的调度频率

  **参考文件**：
  - `tradingagents/dataflows/akshare.py` — 查找 `get_market_context`、`get_stock_data`、`get_real_time_quotes` 函数签名
  - `tradingagents/agents/utils/social_sentiment_tools.py` — 参考 "直接 import akshare 函数" 的模式
  - `tradingagents/collector/market_collector.py:28-56` — 当前 `collect()` 和 `_fetch_raw()` 结构
  - `tradingagents/scheduler/scheduler.py:37-39` — 确认 scheduler 如何调用该 collector

  **验收标准**：
  - [ ] `_fetch_raw()` 返回非空 dict，包含 `indices`、`sectors`、`northbound` 等字段
  - [ ] `_summarize()` 返回 ≥50 字符的中文摘要文本
  - [ ] LLM 失败时回退到规则引擎摘要（非空字符串）
  - [ ] 非交易日 `collect()` 返回 `None`

  **QA 场景**：

  ```
  Scenario: 交易日获取市场数据成功
    Tool: Bash (python -c)
    Preconditions: DEEPSEEK_API_KEY 已设置
    Steps:
      1. 运行冒烟脚本（见 F2 验证）
      2. 检查 result 非 None
      3. 检查 result['data'] 长度 ≥ 50
    Expected Result: PASS — 有真实摘要文本
    Evidence: .sisyphus/evidence/task-3-market-success.txt

  Scenario: LLM 调用失败时回退到规则引擎
    Tool: Bash (python -c)
    Preconditions: 临时设置错误 API key 模拟失败
    Steps:
      1. 用无效 key 初始化 collector
      2. await c.collect()
      3. 检查 result['data'] 非空（规则引擎摘要）
    Expected Result: 非空摘要文本，不含"Error"
    Evidence: .sisyphus/evidence/task-3-market-fallback.txt

  Scenario: 非交易日不采集
    Tool: Bash (python -c)
    Preconditions: 模拟周六
    Steps:
      1. 用日期为周六触发 collect()
      2. assert result is None
    Expected Result: collect() 返回 None（静默跳过）
    Evidence: .sisyphus/evidence/task-3-non-trading.txt
  ```

  **提交**：是
  - 消息：`feat(collector): integrate AkShare into MarketDataCollector`
  - 文件：`tradingagents/collector/market_collector.py`

- [x] 4. SentimentCollector 接入 AkShare + LLM 分析

  **推荐 Agent**：`unspecified-high`
  **并行**：否（顺序执行，可借鉴 Task 3 模式）

  **做什么**：
  - 在 `_fetch_sentiment_raw()` 中调用 AkShare：
    - 使用 `get_news()` 获取财经新闻列表
    - 使用 `get_global_news()` 获取国际财经新闻
    - 将结果整理成 `list[dict]`，每项包含 `{title, content, source, time}`
  - 在 `_analyze()` 中用 `self._llm.invoke(prompt)` 生成情感分析摘要（2-3 条要点，含情感倾向）
    - LLM 失败时回退："今日采集{count}条财经新闻，整体情绪中性偏正面"
  - 参照 Task 3 模式添加交易日检测和错误处理

  **不做**：
  - 不调用社交情绪相关函数（`get_social_sentiment` 需要额外依赖）

  **参考文件**：
  - `tradingagents/dataflows/akshare.py` — 查找 `get_news`、`get_global_news` 函数
  - `tradingagents/collector/sentiment_collector.py` — 当前骨架
  - `tradingagents/collector/market_collector.py` — Task 3 完成后的模式参考

  **验收标准**：
  - [ ] `_fetch_sentiment_raw()` 返回 list，每项含 title/content/source
  - [ ] `_analyze()` 返回 ≥30 字符的中文摘要
  - [ ] LLM 失败时有降级摘要

  **QA 场景**：

  ```
  Scenario: 获取舆情数据成功
    Tool: Bash (python -c)
    Steps:
      1. 初始化 SentimentCollector 并调用 collect()
      2. assert result is not None
      3. assert len(result['data']) >= 30
    Expected Result: PASS
    Evidence: .sisyphus/evidence/task-4-sentiment-success.txt
  ```

  **提交**：是
  - 消息：`feat(collector): integrate AkShare into SentimentCollector`
  - 文件：`tradingagents/collector/sentiment_collector.py`

- [x] 5. AnnouncementCollector 接入 AkShare + 解决参数注入

  **推荐 Agent**：`unspecified-high` | **并行**：否

  **做什么**：
  - 在 `_fetch_announcements()` 中调用 AkShare 获取公告数据（`get_individual_notices(ticker, days_back=1)` 或降级为 `get_news(ticker)`）
  - 在 `_annotate(ticker, raw)` 中用 `self._llm.invoke(prompt)` 生成每条公告的摘要解读
  - **关键修复**：解决 watchlist 参数注入。当前 scheduler 调用 `announcement.collect` 不传参数（`scheduler.py:40-42`）。采用方案 A：collector 内部从 `PortfolioManager` 读取用户持仓/自选列表
  - LLM 失败时降级："{ticker} 公告：{title}（发布时间：{time}）"

  **不做**：不修改 scheduler 的调度配置

  **参考**：`tradingagents/dataflows/akshare.py`→`get_individual_notices`，`tradingagents/portfolio/portfolio_manager.py:86-89`→`get_holdings_list()/get_watchlist()`

  **验收**：`_fetch_announcements()` 返回非 None（最小为空 list）；能从 PortfolioManager 读取用户股票列表；LLM 失败时有降级

  **QA**：初始化 AnnouncementCollector + PortfolioManager → 调用 `collect()` → 无异常崩溃 → Evidence: `.sisyphus/evidence/task-5-announcement.txt`

  **提交**：`feat(collector): integrate AkShare into AnnouncementCollector with portfolio-driven stock list` — `tradingagents/collector/announcement_collector.py`

- [x] 6. PolicyCollector 接入 AkShare + LLM 分析

  **推荐 Agent**：`unspecified-high` | **并行**：否

  **做什么**：
  - 在 `_fetch_policy_news()` 中调用 `get_macro_data()`（国信数据源）或 `get_news()` 配合关键词过滤（"央行", "证监会", "政策"）
  - `_is_new()` 利用返回的 `title` 字段做去重检测
  - 在 `_analyze()` 中用 `self._llm.invoke(prompt)` 生成政策影响分析（2-3 条要点）
  - LLM 失败时降级："{time} 政策动态：{title}"
  - 参照 Task 3 模式添加交易日检测和错误处理
  - 假设 Task 2 已完成（重复 `set_llm` 已删除）

  **不做**：不修改调度频率（2h 保持）

  **参考**：`tradingagents/dataflows/akshare.py`→`get_macro_data`，`tradingagents/dataflows/interface.py`→确认路由到 `guosen.py`

  **验收**：`_fetch_policy_news()` 返回非空；`_is_new()` 能正确去重；降级摘要非空

  **QA**：初始化 PolicyCollector → 调用 `collect()` → 检查返回非 None → Evidence: `.sisyphus/evidence/task-6-policy.txt`

  **提交**：`feat(collector): integrate AkShare into PolicyCollector` — `tradingagents/collector/policy_collector.py`

- [ ] 7. KB freshness.maintain() 实现

  **推荐 Agent**：`quick` | **并行**：否

  **做什么**：
  - 在 `kb/freshness.py` 的 `maintain()` 方法中实现遍历逻辑：
    1. 遍历 `shared/` 和 `users/{user_id}/` 下的所有 collection 目录
    2. 对每个 `.json` 文件读取 `collected_at` 字段
    3. 调用 `compute_freshness(collection, collected_at)` 计算新标签
    4. 如果标签变化（尤其是 STALE→EXPIRED 或 FRESH→STALE），更新文件
    5. 添加日志记录更新数量

  **不做**：不修改 collection TTL 配置；不添加新 collection 类型

  **参考**：`tradingagents/kb/freshness.py:52-56`→当前 maintain() stub；`tradingagents/kb/knowledge_base.py:23-29`→目录结构（shared_dir/users_dir/collections）

  **验收**：`maintain()` 更新至少一批文件的新鲜度标签；无异常崩溃

  **QA**：`python -c "from tradingagents.kb.freshness import FreshnessManager; fm = FreshnessManager('/tmp/test_kb'); fm.maintain(); print('PASS')"` → Evidence: `.sisyphus/evidence/task-7-maintain.txt`

  **提交**：`feat(kb): implement maintain() for freshness batch update` — `tradingagents/kb/freshness.py`

- [ ] F1. **配置验证** — `quick`
  验证 `deep_llm.model_name == "deepseek-v4-pro"` 和 `quick_llm.model_name == "deepseek-v4-flash"`。运行：
  ```python
  from tradingagents.default_config import DEFAULT_CONFIG
  assert DEFAULT_CONFIG["deep_think_llm"] == "deepseek-v4-pro"
  assert DEFAULT_CONFIG["quick_think_llm"] == "deepseek-v4-flash"
  print("PASS")
  ```
  输出：`配置 [PASS/FAIL] | VERDICT`

- [ ] F2. **Collector 冒烟验证** — `unspecified-high`
  依次对 4 个 Collector 运行冒烟测试（需环境变量中配置 DEEPSEEK_API_KEY）：
  ```bash
  python -c "
  from tradingagents.kb import KnowledgeBase
  from tradingagents.collector.market_collector import MarketDataCollector
  import asyncio
  kb = KnowledgeBase('/tmp/test_kb_v1fix')
  c = MarketDataCollector(kb, {'market_type': 'A_SHARE', 'quick_think_llm': 'deepseek-v4-flash'})
  result = asyncio.run(c.collect())
  assert result is not None, 'collect() returned None'
  assert result.get('data'), 'No summary in result'
  print('PASS: MarketDataCollector')
  "
  ```
  输出：`Collector [N/4 PASS] | VERDICT`

- [ ] F3. **KB 数据完整性验证** — `unspecified-high`
  验证 Collector 写入 KB 的数据可被检索：
  ```bash
  python -c "
  from tradingagents.kb import KnowledgeBase
  kb = KnowledgeBase('/tmp/test_kb_v1fix')
  entries = kb.query_for_event(None, type('ctx',(),{'ticker':'','industry':''}))
  assert entries['coverage_score'] > 0, f'Coverage is {entries[\"coverage_score\"]}'
  print('PASS: KB data accessible')
  "
  ```
  输出：`KB [PASS/FAIL] | VERDICT`

- [ ] F4. **代码质量审查** — `unspecified-high`
  检查所有修改文件：无 `as any`/`@ts-ignore`，无空 catch，无 console.log，无注释掉的代码，无 unused import。
  输出：`文件 [N/N clean] | VERDICT`

---

## 提交策略

- **T1**: `config(deepseek): set deepseek-v4-pro/flash as default models` — default_config.py, .env.example
- **T2**: `fix(collector): remove duplicate set_llm in PolicyCollector` — collector/policy_collector.py
- **T3**: `feat(collector): integrate AkShare into MarketDataCollector` — collector/market_collector.py
- **T4**: `feat(collector): integrate AkShare into SentimentCollector` — collector/sentiment_collector.py
- **T5**: `feat(collector): integrate AkShare into AnnouncementCollector with portfolio-driven stock list` — collector/announcement_collector.py
- **T6**: `feat(collector): integrate AkShare into PolicyCollector` — collector/policy_collector.py
- **T7**: `feat(kb): implement maintain() for freshness batch update` — kb/freshness.py

---

## 成功标准

- [ ] DeepSeek v4-pro/flash 作为默认模型
- [ ] 4 个 Collector 均能调用 AkShare 获取真实数据
- [ ] Collector 数据通过 LLM 摘要后写入 KB
- [ ] KB 数据可被 `query()` 和 `query_for_event()` 检索
- [ ] LLM 调用失败时降级为规则引擎摘要
- [ ] 非交易日 Collector 不运行
- [ ] KB `maintain_freshness()` 可定期批量更新新鲜度标签
