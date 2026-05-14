# 数据源补齐计划

## TL;DR

> **核心目标**：补齐 tradingagents-cn 中 7 类缺失的 A 股数据源，使每个 Agent 都能获取完整、准确的市场数据
>
> **交付物**：
> - akshare 增强：融资融券、机构持仓、公告增强、舆情增强、资金流北向分类（5个功能模块）
> - tushare vendor 新模块：北向资金明细 + 机构持仓增强
> - 爬虫模块：监管/政策快讯
> - 新 Agent：position_analyst 持仓数据聚合器
> - 配套 pytest 测试用例
>
> **预估工作规模**：中型（14 个实现任务 + 4 个最终验证任务）
> **并行执行**：是 — 4 个并行波次
> **关键路径**：T1/T2 → T4-T10 → T11-T13 → T14 → F1-F4

---

## 背景

### 原始需求

补齐以下 7 类缺失的 A 股数据源：

| # | 数据类别 | 影响 | 现有状态 |
|---|----------|------|----------|
| 1 | 公告/新闻 | News Analyst 空 | akshare `stock_news_em` 有基础新闻，`get_individual_notices` 和 `get_research_reports` 已存在但未充分集成 |
| 2 | 北向资金明细 | 宏观不完整 | `macro_context.py` 有汇总（EastMoney），但 2024-08-16 停止发布详情 |
| 3 | 机构持仓/股东变化 | 基本面粗糙 | 完全缺失，akshare 有对应接口但未封装 |
| 4 | 融资融券数据 | 风控缺失 | 完全缺失，akshare 有沪深深交所接口 |
| 5 | 大盘资金流（北向分类） | 资金面不精准 | `market_context.py` 有主力资金流，无北向分类 |
| 6 | 舆情监控 | 消息滞后 | `get_social_sentiment` 已有基础实现（东方财富评论+雪球+热度） |
| 7 | 监管/政策快讯 | 策略盲区 | 完全缺失 |

### 访谈总结

**关键决策**：
- **补齐路线**：混合方案 — akshare（免费主力）+ tushare pro ¥200/年（增强核心数据）+ 自建爬虫（政策快讯）
- **付费接受度**：可接受小额付费（¥200-500/年）
- **测试策略**：TDD（pytest，先写测试再实现）
- **北向资金粒度**：个股持股变化 + 沪深股通持仓排名
- **不覆盖范围**：不改变 LLM 调用逻辑、不改变交易决策框架、不改变回测系统

### 调研发现（akshare + tushare + 爬虫对比）

**akshare 免费能力（已有但未使用）**：
- ✅ 融资融券：`stock_margin_detail_sse/szse()`（沪深明细）、`stock_margin_sse()`（沪市汇总）
- ✅ 机构持仓：`stock_institute_hold/stock_institute_hold_detail()`（新浪）、`stock_fund_hold_detail_em()`（东财基金持仓）
- ✅ 股东变化：`stock_gdfx_free_holding_change_em()`（十大流通股东变动）、`stock_gdfx_holding_analyse_em()`（十大股东分析）
- ✅ 公告：`stock_notice_report()`（巨潮资讯公告全文）
- ✅ 北向板块：`stock_hsgt_board_rank_em()`（沪深港通板块排名）

**tushare pro ¥200/年（2000积分）增强能力**：
- ✅ 北向资金明细：`moneyflow_hsgt`（120积分）— 沪深港通资金流向个股级别
- ✅ 机构持仓：`top10_holders/ top10_floatholders`（120积分）— 前十大股东/流通股东
- ✅ 股东人数：`stk_holdernumber`（120积分）— 股东户数变化趋势
- ✅ 融资融券：`margin_detail`（120积分）— 两融交易明细

**爬虫基础设施（已有依赖可就绪）**：
- ✅ `parsel >= 1.10.0` — Scrapy 团队的 CSS/XPath 解析库（已在 `pyproject.toml` 中）
- ✅ `requests >= 2.32.4` — HTTP 请求库（已存在）
- ✅ 项目代码风格为同步（无需引入 async/await）

### Metis 审查

**识别到的关键缺口（已处理）**：
- **F1**：`get_individual_notices()` 和 `get_research_reports()` 已存在 → Task 6 定位为"增强"而非"从零构建"
- **F2**：北向资金东方财富接口已确认于 2024-08-16 断更 → T9（tushare module）作为主攻方案
- **F4**：`parsel` 已在依赖中 → T3（爬虫基础设施）直接使用 parsel
- **F8**：interface.py 只有 4 个分类 → 需新增 `position_data` 和 `margin_data` 分类

**应用的护栏**：
- **G1**：不修改现有 `get_individual_notices` / `get_research_reports` 函数签名
- **G2**：每个新工具必须在三处注册（TOOLS_CATEGORIES + VENDOR_METHODS + default_config）
- **G3**：akshare.py 不超过 2000 行，超出部分拆分为子模块
- **G4**：爬虫使用 `parsel`（已有依赖），不引入新库

---

## 目标

### 核心目标

通过增强 akshare 采集模块、新建 tushare vendor 模块和自建爬虫，补齐 7 类缺失的 A 股数据源，使所有分析 Agent 能够获取完整准确的市场数据。

### 具体交付物

- `tradingagents/dataflows/akshare.py` — 新增融资融券、机构持仓、公告增强、舆情增强函数（5-6个新函数）
- `tradingagents/dataflows/market_context.py` — `_fetch_capital_flow()` 增强北向分类
- `tradingagents/dataflows/tushare.py` — 全新 vendor 模块，北向资金明细 + 机构持仓数据
- `tradingagents/dataflows/crawlers/` — 全新爬虫子目录，监管/政策快讯爬虫
- `tradingagents/dataflows/interface.py` — 新增工具分类和 vendor 注册
- `tradingagents/dataflows/config.py` / `default_config.py` — 新增 vendor 配置项
- `tradingagents/agents/analysts/position_analyst.py` — 新 Agent 持仓数据聚合器
- `tradingagents/dataflows/schemas.py` — 新数据类型定义
- `tests/test_margin_data.py` — 融资融券测试
- `tests/test_institutional_holdings.py` — 机构持仓测试
- `tests/test_tushare_vendor.py` — tushare 模块测试
- `tests/test_policy_crawler.py` — 爬虫测试

### 完成标准

- [ ] `bun test` → PASS（新增测试全部通过）
- [ ] 所有新数据源函数在实际交易日能返回非空数据（通过 Agent QA 脚本验证）
- [ ] 优雅降级：数据不可用时返回明确提示，不阻断分析流程
- [ ] 新数据分类已注册且 Agent 可调用

### 必须包含

