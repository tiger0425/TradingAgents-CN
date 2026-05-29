# 持仓成本价与操作指导功能

## 摘要

> **快速总结**：在 TradingAgents-CN 多智能体分析框架中新增持仓成本价和数量的输入能力，系统自动计算浮动盈亏，并将盈亏状态注入 Trader 和 Portfolio Manager 的决策 prompt 中，实现盈亏分析、止盈止损建议、加仓减仓指导和风险调整四合一的操作指导。持仓数据跨运行持久化，并支持模拟自动更新。
>
> **交付物**：
> - `AgentState` 新增 `cost_price`、`quantity`、`position_pnl`、`position_opened_date` 字段
> - 独立持仓状态持久化文件 `~/.tradingagents/memory/position_state.json`
> - CLI 新增成本价/数量输入步骤（可跳过）
> - Python API `propagate()` 支持持仓参数（向后兼容）
> - Trader + Portfolio Manager prompt 注入格式化持仓上下文
> - 持仓盈亏计算工具函数 `position_utils.py`
> - 模拟持仓自动更新逻辑
> - 完整的 pytest 单元测试覆盖
>
> **预估工作量**：中等
> **并行执行**：是 — 3 个波次
> **关键路径**：数据层定义 → 持久化存储 → Prompt 注入 → CLI 交互

---

## 背景

### 原始需求
用户当前项目只对股票进行深度分析（多智能体框架：分析师→研究员→交易员→风控→组合经理），希望新增功能：如果提供了股票成本价和数量，系统能结合持仓盈亏给出个性化的操作指导。

### 访谈总结

**关键讨论与决策**：
- **操作指导范围**：全部四项——盈亏分析、止盈止损建议、加仓/减仓指导、风险立场调整
- **输入路径**：CLI 交互输入 + Python API 参数，两者都要
- **持久化策略**：跨运行持久化 — 独立存储 `position_state.json`，下次分析自动加载
- **Prompt 注入范围**：仅决策层（Trader + Portfolio Manager），分析师层保持客观独立
- **模拟自动更新**：基于系统建议 + 分析日收盘价自动更新模拟持仓
- **测试策略**：TDD（pytest），先写测试再写实现

**技术选型**：
- V1 使用加权平均成本，分批建仓的复杂场景留待后续版本
- 数量单位为"股"，接受任意正整数（不强制 100 的倍数）
- 模拟成交价使用分析日收盘价
- 持仓状态独立存储于 `~/.tradingagents/memory/position_state.json`，与事件流记忆日志分离

### 研究发现的现有基础设施

| 文件 | 现状 | 可复用内容 |
|------|------|-----------|
| `agent_states.py` | `AgentState` 已有 `position_opened_date` | 直接复用，仅需新增 cost_price/quantity |
| `schemas.py` | `TraderProposal` 有 entry_price/stop_loss/position_sizing | 自动更新逻辑可读取这些字段 |
| `propagation.py` | `create_initial_state()` 接受 company_name/trade_date | 扩展参数，保持向后兼容 |
| `memory.py` | `TradingMemoryLog` 管理决策日志 | 参考其原子写入模式，新建独立持久化模块 |
| `a_share_constraints.py` | T+1 约束 + 涨跌停约束 | 自动更新前校验 T+1 和涨跌停 |
| `cli/main.py` | `get_user_selections()` 8 步输入流程 | 参照现有 step 模式新增步骤 |
| `tests/` | pytest + markers (unit/integration/smoke) | 遵循现有测试风格 |

### Metis 审查

**已处理的缺口**：
- **成本价语义**：V1 使用加权平均成本价（用户输入即视为当前平均成本）
- **数量单位**：统一使用"股"（不是"手"）
- **模拟成交价**：使用分析日收盘价（通过 akshare `stock_zh_a_daily` 获取）
- **幂等性**：同一 ticker + 同一天重复运行时，自动跳过持仓更新（已检查日期）
- **持仓独立存储**：新建 `position_state.json`，不污染记忆日志 tag 格式
- **向后兼容**：所有新字段带默认值，无持仓参数时行为不变
- **输入校验**：CLI 层校验 cost_price>0、quantity>=0、opened_date<=trade_date

---

## 目标

### 核心目标
在 TradingAgents-CN 的 A 股分析流程中新增持仓成本价和数量输入，使系统能基于用户实际持仓生成个性化操作指导（盈亏分析、止盈止损、加仓减仓、风险调整）。

### 具体交付物
- `tradingagents/dataflows/position_utils.py` — 持仓盈亏计算工具
- `tradingagents/agents/utils/position_state.py` — 持仓状态持久化管理
- `tradingagents/agents/utils/agent_states.py` — 新增持仓字段
- `tradingagents/agents/schemas.py` — 可能扩展 schema（如有需要）
- `tradingagents/graph/propagation.py` — 初始状态注入持仓数据
- `tradingagents/graph/trading_graph.py` — propagate() 增加持仓参数 + 自动更新逻辑
- `tradingagents/agents/trader/trader.py` — prompt 注入持仓上下文
- `tradingagents/agents/managers/portfolio_manager.py` — prompt 注入持仓上下文
- `cli/main.py` — CLI 新增持仓输入步骤
- `tests/test_position_tracking.py` — 完整测试用例

### 完成定义
- [ ] CLI 输入 `600519 2026-05-06 cost=1580 qty=100` → 报告中包含盈亏分析
- [ ] CLI 跳过持仓输入 → 输出与当前版本完全一致
- [ ] Python API `propagate("600519", "2026-05-06", cost_price=1580, quantity=100)` → 正常工作
- [ ] Python API `propagate("600519", "2026-05-06")` → 向后兼容，正常工作
- [ ] 第二次运行自动加载上次持仓
- [ ] 所有新增代码通过 pytest

### 必须包含
- AgentState 新增字段带默认值（向后兼容）
- 持仓状态独立持久化（`position_state.json`）
- Prompt 仅注入给 Trader 和 Portfolio Manager，不注入分析师层
- 无持仓时系统完全降级为当前行为
- T+1 约束与持仓自动更新正确交互
- 涨跌停约束下的模拟成交检查

### 必须排除（护栏）
- **严禁修改分析师层 prompt**（Market/Social/News/Fundamentals Analyst）
- **严禁修改记忆日志 tag 格式或解析器**
- **严禁持仓盈亏覆盖/替代基本面评级**
- **不涉及多股票组合管理**
- **不涉及真实券商 API 对接**
- **不涉及盈亏曲线/图表可视化**
- **不涉及美股持仓支持**（market_type != "A_SHARE" 时持仓功能静默降级）
- **不涉及历史持仓回测**

---

## 验证策略

> **零人工干预** — 所有验证由 Agent 执行，无需用户手动操作。

### 测试决策
- **测试基础设施**：已存在 — pytest + markers (unit/integration/smoke)
- **自动测试**：TDD — 每个任务遵循 RED（失败测试）→ GREEN（最小实现）→ REFACTOR
- **测试框架**：pytest
- **测试文件**：`tests/test_position_tracking.py`（新建）

### QA 策略
每个任务都包含 Agent 可执行的 QA 场景。证据保存到 `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`。

