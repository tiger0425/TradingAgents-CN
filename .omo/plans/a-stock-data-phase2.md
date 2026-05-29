# Phase 2 — a-stock-data 替换升级现有能力

## 摘要

> **核心目标**：用 a-stock-data V3.1 的 4 个端点替换/新增 tradingagents-cn 中的对应数据能力。2 个直接替换 akshare 实现（修改现有文件）、2 个仿 Phase 1 模式纯新增。
>
> **交付物**：
> - `a_stock_data.py` 新增 4 个函数（2 替换 + 2 新增）
> - `macro_context.py` 替换 `_fetch_northbound_flow()` 内部实现
> - `market_context.py` 替换 `_fetch_sector_rotation()` 内部实现
> - `interface.py` 注册新端点 + 修复 VENDOR_LIST 遗漏
> - `a_stock_data_tools.py` 新增 2 个 Tool 包装
> - `test_a_stock_data.py` 新增冒烟测试
>
> **预估工作量**：中等（< Phase 1 工作量）
> **并行执行**：YES — Step 1(2 新增端点) 和 Step 2(2 替换) 可并行
> **关键路径**：Step 2（修改 macro_context.py + market_context.py）→ 注册 → 测试

---

## 背景

### Phase 1 已完成

- a_stock_data.py：9 个端点 + `_eastmoney_datacenter()` / `_format_result()` / `_ensure_mootdx()` / `PUSH2_URL` 基础设施
- interface.py：`specialty_data` TOOLS_CATEGORIES + VENDOR_METHODS
- 冒烟测试 19/19 通过

### 探索发现

| 替换点 | 文件 | 函数 | 当前 akshare API | 替换为 |
|--------|------|------|-----------------|--------|
| 北向资金 | `macro_context.py` | `_fetch_northbound_flow()` (行 187-250) | `ak.stock_hsgt_fund_flow_summary_em()` | 同花顺 `data.hexin.cn` + CSV 缓存 |
| 行业排名 | `market_context.py` | `_fetch_sector_rotation()` (行 65-92) | `ak.stock_sector_fund_flow_rank()` | 东财 push2 `m:90+t:2` |

| 新增 | 数据源 | a_stock_data 函数名 |
|------|--------|-------------------|
| 概念板块 | 百度股市通 `finance.pae.baidu.com` | `get_concept_blocks()` |
| 题材归因 | 同花顺 `zx.10jqka.com.cn` | `get_hot_stock_reasons()` |

### 设计决策（已确认）

- ✅ 北向资金：汇总输出 + CSV 缓存 262 分钟明细
- ✅ 移除 `TRADINGAGENTS_NORTHBOUND_FLOW` 环境变量覆盖
- ✅ 新增端点注册为 Agent 工具

---

## 工作目标

### 核心目标

用 a-stock-data 直连 HTTP 替换 2 处 akshare 调用，新增 2 个数据端点。

### 具体交付物

- `tradingagents/dataflows/a_stock_data.py`：新增 4 个函数
- `tradingagents/dataflows/macro_context.py`：替换 `_fetch_northbound_flow()` 内部实现
- `tradingagents/dataflows/market_context.py`：替换 `_fetch_sector_rotation()` 内部实现
- `tradingagents/dataflows/interface.py`：注册 2 新端点 + 修复 VENDOR_LIST 遗漏
- `tradingagents/agents/utils/a_stock_data_tools.py`：新增 2 个 Tool 包装
- `tests/test_a_stock_data.py`：新增 4+ 冒烟测试

### 完成定义

- [ ] `_fetch_northbound_flow()` 返回格式不变（`"北向资金...`" 一行文本）
- [ ] `_fetch_sector_rotation()` 返回格式不变（`"领涨:... | 领跌:...”`）
- [ ] 2 个新增端点通过 `route_to_vendor()` 可调用
- [ ] 冒烟测试全部通过（含现有 19 个 + 新增）
- [ ] `macro_context.py` 仅移除北向相关的 akshare 调用，保留其他 6 个函数不变
- [ ] `market_context.py` 仅移除 `stock_sector_fund_flow_rank` 调用，保留其他 3 个函数不变
- [ ] VENDOR_LIST 包含 `a_stock_data`

## 必须实现

- 4 个端点全部实现（`→ str`）
- 数据函数遵循 guosen.py 的 `try/except → return "错误: ..."` 模式
- `_fetch_northbound_flow()` 和 `_fetch_sector_rotation()` 签名和返回格式不变
- 北向 CSV 缓存写入 `~/.tradingagents/cache/northbound_daily.csv`
- `fetch_macro_context()` 仍含 6 个章节标题
- `fetch_market_context()` 仍含 4 个章节标题