- 融资融券：沪市+深市汇总和明细（akshare）
- 机构持仓/股东变化：基金持仓、前十大股东、股东户数变化（akshare + tushare）
- 北向资金明细：个股持股变化 + 沪深股通持仓排名（tushare 为主）
- 公告/新闻增强：巨潮资讯公告全文（akshare）
- 大盘资金流北向分类（market_context 增强）
- 监管/政策快讯：证监会+央行（爬虫）
- 所有函数支持缓存和优雅降级

### 必须不包含（护栏）

- 不修改现有函数签名（`get_individual_notices` / `get_research_reports` 等保持不变）
- 不改变 LLM 调用逻辑和交易决策框架
- 不新增 pip 依赖（parsel 和 requests 已满足）
- akshare.py 不超过 2000 行（超过部分拆分为子模块）
- 爬虫不引入 Selenium/Playwright（纯 HTTP + parsel）

---

## 验证策略

> **零人工干预** — 所有验证由 agent 执行。不接受任何需要人工手动测试的验收标准。

### 测试决策
- **测试基础设施**：已存在（pytest，39 个测试文件）
- **自动化测试**：TDD（先写测试→实现→通过）
- **测试框架**：pytest + `conftest.py` fixtures
- **流程**：每个任务遵循 RED（写失败测试）→ GREEN（最小实现）→ REFACTOR

### QA 策略

每个任务配备 Agent 执行的 QA 场景：
- **数据源函数**：使用 `bash` 运行 pytest 验证返回值格式+内容
- **爬虫**：使用 `bash` 运行脚本检查爬取结果文件
- **API 端点**：使用 `bash` 运行 `python -c "import..."` 直接调用函数验证
- **Agent 集成**：使用 `bash` 运行 pytest 验证工具已注册可调用
- 证据保存到：`.sisyphus/evidence/task-{N}-{scenario-slug}.log`

---

## 执行策略

### 并行执行波次

```
Wave 1（立即启动 — 基础设施 + 类型定义）：
├── T1: 测试 fixtures + conftest 扩展
├── T2: 数据 schema/类型定义
└── T3: 爬虫基础设施（parsel + requests 基类）

Wave 2（Wave 1 完成后 — 数据采集模块，最大并行）：
├── T4: akshare 融资融券数据采集（TDD）
├── T5: akshare 机构持仓/股东变化（TDD）
├── T6: akshare 公告/新闻增强（TDD）
├── T7: akshare 舆情监控增强（TDD）
├── T8: market_context 资金流北向分类增强（TDD）
├── T9: Tushare vendor 模块（TDD）
└── T10: 监管/政策快讯爬虫（TDD）

Wave 3（Wave 2 完成后 — 集成注册 + Agent）：
├── T11: interface.py 工具注册
├── T12: config.py / default_config.py 更新
└── T13: position_analyst 数据聚合器

Wave 4（Wave 3 完成后）：
└── T14: 端到端集成测试

最终验证（全部完成后 — 4 个并行审查）：
├── F1: 计划合规审计（oracle）
├── F2: 代码质量审查（unspecified-high）
├── F3: 实机 QA 执行（unspecified-high）
└── F4: 范围保真度检查（deep）
→ 呈现结果 → 获取用户明确确认
```

**关键路径**：T1 → T4-T10 → T11 → T14 → F1-F4
**并行加速**：Wave 2 中 7 个任务并行执行，相比串行提速约 80%
**最大并发**：7（Wave 2）

### 依赖关系矩阵

- **T1**：无 → T4-T10
- **T2**：无 → T4-T10, T11
- **T3**：无 → T10
- **T4-T8**：T1, T2 → T11-T13
- **T9**：T1, T2 → T11-T13
- **T10**：T1, T2, T3 → T11-T13
- **T11**：T4-T10 → T13, T14
- **T12**：T4-T10 → T14
- **T13**：T11 → T14
- **T14**：T11-T13 → F1-F4
- **F1-F4**：T14 → 用户确认（并行执行）

### Agent 分配摘要

- **Wave 1**：3 个 — T1 → `quick`，T2 → `quick`，T3 → `quick`
- **Wave 2**：7 个 — T4-T8 → `deep`，T9 → `deep`，T10 → `deep`
- **Wave 3**：3 个 — T11 → `quick`，T12 → `quick`，T13 → `deep`
- **Wave 4**：1 个 — T14 → `deep`
- **最终验证**：4 个 — F1 → `oracle`，F2 → `unspecified-high`，F3 → `unspecified-high`，F4 → `deep`

---

## 待办事项

> 实现 + 测试 = 一个任务。不可分拆。
> 每个任务必须包含：推荐 Agent 配置 + 并行信息 + QA 场景。
> **缺少 QA 场景的任务不完整，不可接受。**

- [ ] 1. 测试 fixtures + conftest 扩展

  **做什么**：
  - 在 `tests/conftest.py` 中新增 `mock_akshare`、`mock_tushare` 和 `sample_margin_df` fixture
  - `mock_akshare`：返回模拟融资融券/机构持仓数据 DataFrame（列名与真实 akshare API 对齐）
  - `mock_tushare`：返回模拟北向资金明细 DataFrame
  - `sample_margin_df`：包含 `股票代码, 股票简称, 融资余额, 融券余量` 等标准列的 fixture
  - 新增 `create_temp_cache_dir` fixture，为数据缓存测试创建临时目录
  - 在 `pytest.ini` 或 `pyproject.toml` 中添加 `markers` 配置：`slow`（网络测试）、`crawler`（爬虫测试）

  **禁止做**：
  - 不修改任何现有 fixture 签名
  - 不引入新依赖（pytest 已存在）

  **推荐 Agent 配置**：
  - **类别**：`quick` — 测试 infrastructure 修改，范围小
  - **技能**：无（纯 pytest 代码）
  - **并行**：Wave 1，与 T2、T3 并行

  **参考文献**：
  - `tests/conftest.py` — 现有 fixture 模式和 pytest 插件配置
  - `tradingagents/dataflows/akshare.py:1-50` — akshare 数据格式参考（了解 DataFrame 列名约定）

  **验收标准（TDD）**：
  - [ ] fixture 定义存在于 tests/conftest.py
  - [ ] `pytest --collect-only` 能识别新 fixtures 且无错误

  **QA 场景**：

  ```
  场景：验证 mock_akshare fixture 返回正确的融资融券 DataFrame
    工具：bash
    前置条件：pytest 已安装
    步骤：
      1. 运行 python -c "from tests.conftest import mock_akshare; df = mock_akshare(); print(df.columns.tolist())"
      2. 验证输出包含 ['股票代码', '股票简称', '融资余额', '融券余量']
    预期结果：输出列名完全匹配
    失败指标：ImportError 或列名不匹配
    证据：.sisyphus/evidence/task-1-fixture-check.log
  ```

  **提交**：是（归入 Wave 1 组）
  - 消息：`test(data): 新增数据源测试 fixtures（mock_akshare/mock_tushare）`
  - 文件：`tests/conftest.py`

