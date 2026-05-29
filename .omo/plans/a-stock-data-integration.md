# a-stock-data 整合到 tradingagents-cn dataflows 层

## 摘要

> **核心目标**：将 simonlin1212/a-stock-data V3.1 中当前项目缺失的 A 股数据端点整合到 `dataflows/` 层，作为第四个数据供应商，同时建立上游更新同步机制。
>
> **交付物**：
> - `tradingagents/dataflows/a_stock_data.py` — 新增 vendor 模块，封装 9 个缺失端点
> - `tradingagents/agents/utils/a_stock_data_tools.py` — LangChain Tool 包装器
> - `tests/test_a_stock_data.py` — 冒烟测试（600519 贵州茅台验证）
> - 修改 3 个现有文件（`interface.py`、`default_config.py`、`pyproject.toml`）— 仅新增，不破坏现有路径
>
> **预估工作量**：中等
> **并行执行**：YES — 3 波次，Wave 2 可 9 任务并行
> **关键路径**：Task 2（骨架 + Helper）→ Tasks 4-12（端点实现，可并行）→ Tasks 13-15（集成）

---

## 背景

### 原始需求

用户要求将 `simonlin1212/a-stock-data`（GitHub 2.7k star，V3.1，28 端点，13 数据源）整合到 `tradingagents-cn` 的 `dataflows/` 层，按 Phase 1 → 2 → 3 分阶段推进，同时确保上游更新时能同步。本次计划仅覆盖 **Phase 1**。

### 访谈摘要

**关键讨论**：
- **Phase 1 范围**：全部 8 类 9 个缺失端点一次性封装（龙虎榜个股 + 全市场、融资融券、大宗交易、限售解禁、股东户数变化、分红送转、财联社快讯、巨潮公告）
- **Phase 2**（本次不做）：增强现有能力（北向资金、行业排名、概念板块、同花顺热点）
- **Phase 3**（本次不做）：渐进替换 akshare
- **测试策略**：冒烟测试，用 600519 贵州茅台验证核心端点
- **Tool 包装器**：数据函数 + LangChain Tool 包装器都做
- **上游同步**：`a_stock_data.py` 文件头标记版本号 + 锚点映射表 + 手动 Watch GitHub Release

**研究结论**：
- guosen.py（578 行，13 函数）是最佳参考模式 — 所有函数返回 `str`，使用 `Annotated` 类型提示
- `requests`、`pandas`、`stockstats` 已在 `pyproject.toml` 中，只需新增 `mootdx`
- `tests/smoke/` 目录不存在，应使用 `tests/test_a_stock_data.py` 扁平结构
- `@pytest.mark.smoke` 标记已定义但从未被使用

### Metis 审查

**已处理的差距**：
- **tests/smoke/ 不存在** → 改为 `tests/test_a_stock_data.py`，符合现有扁平测试约定
- **mootdx TCP 协议风险** → Task 1 需先在目标环境验证安装和连通性，采用 lazy import 避免阻塞启动
- **Phase 2/3 未定义** → 本次计划严格锁定 Phase 1 交付物，后续阶段另行规划
- **8 端点计数歧义** → 澄清为"8 类 9 端点"（龙虎榜拆为个股 + 全市场两个函数）
- **HTTP mock 缺失** → 冒烟测试走真实网络；未来可引入 vcrpy（Phase 2 考虑）

---

## 工作目标

### 核心目标

将 a-stock-data 中 tradingagents-cn 完全缺失的 9 个数据端点封装为第四个数据供应商模块，供 Agent 通过现有路由系统调用。

### 具体交付物

- `tradingagents/dataflows/a_stock_data.py`：~900 行，9 个公开函数 + 2 个内部 helper，按上游 7 层架构组织，含版本标签和锚点映射表
- `tradingagents/agents/utils/a_stock_data_tools.py`：~100 行，9 个 LangChain Tool 包装器
- `tests/test_a_stock_data.py`：验证 9 个端点的冒烟测试
- 修改 `tradingagents/dataflows/interface.py`：新增 `VENDOR_METHODS` 条目 + `TOOLS_CATEGORIES` 新分类
- 修改 `tradingagents/default_config.py`：新增 `data_vendors.specialty_data` 配置项
- 修改 `pyproject.toml`：新增 `mootdx>=1.0.0` 依赖

### 完成定义

- [ ] `pytest tests/test_a_stock_data.py -m smoke` — 所有 smoke 用例 PASS
- [ ] `python -c "from tradingagents.dataflows.a_stock_data import *"` — 导入成功，9 个公开函数可调用
- [ ] `python -c "from tradingagents.agents.utils.a_stock_data_tools import *"` — 导入成功，9 个 Tool 可调用
- [ ] `grep "Upstream: simonlin1212/a-stock-data v3.1" tradingagents/dataflows/a_stock_data.py` — 版本标签存在
- [ ] 现有测试全部通过：`pytest tests/ --ignore=tests/test_a_stock_data.py -x -q`
- [ ] 无 akshare.py、guosen.py、y_finance.py、alpha_vantage*.py 的任何改动

### 必须实现