- **后端/API**：使用 Bash（curl/pytest）— 运行测试，断言输出和返回值
- **CLI/TUI**：使用 interactive_bash（tmux）— 模拟用户输入，验证输出
- **库/模块**：使用 Bash（pytest）— 导入模块，调用函数，比较输出

---

## 执行策略

### 并行执行波次

> 按依赖关系将独立任务分组，最大化并行吞吐量。
> 目标：每波至少 3 个任务。

```
第 1 波（立即启动 — 基础数据层）：
├── 任务 1：持仓盈亏计算工具 [quick]
├── 任务 2：持仓状态持久化模块 [quick]
├── 任务 3：AgentState 新增持仓字段 [quick]
└── 任务 4：持仓上下文格式化工具 [quick]

第 2 波（第 1 波完成后 — 注入层 + 核心逻辑，最大并行）：
├── 任务 5：Propagator 初始状态注入持仓 [quick]
├── 任务 6：Trader prompt 持仓注入 [deep]
├── 任务 7：Portfolio Manager prompt 持仓注入 [deep]
├── 任务 8：TradingGraph propagate() 扩展 + 自动更新 [deep]
└── 任务 9：CLI 持仓输入步骤 [quick]

第 3 波（第 2 波完成后 — 集成 + 测试 + 文档）：
├── 任务 10：A 股约束与持仓联动 [deep]
├── 任务 11：端到端集成测试 [deep]
└── 任务 12：回归安全验证 [quick]

最终验证波次（全部任务完成后 — 4 个并行审查）：
├── 任务 F1：计划合规审计 (oracle)
├── 任务 F2：代码质量审查 (unspecified-high)
├── 任务 F3：手动 QA 执行 (unspecified-high)
└── 任务 F4：范围忠实度检查 (deep)

关键路径：任务 1/3 → 任务 5 → 任务 7 → 任务 8 → 任务 11 → F1-F4
并行加速：约 60% 比完全串行更快
最大并发：4（第 1 波和第 2 波）
```

### 依赖矩阵

- **1-4**: - - 5-12, 无依赖
- **5**: 3, 4 - 6, 7, 8, 1
- **6**: 4, 5 - 11, 1
- **7**: 4, 5 - 11, 1
- **8**: 2, 4, 5, 6, 7 - 11, 3
- **9**: 5 - 11, 1
- **10**: 8 - 11, 1
- **11**: 6, 7, 8, 9, 10 - F1-F4, 5
- **12**: 11 - F1-F4, 1

### Agent 派遣摘要

- **第 1 波**: 4 — T1-T4 → `quick`
- **第 2 波**: 5 — T5 → `quick`, T6 → `deep`, T7 → `deep`, T8 → `deep`, T9 → `quick`
- **第 3 波**: 3 — T10 → `deep`, T11 → `deep`, T12 → `quick`
- **最终**: 4 — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## 待办事项

> 实现 + 测试 = 一个任务。不可分离。
> 每个任务**必须**包含：推荐 Agent 配置 + 并行信息 + QA 场景。
> **缺少 QA 场景的任务是不完整的。绝对不可以缺少。**

- [x] 1. 持仓盈亏计算工具 `position_utils.py`

  **做什么**：
  - 新建 `tradingagents/dataflows/position_utils.py`
  - 实现 `calc_position_pnl(current_price: float, cost_price: float, quantity: int) -> dict`：
    - 返回 `{"pnl_amount": float, "pnl_pct": float, "cost_price": float, "current_price": float, "quantity": int}`
    - 当 `cost_price == 0` 时 `pnl_pct` 返回 `None`（零成本持仓，不适用百分比）
  - 实现 `calc_avg_cost_after_add(old_cost: float, old_qty: int, add_price: float, add_qty: int) -> float`：
    - 加权平均成本计算：`(old_cost * old_qty + add_price * add_qty) / (old_qty + add_qty)`
  - 实现 `calc_realized_pnl(sell_price: float, cost_price: float, sell_qty: int) -> dict`：
    - 卖出盈亏计算
  - 实现 `format_position_context(current_price, cost_price, quantity, market_type="A_SHARE") -> str`：
    - 返回格式化的持仓上下文字符串，用于注入 agent prompt
    - 无持仓时返回空字符串

  **禁止做**：
  - 不依赖任何外部 API（纯计算函数）
  - 不在函数中处理数据获取（只接收参数计算）
  - 不修改任何现有文件

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：纯计算工具函数，逻辑简单清晰，无复杂依赖
  - **技能**：`[]`
  - **评估但未选用的技能**：
    - 无：这是纯 Python 数学运算，不需要特殊技能

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 1 波（与任务 2、3、4 并行）
  - **阻塞**：任务 4、5、6、7、8
  - **被阻塞于**：无（可立即开始）

  **参考**：

  **模式参考**（遵循的现有代码）：
  - `tradingagents/dataflows/a_share_constraints.py:7-33` — 计算函数风格：接受参数、返回计算结果、纯函数无副作用

  **测试参考**（测试模式）：
  - `tests/test_signal_processing.py` — pytest 单元测试风格：参数化测试、明确的输入/期望输出

  **引用说明**：
  - `a_share_constraints.py` 展示了项目中"计算工具函数"的标准写法：独立函数、明确的输入输出类型、不依赖外部状态

  **验收标准**：

  **TDD 流程（先写测试再写实现）**：
  - [ ] 测试文件已创建：`tests/test_position_tracking.py`
  - [ ] `pytest tests/test_position_tracking.py::TestPositionCalc -v` → PASS（至少 6 个测试）

  **QA 场景**：

  ```
  场景：正常持仓盈亏计算（浮盈）
    工具：Bash（pytest）
    前提条件：测试文件 tests/test_position_tracking.py 存在
    步骤：
      1. 运行：python -c "from tradingagents.dataflows.position_utils import calc_position_pnl; r = calc_position_pnl(1650.0, 1580.0, 100); print(r)"
      2. 断言输出包含 pnl_amount: 7000.0（(1650-1580)*100）
      3. 断言输出包含 pnl_pct: 约 0.0443（7000/158000）
    预期结果：正确计算浮动盈亏金额和百分比
    证据：.sisyphus/evidence/task-1-pnl-profit.txt

  场景：零成本持仓（cost_price=0）
    工具：Bash（pytest）
    步骤：
      1. 运行：python -c "from tradingagents.dataflows.position_utils import calc_position_pnl; r = calc_position_pnl(100.0, 0.0, 100); print(r)"
      2. 断言 pnl_pct 为 None
      3. 断言 pnl_amount 为 10000.0
    预期结果：零成本持仓不计算百分比
    证据：.sisyphus/evidence/task-1-pnl-zero-cost.txt

  场景：加仓后平均成本计算
    工具：Bash（pytest）
    步骤：
      1. 运行：python -c "from tradingagents.dataflows.position_utils import calc_avg_cost_after_add; r = calc_avg_cost_after_add(50.0, 100, 55.0, 100); print(r)"
      2. 断言结果为 52.5（(50*100 + 55*100) / 200）
    预期结果：正确计算加权平均成本
    证据：.sisyphus/evidence/task-1-avg-cost.txt
  ```

  **证据捕获**：
  - [ ] 每个证据文件命名为：task-1-{scenario-slug}.txt
  - [ ] API 调用的响应体文本

  **提交**：是（与任务 2、3、4 同组）
  - 消息：`feat(position): add P&L calculation utilities for position tracking`
  - 文件：`tradingagents/dataflows/position_utils.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPositionCalc -v`