- [ ] 2. 数据 schema/类型定义

  **做什么**：
  - 在 `tradingagents/dataflows/` 下新建 `schemas.py`，定义新数据源的标准字段名和类型
  - 定义 `MarginData` dataclass：字段包括 `symbol, name, margin_balance（融资余额）, short_balance（融券余量）, margin_buy（融资买入额）, short_sell（融券卖出量）, date`
  - 定义 `InstitutionalHolding` dataclass：字段包括 `symbol, name, institution_type（机构类型）, institution_name, holding_amount（持股数）, holding_ratio（持股比例）, report_date`
  - 定义 `NorthboundDetail` dataclass：字段包括 `symbol, name, hold_amount（持股量）, hold_ratio（持股比例/占流通股）, change_amount（持股变化）, date`
  - 定义 `PolicyNews` dataclass：字段包括 `title, source, publish_time, summary, url`
  - 每个 dataclass 包含 `to_dict()` 和 `from_dataframe_row()` 类方法

  **禁止做**：
  - 不依赖 pydantic（项目未使用），使用 Python 原生 dataclass
  - 不定义与现有 `agent_states.py` 冲突的字段名

  **推荐 Agent 配置**：
  - **类别**：`quick` — 纯数据结构定义，无外部依赖
  - **技能**：无
  - **并行**：Wave 1，与 T1、T3 并行

  **参考文献**：
  - `tradingagents/agents/agent_states.py` — 现有 Agent 状态字段定义，避免命名冲突
  - `tradingagents/dataflows/akshare.py:398-560` — 现有基本面数据结构参考

  **验收标准（TDD）**：
  - [ ] `tradingagents/dataflows/schemas.py` 存在
  - [ ] `python -c "from tradingagents.dataflows.schemas import MarginData, InstitutionalHolding, NorthboundDetail, PolicyNews; print('OK')"` → OK
  - [ ] 每个 dataclass 测试：实例化并验证字段类型

  **QA 场景**：

  ```
  场景：MarginData 可从模拟 DataFrame 行正确构建
    工具：bash
    前置条件：schemas.py 存在
    步骤：
      1. 运行验证脚本创建 MarginData 实例：
         python -c "
         from tradingagents.dataflows.schemas import MarginData
         import pandas as pd
         row = pd.Series({'股票代码': '000001', '股票简称': '平安银行', '融资余额': 1000000, '融券余量': 5000, '日期': '2026-05-10'})
         m = MarginData.from_dataframe_row(row)
         print(m.symbol, m.name, m.margin_balance)
         "
      2. 验证输出包含 "000001 平安银行 1000000"
    预期结果：正确解析 DataFrame 行
    失败指标：AttributeError 或 KeyError
    证据：.sisyphus/evidence/task-2-schema.log
  ```

  **提交**：是
  - 消息：`feat(data): 新增数据结构定义（MarginData/InstitutionalHolding/NorthboundDetail/PolicyNews）`
  - 文件：`tradingagents/dataflows/schemas.py`

- [ ] 3. 爬虫基础设施

  **做什么**：
  - 在 `tradingagents/dataflows/` 下新建 `crawlers/` 子目录，含 `__init__.py` 和 `base.py`
  - `base.py` 实现 `BaseCrawler` 类：
    - 属性：`base_url`, `session (requests.Session)`, `cache_dir`, `user_agent`
    - 方法：`_get(url, params) → Response`（带重试 3 次+指数退避），`_parse_html(html) → parsel.Selector`
    - 方法：`_cache_key(url) → str`，`_load_cache(key) → Optional[str]`，`_save_cache(key, content)`
    - `fetch(url, cache_ttl) → str`：优先读缓存，过期则重新请求
  - `__init__.py`：导出 `BaseCrawler`
  - 遵循项目的优雅降级模式：网络错误返回 `"数据暂不可用"` 而非抛异常

  **禁止做**：
  - 不引入 Selenium/Playwright/Scrapy — 纯 HTTP + parsel
  - 不新增 pip 依赖（requests + parsel 已存在）
  - 不包含任何实际爬取逻辑（仅基类）

  **推荐 Agent 配置**：
  - **类别**：`quick` — 基类基础设施，无复杂业务逻辑
  - **技能**：无
  - **并行**：Wave 1，与 T1、T2 并行

  **参考文献**：
  - `pyproject.toml` — 确认 `parsel >= 1.10.0` 和 `requests >= 2.32.4` 已存在
  - `tradingagents/dataflows/config.py:23-27` — 数据缓存目录配置 `data_cache_dir`
  - `tradingagents/dataflows/akshare.py:100-148` — 现有缓存模式（CSV 文件缓存）

  **验收标准（TDD）**：
  - [ ] `tests/test_crawler_base.py` 存在，测试 BaseCrawler 初始化、缓存读写、重试逻辑
  - [ ] `python -c "from tradingagents.dataflows.crawlers import BaseCrawler"` → OK
  - [ ] 测试通过：`pytest tests/test_crawler_base.py -v`

  **QA 场景**：

  ```
  场景：BaseCrawler 缓存读写正常工作
    工具：bash
    前置条件：crawlers/base.py 存在
    步骤：
      1. 运行 python -c "
         from tradingagents.dataflows.crawlers.base import BaseCrawler
         import tempfile, os
         with tempfile.TemporaryDirectory() as d:
             c = BaseCrawler(base_url='https://example.com', cache_dir=d)
             c._save_cache('test_key', 'cached_content')
             val = c._load_cache('test_key')
             print('CACHE_OK' if val == 'cached_content' else 'CACHE_FAIL')
         "
      2. 验证输出 "CACHE_OK"
    预期结果：缓存读写正确
    失败指标：输出 "CACHE_FAIL" 或异常
    证据：.sisyphus/evidence/task-3-crawler-base.log
  ```

  **提交**：是
  - 消息：`feat(crawler): 新增爬虫基础设施（BaseCrawler + parsel/requests）`
  - 文件：`tradingagents/dataflows/crawlers/__init__.py`, `tradingagents/dataflows/crawlers/base.py`, `tests/test_crawler_base.py`