## 必须避免

- ❌ 不修改 `fetch_macro_context()` 的公开签名
- ❌ 不修改 `fetch_market_context()` 的公开签名
- ❌ 不修改 `macro_context.py` 中其他 6 个 `_fetch_*` 函数
- ❌ 不修改 `market_context.py` 中 `_fetch_capital_flow()` 和 `_fetch_market_breadth()`
- ❌ 不修改 `collector/market_collector.py`、`graph/trading_graph.py`、`agents/utils/market_context_tools.py`
- ❌ 不修改 `pyproject.toml`（mootdx 已在 Phase 1 添加）
- ❌ 不引入新依赖

---

## 验证策略

- **冒烟测试**：`pytest tests/test_a_stock_data.py -m smoke`（600519 验证）
- **回归测试**：`pytest tests/test_macro_context.py` + `tests/test_market_context.py`
- **输出格式验证**：grep 章节标题确认结构不变

---

## 执行策略

### 并行执行波次

```
Wave 1（基础准备 — 2 任务并行）：
├── Task 1: 修复 VENDOR_LIST 遗漏 a_stock_data [quick]
└── Task 2: 修复 test_macro_context.py mock 列名 [quick]

Wave 2（纯新增 — 2 任务并行）：
├── Task 3: a_stock_data.py 新增 get_concept_blocks() [quick]
└── Task 4: a_stock_data.py 新增 get_hot_stock_reasons() [quick]

Wave 3（替换实现 — 2 任务并行）：
├── Task 5: 替换 macro_context.py _fetch_northbound_flow() [quick]
└── Task 6: 替换 market_context.py _fetch_sector_rotation() [quick]

Wave 4（集成 — 3 任务）：
├── Task 7: interface.py 注册 2 新端点 [quick]
├── Task 8: a_stock_data_tools.py 新增 2 个 Tool 包装 [quick]
└── Task 9: test_a_stock_data.py 新增冒烟测试 [quick]

Wave FINAL（审查）：
├── F1: 计划合规审计 (oracle)
├── F2: 代码质量审查 (unspecified-high)
├── F3: 手动 QA (unspecified-high)
└── F4: 范围保真度检查 (deep)
```

### 依赖矩阵

| 任务 | 依赖 | 被依赖 |
|------|------|--------|
| 1 | - | - |
| 2 | - | 5 |
| 3 | - | 7, 8, 9 |
| 4 | - | 7, 8, 9 |
| 5 | 2 | 7, 8 |
| 6 | - | 7, 8 |
| 7 | 3, 4, 5, 6 | 8 |
| 8 | 7 | - |
| 9 | 3, 4 | F1-F4 |

---

- [ ] 3. 在 a_stock_data.py 新增 get_concept_blocks()

  **做什么**：
  - 在 `a_stock_data.py` 中新增 `get_concept_blocks(code: str) -> str` 函数
  - 实现逻辑（参考 a-stock-data SKILL.md Layer 3.3）：
    1. GET `https://finance.pae.baidu.com/api/getrelatedblock?code={code}&market=ab&typeCode=all&finClientType=pc`
    2. Headers：`Host: finance.pae.baidu.com`, `Accept: application/vnd.finance-web.v1+json`, `Origin/Referer: gushitong.baidu.com`
    3. `ResultCode` 检查：`str(d.get("ResultCode", -1)) != "0"` → 错误
    4. 三维分类：行业列表、概念列表、地域列表
    5. 用 `_format_result()` 格式化，标题 "概念板块 — {code}"
  - 注意 `ResultCode` 类型不稳定（int/string），用 `str()` 统一比较

  **禁止做**：不调用 `_eastmoney_datacenter()`（百度 PAE 是独立数据源）

  **推荐 Agent 配置**：`quick`

  **并行化**：Wave 2（与 Task 4 同时），依赖：无（仅需 a_stock_data.py 骨架存在）

  **参考**：a-stock-data SKILL.md "### 3.3 百度股市通 — 概念板块归属"

  **验收标准**：
  - `get_concept_blocks("600519")` 返回 str
  - 输出含 `# 数据来源: a-stock-data`
  - `get_concept_blocks("000000")` 返回含 "错误"/"失败"/"无数据" 的字符串