- [x] 2. 持仓状态持久化模块 `position_state.py`

  **做什么**：
  - 新建 `tradingagents/agents/utils/position_state.py`
  - 实现 `PositionStateManager` 类：
    - `__init__(config: dict)` — 从配置读取存储路径（默认 `~/.tradingagents/memory/position_state.json`）
    - `load(ticker: str) -> dict` — 加载指定 ticker 的持仓状态，返回 `{"cost_price": float, "quantity": int, "opened_date": str, "updated_at": str}` 或 `None`
    - `save(ticker: str, cost_price: float, quantity: int, opened_date: str) -> None` — 原子写入（tmp 文件 + os.replace）
    - `reset(ticker: str) -> None` — 清除指定 ticker 的持仓（用户手动重置）
    - 内部使用 JSON 格式：`{"600519": {"cost_price": 1580.0, "quantity": 100, "opened_date": "2026-01-15", "updated_at": "2026-05-06T10:00:00"}}`
  - 数据格式：每个 ticker 一个顶层 key，支持多 ticker 共存
  - 读写必须使用原子操作（`tmp_path.write_text() + tmp_path.replace()`），参考 `memory.py` 的 `update_with_outcome()`

  **禁止做**：
  - 不修改记忆日志的 tag 格式或解析器
  - 不创建新的目录结构（使用现有的 `~/.tradingagents/memory/` 目录）
  - 不在 load() 返回 None 时崩溃（调用方自行处理空持仓）

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：文件 I/O + JSON 序列化，逻辑简单
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 1 波（与任务 1、3、4 并行）
  - **阻塞**：任务 8
  - **被阻塞于**：无

  **参考**：

  **模式参考**：
  - `tradingagents/agents/utils/memory.py:161-163` — 原子写入模式：`tmp_path.write_text() + tmp_path.replace()`
  - `tradingagents/agents/utils/memory.py:19-27` — 构造函数从 config 读取路径并创建目录

  **测试参考**：
  - `tests/test_memory_log.py` — 使用 `tmp_path` fixture 进行文件 I/O 测试

  **引用说明**：
  - `memory.py` 的原子写入是防止文件损坏的关键模式，必须遵循
  - `test_memory_log.py` 展示了如何用 pytest 的 tmp_path 测试文件持久化

  **验收标准**：

  **TDD 流程**：
  - [ ] 测试文件已扩展：`tests/test_position_tracking.py::TestPositionState`
  - [ ] `pytest tests/test_position_tracking.py::TestPositionState -v` → PASS（至少 5 个测试）

  **QA 场景**：

  ```
  场景：保存并加载持仓状态
    工具：Bash（pytest）
    前提条件：tmp_path fixture 提供临时目录
    步骤：
      1. 初始化 PositionStateManager，配置指向 tmp_path
      2. save("600519", 1580.0, 100, "2026-01-15")
      3. 调用 load("600519")，断言返回的 cost_price==1580.0, quantity==100
    预期结果：保存后立即加载，数据完全一致
    证据：.sisyphus/evidence/task-2-save-load.txt

  场景：加载不存在的 ticker 返回 None
    工具：Bash（pytest）
    步骤：
      1. 调用 load("000001") — 从未保存过
      2. 断言返回 None（不抛异常）
    预期结果：空持仓优雅处理
    证据：.sisyphus/evidence/task-2-load-none.txt

  场景：reset 清除持仓
    工具：Bash（pytest）
    步骤：
      1. save("600519", 1580.0, 100, "2026-01-15")
      2. reset("600519")
      3. load("600519") → None
    预期结果：reset 后状态完全清除
    证据：.sisyphus/evidence/task-2-reset.txt
  ```

  **证据捕获**：
  - [ ] 每个证据文件：task-2-{scenario-slug}.txt

  **提交**：是（与任务 1、3、4 同组）
  - 消息：`feat(position): add PositionStateManager for persistent position tracking`
  - 文件：`tradingagents/agents/utils/position_state.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPositionState -v`

- [x] 3. AgentState 新增持仓字段

  **做什么**：
  - 修改 `tradingagents/agents/utils/agent_states.py`
  - 在 `AgentState` 类中新增以下字段（全部带默认值以保证向后兼容）：
    - `cost_price: Annotated[float, "Average cost price of current position"] = 0.0`
    - `quantity: Annotated[int, "Number of shares held"] = 0`
    - `position_pnl: Annotated[float, "Unrealized P&L amount"] = 0.0`
    - `position_pnl_pct: Annotated[Optional[float], "Unrealized P&L percentage"] = None`
  - 确保 `position_opened_date` 字段已有默认值 `""`（当前已存在，确认即可）
  - 添加 `from typing import Optional`（如果尚未导入）

  **禁止做**：
  - 不删除或修改任何现有字段
  - 不改变现有字段的默认值
  - 不添加与持仓无关的字段

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：单文件修改，纯声明式字段添加
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 1 波（与任务 1、2、4 并行）
  - **阻塞**：任务 5、8
  - **被阻塞于**：无

  **参考**：

  **模式参考**：
  - `tradingagents/agents/utils/agent_states.py:78-80` — 现有 `position_opened_date` 和 `limit_up_price` 字段的定义风格：`Annotated[type, "description"] = default`

  **引用说明**：
  - 新增字段必须严格遵循现有字段的声明风格（TypedDict + Annotated + 默认值）

  **验收标准**：

  **TDD 流程**：
  - [ ] 测试验证默认值：`state = AgentState(...)` 后 `state["cost_price"] == 0.0` 且 `state["quantity"] == 0`
  - [ ] `pytest tests/test_position_tracking.py::TestAgentStateFields -v` → PASS

  **QA 场景**：

  ```
  场景：AgentState 默认值验证
    工具：Bash（pytest）
    步骤：
      1. 导入 AgentState，创建默认实例（不传持仓字段）
      2. 断言 cost_price == 0.0, quantity == 0, position_pnl == 0.0
    预期结果：所有新字段有正确默认值，不影响现有代码
    证据：.sisyphus/evidence/task-3-defaults.txt

  场景：AgentState 显式赋值
    工具：Bash（pytest）
    步骤：
      1. 创建 AgentState，传入 cost_price=1580.0, quantity=100
      2. 断言字段值正确
    预期结果：字段可正常赋值和读取
    证据：.sisyphus/evidence/task-3-explicit.txt
  ```

  **证据捕获**：
  - [ ] 每个证据文件：task-3-{scenario-slug}.txt

  **提交**：是（与任务 1、2、4 同组）
  - 消息：`feat(position): add cost_price, quantity, position_pnl fields to AgentState`
  - 文件：`tradingagents/agents/utils/agent_states.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestAgentStateFields -v`