- [ ] 4. akshare 融资融券数据采集（TDD）

  **做什么**：
  - 在 `akshare.py` 中新增 `get_margin_data(symbol, trade_date) → str` 函数
    - 调用 `ak.stock_margin_detail_sse(date)` 获取沪市融资融券明细
    - 调用 `ak.stock_margin_detail_szse(date)` 获取深市融资融券明细
    - 根据 symbol 首位码判断交易所（5/6 → 沪市, 0/1/2/3 → 深市）
    - 提取字段：融资余额、融资买入额、融资偿还额、融券余量、融券卖出量、融券偿还量
    - 返回 Markdown 格式字符串（遵循现有函数返回格式约定）
  - 在 `akshare.py` 中新增 `get_margin_summary(trade_date) → str` 函数
    - 调用 `ak.stock_margin_sse(start_date, end_date)` 获取沪市汇总
    - 返回市场整体两融余额和变化
  - 测试文件：`tests/test_margin_data.py`
    - RED：先写测试，mock akshare 调用，验证返回格式、错误处理、空数据降级
    - GREEN：实现函数直到测试通过

  **禁止做**：
  - 不修改 akshare.py 中任何现有函数签名（护栏 G1）
  - akshare.py 总行数不超过 2000 行（如超出，拆为 `akshare_margin.py`）
  - 不在返回中使用 `print()` 代替 markdown 格式化

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要理解 akshare API 语义 + 遵循项目数据格式约定
  - **技能**：无
  - **并行**：Wave 2，与 T5-T10 并行（无相互依赖）

  **参考文献**：
  - `tradingagents/dataflows/akshare.py:155-212` — `get_stock_data` 函数模式（Markdown header + CSV body）
  - `tradingagents/dataflows/akshare.py:38-44` — `_ensure_akshare()` lazy import 守卫
  - `tradingagents/dataflows/akshare.py:56-81` — `_to_sina_symbol` 交易所判断逻辑（参考 first 位码）
  - `tradingagents/dataflows/schemas.py:MarginData` — 标准字段定义
  - akshare 官方文档：`ak.stock_margin_detail_sse()` / `ak.stock_margin_detail_szse()` API 签名

  **验收标准（TDD）**：
  - [ ] `tests/test_margin_data.py` 存在，包含至少 3 个测试用例
  - [ ] `pytest tests/test_margin_data.py -v` → PASS
  - [ ] 测试覆盖：正常数据返回、无效 symbol 返回错误提示、空数据优雅降级

  **QA 场景**：

  ```
  场景：获取个股融资融券明细（mock 数据）
    工具：bash
    前置条件：mock_akshare fixture 已部署
    步骤：
      1. pytest tests/test_margin_data.py::test_get_margin_data_normal -v
      2. 验证返回的 Markdown 字符串包含 "## 融资融券数据" 标题
      3. 验证包含 "融资余额" 和 "融券余量" 字段
    预期结果：测试 PASS，返回格式化数据
    失败指标：测试 FAIL 或返回 "Error" 字符串
    证据：.sisyphus/evidence/task-4-margin-data.log

  场景：无效 symbol 优雅降级
    工具：bash
    前置条件：同上
    步骤：
      1. pytest tests/test_margin_data.py::test_get_margin_data_invalid_symbol -v
      2. 验证返回字符串包含 "不支持" 或 "无法识别"
    预期结果：优雅返回错误提示而非抛异常
    证据：.sisyphus/evidence/task-4-margin-error.log
  ```

  **提交**：是（归入 Wave 2 组）
  - 消息：`feat(akshare): 新增融资融券数据采集（get_margin_data/get_margin_summary）`
  - 文件：`tradingagents/dataflows/akshare.py`, `tests/test_margin_data.py`

- [ ] 5. akshare 机构持仓/股东变化（TDD）

  **做什么**：
  - 在 `akshare.py` 中新增 `get_institutional_holdings(symbol, quarter) → str` 函数
    - 调用 `ak.stock_institute_hold_detail(stock=symbol, quarter=quarter)` 获取机构持股详情
    - 返回字段：持股机构类型（基金/社保/QFII/保险/券商）、机构名称、持股数、持股比例、占流通股比例
  - 在 `akshare.py` 中新增 `get_shareholder_changes(symbol, report_date) → str` 函数
    - 调用 `ak.stock_gdfx_free_holding_change_em(date=report_date)` 获取十大流通股东变动
    - 解析当前 symbol 在数据中的行，提取股东名称、持股变动方向（新进/增加/减少/不变）
  - 在 `akshare.py` 中新增 `get_fund_holdings(symbol, report_date) → str` 函数
    - 调用 `ak.stock_fund_hold_detail_em(symbol=symbol, date=report_date)` 获取基金持仓
    - 返回基金公司名称、持仓市值、持仓占比
  - 测试文件：`tests/test_institutional_holdings.py`（RED → GREEN）

  **禁止做**：
  - 不修改现有 `get_fundamentals` 签名（该函数返回基本面财务数据，非持仓数据）
  - 返回格式保持与现有 akshare 函数一致（Markdown header + table/content）
  - akshare.py 不超过 2000 行

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要理解 akshare 股东/机构 API 并适配项目格式
  - **技能**：无
  - **并行**：Wave 2，与 T4、T6-T10 并行

  **参考文献**：
  - `tradingagents/dataflows/akshare.py:608-668` — `get_news` 函数模式（日期过滤 + Markdown 格式化新闻列表）
  - `tradingagents/dataflows/schemas.py:InstitutionalHolding` — 标准字段定义
  - `tradingagents/dataflows/akshare.py:46-53` — `_ak_date` 和 `_to_date` 日期转换工具

  **验收标准（TDD）**：
  - [ ] `tests/test_institutional_holdings.py` 包含至少 4 个测试用例
  - [ ] `pytest tests/test_institutional_holdings.py -v` → PASS
  - [ ] 测试覆盖：正常数据、无效 quarter 格式、无数据返回、基金持仓/机构持股/股东变动三个函数

  **QA 场景**：

  ```
  场景：获取机构持股详情（mock）
    工具：bash
    前置条件：mock_akshare fixture
    步骤：
      1. pytest tests/test_institutional_holdings.py::test_get_institutional_holdings -v
      2. 验证返回 Markdown 含 "## 机构持股详情" 标题和 "持股机构类型" 列
    预期结果：测试 PASS，数据格式正确
    证据：.sisyphus/evidence/task-5-holdings.log
  ```

  **提交**：是
  - 消息：`feat(akshare): 新增机构持仓/股东变化数据采集`
  - 文件：`tradingagents/dataflows/akshare.py`, `tests/test_institutional_holdings.py`