- 9 个端点全部有对应的数据函数（`→ str`）和 LangChain Tool 包装器
- 数据函数遵循 guosen.py 的错误处理模式（`try/except → return "错误: ..."`）
- mootdx 采用 lazy import（安装缺失时仅警告，不阻止应用启动）
- 文件头包含上游版本标签和端点→锚点映射表
- 所有修改仅新增（不改动现有代码路径）

### 必须避免（护栏）

- ❌ **不得触碰** `akshare.py`、`guosen.py`、`y_finance.py`、`alpha_vantage*.py` 任何一行
- ❌ **不得修改** `route_to_vendor()` 核心路由逻辑（只新增 VENDOR_METHODS 条目）
- ❌ **不得修改** `TOOLS_CATEGORIES` 现有分类（只新增 `specialty_data` 分类）
- ❌ **不得修改** `default_config.py` 现有 6 个 vendor 默认值
- ❌ **不得修改** `pyproject.toml` 现有依赖版本号
- ❌ **不得创建** `tests/smoke/` 子目录
- ❌ **不得实现** Phase 2/3 的 20 个端点（即使是空壳函数）
- ❌ **不得集成** 缓存层、知识库写入、debate 路由修改
- ❌ **不得引入** 除 `mootdx` 外的任何新依赖
- ❌ **不得引入** 新错误处理模式（坚持 `try/except → str`）
- ❌ **不得** 将 a_stock_data 函数注册到 akshare/yfinance/alpha_vantage 的 VENDOR_METHODS 条目中

---

## 验证策略

### 测试决策

- **测试基础设施存在**：YES（pytest + @pytest.mark.smoke 已定义）
- **自动化测试**：冒烟测试（tests-after）
- **框架**：pytest（`-m smoke`）
- **测试股票**：600519（贵州茅台）— 覆盖主板蓝筹

### QA 策略

每个任务必须包含 agent 可执行的 QA 场景。由于本计划涉及网络 API 调用：
- **API 端点**：使用 `bash`（`curl` 或 `python -c`）直接调用函数，验证返回值和格式
- **集成验证**：使用 `bash`（`pytest -m smoke`）运行测试套件
- 证据保存到 `.omo/evidence/task-{N}-{slug}.txt`

---

## 执行策略

### 并行执行波次

```
Wave 1（立即开始 — 基础 + 骨架，3 任务并行）：
├── Task 1: 验证 mootdx 依赖安装与连通性 [quick]
├── Task 2: 创建 a_stock_data.py 骨架（Helper + 版本标签 + 锚点映射表）[quick]
└── Task 3: 注册 vendor 配置（default_config.py + interface.py 分类注册 + pyproject.toml）[quick]

Wave 2（Wave 1 完成后 — 东财 datacenter 端点，5 任务并行）：
├── Task 4: 龙虎榜个股端点 [quick]
├── Task 5: 全市场龙虎榜端点 [quick]
├── Task 6: 融资融券明细端点 [quick]
├── Task 7: 大宗交易端点 [quick]
└── Task 8: 限售解禁端点 [quick]

Wave 3（Wave 1 完成后 — 东财 + 独立源端点，4 任务并行）：
├── Task 9: 股东户数变化端点 [quick]
├── Task 10: 分红送转端点 [quick]
├── Task 11: 财联社快讯端点 [quick]
└── Task 12: 巨潮公告端点 [quick]

Wave 4（Wave 2 + 3 完成后 — 集成 + 测试，3 任务并行）：
├── Task 13: interface.py 注册全部 9 端点 [quick]
├── Task 14: LangChain Tool 包装器 [quick]
└── Task 15: 冒烟测试 [quick]

Wave FINAL（所有实现任务完成后 — 4 并行审查）：
├── Task F1: 计划合规审计 (oracle)
├── Task F2: 代码质量审查 (unspecified-high)
├── Task F3: 实际手动 QA (unspecified-high)
└── Task F4: 范围保真度检查 (deep)
    → 展示结果 → 获取用户明确 "okay"

关键路径：Task 2 → Tasks 4-8 / Tasks 9-12（可各自并行）→ Tasks 13-15
并行加速：Wave 2(5) 和 Wave 3(4) 合计 9 端点，跨两波实现，~75% 时间节省
最大并发：5（Wave 2）
```

### 依赖矩阵

| 任务 | 依赖 | 被依赖 |
|------|------|--------|
| 1 | - | - |
| 2 | - | 4-12 |
| 3 | - | 13 |
| 4 | 2 | 13 |
| 5 | 2 | 13 |
| 6 | 2 | 13 |
| 7 | 2 | 13 |
| 8 | 2 | 13 |
| 9 | 2 | 13 |
| 10 | 2 | 13 |
| 11 | 2 | 13 |
| 12 | 2 | 13 |
| 13 | 3, 4-12 | 14, 15 |
| 14 | 13 | - |
| 15 | 13 | F1-F4 |

### Agent 调度摘要