- [x] 4. 持仓上下文格式化工具

  **做什么**：
  - 在 `tradingagents/dataflows/position_utils.py` 中追加函数（与任务 1 同文件）
  - 实现 `format_position_for_trader(state: dict) -> str`：
    - 从 AgentState 提取 cost_price, quantity, current_price（从 market_report 或工具调用结果中获取）
    - 返回适合注入 Trader prompt 的持仓上下文字符串，例如：
      ```
      当前持仓：成本价 1580.00，持有 100 股，现价 1650.00
      浮动盈亏：+7000.00 元 (+4.43%)
      ```
    - 无持仓（cost_price==0 或 quantity==0）时返回空字符串
  - 实现 `format_position_for_pm(state: dict) -> str`：
    - 更详细的持仓上下文，包含操作指导提示：
      - 浮盈 > 10%：提示"考虑分批止盈，锁定利润"
      - 浮亏 > 10%：提示"评估是否需要止损，避免深套"
      - 震荡区间（-5% 到 +5%）：提示"持仓观望，等待趋势确认"
    - 注入风险调整提示（浮盈大时提醒保守、浮亏时提醒理性评估）
    - 无持仓时返回空字符串

  **禁止做**：
  - 不在格式化函数中做出交易决策（决策由 LLM agent 做出）
  - 不编造不存在的价格数据
  - 格式化文本中不含主观判断（如"强烈建议"），只含客观提示

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：字符串拼接 + 条件判断，逻辑简单
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 1 波（与任务 1、2、3 并行）
  - **阻塞**：任务 5、6、7
  - **被阻塞于**：任务 1（依赖 `calc_position_pnl`）

  **参考**：

  **模式参考**：
  - `tradingagents/agents/utils/agent_utils.py:56-74` — `build_instrument_context()` 函数风格：接受参数，返回格式化的上下文字符串
  - `tradingagents/dataflows/a_share_constraints.py:36-51` — `format_limit_constraint()` 函数风格：条件判断后返回格式化的约束文本
  - `tradingagents/agents/utils/agent_utils.py:76-91` — `format_past_context()` 函数风格：处理空输入时返回空字符串

  **引用说明**：
  - `build_instrument_context` 展示了项目中"构建 agent prompt 上下文片段"的标准模式
  - `format_limit_constraint` 展示了"条件返回格式化文本或空字符串"的模式

  **验收标准**：

  **TDD 流程**：
  - [ ] 测试 `format_position_for_trader` 有持仓和无持仓两种情况
  - [ ] 测试 `format_position_for_pm` 的浮盈/浮亏/持平三种状态
  - [ ] `pytest tests/test_position_tracking.py::TestPositionFormatting -v` → PASS

  **QA 场景**：

  ```
  场景：Trader 持仓格式化（有持仓，浮盈）
    工具：Bash（pytest）
    步骤：
      1. 构造 mock state：cost_price=50.0, quantity=200, current_price=55.0
      2. 调用 format_position_for_trader(state)
      3. 断言输出包含 "成本价 50.00"、"200 股"、"浮动盈亏：+1000.00"
    预期结果：正确格式化 Trader 上下文
    证据：.sisyphus/evidence/task-4-trader-profit.txt

  场景：PM 持仓格式化（浮亏超过 10%）
    工具：Bash（pytest）
    步骤：
      1. 构造 mock state：cost_price=100.0, quantity=100, current_price=85.0（浮亏 15%）
      2. 调用 format_position_for_pm(state)
      3. 断言输出包含止损相关提示文案
    预期结果：浮亏超阈值时触发止损提醒
    证据：.sisyphus/evidence/task-4-pm-loss-warning.txt

  场景：格式化空持仓
    工具：Bash（pytest）
    步骤：
      1. 构造 mock state：cost_price=0.0, quantity=0
      2. 调用 format_position_for_trader 和 format_position_for_pm
      3. 断言两者都返回空字符串
    预期结果：无持仓时不产生任何上下文文本
    证据：.sisyphus/evidence/task-4-empty.txt
  ```

  **提交**：是（与任务 1、2、3 同组）
  - 消息：`feat(position): add position context formatters for Trader and PM`
  - 文件：`tradingagents/dataflows/position_utils.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPositionFormatting -v`

- [x] 5. Propagator 初始状态注入持仓数据

  **做什么**：
  - 修改 `tradingagents/graph/propagation.py`
  - 扩展 `create_initial_state()` 方法签名：
    ```python
    def create_initial_state(
        self, company_name: str, trade_date: str,
        past_context: str = "",
        cost_price: float = 0.0,
        quantity: int = 0,
        position_opened_date: str = "",
    ) -> Dict[str, Any]:
    ```
  - 在返回的初始状态 dict 中加入 `cost_price`、`quantity`、`position_opened_date` 字段
  - 保持所有新参数带默认值（向后兼容）

  **禁止做**：
  - 不在此处计算盈亏（盈亏计算在 trading_graph 中获取收盘价后进行）
  - 不改变现有参数的顺序或默认值
  - 不在 create_initial_state 中进行任何 I/O 操作

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：参数扩展 + 字典字段注入，逻辑简单
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 2 波（与任务 6、7、8、9 并行）
  - **阻塞**：任务 8
  - **被阻塞于**：任务 3、4

  **参考**：

  **模式参考**：
  - `tradingagents/graph/propagation.py:18-55` — 当前 `create_initial_state()` 实现：返回包含公司名、日期和空报告字段的 dict

  **测试参考**：
  - `tests/test_checkpoint_resume.py` — 如何测试 propagator 和相关的状态创建

  **引用说明**：
  - 当前方法返回一个 dict，新字段直接添加到 dict 中即可，不需要修改 TypedDict 以外的任何东西

  **验收标准**：

  **TDD 流程**：
  - [ ] `pytest tests/test_position_tracking.py::TestPropagatorState -v` → PASS

  **QA 场景**：

  ```
  场景：带持仓参数创建初始状态
    工具：Bash（pytest）
    步骤：
      1. 调用 create_initial_state("600519", "2026-05-06", cost_price=1580.0, quantity=100)
      2. 断言返回 dict 中 cost_price==1580.0, quantity==100
    预期结果：持仓数据正确注入初始状态
    证据：.sisyphus/evidence/task-5-with-position.txt

  场景：不带持仓参数创建初始状态（向后兼容）
    工具：Bash（pytest）
    步骤：
      1. 调用 create_initial_state("600519", "2026-05-06") — 不传持仓参数
      2. 断言 cost_price==0.0, quantity==0
    预期结果：默认值生效，行为不变
    证据：.sisyphus/evidence/task-5-without-position.txt
  ```

  **提交**：是（与任务 6、7、8、9 同组）
  - 消息：`feat(position): inject cost_price and quantity into initial agent state`
  - 文件：`tradingagents/graph/propagation.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPropagatorState -v`