- [ ] 6. akshare 公告/新闻增强（TDD）

  **做什么**：
  - 增强现有 `get_news` 函数：增加对 `ak.stock_notice_report(symbol)` 的调用作为补充公告源
    - 巨潮资讯公告提供更完整的公告全文链接和分类
  - 在 `akshare.py` 中新增 `get_announcements(symbol, start_date, end_date, category=None) → str` 函数
    - category 可选：`"定期报告"` / `"临时公告"` / `"IPO"` / `None`（全部）
    - 调用 `ak.stock_notice_report(symbol=symbol)` 获取公告列表
    - 按日期过滤、按类别过滤
    - 返回 Markdown 格式：公告标题 + 类型 + 发布日期 + 链接
  - 不改变现有 `get_news`、`get_individual_notices`、`get_research_reports` 的函数签名（护栏 G1）
  - 测试文件：`tests/test_announcements.py`

  **禁止做**：
  - 不删除或重命名现有的 `get_news`、`get_individual_notices`、`get_research_reports`
  - 不改变这些函数的现有签名

  **推荐 Agent 配置**：
  - **类别**：`quick` — 基于现有 akshare API 的增量增强
  - **技能**：无
  - **并行**：Wave 2，与 T4-T5、T7-T10 并行

  **参考文献**：
  - `tradingagents/dataflows/akshare.py:608-668` — 现有 `get_news` 实现（需增强）
  - `tradingagents/dataflows/akshare.py:1121-1199` — `get_individual_notices` 现有实现
  - `tradingagents/dataflows/akshare.py:1200+` — `get_research_reports` 现有实现

  **验收标准（TDD）**：
  - [ ] `tests/test_announcements.py` 包含至少 2 个测试用例
  - [ ] `pytest tests/test_announcements.py -v` → PASS
  - [ ] 测试 `get_announcements` 正常返回 + 空数据降级

  **QA 场景**：

  ```
  场景：获取个股公告（mock）
    工具：bash
    前置条件：mock_akshare fixture
    步骤：
      1. pytest tests/test_announcements.py -v
      2. 验证测试通过
    预期结果：PASS，无回归
    证据：.sisyphus/evidence/task-6-announcements.log
  ```

  **提交**：是
  - 消息：`feat(akshare): 增强公告/新闻数据源（新增 get_announcements + 增强 get_news）`
  - 文件：`tradingagents/dataflows/akshare.py`, `tests/test_announcements.py`

- [ ] 7. akshare 舆情监控增强（TDD）

  **做什么**：
  - 增强 `get_social_sentiment` 函数（`akshare.py:929-996`）：
    - 增加 `ak.stock_hot_rank_em()` 全市场热度排名（供全局舆情视图）
    - 增加 `ak.stock_hot_search_baidu(symbol, date)` 百度搜索指数（可选，如 API 可用）
    - 增强数据聚合：合并东方财富评论 + 雪球关注 + 股吧热帖
  - 在 `akshare.py` 中新增 `get_market_sentiment() → str` 函数
    - 调用 `ak.stock_hot_rank_em()` 获取全市场热度排名 Top 20
    - 调用 `ak.stock_hot_rank_detail_realtime_em()` 获取实时热度明细
    - 返回格式：包含热度排名表 + 情绪概要
  - 测试文件：`tests/test_sentiment.py`

  **禁止做**：
  - 不删除现有 `get_social_sentiment` 的任何子功能
  - 不引入 NLP 情绪分析库（保持纯数据采集）

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要理解多个 akshare 舆情 API 并聚合数据
  - **技能**：无
  - **并行**：Wave 2，与 T4-T6、T8-T10 并行

  **参考文献**：
  - `tradingagents/dataflows/akshare.py:929-996` — 现有 `get_social_sentiment` 实现
  - `tradingagents/agents/analysts/social_media_analyst.py` — 舆情分析师消费模式

  **验收标准（TDD）**：
  - [ ] `tests/test_sentiment.py` 包含至少 3 个测试用例
  - [ ] `pytest tests/test_sentiment.py -v` → PASS
  - [ ] 测试 `get_market_sentiment` 返回 Top 20 格式正确

  **QA 场景**：

  ```
  场景：获取全市场热度排名（mock）
    工具：bash
    步骤：
      1. pytest tests/test_sentiment.py::test_get_market_sentiment -v
      2. 验证返回字符串含 "排名" 和 "热度" 字段
    预期结果：测试 PASS
    证据：.sisyphus/evidence/task-7-sentiment.log
  ```

  **提交**：是
  - 消息：`feat(akshare): 增强舆情监控（新增 get_market_sentiment + 增强 get_social_sentiment）`
  - 文件：`tradingagents/dataflows/akshare.py`, `tests/test_sentiment.py`

- [ ] 8. market_context 资金流北向分类增强（TDD）

  **做什么**：
  - 在 `market_context.py` 中增强 `_fetch_capital_flow()` 函数（`line 95-114`）：
    - 新增调用 `ak.stock_hsgt_fund_flow_summary_em()` 获取北向/南向分类汇总
    - 提取北向资金流向（沪股通 + 深股通）的净流入数据
    - 在返回字符串中追加一行 `北向净流入: +X.X亿 | 南向净流入: +X.X亿`
  - 在 `market_context.py` 中新增 `_fetch_northbound_sectors() → str` 函数
    - 调用 `ak.stock_hsgt_board_rank_em()` 获取北向资金板块排名
    - 返回北向资金流入最多的 Top 5 板块
  - 修改 `fetch_market_context()` 调用新增的 `_fetch_northbound_sectors()`
  - 测试文件：`tests/test_market_context_northbound.py`

  **禁止做**：
  - 不删除或重命名 `_fetch_capital_flow`（它是 `fetch_market_context` 的一部分）
  - 不在 market_context 中进行 LLM 调用（该模块保持纯数据函数）

  **推荐 Agent 配置**：
  - **类别**：`quick` — 增量增强现有函数
  - **技能**：无
  - **并行**：Wave 2，与 T4-T7、T9-T10 并行

  **参考文献**：
  - `tradingagents/dataflows/market_context.py:95-114` — `_fetch_capital_flow` 现有实现
  - `tradingagents/dataflows/market_context.py:160+` — `fetch_market_context` 主聚合器
  - `tradingagents/dataflows/macro_context.py:187-250` — `_fetch_northbound_flow` 北向资金提取模式
  - `tests/test_macro_context.py` — 现有 macro context 测试模式

  **验收标准（TDD）**：
  - [ ] `tests/test_market_context_northbound.py` 包含至少 2 个测试用例
  - [ ] `pytest tests/test_market_context_northbound.py -v` → PASS
  - [ ] `fetch_market_context()` 返回包含 "北向" 关键词

  **QA 场景**：

  ```
  场景：资金流返回含北向分类
    工具：bash
    步骤：
      1. pytest tests/test_market_context_northbound.py::test_capital_flow_with_northbound -v
      2. 验证 mock 场景下函数返回字符串含 "北向净流入" 或 "北向"
    预期结果：输出含北向分类信息
    证据：.sisyphus/evidence/task-8-northbound-flow.log
  ```

  **提交**：是
  - 消息：`feat(market_context): 资金流增加北向分类（北向板块排名 + 北向净流入）`
  - 文件：`tradingagents/dataflows/market_context.py`, `tests/test_market_context_northbound.py`