- [ ] 4. 在 a_stock_data.py 新增 get_hot_stock_reasons()

  **做什么**：
  - 在 `a_stock_data.py` 中新增 `get_hot_stock_reasons(date: str = "") -> str` 函数
  - 实现逻辑（参考 a-stock-data SKILL.md Layer 3.1）：
    1. date 为空则用当天
    2. GET `http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/`
    3. 检查 `errocode`（注意拼写）!= 0 → 错误
    4. 返回 ~125 条记录，每条含 code/name/reason/zhangfu/huanshou 等
    5. reason 字段为 `+` 分隔的题材标签（如 "算力租赁+Token工厂+AI政务"）
    6. 用 `_format_result()` 格式化，标题 "强势股题材归因 — {date}"

  **禁止做**：不调用 `_eastmoney_datacenter()`（同花顺是独立数据源）

  **推荐 Agent 配置**：`quick`

  **并行化**：Wave 2（与 Task 3 同时），依赖：无

  **参考**：a-stock-data SKILL.md "### 3.1 同花顺热点"

  **验收标准**：
  - `get_hot_stock_reasons()` 返回 str，含 reason 标签
  - 输出含 `# 数据来源: a-stock-data`
  - 无效日期返回错误字符串

  **做什么**：
  - 在 `interface.py` 的 `VENDOR_LIST` 列表中添加 `"a_stock_data"`
  - 当前第 173-178 行：`VENDOR_LIST = ["akshare", "yfinance", "alpha_vantage", "guosen"]`
  - 新增后：`VENDOR_LIST = ["akshare", "yfinance", "alpha_vantage", "guosen", "a_stock_data"]`

  **禁止做**：不修改 VENDOR_LIST 中其他 vendor 的顺序

  **推荐 Agent 配置**：`quick`

  **并行化**：Wave 1（与 Task 2 同时），无依赖

  **验收标准**：
  - `python3 -c "from tradingagents.dataflows.interface import VENDOR_LIST; assert 'a_stock_data' in VENDOR_LIST; print('OK')"` 成功