- [x] 6. Trader prompt 持仓注入

  **做什么**：
  - 修改 `tradingagents/agents/trader/trader.py`
  - 在 `trader_node()` 函数中，构建 prompt 前：
    1. 从 state 提取 `cost_price`, `quantity`, `position_opened_date`
    2. 如果有持仓（cost_price > 0 且 quantity > 0），调用 `format_position_for_trader(state)` 获取持仓上下文
    3. 将持仓上下文注入到 user message 的 content 中（在 investment plan 之后）
  - 注入格式：在 investment plan 和限价约束之间插入持仓上下文段落
  - Prompt 调整：在 system prompt 中增加一句指示："If position context is provided, factor existing P&L into your transaction proposal (e.g., avoid adding to a deeply losing position without strong conviction; consider taking partial profits on large gains)."

  **禁止做**：
  - 不修改 Trader 的核心逻辑结构（LLM 调用方式不变）
  - 不修改 `TraderProposal` schema（除非确实需要新字段）
  - 不在 prompt 中强制要求特定操作（如"必须止损"），只提供上下文供 LLM 判断

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 原因：LLM prompt 工程 — 需要精心设计注入格式和措辞，确保不破坏现有决策质量
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 2 波（与任务 5、7、8、9 并行）
  - **阻塞**：任务 11
  - **被阻塞于**：任务 4、5

  **参考**：

  **模式参考**：
  - `tradingagents/agents/trader/trader.py:30-61` — 当前 prompt 构建逻辑：system message + user message，包含 instrument context 和 investment plan
  - `tradingagents/dataflows/a_share_constraints.py:36-51` — `format_limit_constraint()` — 已注入到 trader prompt 的约束文本格式

  **引用说明**：
  - 当前 prompt 结构为 system message + user message，持仓上下文应追加到 user message 中，保持 system message 干净
  - `format_limit_constraint` 已展示了如何将约束文本注入 user message，持仓上下文应遵循相同的注入模式

  **验收标准**：

  **TDD 流程**：
  - [ ] 测试有持仓时 prompt 中包含持仓上下文
  - [ ] 测试无持仓时 prompt 中不含持仓上下文
  - [ ] `pytest tests/test_position_tracking.py::TestTraderPrompt -v` → PASS

  **QA 场景**：

  ```
  场景：Trader prompt 含持仓信息
    工具：Bash（pytest）
    前提条件：Mock LLM，捕获发送的 prompt
    步骤：
      1. 构造 state：cost_price=1580.0, quantity=100, investment_plan="..."
      2. 调用 trader_node(state)
      3. 断言 prompt 中包含 "成本价 1580"、浮动盈亏相关文本
    预期结果：prompt 正确注入持仓上下文
    证据：.sisyphus/evidence/task-6-prompt-with-position.txt

  场景：Trader prompt 无持仓信息
    工具：Bash（pytest）
    步骤：
      1. 构造 state：cost_price=0.0, quantity=0
      2. 调用 trader_node(state)
      3. 断言 prompt 中不含 "成本价" 或 "浮动盈亏"
    预期结果：无持仓时 prompt 与当前版本一致
    证据：.sisyphus/evidence/task-6-prompt-no-position.txt
  ```

  **提交**：是（与任务 5、7、8、9 同组）
  - 消息：`feat(position): inject position context into Trader prompt`
  - 文件：`tradingagents/agents/trader/trader.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestTraderPrompt -v`

- [x] 7. Portfolio Manager prompt 持仓注入

  **做什么**：
  - 修改 `tradingagents/agents/managers/portfolio_manager.py`
  - 在 `portfolio_manager_node()` 函数中，构建 prompt 前：
    1. 从 state 提取 `cost_price`, `quantity`, `position_pnl`, `position_pnl_pct`
    2. 如果有持仓，调用 `format_position_for_pm(state)` 获取详细持仓上下文
    3. 将持仓上下文注入到 prompt 中（在 trader_plan 和 risk debate history 之间）
    4. 如果有持仓，调整 rating scale 描述，增加持仓相关维度（如"已有持仓浮盈 X%，是否建议止盈"）
  - 注入位置：`{lessons_line}` 之后、`**Risk Analysts Debate History:**` 之前
  - System prompt 调整：增加持仓感知指导（不强制特定操作，提供上下文框架）

  **禁止做**：
  - 不修改 `PortfolioDecision` schema 的字段定义
  - 不改变 PM 的核心逻辑（LLM 调用方式不变）
  - 不在 prompt 中硬编码止盈/止损阈值（阈值由 LLM 根据市场环境判断）

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 原因：LLM prompt 工程 — PM 是最终决策 agent，prompt 质量直接决定输出质量
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 2 波（与任务 5、6、8、9 并行）
  - **阻塞**：任务 11
  - **被阻塞于**：任务 4、5

  **参考**：

  **模式参考**：
  - `tradingagents/agents/managers/portfolio_manager.py:30-74` — 当前 PM prompt 构建逻辑：使用 f-string 模板拼接 research_plan, trader_plan, lessons_line, history
  - `tradingagents/agents/utils/agent_utils.py:76-91` — `format_past_context()` — 已有上下文注入到 PM prompt 的模式

  **引用说明**：
  - PM prompt 已有 `lessons_line` 注入点，持仓上下文应在之后插入，保持结构清晰
  - `format_past_context` 展示了"生成格式化段落并插入 prompt"的标准模式

  **验收标准**：

  **TDD 流程**：
  - [ ] 测试有持仓时 prompt 中包含详细持仓上下文和操作指导提示
  - [ ] 测试浮盈 > 10% 时 prompt 包含止盈提示
  - [ ] 测试浮亏 > 10% 时 prompt 包含止损评估提示
  - [ ] 测试无持仓时 prompt 不含持仓上下文
  - [ ] `pytest tests/test_position_tracking.py::TestPMPrompt -v` → PASS

  **QA 场景**：

  ```
  场景：PM prompt 含持仓浮盈信息（触达止盈阈值）
    工具：Bash（pytest）
    步骤：
      1. 构造 state：cost_price=100.0, quantity=100, current_price=115.0（浮盈 15%）
      2. 调用 portfolio_manager_node(state)
      3. 断言 prompt 中包含 "浮盈 1500.00 元 (+15.00%)" 和止盈相关提示
    预期结果：PM 获得完整持仓上下文用于决策
    证据：.sisyphus/evidence/task-7-pm-profit.txt

  场景：PM prompt 含持仓浮亏信息（触达止损阈值）
    工具：Bash（pytest）
    步骤：
      1. 构造 state：cost_price=100.0, quantity=100, current_price=85.0（浮亏 15%）
      2. 调用 portfolio_manager_node(state)
      3. 断言 prompt 中包含止损评估提示
    预期结果：浮亏时 PM 获得止损提醒上下文
    证据：.sisyphus/evidence/task-7-pm-loss.txt

  场景：PM prompt 无持仓
    工具：Bash（pytest）
    步骤：
      1. 构造 state：cost_price=0.0, quantity=0
      2. 调用 portfolio_manager_node(state)
      3. 断言 prompt 中不含持仓相关文本
    预期结果：无持仓时 PM prompt 与当前一致
    证据：.sisyphus/evidence/task-7-pm-no-position.txt
  ```

  **提交**：是（与任务 5、6、8、9 同组）
  - 消息：`feat(position): inject position context into Portfolio Manager prompt`
  - 文件：`tradingagents/agents/managers/portfolio_manager.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPMPrompt -v`