- **Wave 1**：3 任务 — T1-T3→`quick`
- **Wave 2**：5 任务 — T4-T8→`quick`（东财 datacenter 端点）
- **Wave 3**：4 任务 — T9-T12→`quick`（东财 + 独立源端点）
- **Wave 4**：3 任务 — T13-T15→`quick`
- **Wave FINAL**：4 任务 — F1→`oracle`，F2→`unspecified-high`，F3→`unspecified-high`，F4→`deep`

---

## 待办事项

- [x] 1. 验证 mootdx 依赖安装与网络连通性

  **做什么**：
  - 在目标 Python 环境安装 mootdx：`pip install mootdx>=1.0.0`
  - 验证导入：`python -c "import mootdx; print(mootdx.__version__)"`
  - 验证 TCP 连接：用 mootdx 拉取 600519 的日线数据（`client.bars(symbol='600519', category=4, offset=1)`）
  - 在 `pyproject.toml` 的 `dependencies` 列表末尾添加 `"mootdx>=0.11.7"`（mootdx 无 1.0.0 版本，最新为 0.11.7）

  **禁止做**：
  - 不修改 pyproject.toml 中任何现有依赖的版本号
  - 不添加 mootdx 以外的任何新依赖

  **推荐 Agent 配置**：
  - **分类**：`quick`
    - 原因：单文件修改 + 单条命令验证，无需复杂推理
  - **技能**：[]
    - 无需特定技能

  **并行化**：
  - **可并行运行**：YES
  - **并行组**：Wave 1（与 Task 2、3 同时）
  - **阻塞**：无（不阻塞任何后续任务，但 Wave 2 端点实现隐含需要 mootdx）
  - **被阻塞于**：无（可立即开始）

  **参考**：
  - `pyproject.toml:11-38` — 现有依赖列表格式（按字母排序，`"name>=version"` 格式）
  - a-stock-data SKILL.md: "Prerequisites" 节 — `pip install mootdx requests pandas stockstats`

  **验收标准**：
  - [ ] `pip install mootdx>=0.11.7` 成功执行
  - [ ] `python -c "import mootdx; print(mootdx.__version__)"` 输出版本号，无 ImportError
  - [ ] `pyproject.toml` 中 `dependencies` 列表包含 `"mootdx>=1.0.0"`
  - [ ] `pyproject.toml` 中现有依赖版本号未被修改

  **QA 场景**：

  ```
  Scenario: mootdx 安装并成功连接通达信服务器
    Tool: Bash
    Preconditions: 有网络连接，pip 可用
    Steps:
      1. pip install mootdx>=1.0.0
      2. python -c "from mootdx.quotes import Quotes; c = Quotes.factory(market='std'); r = c.bars(symbol='600519', category=4, offset=1); print(type(r)); print('open' in r if hasattr(r, '__contains__') else str(r)[:100])"
    Expected Result: 打印 DataFrame 或包含 'open' 的字符串，无异常
    Failure Indicators: ImportError、ConnectionError、超时
    Evidence: .omo/evidence/task-1-mootdx-verify.txt

  Scenario: pyproject.toml 依赖格式正确
    Tool: Bash
    Steps:
      1. python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); deps = d['project']['dependencies']; assert any('mootdx' in dep for dep in deps), 'mootdx not found'; print('OK: mootdx in dependencies')"
    Expected Result: 打印 "OK: mootdx in dependencies"
    Evidence: .omo/evidence/task-1-pyproject-verify.txt
  ```

  **提交**：YES（独立提交）
  - Message: `chore(deps): add mootdx>=1.0.0 for a-stock-data integration`
  - Files: `pyproject.toml`
  - Pre-commit: `pip install -e .[dev]`