- [ ] 2. 修复 test_macro_context.py mock 列名

  **做什么**：
  - 在 `tests/test_macro_context.py` 中找到 `_fake_northbound()` mock 函数
  - 当前 mock 数据使用 `{"北向资金-净流入": ...}` 列名，但实际 `_fetch_northbound_flow()` 函数查询的是 `ak.stock_hsgt_fund_flow_summary_em()` 返回的 `资金方向`/`交易状态` 列
  - 修复 mock 数据列名，使其与实际函数期望的列名一致
  - 修复后运行 `pytest tests/test_macro_context.py -v --tb=short` 确认通过

  **禁止做**：不修改测试断言逻辑，只修复 mock 数据

  **推荐 Agent 配置**：`quick`

  **并行化**：Wave 1（与 Task 1 同时），Task 5 依赖此任务

  **参考**：
  - `tradingagents/dataflows/macro_context.py:208-250` — 查看实际列名
  - `tests/test_macro_context.py` — 找到 `_fake_northbound()`

  **验收标准**：
   - [`pytest tests/test_macro_context.py -v --tb=short` 通过（或至少北向相关测试不因 mock 列名而假失败）

- [ ] 3. a_stock_data.py 新增 get_concept_blocks()

  **做什么**：在 `a_stock_data.py` 中新增。直连百度股市通 `finance.pae.baidu.com`。`ResultCode` 用 `str()` 统一比较。返回三维分类（行业/概念/地域），用 `_format_result()` 格式化。标题 "概念板块 — {code}"。

  **推荐 Agent**：`quick` | **并行**：Wave 2（与 Task 4 同时）

  **验收标准**：`get_concept_blocks("600519")` 返回 str 含 `# 数据来源: a-stock-data`；无效代码返回错误字符串

- [ ] 4. a_stock_data.py 新增 get_hot_stock_reasons()

  **做什么**：在 `a_stock_data.py` 中新增。直连同花顺 `zx.10jqka.com.cn`。检查 `errocode` != 0。reason 字段 `+` 分隔题材标签。返回 ~125 条，用 `_format_result()` 格式化。标题 "强势股题材归因 — {date}"。

  **推荐 Agent**：`quick` | **并行**：Wave 2（与 Task 3 同时）

  **验收标准**：`get_hot_stock_reasons()` 返回 str 含 reason 标签 + `# 数据来源: a-stock-data`

- [ ] 5. 替换 macro_context.py _fetch_northbound_flow()

  **做什么**：修改 `macro_context.py:187-250`。移除 akshare 北向调用；改为调用 a_stock_data.py 新增的同花顺 API（取最后数据点合计净流入）。输出格式不变（`"北向资金 净流入 XX.X亿"`）。实现 CSV 缓存到 `~/.tradingagents/cache/northbound_daily.csv`。移除 `TRADINGAGENTS_NORTHBOUND_FLOW` 环境变量覆盖。保留 `import akshare`。

  **推荐 Agent**：`quick` | **并行**：Wave 3（与 Task 6 同时）| **依赖**：Task 2（mock 修复）

  **验收标准**：返回格式 `"北向资金..."` 一行文本；CSV 缓存文件创建；六个章节标题不变

- [ ] 6. 替换 market_context.py _fetch_sector_rotation()

  **做什么**：修改 `market_context.py:65-92`。移除 `ak.stock_sector_fund_flow_rank()`；改为东财 push2 `fs=m:90+t:2`。输出格式不变（`"领涨:... | 领跌:..."`）。保留 `import akshare`。

  **推荐 Agent**：`quick` | **并行**：Wave 3（与 Task 5 同时）

  **验收标准**：返回格式 `"领涨:... | 领跌:..."` 文本；四个章节标题不变

- [ ] 7. interface.py 注册 2 新端点

  **做什么**：更新 import（添加 get_concept_blocks, get_hot_stock_reasons）。扩展 VENDOR_METHODS（2 新条目）。扩展 TOOLS_CATEGORIES["specialty_data"]["tools"]（+2 工具名）。

  **推荐 Agent**：`quick` | **并行**：Wave 4 | **依赖**：Tasks 3-6

  **验收标准**：`route_to_vendor("get_concept_blocks", "600519")` 返回 str；现有 9 个端点路由不受影响

- [ ] 8. a_stock_data_tools.py 新增 2 个 Tool 包装

  **做什么**：仿现有模式，新增 `get_concept_blocks` 和 `get_hot_stock_reasons` 的 LangChain Tool 包装器。通过 `route_to_vendor()` 调用。

  **推荐 Agent**：`quick` | **并行**：Wave 4 | **依赖**：Task 7

  **验收标准**：2 个 Tool 可导入且可调用

- [ ] 9. test_a_stock_data.py 新增冒烟测试

  **做什么**：新增 `test_concept_blocks_moutai`（正例 600519）+ `test_concept_blocks_invalid`（负例 000000）+ `test_hot_stock_reasons`（当日数据）+ `test_hot_stock_reasons_invalid_date`（负例）。使用 `@pytest.mark.smoke`。

  **推荐 Agent**：`quick` | **并行**：Wave 4 | **依赖**：Tasks 3-4

  **验收标准**：`pytest tests/test_a_stock_data.py -m smoke -v` 全部通过（含新增 4 个 + 现有 19 个）

---

## 最终验证波次

- [ ] F1. **计划合规审计** — `oracle`：验证必须实现/必须避免清单，检查 evidence 文件
- [ ] F2. **代码质量审查** — `unspecified-high`：lint、类型错误、AI slop、空 except
- [ ] F3. **手动 QA** — `unspecified-high`：9 个场景验证（含新增 + 替换端点）
- [ ] F4. **范围保真度检查** — `deep`：修改文件未超出 spec 范围

---

## 承诺策略

| 批次 | 消息 | 文件 |
|------|------|------|
| 1 | `fix(interface): add a_stock_data to VENDOR_LIST` | `interface.py` |
| 2 | `test: fix mock column names in test_macro_context` | `test_macro_context.py` |
| 3 | `feat(data): add concept blocks and hot stock reasons endpoints` | `a_stock_data.py` |
| 4 | `refactor(data): replace akshare northbound/sector with direct HTTP` | `macro_context.py`, `market_context.py`, `a_stock_data.py` |
| 5 | `feat(data): register new endpoints in interface and tools` | `interface.py`, `a_stock_data_tools.py`, `test_a_stock_data.py` |

---

## 成功标准

```bash
# 冒烟测试
pytest tests/test_a_stock_data.py -v -m smoke --tb=short

# 回归测试
pytest tests/test_macro_context.py tests/test_market_context.py -v --tb=short

# 路由验证
python3 -c "from tradingagents.dataflows.interface import route_to_vendor; print(route_to_vendor('get_concept_blocks', '600519')[:100])"

# VENDOR_LIST 修复验证
python3 -c "from tradingagents.dataflows.interface import VENDOR_LIST; assert 'a_stock_data' in VENDOR_LIST"
```