- [x] 8. TradingGraph propagate() 扩展 + 模拟持仓自动更新

  **做什么**：
  - 修改 `tradingagents/graph/trading_graph.py`
  - 扩展 `propagate()` 方法签名：
    ```python
    def propagate(self, company_name, trade_date,
                  cost_price: float = 0.0,
                  quantity: int = 0,
                  position_opened_date: str = "") -> ...
    ```
  - 在 `_run_graph()` 中：
    1. 运行分析前：如果 cost_price > 0 且 quantity > 0，从 `PositionStateManager` 加载上次持仓
    2. 如果用户提供了新的持仓参数，覆盖持久化数据
    3. 将持仓参数传递给 `create_initial_state()`
    4. 分析完成后：获取分析日收盘价，计算 P&L，更新 `position_state.json`
    5. 如果系统建议 Buy（且用户无持仓）→ 以收盘价自动开仓并在 position_state 记录
    6. 如果系统建议 Sell（且用户有持仓）→ 检查 T+1 约束；若允许，计算已实现盈亏并清除持仓
    7. 如果系统建议 Hold → 持仓状态不变
  - 实现 `_get_analysis_day_close(ticker, trade_date) -> Optional[float]` 辅助方法
  - 实现 `_auto_update_position(ticker, trade_date, final_decision, cost_price, quantity)` 辅助方法
  - 在 `__init__` 中初始化 `self.position_state = PositionStateManager(config)`
  - 实现幂等性：同一 ticker 同一天重复运行时，如果 position_state 中 `updated_at` 已等于 `trade_date`，跳过自动更新

  **禁止做**：
  - 不修改 `_run_graph()` 的核心图执行逻辑（graph.stream/invoke）
  - 不在自动更新中调用外部 API（收盘价从已有数据获取）
  - 不在 `market_type != "A_SHARE"` 时执行持仓自动更新（静默跳过）

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 原因：涉及多个子系统的协调（记忆日志、持仓状态、图执行、收益计算），逻辑较复杂
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：否（依赖任务 5、6、7 全部完成后才能集成）
  - **并行组**：第 2 波末尾（任务 5、6、7、9 并行完成后执行）
  - **阻塞**：任务 10、11
  - **被阻塞于**：任务 2、4、5、6、7

  **参考**：

  **模式参考**：
  - `tradingagents/graph/trading_graph.py:329-365` — `propagate()` 方法：当前签名和参数处理
  - `tradingagents/graph/trading_graph.py:367-451` — `_run_graph()` 方法：初始状态创建、图执行、状态日志、记忆日志存储、信号处理
  - `tradingagents/graph/trading_graph.py:197-244` — `_fetch_returns()` — 从 trade_date 获取 N 天后收盘价的模式
  - `tradingagents/graph/trading_graph.py:293-327` — `_resolve_pending_entries()` — 在 propagate() 开始时处理持久化数据的模式
  - `tradingagents/graph/trading_graph.py:376-411` — A 股限价注入到初始状态的模式（持仓数据注入的参考）

  **测试参考**：
  - `tests/test_memory_log.py` — 持久化操作的测试模式

  **引用说明**：
  - `_fetch_returns` 展示了如何获取 A 股收盘价，持仓自动更新需要类似的价格获取逻辑
  - `_resolve_pending_entries` 展示了"在 propagate() 开始时处理持久化数据"的模式
  - A 股限价注入代码展示了如何在 `_run_graph` 中扩展初始状态

  **验收标准**：

  **TDD 流程**：
  - [ ] `pytest tests/test_position_tracking.py::TestPropagate -v` → PASS（至少 6 个测试）

  **QA 场景**：

  ```
  场景：无持仓 propagate() 向后兼容
    工具：Bash（pytest）
    步骤：
      1. 使用 Mock 运行 ta.propagate("600519", "2026-05-06") — 不传持仓参数
      2. 断言调用成功，返回 (final_state, decision)
      3. 断言 decision 非空
    预期结果：与当前版本行为完全一致
    证据：.sisyphus/evidence/task-8-backward-compat.txt

  场景：带持仓 propagate() 并自动更新
    工具：Bash（pytest，使用 tmp_path）
    步骤：
      1. 运行 ta.propagate("600519", "2026-05-06", cost_price=1580.0, quantity=100)
      2. 断言 position_state 中保存了持仓数据
      3. 第二次运行同一 ticker 同一日期 → 跳过自动更新（幂等性）
    预期结果：持仓数据正确持久化，幂等性生效
    证据：.sisyphus/evidence/task-8-auto-update.txt

  场景：系统建议 Buy（用户无持仓）→ 自动开仓
    工具：Bash（pytest，Mock LLM 返回 Buy 建议）
    步骤：
      1. 运行 propagate("600519", "2026-05-06") — 无持仓
      2. Mock PM 返回 Buy 建议
      3. 断言 position_state 中新增了 600519 的持仓记录
    预期结果：模拟自动开仓成功
    证据：.sisyphus/evidence/task-8-auto-open.txt
  ```

  **提交**：是（与任务 5、6、7、9 同组）
  - 消息：`feat(position): extend propagate() with position params and auto-update`
  - 文件：`tradingagents/graph/trading_graph.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestPropagate -v`

- [x] 9. CLI 持仓输入步骤

  **做什么**：
  - 修改 `cli/main.py`
  - 在 `get_user_selections()` 中新增两个步骤（在分析师选择之后，研究深度之前）：
    - **Step 4.5：持仓成本价**（可选，按 Enter 跳过）
      - 提示："输入当前持仓成本价（按 Enter 跳过，仅分析）"
      - 校验：必须为正浮点数或空；非数字提示重新输入
    - **Step 4.6：持仓数量**（可选，仅在上一步输入了成本价时才出现）
      - 提示："输入当前持仓股数（按 Enter 跳过）"
      - 校验：必须为正整数或空
    - **Step 4.7：开仓日期**（可选）
      - 提示："输入开仓日期 YYYY-MM-DD（按 Enter 跳过）"
      - 校验：日期格式正确且不晚于分析日期
  - 更新 `run_analysis()`：
    - 从 selections 中读取持仓参数
    - 传递给 `propagator.create_initial_state()` 和 `graph.propagate()`
  - 更新 `MessageBuffer`: 在分析开始时显示持仓信息（如果有）

  **禁止做**：
  - 不改变现有 8 个步骤的顺序或行为
  - 不在 TUI（Live display）中新增面板（持仓信息仅在初始消息中显示）
  - 不强制要求用户输入持仓（所有步骤可选跳过）

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：CLI 交互逻辑，参照已有步骤模式，逻辑简单
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 2 波（与任务 5、6、7、8 并行）
  - **阻塞**：任务 11
  - **被阻塞于**：任务 5

  **参考**：

  **模式参考**：
  - `cli/main.py:463-612` — `get_user_selections()`：8 个步骤的 CLI 交互模式，每个步骤有独立的 prompt 和校验
  - `cli/main.py:615-636` — `get_ticker()` 和 `get_analysis_date()`：输入函数风格，含循环校验
  - `cli/main.py:929-1198` — `run_analysis()`：如何创建初始状态并启动分析流程

  **引用说明**：
  - 现有步骤使用 `create_question_box()` + `typer.prompt()` 模式，新步骤应完全遵循此模式
  - 日期校验已有 `get_analysis_date()` 可参考

  **验收标准**：

  **TDD 流程**：
  - [ ] CLI 交互测试：模拟用户输入持仓参数，验证参数正确传递
  - [ ] `pytest tests/test_position_tracking.py::TestCLIInput -v` → PASS

  **QA 场景**：

  ```
  场景：CLI 输入完整持仓参数
    工具：interactive_bash（tmux）
    前提条件：启动 CLI 交互环境
    步骤：
      1. 输入 ticker: 600519
      2. 输入日期: 2026-05-06（或按 Enter 使用默认值）
      3. 输入语言: Chinese
      4. 选择分析师: market
      5. 成本价: 1580.00
      6. 数量: 100
      7. 开仓日期: 2026-01-15
      8. 后续步骤正常选择
      9. 观察分析完成后报告中是否包含持仓盈亏相关内容
    预期结果：CLI 流畅输入持仓参数，分析报告含操作指导
    证据：.sisyphus/evidence/task-9-cli-full-input.txt

  场景：CLI 跳过持仓输入
    工具：interactive_bash（tmux）
    步骤：
      1. 输入 ticker: 600519
      2. 输入日期: 2026-05-06
      3. 输入语言: Chinese
      4. 选择分析师: market
      5. 成本价: （按 Enter 跳过）
      6. 后续步骤正常选择，分析正常执行
    预期结果：跳过持仓后系统降级为纯分析模式，与当前版本一致
    证据：.sisyphus/evidence/task-9-cli-skip.txt

  场景：CLI 输入无效成本价（负数）
    工具：interactive_bash（tmux）
    步骤：
      1. 成本价输入 -10
      2. 断言系统提示"成本价必须大于 0"并重新要求输入
    预期结果：无效输入被正确拦截
    证据：.sisyphus/evidence/task-9-cli-validation.txt
  ```

  **提交**：是（与任务 5、6、7、8 同组）
  - 消息：`feat(position): add CLI input steps for cost price and quantity`
  - 文件：`cli/main.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestCLIInput -v`