- [ ] 9. Tushare vendor 模块（TDD）

  **做什么**：
  - 在 `tradingagents/dataflows/` 下新建 `tushare.py`
    - Lazy import guard：`try: import tushare as ts except ImportError: ts = None`
    - `_ensure_tushare()`：检查 token 是否配置（从 `get_config()` 读取 `tushare_token`）
  - 实现 `get_northbound_detail(symbol, start_date, end_date) → str`
    - 调用 `pro.moneyflow_hsgt(ts_code=symbol, start_date=start_date, end_date=end_date)`
    - 返回个股级别的北向资金明细：买入额、卖出额、净买入额、持股量
  - 实现 `get_top_holders(symbol, report_date) → str`
    - 调用 `pro.top10_holders(ts_code=symbol, end_date=report_date)` 和 `pro.top10_floatholders`
    - 返回前十大股东/流通股东信息
  - 实现 `get_shareholder_count(symbol, start_date, end_date) → str`
    - 调用 `pro.stk_holdernumber(ts_code=symbol, start_date=start_date, end_date=end_date)`
    - 返回股东户数变化趋势
  - 测试文件：`tests/test_tushare_vendor.py`

  **禁止做**：
  - 不硬编码 tushare token（从配置读取）
  - 不覆盖 or 替代 akshare 的同名函数（tushare 是补充源，非替代源）
  - tushare 函数返回格式与 akshare 一致（Markdown CSV）

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要查阅 tushare pro API 文档，确保字段映射正确
  - **技能**：无
  - **并行**：Wave 2，与 T4-T8、T10 并行

  **参考文献**：
  - `tradingagents/dataflows/akshare.py:1-50` — vendor 模块结构模式（lazy import + _ensure 守卫）
  - `tradingagents/dataflows/akshare.py:155-212` — `get_stock_data` Markdown 返回格式
  - `tradingagents/dataflows/config.py:23-27` — 配置读取模式 `get_config()`
  - `tradingagents/dataflows/schemas.py:NorthboundDetail` — 北向数据标准字段
  - tushare pro 官方文档：`moneyflow_hsgt` / `top10_holders` / `stk_holdernumber` API

  **验收标准（TDD）**：
  - [ ] `tests/test_tushare_vendor.py` 包含至少 4 个测试用例（mock tushare 调用）
  - [ ] `pytest tests/test_tushare_vendor.py -v` → PASS
  - [ ] 测试：无 token 时优雅降级、正常数据、空数据、字段缺失容错

  **QA 场景**：

  ```
  场景：tushare 模块在无 token 时优雅降级
    工具：bash
    前置条件：mock tushare import
    步骤：
      1. pytest tests/test_tushare_vendor.py::test_no_token_graceful -v
      2. 验证返回包含 "tushare token 未配置" 提示
    预期结果：不抛异常，返回提示信息
    证据：.sisyphus/evidence/task-9-tushare-no-token.log

  场景：获取北向资金明细（mock）
    工具：bash
    步骤：
      1. pytest tests/test_tushare_vendor.py::test_get_northbound_detail -v
      2. 验证返回包含 "北向资金明细" 和 "净买入" 字段
    预期结果：测试 PASS
    证据：.sisyphus/evidence/task-9-northbound.log
  ```

  **提交**：是
  - 消息：`feat(tushare): 新建 tushare vendor 模块（北向资金明细 + 机构持仓）`
  - 文件：`tradingagents/dataflows/tushare.py`, `tests/test_tushare_vendor.py`

- [ ] 10. 监管/政策快讯爬虫（TDD）

  **做什么**：
  - 在 `tradingagents/dataflows/crawlers/` 下新建 `policy.py`
    - 继承 `BaseCrawler`，实现 `PolicyCrawler` 类
    - `fetch_csrc_news() → str`：爬取证监会官网 (csrc.gov.cn) 最新政策发布
      - URL：`http://www.csrc.gov.cn/csrc/c100028/common_list.shtml`（证监会要闻）
      - 使用 parsel 提取标题、日期、链接
      - 返回 Markdown 格式列表（最近10条）
    - `fetch_pbc_policy() → str`：爬取央行官网 (pbc.gov.cn) 货币政策
      - URL：`http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/index.html`
      - 提取标题、日期、摘要
      - 返回 Markdown 格式
    - `fetch_financial_express() → str`：聚合快讯（如上两源 + 如果可爬的财经媒体 RSS）
  - 在 `akshare.py` 中暴露统一入口 `get_policy_news() → str`
    - 内部调用 PolicyCrawler 的聚合方法
    - 提供缓存（T+1 级别，政策新闻不需要实时）
  - 测试文件：`tests/test_policy_crawler.py`

  **禁止做**：
  - 不对同一 URL 重复请求超过 1 次/小时（遵守 robots.txt）
  - 不爬取需要登录的页面
  - 爬虫失败不阻断分析（返回 "政策数据暂不可用"）

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要正确解析政府网站 HTML 结构
  - **技能**：无
  - **并行**：Wave 2，与 T4-T9 并行

  **参考文献**：
  - `tradingagents/dataflows/crawlers/base.py:BaseCrawler` — 基类 API
  - `tradingagents/dataflows/akshare.py:608-668` — `get_news` Markdown 格式化参考
  - `tradingagents/dataflows/schemas.py:PolicyNews` — 标准字段定义

  **验收标准（TDD）**：
  - [ ] `tests/test_policy_crawler.py` 包含至少 3 个测试用例（mock HTTP 响应）
  - [ ] `pytest tests/test_policy_crawler.py -v` → PASS
  - [ ] 测试：正常爬取、网络错误降级、HTML 结构变化容错

  **QA 场景**：

  ```
  场景：PolicyCrawler 网络错误降级
    工具：bash
    步骤：
      1. 使用 mock 模拟 requests.get 抛出 ConnectionError
      2. pytests tests/test_policy_crawler.py::test_network_error_graceful -v
      3. 验证返回 "政策数据暂不可用"
    预期结果：测试 PASS，不抛异常
    证据：.sisyphus/evidence/task-10-policy-graceful.log
  ```

  **提交**：是
  - 消息：`feat(crawler): 新增监管/政策快讯爬虫（证监会+央行）`
  - 文件：`tradingagents/dataflows/crawlers/policy.py`, `tests/test_policy_crawler.py`