- [x] 2. 创建 a_stock_data.py 骨架

  **做什么**：
  - 新建 `tradingagents/dataflows/a_stock_data.py`
  - 文件头含：
    - 模块 docstring（说明数据源、上游版本 v3.1、仓库地址）
    - 上游版本标记：`# Upstream: simonlin1212/a-stock-data v3.1`
    - 端点→锚点映射表（9 个函数 → SKILL.md Section 号）
    - Lazy import guard for mootdx（`try: import mootdx ... except ImportError: mootdx = None`）
  - 内部 helper 函数：
    - `_eastmoney_datacenter(report_name, columns, filter_str, page_size, sort_columns, sort_types)` — 共用东财数据中心查询（参考 SKILL.md Layer 3.5 的 `eastmoney_datacenter` 函数）
    - `_format_result(data, title)` — 格式化输出为 Markdown 字符串，含 `# 数据来源: a-stock-data` + `# 请求时间`
    - `_ensure_mootdx()` — 抛出友好错误（如果未安装）
    - 全局常量：`UA`（User-Agent）、`DATACENTER_URL`、`PUSH2_URL`
  - 9 个占位函数（仅签名 + docstring + `raise NotImplementedError`），函数签名参考 guosen.py 模式：
    - `get_dragon_tiger_stock(code: str, trade_date: str, look_back: int = 30) -> str`
    - `get_dragon_tiger_market(trade_date: str = "", min_net_buy: float = 0) -> str`
    - `get_margin_trading(code: str, page_size: int = 30) -> str`
    - `get_block_trade(code: str, page_size: int = 20) -> str`
    - `get_lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> str`
    - `get_shareholder_count(code: str) -> str`
    - `get_dividend_history(code: str, page_size: int = 30) -> str`
    - `get_cls_flash(count: int = 20) -> str`
    - `get_cninfo_announcements(code: str, page_size: int = 20) -> str`

  **禁止做**：
  - 不实现任何端点的具体逻辑（仅占位符，实际代码在 Tasks 4-12）
  - 不添加 Phase 2/3 的端点（即使是空壳函数）
  - 不创建 `tests/smoke/` 目录

  **推荐 Agent 配置**：
  - **分类**：`quick`
    - 原因：纯样板代码创建，无需复杂逻辑，遵循 guosen.py 模式即可
  - **技能**：[]
    - 无需特定技能

  **并行化**：
  - **可并行运行**：YES
  - **并行组**：Wave 1（与 Task 1、3 同时）
  - **阻塞**：Tasks 4-12（端点实现依赖此骨架中的 Helper）
  - **被阻塞于**：无

  **参考**：
  - `tradingagents/dataflows/guosen.py:1-90` — 模块结构模式（docstring → imports → 常量 → session 工厂 → 内部 helper → 公开函数）
  - `tradingagents/dataflows/guosen.py:91-99` — `_get_session()` 单例模式
  - `tradingagents/dataflows/guosen.py:161-178` — `_format_json_result()` 格式化 helper
  - `tradingagents/dataflows/guosen.py:105-113` — `_ensure_gs_api_key()` 错误提示模式
  - a-stock-data SKILL.md: "东财数据中心统一查询" — `eastmoney_datacenter()` 完整实现
  - a-stock-data SKILL.md: "市场前缀规则" — `get_prefix()` 函数

  **验收标准**：
  - [ ] 文件 `tradingagents/dataflows/a_stock_data.py` 存在
  - [ ] `grep "Upstream: simonlin1212/a-stock-data v3.1" tradingagents/dataflows/a_stock_data.py` 匹配
  - [ ] `python -c "from tradingagents.dataflows.a_stock_data import *"` 成功导入（即使 mootdx 未安装也不崩溃）
  - [ ] 9 个占位函数均可调用但抛 `NotImplementedError`

  **QA 场景**：

  ```
  Scenario: 模块在 mootdx 未安装时可导入
    Tool: Bash
    Preconditions: mootdx 可选未安装
    Steps:
      1. python -c "from tradingagents.dataflows import a_stock_data; print(dir(a_stock_data))"
    Expected Result: 打印模块属性列表，包含 _eastmoney_datacenter, _format_result, _ensure_mootdx, UA, DATACENTER_URL, 以及 9 个公开函数名；无 ImportError
    Evidence: .omo/evidence/task-2-lazy-import.txt

  Scenario: 占位函数抛出 NotImplementedError
    Tool: Bash
    Steps:
      1. python -c "from tradingagents.dataflows.a_stock_data import get_dragon_tiger_stock; get_dragon_tiger_stock('600519')"
    Expected Result: 抛出 NotImplementedError（预期行为，因为 Task 2 仅为骨架）
    Evidence: .omo/evidence/task-2-placeholder.txt
  ```

  **提交**：YES（独立提交）
  - Message: `feat(dataflows): add a_stock_data.py skeleton with 9 endpoint stubs`
  - Files: `tradingagents/dataflows/a_stock_data.py`
  - Pre-commit: 无