- [x] 10. A 股约束与持仓联动

  **做什么**：
  - 修改 `tradingagents/dataflows/a_share_constraints.py`
  - 扩展 `format_t_plus_1_constraint()`：当持仓由系统自动开仓（`position_opened_date == trade_date`）时，标注"今日新开仓，受 T+1 约束，无法卖出"
  - 新增 `format_position_constraint(cost_price, quantity, limit_up, limit_down, current_price) -> str`：
    - 检查成本价是否在涨跌停范围内
    - 如果成本价高于涨停价 → 标注"成本价超出涨停范围，当前无法盈利"
    - 如果数量超过日均成交量的一定比例 → 标注流动性风险提示
  - 在 `TradingAgentsGraph._auto_update_position()` 中：
    - 买入自动更新前检查是否涨停（如果涨停，模拟自动开仓可能失败，记录日志）
    - 卖出自动更新前检查是否跌停（如果跌停，模拟卖出可能失败）

  **禁止做**：
  - 不修改涨跌停计算逻辑（`get_limit_prices`, `get_limit_rate`）
  - 不在约束函数中做出交易决策
  - 流动性检查为软提示，不阻止自动更新

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 原因：A 股规则逻辑，需要理解涨跌停、T+1 与持仓的交互边界条件
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 3 波（与任务 11、12 并行）
  - **阻塞**：任务 11
  - **被阻塞于**：任务 8

  **参考**：

  **模式参考**：
  - `tradingagents/dataflows/a_share_constraints.py:7-33` — `get_limit_prices()` 和 `get_limit_rate()`：板块判断逻辑
  - `tradingagents/dataflows/a_share_constraints.py:54-83` — `format_t_plus_1_constraint()`：T+1 约束格式化

  **引用说明**：
  - `format_t_plus_1_constraint` 已处理 `position_opened_date`，需要在此基础上增加自动开仓的 T+1 提示
  - 涨跌停获取已由 `trading_graph.py:_run_graph` 完成，约束函数接收计算结果而非自己查询

  **验收标准**：

  **TDD 流程**：
  - [ ] `pytest tests/test_position_tracking.py::TestAStickConstraints -v` → PASS

  **QA 场景**：

  ```
  场景：成本价高于涨停价
    工具：Bash（pytest）
    步骤：
      1. 调用 format_position_constraint(cost_price=200.0, quantity=100, limit_up=180.0, limit_down=160.0, current_price=175.0)
      2. 断言输出包含 "成本价超出涨停范围" 相关提示
    预期结果：正确识别并提示无法回本的情况
    证据：.sisyphus/evidence/task-10-cost-above-limit.txt

  场景：自动开仓当日 T+1 约束
    工具：Bash（pytest）
    步骤：
      1. 调用 format_t_plus_1_constraint("2026-05-06", "2026-05-06", "A_SHARE")
      2. 断言输出包含 "今日新开仓" 和 "T+1 约束" 相关提示
    预期结果：同日开仓自动触发 T+1 约束提醒
    证据：.sisyphus/evidence/task-10-t1-same-day.txt
  ```

  **提交**：是（与任务 11、12 同组）
  - 消息：`feat(position): integrate A-share constraints with position tracking`
  - 文件：`tradingagents/dataflows/a_share_constraints.py`, `tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestAStickConstraints -v`

- [x] 11. 端到端集成测试

  **做什么**：
  - 在 `tests/test_position_tracking.py` 中追加集成测试类 `TestIntegration`
  - 测试场景：
    1. **无持仓全流程**：propagate() 不传持仓 → 验证输出与当前版本一致（回归）
    2. **有持仓全流程**：propagate() 传持仓 → 验证 P&L 计算正确、prompt 含持仓信息、position_state 正确更新
    3. **跨运行持久化**：第一次 propagate() 传持仓 → 第二次 propagate() 不传持仓 → 验证自动加载了上次持仓
    4. **覆盖持久化**：第一次传持仓 A → 第二次传持仓 B → 验证使用新数据
    5. **T+1 阻止卖出**：当日开仓 → 系统建议 Sell → 验证 T+1 阻止生效
    6. **幂等性**：同一 ticker 同一日期运行两次 → 验证第二次不重复更新 position_state
    7. **非 A 股静默**：market_type=US_STOCK → 持仓功能静默跳过
  - 使用 Mock LLM 来模拟交易建议（Buy/Sell/Hold），避免实际 LLM 调用

  **禁止做**：
  - 不在集成测试中调用真实 LLM API（全部 Mock）
  - 不修改生产代码来适配测试
  - 测试不做真实的 akshare 网络调用（Mock 数据）

  **推荐 Agent 配置**：
  - **类别**：`deep`
    - 原因：集成测试需要编排多个组件，涉及 mock 策略设计
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：否（依赖所有功能开发完成）
  - **并行组**：第 3 波末尾
  - **阻塞**：F1、F2、F3、F4
  - **被阻塞于**：任务 6、7、8、9、10

  **参考**：

  **测试参考**：
  - `tests/test_checkpoint_resume.py` — Mock LLM 集成测试模式
  - `tests/test_memory_log.py` — 使用 tmp_path 的文件持久化测试
  - `tests/conftest.py` — 共享 fixture 定义

  **引用说明**：
  - 集成测试的 mock 粒度：Mock LLM 层（返回预设建议），Mock akshare 网络调用（返回预设价格），真实调用 position_state 和其他内部组件

  **验收标准**：

  **TDD 流程**：
  - [ ] `pytest tests/test_position_tracking.py::TestIntegration -v` → PASS（至少 7 个测试）
  - [ ] `pytest tests/ -v --ignore=tests/test_position_tracking.py` → PASS（现有测试不受影响）

  **QA 场景**：

  ```
  场景：有持仓全流程（最核心的端到端验证）
    工具：Bash（pytest）
    步骤：
      1. 使用 Mock LLM（返回 Buy 建议）
      2. propagate("600519", "2026-05-06", cost_price=1580.0, quantity=100)
      3. 断言返回的 final_state 含 final_trade_decision
      4. 断言 position_state 已更新
      5. 断言 Prompt 中包含持仓上下文
    预期结果：全链路数据流通正确
    证据：.sisyphus/evidence/task-11-e2e-with-position.txt

  场景：无持仓回归验证
    工具：Bash（pytest）
    步骤：
      1. propagate("600519", "2026-05-06") 不传持仓
      2. 断言返回的 decision 非空
      3. 断言 position_state 没有新增记录
    预期结果：向后兼容，无持仓时行为不变
    证据：.sisyphus/evidence/task-11-e2e-no-position.txt
  ```

  **提交**：是（与任务 10、12 同组）
  - 消息：`test(position): add end-to-end integration tests for position tracking`
  - 文件：`tests/test_position_tracking.py`
  - 预提交：`pytest tests/test_position_tracking.py::TestIntegration -v`