- [ ] 11. interface.py 工具注册

  **做什么**：
  - 在 `tradingagents/dataflows/interface.py` 中：
    - `TOOLS_CATEGORIES` 新增分类：
      ```python
      "margin_data": {"description": "融资融券数据", "tools": ["get_margin_data", "get_margin_summary"]},
      "position_data": {"description": "机构持仓/股东变化", "tools": ["get_institutional_holdings", "get_shareholder_changes", "get_fund_holdings"]},
      "macro_flow_data": {"description": "资金流分类数据", "tools": ["get_northbound_detail"]},
      ```
    - `VENDOR_LIST` 新增 `"tushare"`（如不存在）
    - 为 tushare 函数创建路由别名（`get_northbound_detail_tushare` 等）
    - 在 `VENDOR_METHODS` 中注册新方法映射
    - 更新 `TOOLS_CATEGORIES["news_data"]["tools"]` 包含 `"get_announcements"` 和 `"get_policy_news"`

  **禁止做**：
  - 不修改现有 TOOLS_CATEGORIES 的 key（保持向后兼容）
  - 不删除任何现有注册项

  **推荐 Agent 配置**：
  - **类别**：`quick` — 配置型任务，无业务逻辑
  - **技能**：无
  - **并行**：Wave 3，与 T12-T13 并行

  **参考文献**：
  - `tradingagents/dataflows/interface.py:43-74` — 现有 TOOLS_CATEGORIES 结构
  - `tradingagents/dataflows/interface.py:76-80` — VENDOR_LIST 定义
  - `tradingagents/dataflows/interface.py:82+` — VENDOR_METHODS 注册模式

  **验收标准（TDD）**：
  - [ ] `python -c "from tradingagents.dataflows.interface import TOOLS_CATEGORIES; print(list(TOOLS_CATEGORIES.keys()))"` 输出含 `margin_data`, `position_data`, `macro_flow_data`
  - [ ] `python -c "from tradingagents.dataflows.interface import VENDOR_LIST; print('tushare' in VENDOR_LIST)"` → True

  **QA 场景**：

  ```
  场景：新分类已注册且可导入
    工具：bash
    步骤：
      1. python -c "
        from tradingagents.dataflows.interface import TOOLS_CATEGORIES
        assert 'margin_data' in TOOLS_CATEGORIES, 'margin_data missing'
        assert 'position_data' in TOOLS_CATEGORIES, 'position_data missing'
        print('ALL_CATEGORIES_REGISTERED')
        "
    预期结果：输出 ALL_CATEGORIES_REGISTERED
    证据：.sisyphus/evidence/task-11-interface.log
  ```

  **提交**：是
  - 消息：`feat(config): 注册新数据源工具分类（margin_data/position_data/macro_flow_data）`
  - 文件：`tradingagents/dataflows/interface.py`

- [ ] 12. config.py / default_config.py 更新

  **做什么**：
  - 在 `default_config.py` 中：
    - `data_vendors` 新增：
      ```python
      "margin_data": "akshare",
      "position_data": "akshare",
      "macro_flow_data": "tushare",
      ```
    - 新增 `"tushare_token": os.getenv("TUSHARE_TOKEN", "")` 配置项
  - 在 `config.py` 中无需修改（已支持动态覆盖）
  - 确保 `akshare.py` 和 `tushare.py` 中通过 `get_config()` 读取到正确配置

  **禁止做**：
  - 不删除或重命名现有 vendor 配置键

  **推荐 Agent 配置**：
  - **类别**：`quick` — 纯配置项添加
  - **技能**：无
  - **并行**：Wave 3，与 T11、T13 并行

  **参考文献**：
  - `tradingagents/default_config.py:38-45` — 现有 data_vendors 配置
  - `tradingagents/dataflows/config.py:15-27` — 配置覆盖机制
  - `tradingagents/dataflows/akshare.py:92-93` — `_load_ohlcv_akshare` 中的 `get_config()` 调用模式
  - `.env.example` — 环境变量命名约定

  **验收标准（TDD）**：
  - [ ] `python -c "from tradingagents.dataflows.config import get_config; c=get_config(); print(c['data_vendors']['margin_data'])"` → `akshare`
  - [ ] `python -c "from tradingagents.dataflows.config import get_config; print('tushare_token' in get_config())"` → True

  **QA 场景**：

  ```
  场景：新 data_vendors 配置可读取
    工具：bash
    步骤：
      1. python -c "
        from tradingagents.dataflows.config import get_config
        c = get_config()
        assert c['data_vendors']['margin_data'] == 'akshare'
        assert 'tushare_token' in c
        print('CONFIG_OK')
        "
    预期结果：输出 CONFIG_OK
    证据：.sisyphus/evidence/task-12-config.log
  ```

  **提交**：是
  - 消息：`feat(config): 新增数据 vendor 配置（margin/position/macro_flow + tushare_token）`
  - 文件：`tradingagents/default_config.py`, `.env.example`

- [ ] 13. position_analyst 持仓数据聚合器

  **做什么**：
  - 在 `tradingagents/agents/analysts/` 下新建 `position_analyst.py`
    - 纯数据聚合器（类似 `market_context.py`），不包含 LLM 调用
    - 函数签名：`fetch_position_context(symbol, trade_date) → str`
    - 聚合来源：
      1. `get_institutional_holdings(symbol, latest_quarter)` — 机构持股
      2. `get_shareholder_changes(symbol, latest_report)` — 十大股东变动
      3. `get_fund_holdings(symbol, latest_report)` — 基金持仓
      4. `get_margin_data(symbol, trade_date)` — 融资融券状态
      5. `get_northbound_detail(symbol, trade_date)` — 北向资金持股
    - 返回：整合 Markdown 报告，含各维度持仓数据摘要（不超过 800 字符，控制 prompt 长度）
    - 优雅降级：任一源失败用 "数据暂不可用" 标注
  - 在 `tradingagents/agents/analysts/__init__.py` 中导出 `fetch_position_context`
  - 测试文件：`tests/test_position_analyst.py`

  **禁止做**：
  - position_analyst 不包含 LLM 调用 — 它只是数据聚合器
  - 返回长度不超过 1200 字符（参照 macro_context 的 cap）

  **推荐 Agent 配置**：
  - **类别**：`deep` — 需要理解所有新数据源并协调聚合
  - **技能**：无
  - **并行**：Wave 3，与 T11-T12 并行

  **参考文献**：
  - `tradingagents/dataflows/macro_context.py:278-310` — `fetch_macro_context` 聚合模式
  - `tradingagents/dataflows/market_context.py:160+` — `fetch_market_context` 聚合模式
  - `tradingagents/agents/analysts/fundamentals_analyst.py` — Agent 工厂模式（如需后续升级为 LLM Agent）

  **验收标准（TDD）**：
  - [ ] `tests/test_position_analyst.py` 包含至少 2 个测试用例
  - [ ] `pytest tests/test_position_analyst.py -v` → PASS
  - [ ] 测试：正常聚合、部分源失败的降级、返回长度 ≤ 1200 字符

  **QA 场景**：

  ```
  场景：position_analyst 聚合所有数据源（mock）
    工具：bash
    步骤：
      1. pytest tests/test_position_analyst.py::test_fetch_position_context -v
      2. 验证返回字符串含 "机构持股" 或 "融资融券" 或 "北向资金"
    预期结果：返回聚合报告
    证据：.sisyphus/evidence/task-13-position-analyst.log
  ```

  **提交**：是
  - 消息：`feat(agent): 新增 position_analyst 持仓数据聚合器`
  - 文件：`tradingagents/agents/analysts/position_analyst.py`, `tradingagents/agents/analysts/__init__.py`, `tests/test_position_analyst.py`