- [x] 3. 注册 vendor 配置并更新依赖文件

  **做什么**：
  - 在 `tradingagents/default_config.py` 的 `data_vendors` 字典中新增：
    ```python
    "specialty_data": "a_stock_data",  # 龙虎榜/融资融券/大宗交易/解禁/股东户数/分红/快讯/公告
    ```
  - 在 `tradingagents/dataflows/interface.py` 中：
    - 新增 `TOOLS_CATEGORIES["specialty_data"]` 条目（`description` + 9 个方法名列表）
    - 新增 `VENDOR_METHODS` 条目：9 个方法名各映射到 `{"a_stock_data": fn}`（先用占位 lambda 或导入占位函数）
    - 新增 import 语句：`from .a_stock_data import (get_dragon_tiger_stock, ...)`
  - 确认 `pyproject.toml` 已有 Task 1 添加的 mootdx 依赖

  **禁止做**：
  - 不修改 `TOOLS_CATEGORIES` 现有 6 个分类
  - 不修改 `data_vendors` 现有 6 个 vendor 默认值
  - 不修改 `route_to_vendor()` 核心逻辑
  - 不在 VENDOR_METHODS 中将 a_stock_data 函数注册到 akshare/yfinance/alpha_vantage 条目

  **推荐 Agent 配置**：
  - **分类**：`quick`
    - 原因：纯配置注册，参考现有 guosen 模式，无需复杂逻辑
  - **技能**：[]
    - 无需特定技能

  **并行化**：
  - **可并行运行**：YES
  - **并行组**：Wave 1（与 Task 1、2 同时）
  - **阻塞**：Task 13（但 Task 13 会更新 import，故本 Task 仅做最小注册）
  - **被阻塞于**：无

  **参考**：
  - `tradingagents/default_config.py:47-55` — `data_vendors` 字典格式
  - `tradingagents/dataflows/interface.py:220-245` — guosen 独有能力在 `VENDOR_METHODS` 的注册模式
  - `tradingagents/dataflows/interface.py:153-158` — `VENDOR_LIST` 格式
  - `tradingagents/dataflows/interface.py:37-51` — guosen import 语句和 adapter wrapper 模式
  - `tradingagents/agents/utils/guosen_tools.py` — Tool 包装器注册模式

  **验收标准**：
  - [ ] `python -c "from tradingagents.default_config import DEFAULT_CONFIG; assert DEFAULT_CONFIG['data_vendors']['specialty_data'] == 'a_stock_data'"` 通过
  - [ ] `python -c "from tradingagents.dataflows.interface import TOOLS_CATEGORIES; assert 'specialty_data' in TOOLS_CATEGORIES; assert len(TOOLS_CATEGORIES['specialty_data']['tools']) == 9"` 通过
  - [ ] 现有分类未被修改：`assert TOOLS_CATEGORIES['core_stock_apis']['tools']` 仍存在
  - [ ] `route_to_vendor()` 函数体未被修改

  **QA 场景**：

  ```
  Scenario: 新 vendor 配置可正确读取
    Tool: Bash
    Steps:
      1. python -c "
  from tradingagents.default_config import DEFAULT_CONFIG
  assert DEFAULT_CONFIG['data_vendors']['specialty_data'] == 'a_stock_data', 'vendor not configured'
  from tradingagents.dataflows.interface import TOOLS_CATEGORIES, VENDOR_METHODS
  cat = TOOLS_CATEGORIES['specialty_data']
  assert len(cat['tools']) == 9, f'expected 9 tools, got {len(cat[\"tools\"])}'
  print(f'specialty_data category: {cat[\"description\"]}')
  print(f'tools: {cat[\"tools\"]}')
  "
    Expected Result: 打印分类描述和 9 个工具名列表
    Evidence: .omo/evidence/task-3-vendor-config.txt

  Scenario: 现有配置未被破坏
    Tool: Bash
    Steps:
      1. python -c "
  from tradingagents.default_config import DEFAULT_CONFIG
  orig = ['core_stock_apis','technical_indicators','fundamental_data','news_data','macro_economic','stock_screening']
  for k in orig:
      assert k in DEFAULT_CONFIG['data_vendors'], f'{k} missing from data_vendors'
  print('All 6 original categories intact')
  "
    Expected Result: 打印 "All 6 original categories intact"
    Evidence: .omo/evidence/task-3-config-intact.txt
  ```

  **提交**：YES（独立提交）
  - Message: `feat(dataflows): register a_stock_data vendor in config and interface`
  - Files: `tradingagents/default_config.py`, `tradingagents/dataflows/interface.py`
  - Pre-commit: `python -c "from tradingagents.dataflows.interface import *"`

---

- [x] 4. 实现龙虎榜个股端点
- [x] 5. 实现全市场龙虎榜端点
- [x] 6. 实现融资融券明细端点
- [x] 7. 实现大宗交易端点
- [x] 8. 实现限售解禁端点
- [x] 9. 实现股东户数变化端点
- [x] 10. 实现分红送转端点
- [x] 11. 实现财联社快讯端点
- [x] 12. 实现巨潮公告端点

  **做什么**：
  - 在 `a_stock_data.py` 中实现 `get_cninfo_announcements(code, page_size=20) -> str`
  - 逻辑（参考 SKILL.md Layer 7.1）：
    1. 构造 `stock` 参数格式：`{code},{orgId}`（如 `600519,gssh0600519`）
    2. 直连 HTTP：`POST http://www.cninfo.com.cn/new/hisAnnouncement/query`
    3. 携带 `User-Agent`、`Referer: http://www.cninfo.com.cn/`、`X-Requested-With: XMLHttpRequest`
    4. 请求体：`pageNum=1&pageSize={page_size}&column=szse&tabName=fulltext&stock={code},{orgId}`
    5. 解析返回的 `announcements` 列表
    6. 提取：announcementTitle、announcementTime、secName、 adjunctUrl（PDF 链接）
    7. 用 `_format_result()` 格式化为 Markdown 公告列表
  - 错误处理：try/except → return `f"巨潮公告查询失败 ({code}): {str(e)}"`

  **禁止做**：
  - 不调用 `_eastmoney_datacenter`（巨潮是独立数据源）
  - 不硬编码 orgId（需要动态推导规则：`gssh` + 6 位代码 或 `gssz` + 代码）

  **推荐 Agent 配置**：`quick`

  **并行化**：YES — Wave 3，依赖 Task 2

  **参考**：
  - a-stock-data SKILL.md: "### Layer 7: 公告层 → 巨潮 cninfo"
  - `tradingagents/dataflows/guosen.py:130-151` — `_make_request` 作为 POST 请求参考

  **验收标准**：
  - [ ] 600519 验证：返回茅台近期公告列表
  - [ ] 每条含标题、时间、PDF 链接
  - [ ] 出错时返回错误字符串

  **QA 场景**：

  ```
  Scenario: 巨潮公告检索
    Tool: Bash
    Steps:
      1. python -c "from tradingagents.dataflows.a_stock_data import get_cninfo_announcements; print(get_cninfo_announcements('600519', 5)[:500])"
    Expected Result: 打印茅台近期公告，含标题和时间，无异常
    Evidence: .omo/evidence/task-12-cninfo-announcements.txt

  Scenario: 公告 PDF 链接可访问
    Tool: Bash
    Steps:
      1. python -c "from tradingagents.dataflows.a_stock_data import get_cninfo_announcements; r = get_cninfo_announcements('600519', 1); print('adjunctUrl' in r or 'pdf' in r.lower())"
    Expected Result: 打印 True（输出含 PDF 链接相关内容）
    Evidence: .omo/evidence/task-12-cninfo-pdf-link.txt
  ```

  **提交**：NO（与 Task 4-12 组提交）