- [x] 12. 回归安全验证

  **做什么**：
  - 运行现有全部测试套件，确保无持仓功能不影响现有行为
  - 特别关注：
    - `test_a_share.py` — A 股基本功能
    - `test_memory_log.py` — 记忆日志（tag 格式不能变）
    - `test_signal_processing.py` — 信号处理
    - `test_structured_agents.py` — 结构化输出
    - `test_checkpoint_resume.py` — 检查点恢复
    - `test_ticker_symbol_handling.py` — ticker 处理
  - 如发现任何回归，修复并重新验证
  - 确保 `cost_price=0.0, quantity=0` 时所有 agent 行为不变

  **禁止做**：
  - 不修改任何现有测试文件（除非需要适配签名变更如 propagate()）
  - 不跳过失败的现有测试（必须全部通过或修复代码）

  **推荐 Agent 配置**：
  - **类别**：`quick`
    - 原因：运行现有测试套件 + 分析失败原因，逻辑简单
  - **技能**：`[]`

  **并行化**：
  - **可并行运行**：是
  - **并行组**：第 3 波（与任务 10、11 并行）
  - **阻塞**：F1-F4
  - **被阻塞于**：任务 8（propagate 签名变更可能影响现有测试）

  **参考**：

  **测试参考**：
  - `pyproject.toml:45-54` — pytest 配置：testpaths, markers
  - `tests/conftest.py` — 共享 fixtures

  **验收标准**：

  - [ ] `pytest tests/ -v --ignore=tests/test_position_tracking.py` → ALL PASS
  - [ ] 特别确认 `test_memory_log.py` 不受影响（tag 格式不变）

  **QA 场景**：

  ```
  场景：全部现有测试通过
    工具：Bash
    步骤：
      1. python -m pytest tests/ -v --ignore=tests/test_position_tracking.py
      2. 检查退出码为 0
      3. 检查无 FAILED 或 ERROR
    预期结果：所有现有测试通过，无回归
    证据：.sisyphus/evidence/task-12-regression.txt
  ```

  **提交**：是（与任务 10、11 同组）
  - 消息：`test(position): verify no regression in existing test suite`
  - 文件：无文件变更（仅验证）
  - 预提交：`pytest tests/ -v --ignore=tests/test_position_tracking.py`

---

## 最终验证波次（所有实现任务完成后强制执行）

> 4 个审查 Agent **并行运行**。全部必须 APPROVE。向用户展示合并结果并获取明确"确认"后方可完成。
>
> **不要在验证后自动继续。等待用户明确批准后再标记工作完成。**
> **用户确认前绝对不要勾选 F1-F4。** 若被拒绝或需要修改 → 修复 → 重新运行 → 重新展示 → 等待确认。

- [x] F1. **计划合规审计** — `oracle`
  从头到尾阅读计划。对每个"必须包含"：验证实现是否存在（读取文件、curl 端点、运行命令）。对每个"必须排除"：在代码库中搜索禁止的模式 — 若找到则拒绝并标注 file:line。检查 `.sisyphus/evidence/` 中的证据文件是否存在。将交付物与计划进行对比。
  输出：`必须包含 [N/N] | 必须排除 [N/N] | 任务 [N/N] | 判定: APPROVE/REJECT`

- [x] F2. **代码质量审查** — `unspecified-high`
  运行 `python -m pytest tests/`。审查所有变更文件：`as any`/`@ts-ignore` 等价模式、空 catch/except、生产环境 print/console.log、注释掉的代码、未使用的 import。检查 AI slop：过度注释、过度抽象、通用命名（data/result/item/temp）。
  输出：`测试 [N pass/N fail] | 文件 [N clean/N issues] | 判定`

- [x] F3. **实际手动 QA** — `unspecified-high`
  从干净状态开始。执行**每个**任务中的**每一个** QA 场景 — 遵循精确步骤，捕获证据。测试跨任务集成（功能协同工作，非孤立测试）。测试边缘情况：空状态、无效输入、快速连续操作。证据保存到 `.sisyphus/evidence/final-qa/`。
  输出：`场景 [N/N pass] | 集成 [N/N] | 边缘场景 [N 已测试] | 判定`

- [x] F4. **范围忠实度检查** — `deep`
  对每个任务：读取"做什么"、读取实际 diff（git log/diff）。验证 1:1 — spec 中的内容全部构建（无遗漏），spec 外的内容无一构建（无蔓延）。检查"禁止做"合规性。检测跨任务污染：任务 N 触碰任务 M 的文件。标记未记录的变更。
  输出：`任务 [N/N compliant] | 污染 [CLEAN/N issues] | 未记录 [CLEAN/N files] | 判定`

---

## 提交策略

- **1-4**: 数据层提交 — `feat(position): add P&L calculation and position state persistence`
- **5-9**: 注入和交互层提交 — `feat(position): inject position context into Trader/PM and CLI input`
- **10-12**: 集成层提交 — `feat(position): A-share constraint integration and E2E tests`

---

## 成功标准

### 验证命令
```bash
# 数据层测试
pytest tests/test_position_tracking.py::TestPositionCalc -v

# 持久化测试
pytest tests/test_position_tracking.py::TestPositionState -v

# 集成测试
pytest tests/test_position_tracking.py::TestIntegration -v

# 回归测试（确保现有行为不变）
pytest tests/ -v --ignore=tests/test_position_tracking.py
```

### 最终检查清单
- [ ] 所有"必须包含"项已实现
- [ ] 所有"必须排除"项未被违反
- [ ] 所有测试通过
- [ ] 无持仓参数时行为不变（回归安全）