- [ ] 14. 端到端集成测试

  **做什么**：
  - 在 `tests/` 下新建 `test_data_integration.py`
  - 测试场景：
    1. 完整数据管线：调用 `fetch_position_context` → 验证各子源被调用且贡献了数据
    2. 降级管线：所有子源 mock 为失败 → 验证返回 "数据暂不可用" 而不崩溃
    3. 分类注册完整性：验证 interface.py 中所有新分类的方法在 vendor 中均有对应实现
  - 回归测试：运行 `pytest tests/` 全量测试确保无回归

  **禁止做**：
  - 不在集成测试中对真实 API 调用（全部使用 mock）

  **推荐 Agent 配置**：
  - **类别**：`deep` — 端到端管线测试
  - **技能**：无
  - **并行**：Wave 4（串行，依赖所有 Wave 3 任务完成）

  **参考文献**：
  - `tests/conftest.py` — 现有 mock fixtures
  - `tests/test_macro_context.py` — 现有集成测试模式
  - `tests/test_context_assembly.py` — 上下文装配测试参考

  **验收标准（TDD）**：
  - [ ] `tests/test_data_integration.py` 存在
  - [ ] `pytest tests/test_data_integration.py -v` → PASS
  - [ ] 回归：`pytest tests/ -v --tb=short` 全部通过

  **QA 场景**：

  ```
  场景：完整集成管线（全部 mock）
    工具：bash
    步骤：
      1. pytest tests/test_data_integration.py -v
      2. 验证所有测试通过
    预期结果：全部 PASS
    证据：.sisyphus/evidence/task-14-integration.log

  场景：全量回归测试
    工具：bash
    步骤：
      1. pytest tests/ -v --tb=short
      2. 检查是否有 FAILED 测试
    预期结果：无回归失败
    证据：.sisyphus/evidence/task-14-regression.log
  ```

  **提交**：是
  - 消息：`test(integration): 数据源端到端集成测试 + 回归验证`
  - 文件：`tests/test_data_integration.py`

---

## 最终验证波次（强制 — 所有实现任务完成后）

> 4 个审查 agent 并行运行。全部必须 APPROVE。向用户呈现综合结果，获得明确"okay"后才能完成。
>
> **验证通过后不自动继续。等待用户明确批准后再标记工作完成。**
> **用户拒绝或反馈 → 修复 → 重新运行 → 重新呈现 → 等待批准。**

- [ ] F1. **计划合规审计** — `oracle`
  逐项阅读计划。对每个"必须包含"：验证实现存在（读文件、运行命令）。对每个"必须不包含"：搜索代码库查找禁用模式——如发现以 `file:line` 形式报告拒绝。检查 `.sisyphus/evidence/` 中的证据文件。将交付物与计划进行比对。
  输出：`必须包含 [N/N] | 必须不包含 [N/N] | 任务 [N/N] | 判定：APPROVE/REJECT`

- [ ] F2. **代码质量审查** — `unspecified-high`
  运行 `pytest`。审查所有变更文件：`as any`/`@ts-ignore`、空 catch、console.log、注释掉的代码、未使用的导入。检查 AI slop：过度注释、过度抽象、通用命名（data/result/item/temp）。
  输出：`构建 [PASS/FAIL] | 测试 [N pass/N fail] | 文件 [N clean/N issues] | 判定`

- [ ] F3. **实机 QA 执行** — `unspecified-high`
  从干净状态启动。执行每个任务的每个 QA 场景——严格按步骤操作，采集证据。测试跨任务集成（功能协同工作，非孤立测试）。边界测试：空状态、无效输入、快速重复操作。保存到 `.sisyphus/evidence/final-qa/`。
  输出：`场景 [N/N pass] | 集成 [N/N] | 边界 [N tested] | 判定`

- [ ] F4. **范围保真度检查** — `deep`
  对每个任务：阅读"做什么"，阅读实际 diff（git log/diff）。逐项验证——spec 中所有内容均已实现（不缺失），spec 外内容均未实现（不蔓延）。检查"禁止做"合规性。检测跨任务污染：任务 N 触及任务 M 的文件。标记未计入的变更。
  输出：`任务 [N/N compliant] | 污染 [CLEAN/N issues] | 未计入 [CLEAN/N files] | 判定`

---

## 提交策略

- **T1-T3**：`feat(data): 新增数据源测试基础设施和类型定义` — tests/conftest.py, tradingagents/dataflows/schemas.py, tradingagents/dataflows/crawlers/__init__.py
- **T4-T8**：`feat(akshare): 增强 A 股数据采集（融资融券/机构持仓/公告/舆情/资金流）` — tradingagents/dataflows/akshare.py, tradingagents/dataflows/market_context.py, tests/test_*.py
- **T9**：`feat(tushare): 新建 tushare vendor 模块（北向资金/机构持仓）` — tradingagents/dataflows/tushare.py, tests/test_tushare_vendor.py
- **T10**：`feat(crawler): 新增监管/政策快讯爬虫` — tradingagents/dataflows/crawlers/policy.py, tests/test_policy_crawler.py
- **T11-T12**：`feat(config): 注册新数据源工具和 vendor 配置` — tradingagents/dataflows/interface.py, tradingagents/dataflows/config.py, tradingagents/default_config.py
- **T13**：`feat(agent): 新增 position_analyst 持仓数据聚合器` — tradingagents/agents/analysts/position_analyst.py
- **T14**：`test(integration): 数据源端到端集成测试` — tests/test_data_integration.py

---

## 成功标准

### 验证命令

```bash
# 运行所有测试
pytest tests/ -v --tb=short

# 验证新增测试通过
pytest tests/test_margin_data.py tests/test_institutional_holdings.py tests/test_tushare_vendor.py tests/test_policy_crawler.py -v

# 验证工具已注册
python -c "from tradingagents.dataflows.interface import TOOLS_CATEGORIES; assert 'margin_data' in TOOLS_CATEGORIES; print('OK')"

# 验证 tushare 模块可导入
python -c "from tradingagents.dataflows.tushare import get_northbound_detail; print('Tushare module OK')"

# 验证爬虫可运行（仅检查基础设施，不实际爬取）
python -c "from tradingagents.dataflows.crawlers.policy import PolicyCrawler; print('Crawler module OK')"
```

### 最终检查清单

- [ ] 所有"必须包含"已实现
- [ ] 所有"必须不包含"已落实
- [ ] 所有新增测试通过
- [ ] 优雅降级已测试（数据不可用时返回提示而非异常）
- [ ] 三层注册（TOOLS_CATEGORIES + VENDOR_METHODS + default_config）已同步
- [ ] akshare.py 不超过 2000 行