---

- [x] 13. 在 interface.py 完成最终注册

  **做什么**：
  - 在 `tradingagents/dataflows/interface.py` 中：
    - 更新 import：从 `a_stock_data` 导入全部 9 个端点函数（替换 Task 3 中的占位 lambda）
    - 为需要签适配的端点创建 adapter wrapper（如日期格式转换），参考 `interface.py:58-74` guosen adapter 模式
    - 确认 `VENDOR_METHODS` 中 9 个条目已正确指向实际函数
    - 确认 `TOOLS_CATEGORIES["specialty_data"]` 中工具名与实际函数名一致
  - 验证：`python -c "from tradingagents.dataflows.interface import VENDOR_METHODS, TOOLS_CATEGORIES; ..."` 全量检查

  **禁止做**：
  - 不修改 `route_to_vendor()` 函数体
  - 不删除或修改任何现有 VENDOR_METHODS 条目
  - 不修改现有 categories 的 tools 列表

  **推荐 Agent 配置**：
  - **分类**：`quick`
    - 原因：纯 import 和注册更新，无新逻辑
  - **技能**：[]
    - 无需特定技能

  **并行化**：
  - **可并行运行**：NO（依赖 Tasks 4-12 全部完成）
  - **并行组**：Wave 4（与 Task 14、15 并行——但 14/15 逻辑上依赖 13 的结果，建议串行）
  - **阻塞**：Task 14、15
  - **被阻塞于**：Tasks 3、4-12

  **参考**：
  - `tradingagents/dataflows/interface.py:37-51` — import 语句格式
  - `tradingagents/dataflows/interface.py:60-74` — adapter wrapper 模式（`_guosen_stock_data` 等）
  - `tradingagents/dataflows/interface.py:220-290` — `VENDOR_METHODS` 字典结构

  **验收标准**：
  - [ ] `python -c "from tradingagents.dataflows.interface import VENDOR_METHODS; methods = ['get_dragon_tiger_stock','get_dragon_tiger_market','get_margin_trading','get_block_trade','get_lockup_expiry','get_shareholder_count','get_dividend_history','get_cls_flash','get_cninfo_announcements']; [assert 'a_stock_data' in VENDOR_METHODS[m], f'{m} missing' for m in methods]; print('OK: all 9 endpoints registered')"` 通过
  - [ ] `python -c "from tradingagents.dataflows.interface import route_to_vendor; r = route_to_vendor('get_margin_trading', code='600519'); assert isinstance(r, str); print(r[:200])"` 通过
  - [ ] 现有 vendor 未受影响：`route_to_vendor('get_stock_data', symbol='600519', start_date='...', end_date='...')` 仍走 akshare

  **QA 场景**：

  ```
  Scenario: 通过 route_to_vendor 调用新端点
    Tool: Bash
    Steps:
      1. python -c "
  from tradingagents.dataflows.interface import route_to_vendor
  r = route_to_vendor('get_margin_trading', code='600519', page_size=3)
  assert isinstance(r, str), 'must return str'
  assert len(r) > 0, 'must return non-empty string'
  assert '融资' in r, 'must contain margin data'
  print(r[:400])
  "
    Expected Result: 通过路由系统成功调用新端点，返回融资融券数据
    Evidence: .omo/evidence/task-13-route-to-vendor.txt

  Scenario: 现有 vendor 路由未被破坏
    Tool: Bash
    Steps:
      1. python -c "
  from tradingagents.dataflows.interface import route_to_vendor
  r = route_to_vendor('get_stock_data', symbol='600519', start_date='2026-05-01', end_date='2026-05-20')
  assert isinstance(r, str)
  print('OK: existing route intact')
  "
    Expected Result: 打印 "OK: existing route intact"
    Evidence: .omo/evidence/task-13-existing-route.txt
  ```

  **提交**：YES（与 Task 14、15 组成一个提交）
  - Message: `feat(dataflows): finalize a_stock_data vendor registration and tools`
  - Files: `tradingagents/dataflows/interface.py`, `tradingagents/agents/utils/a_stock_data_tools.py`, `tests/test_a_stock_data.py`

- [x] 14. 创建 LangChain Tool 包装器

  **做什么**：
  - 新建 `tradingagents/agents/utils/a_stock_data_tools.py`
  - 为 9 个端点各创建 1 个 LangChain Tool 包装器
  - 模式参考 `guosen_tools.py`：每个 Tool = `@tool` 装饰器 + 函数体调用 `route_to_vendor()`
  - 工具名使用 snake_case（如在 `guosen_tools.py` 中 `get_macro_data`）
  - 每个 Tool 的 `description` 使用中文说明工具用途和适用场景

  **禁止做**：
  - 不直接在 Tool 中调用数据函数（必须通过 `route_to_vendor()` 以享受 vendor 回退和多供应商支持）
  - 不修改任何现有 tools 文件
  - 不注册到 Agent 的 tool 列表（那是 Phase 2 的事）

  **推荐 Agent 配置**：
  - **分类**：`quick`

  **并行化**：依赖 Task 13

  **参考**：
  - `tradingagents/agents/utils/guosen_tools.py` — 完整 Tool 包装器模式（78 行，8 个 tools）
  - `tradingagents/agents/utils/core_stock_tools.py` — `@tool` + `Annotated` 参数模式

  **验收标准**：
  - [ ] `python -c "from tradingagents.agents.utils.a_stock_data_tools import *; print(len([x for x in dir() if not x.startswith('_')]));"` — 输出 9（共有 9 个 tool 函数）
  - [ ] 每个 tool 函数有 `@tool` 装饰器和中文 description
  - [ ] `get_margin_trading('600519')` 返回 str（非异常）

  **QA 场景**：

  ```
  Scenario: 所有 9 个 Tool 可调用
    Tool: Bash
    Steps:
      1. python -c "
  from tradingagents.agents.utils.a_stock_data_tools import (
      get_dragon_tiger_stock, get_dragon_tiger_market, get_margin_trading,
      get_block_trade, get_lockup_expiry, get_shareholder_count,
      get_dividend_history, get_cls_flash, get_cninfo_announcements,
  )
  r = get_margin_trading('600519', 3)
  print(type(r).__name__, len(r))
  print(r[:300])
  "
    Expected Result: 打印 "str" 和长度，以及融资融券数据片段
    Evidence: .omo/evidence/task-14-tool-wrappers.txt
  ```

  **提交**：NO（与 Task 13、15 组提交）

- [x] 15. 编写冒烟测试

  **做什么**：
  - 新建 `tests/test_a_stock_data.py`
  - 使用 `@pytest.mark.smoke` 标记所有测试
  - 每个端点 1-2 个测试用例：
    - 正例：用 600519 调用，验证返回 str 且含关键字段
    - 负例：用无效代码调用，验证返回错误 str 而非异常
  - 测试结构（参考现有 `tests/test_*.py`）：
    ```python
    import pytest
    from tradingagents.dataflows.a_stock_data import (
        get_dragon_tiger_stock, get_margin_trading, ...
    )

    @pytest.mark.smoke
    def test_margin_trading_moutai():
        r = get_margin_trading("600519", 5)
        assert isinstance(r, str)
        assert "融资" in r

    @pytest.mark.smoke
    def test_margin_trading_invalid_code():
        r = get_margin_trading("000000")
        assert isinstance(r, str)
        assert any(kw in r for kw in ["失败", "错误", "Error"])
    ```
  - 添加 `# 数据来源: a-stock-data` 标记验证

  **禁止做**：
  - 不创建 `tests/smoke/` 子目录
  - 不对所有 28 端点写测试（只测 Phase 1 的 9 个）
  - 不引入 `responses`/`vcrpy` 等新测试依赖

  **推荐 Agent 配置**：
  - **分类**：`quick`

  **并行化**：依赖 Task 13

  **参考**：
  - `pyproject.toml:59-61` — `smoke` marker 定义
  - `tests/` 中现有测试文件 — pytest 约定（扁平结构，函数前缀 `test_`）

  **验收标准**：
  - [ ] `pytest tests/test_a_stock_data.py -v -m smoke --tb=short` — 所有 smoke 标记用例 PASSED
  - [ ] `pytest tests/ --ignore=tests/test_a_stock_data.py -x -q` — 现有全部测试仍然通过
  - [ ] 9 个端点至少各有 1 个正例 + 1 个负例（共 ≥18 测试用例）

  **QA 场景**：

  ```
  Scenario: 全量冒烟测试通过
    Tool: Bash
    Steps:
      1. pytest tests/test_a_stock_data.py -v -m smoke --tb=short 2>&1
    Expected Result: 所有用例 PASSED，0 FAILED，0 ERROR
    Evidence: .omo/evidence/task-15-smoke-test.txt

  Scenario: 现有测试未被破坏
    Tool: Bash
    Steps:
      1. pytest tests/ --ignore=tests/test_a_stock_data.py -x -q 2>&1
    Expected Result: 现有测试全部通过
    Evidence: .omo/evidence/task-15-existing-tests.txt
  ```

  **提交**：NO（与 Task 13、14 组提交）

---

## 最终验证波次（全部实现任务完成后 — 4 并行审查）

> 4 个审查 agent 并行运行。全部必须 APPROVE。展示综合结果给用户，获取明确 "okay" 后再标记完成。
> **禁止自动通过。** 用户拒绝或反馈 → 修复 → 重新运行 → 再次展示 → 等待 okay。

- [x] F1. **计划合规审计** — `oracle`
  从头到尾阅读本计划。对每条"必须实现"：验证实现存在（读取文件、运行命令验证端点可调用）。对每条"必须避免"：搜索代码库查找禁用模式——如发现则以 `文件:行号` 形式报告。检查 `.omo/evidence/` 中证据文件是否存在。对比交付物与计划。
  输出：`必须实现 [N/N] | 必须避免 [N/N] | 任务 [N/N] | 裁决: APPROVE/REJECT`

- [x] F2. **代码质量审查** — `unspecified-high`
- [x] F3. **实际手动 QA** — `unspecified-high`
- [x] F4. **范围保真度检查** — `deep`
  对每个任务：阅读"做什么"、阅读实际 diff（git log/diff）。验证 1:1——所有 spec 内容已构建（无缺失）、超出 spec 的内容未被构建（无蔓延）。检查"禁止做"合规性。检测跨任务污染：Task N 触碰了 Task M 的文件。标记未记录的变更。
  特别注意：确认 akshare.py、guosen.py、y_finance.py、alpha_vantage*.py 未被任何任务触碰。
  输出：`任务 [N/N 合规] | 污染 [干净/N 问题] | 未记录变更 [干净/N 文件] | 裁决`

---

## 提交策略

| 批次 | 提交信息 | 文件 | 验证 |
|------|---------|------|------|
| 1 | `chore(deps): add mootdx>=1.0.0 for a-stock-data integration` | `pyproject.toml` | `pip install -e .[dev]` |
| 2 | `feat(dataflows): add a_stock_data.py skeleton with 9 endpoint stubs` | `tradingagents/dataflows/a_stock_data.py` | `python -c "from tradingagents.dataflows.a_stock_data import *"` |
| 3 | `feat(dataflows): register a_stock_data vendor in config and interface` | `tradingagents/default_config.py`, `tradingagents/dataflows/interface.py` | `python -c "from tradingagents.dataflows.interface import *"` |
| 4 | `feat(dataflows): implement 9 specialty endpoints from a-stock-data V3.1` | `tradingagents/dataflows/a_stock_data.py` | 每个端点用 600519 调用验证 |
| 5 | `feat(dataflows): finalize a_stock_data vendor, tools, and smoke tests` | `tradingagents/dataflows/interface.py`, `tradingagents/agents/utils/a_stock_data_tools.py`, `tests/test_a_stock_data.py` | `pytest tests/test_a_stock_data.py -m smoke` |

---

## 成功标准

### 验证命令

```bash
# 1. 冒烟测试全部通过
pytest tests/test_a_stock_data.py -v -m smoke --tb=short
# 预期: N passed, 0 failed

# 2. 现有测试未被破坏
pytest tests/ --ignore=tests/test_a_stock_data.py -x -q
# 预期: all passed

# 3. 上游版本标签存在
grep "Upstream: simonlin1212/a-stock-data v3.1" tradingagents/dataflows/a_stock_data.py
# 预期: 匹配行输出

# 4. 9 端点全部可导入
python -c "from tradingagents.dataflows.a_stock_data import (
    get_dragon_tiger_stock, get_dragon_tiger_market, get_margin_trading,
    get_block_trade, get_lockup_expiry, get_shareholder_count,
    get_dividend_history, get_cls_flash, get_cninfo_announcements,
); print('OK: all 9 imports successful')"

# 5. 9 Tool 全部可导入
python -c "from tradingagents.agents.utils.a_stock_data_tools import *; print('OK: all tools imported')"

# 6. 路由系统可调用新端点
python -c "
from tradingagents.dataflows.interface import route_to_vendor
r = route_to_vendor('get_margin_trading', code='600519', page_size=3)
assert isinstance(r, str) and len(r) > 0
print('OK: route_to_vendor works')
"

# 7. 护栏验证 — 确认现有文件未被触碰
git diff --name-only HEAD | grep -v 'a_stock_data\|test_a_stock_data\|pyproject.toml\|default_config.py\|interface.py'
# 预期: 空输出（仅上述 5 个预期文件有变更）
```

### 最终检查清单

- [ ] 所有"必须实现"项已实现
- [ ] 所有"必须避免"项未被违反
- [ ] `tests/test_a_stock_data.py` 全部 smoke 用例 PASS
- [ ] 现有测试全部 PASS
- [ ] `a_stock_data.py` 含上游版本标记和锚点映射表
- [ ] akshare.py、guosen.py、y_finance.py、alpha_vantage*.py 零改动
- [ ] `route_to_vendor()` 函数体零改动
- [ ] 仅新增 `mootdx` 依赖
- [ ] 未引入除 `mootdx` 外的任何新依赖
