# 工业级质量差距修复计划

## TL;DR

> **Quick Summary**: 基于 `docs/工业级质量差距全面诊断.md` (v0.2.14-cn) 的全面诊断，通过 10 个独立可回滚的 PR 修复 5 个根因（temperature、bind_tools、防幻觉、双重工具来源、scope泄露）和 3 个架构缺口（temperature配置、结构化输出、内容验证层），使系统从"概率性玩具"升级为"工业级确定性流水线"。
>
> **Deliverables**:
> - 全局 LLM temperature 控制（含辩论 agent 差异化温度）
> - bind_tools/ToolNode 对齐（4 个 client + bootstrap.py）
> - 单一真理源 `indicator_registry.py`
> - 全局防幻觉指令（中英双语全覆盖，含辩论 agent 轻量版）
> - 4 个分析师的 Pydantic schema 结构化输出
> - IndustryVerifier 扩展（行业 benchmark + 数字溯源）
> - 完整测试套件（TDD 流程，≥70% 覆盖率门禁）
>
> **Estimated Effort**: Large（约 30+ 文件改动，5-7 天净工作时间）
> **Parallel Execution**: YES - 10 waves (PR-0 → PR-10)
> **Critical Path**: PR-0 (temperature) → PR-3 (防幻觉) → PR-5 (Pydantic schema)

---

## Context

### Original Request
按 `docs/工业级质量差距全面诊断.md` (v0.2.14-cn) 生成修复计划。文档已完成：
- 5 个根因的代码实证（已二次评审）
- 5 个架构缺口的代码实证
- P0-P3 优先级矩阵
- P0+P1 修复方案（具体到代码段）

### Interview Summary
**Key Discussions**（已通过 Metis 咨询闭合所有决策）：
- 辩论 agent 温度：分层差异化（bull/bear=0.3, risk=0.2, trader/PM=0.1, 分析师=0）
- bind_tools 对齐：方案 A（删除 ToolNode 冗余，最保守）
- 测试策略：TDD（pytest 已有，70% 覆盖率门禁）
- 辩论 agent 防幻觉：选项 B（轻量化约束）
- English 模式防幻觉：必须修复

**Research Findings**:
- 测试基础设施已完善：48 个测试文件、11271 行测试代码、pytest + unittest.mock + pytest-cov + GitHub Actions
- 所有函数位置已验证精确（参见草稿）
- 4 个 LLM 客户端（openai/anthropic/azure/google）都需同步处理 `_PASSTHROUGH_KWARGS`

### Metis Review
**Identified Gaps**（已纳入计划）：
- `_PASSTHROUGH_KWARGS` 不含 temperature —— 文档修复方案不完整
- `ContextWindowManager._llm_summarize()` 静默使用未控温 LLM
- 4 个分散的指标名定义需要单一真理源
- macro_analyst 死代码映射
- 辩论 agent 必须有 temperature 例外（避免失去观点多样性）
- 跨文件依赖的隐藏耦合（prompt_constants.py 是"上帝对象"）

---

## Work Objectives

### Core Objective
通过修复温度非确定、工具绑定不一致、幻觉、scope 泄露等系统性问题，使 LLM 调用达到工业级确定性、可复现、可审计的标准。

### Concrete Deliverables
1. `default_config.py` 增加 `llm_temperature`、`llm_max_tokens`、`llm_debate_temperature` 配置
2. `bootstrap.py` 注入温度参数到所有 LLM 客户端
3. 4 个 LLM 客户端的 `_PASSTHROUGH_KWARGS` 加入 `temperature` 和 `max_tokens`
4. `bootstrap.py:175-201` ToolNode 缩减为只保留 `bind_tools` 实际使用的工具
5. `dynamic_graph_builder.py:31` 删除 `macro_analyst` 死代码映射
6. 新建 `indicator_registry.py` 作为指标名单一真理源
7. 新建 `prompt_constants.py` 提供全局防幻觉指令（12 个 agent 全覆盖，中英双语）
8. `get_degradation_instruction()` 修复为中英双语都返回防幻觉约束
9. 4 个分析师 + RM + Trader + PM 的 system_message 拼接防幻觉指令
10. 5 个辩论/风控 agent 加轻量防幻觉约束（ADR 选项 B）
11. `schemas.py` 扩展 4 个分析师的 Pydantic schema
12. 4 个分析师接入 `with_structured_output`
13. `IndustryVerifier` 扩展：行业 benchmark + 数字溯源验证
14. 完整测试套件（TDD 流程）

### Definition of Done
- [ ] `pytest --cov=tradingagents --cov-fail-under=70 tests/ -v` 全部通过
- [ ] 同一标的（600418 江淮汽车）5 次端到端 run，报告 Jaccard 相似度 ≥ 0.85
- [ ] 工具调用顺序一致性 ≥ 90%
- [ ] English 模式运行 600418，0 次 EPA/Class 8/ACT 关键词命中
- [ ] `filter_valid_tool_calls` 过滤反馈日志次数 = 0
- [ ] 所有 LLM 调用的 `temperature` 参数可通过 `pytest` 验证

### Must Have
- 温度控制全局生效（含 4 个 LLM 客户端）
- bind_tools/ToolNode 完全对齐
- 全局防幻觉指令（中英双语）注入所有 12 个 agent
- 辩论 agent 有差异化温度（避免观点多样性丧失）
- 4 个分析师的 Pydantic schema 结构化输出
- 完整测试覆盖（≥70% 门禁）

### Must NOT Have（Guardrails）
- **不得**对辩论 agent 应用 Pydantic schema（辩论输出是自然语言，schema 会破坏质量）
- **不得**修改 `tradingagents/graph/trading_graph.py` 的核心图结构
- **不得**在 PR-0（temperature=0）之前做任何其他修复（基线未稳定）
- **不得**在 PR-2（indicator_registry）之前清理 system prompt（缺单一真理源）
- **不得**跳过防幻觉指令的 English 模式修复
- **不得**对所有 agent 一刀切 temperature=0（辩论 agent 必须有例外）
- **不得**只改 `_create_llms()` 而忽略 4 个 LLM 客户端的 `_PASSTHROUGH_KWARGS`
- **不得**在没有 TDD failing test 的情况下实现任何功能

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - 所有验证由 agent 执行。禁止任何"用户手动测试 5 次"类验收。

### Test Decision
- **Infrastructure exists**: YES（pytest 已有，48 个测试文件，70% 覆盖率门禁）
- **Automated tests**: TDD（RED-GREEN-REFACTOR）
- **Framework**: pytest + unittest.mock（已有）
- **Mocking strategy**: conftest.py:mock_llm_client fixture + patch() 上下文管理器

### QA Policy
每个 TODO 必须包含 Agent-Executed QA Scenarios（按 Prometheus 规范）：
- **LLM 配置验证**：`grep -r "temperature" tradingagents/llm_clients/` 检查所有 client 含 `temperature`
- **bind_tools 对齐验证**：`python scripts/verify_tool_alignment.py`（AST 解析比对）
- **防幻觉指令验证**：`grep -r "anti_hallucination" tradingagents/agents/` 命中 ≥ 12 个 agent 文件
- **English 模式验证**：构造英文 query 运行，grep 验证不出现 EPA/Class 8/ACT
- **结构化输出验证**：4 个分析师的 `with_structured_output` 调用存在
- **证据保存**：`.omo/evidence/task-{N}-{scenario-slug}.{ext}`

---

## Execution Strategy

### Parallel Execution Waves

> **关键原则**：P0（temperature）必须最先执行，因为它是所有后续修复的基线。
> 每个 PR 独立可回滚，按依赖顺序串行执行（不同 PR 之间不可并行）。

```
PR-0: 温度基础设施（PREREQUISITE — 所有其他修复的基线）
├── Task 1: TDD failing test 验证 temperature 注入
├── Task 2: default_config.py 添加温度配置
├── Task 3: bootstrap.py 注入温度参数
├── Task 4: 4 个 LLM 客户端添加 temperature 到 _PASSTHROUGH_KWARGS
├── Task 5: 冒烟测试（5 次同输入端到端验证确定性）
└── Task 6: macro_analyst 死代码删除（顺带清理）

PR-1: bind_tools / ToolNode 对齐（依赖 PR-0）
├── Task 7: TDD failing test 验证对齐
├── Task 8: 编写 AST 验证脚本 scripts/verify_tool_alignment.py
└── Task 9: bootstrap.py 缩减 ToolNode（方案 A）

PR-2: indicator_registry.py 单一真理源（依赖 PR-1，可与 PR-3 并行准备）
├── Task 10: TDD failing test 验证注册表
├── Task 11: 新建 indicator_registry.py
├── Task 12: 4 个分散位置从注册表导入
└── Task 13: 删除分散硬编码

PR-3: 全局防幻觉指令（依赖 PR-2 的 indicator_registry）
├── Task 14: TDD failing test 验证中英双语防幻觉
├── Task 15: 新建 prompt_constants.py
├── Task 16: 修复 get_degradation_instruction() 中英双语
├── Task 17: 4 个分析师 + RM + Trader + PM 注入防幻觉
└── Task 18: 5 个辩论/风控 agent 加轻量防幻觉（ADR 选项 B）

PR-4: IndustryVerifier 扩展（依赖 PR-3 的稳定 prompt 拼接）
├── Task 19: TDD failing test 验证 benchmark 检测
├── Task 20: verifier.py 添加 benchmark 检查
└── Task 21: verifier.py 添加数字溯源检查

PR-5: Pydantic schema 扩展（依赖 PR-4 的稳定验证）
├── Task 22: TDD failing test 验证 schema 化
├── Task 23: schemas.py 添加 4 个分析师 schema
└── Task 24: 4 个分析师接入 with_structured_output（不含辩论 agent）

Final Verification Wave（所有 PR 完成后）
├── Task F1: Plan compliance audit
├── Task F2: Code quality review
├── Task F3: Real manual QA
└── Task F4: Scope fidelity check
```

### Dependency Matrix（缩写版）

| Task | 依赖 | 阻塞 | 可并行组 |
|------|------|------|----------|
| 1-6 (PR-0) | — | 7-30 | PR-0 单独执行 |
| 7-9 (PR-1) | 1-6 | 10-30 | PR-1 单独执行 |
| 10-13 (PR-2) | 7-9 | 14-30 | PR-2 单独执行 |
| 14-18 (PR-3) | 10-13 | 19-30 | PR-3 单独执行 |
| 19-21 (PR-4) | 14-18 | 22-30 | PR-4 单独执行 |
| 22-24 (PR-5) | 19-21 | F1-F4 | PR-5 单独执行 |
| F1-F4 | 22-24 | — | Final Wave 4 并行 |

> **注意**：PR 内部 tasks 可并行（如 PR-0 的 1+2+3+4），但 PR 之间必须串行。
> 完整依赖矩阵见下方"Agent Dispatch Summary"。

### Agent Dispatch Summary

| PR | Task 数 | Agent Profiles |
|----|---------|----------------|
| PR-0 | 6 | T1-T2 → `quick`, T3-T4 → `quick`, T5 → `unspecified-high`（端到端测试）, T6 → `quick` |
| PR-1 | 3 | T7-T8 → `quick`, T9 → `quick` |
| PR-2 | 4 | T10 → `quick`, T11-T13 → `quick` |
| PR-3 | 5 | T14 → `quick`, T15 → `quick`, T16-T18 → `unspecified-high`（prompt 工程） |
| PR-4 | 3 | T19-T20 → `deep`, T21 → `unspecified-high` |
| PR-5 | 3 | T22 → `quick`, T23-T24 → `unspecified-high`（schema 迁移） |
| FINAL | 4 | F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

> **格式要求**：任务标签使用纯数字（`1.`, `2.`），不使用 `T1.` / `Phase 1:` / `Task-1.`。
> Final Wave 标签使用 `F1.`, `F2.`。
> 每个任务包含：What to do / Must NOT do / Recommended Agent Profile / Parallelization / References / Acceptance Criteria / QA Scenarios。
> **每个任务必须有 QA Scenarios，缺则视为不完整。**

### PR-0：温度基础设施（基线层 — 必须最先执行）

- [x] 1. TDD: 编写 failing test 验证 temperature 注入链路

  **What to do**:
  - 在 `tests/test_llm_config.py` 新建测试文件
  - 编写测试：`test_default_config_has_temperature_key` 验证 `DEFAULT_CONFIG["llm_temperature"] == 0.0`
  - 编写测试：`test_bootstrap_injects_temperature` 验证 `_create_llms()` 调用后 `deep_client` 和 `quick_client` 的 `temperature` 参数为 0
  - 编写测试：`test_openai_client_passes_temperature` 验证 `OpenAIClient.get_llm()` 返回的实例 `temperature == 0`
  - 编写测试：`test_anthropic_client_passes_temperature`（如果 AnthropicClient 支持 temperature）
  - 编写测试：`test_google_client_passes_temperature`（如果 GoogleClient 支持 temperature）
  - **TDD 流程**：先写测试 → 确认测试 fail（因为当前实现没传 temperature）→ 进入 Task 2-4 实现

  **Must NOT do**:
  - 不要测试 LLM 的实际推理行为（只测配置传递）
  - 不要 mock `_create_llms()` 本身（要测真实路径）

  **Recommended Agent Profile**:
  - **Category**: `quick`（简单单元测试）
  - **Skills**: `[]`
  - **Reason**: 标准的 pytest 单元测试编写

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-0 Wave 1（与 Task 2-4 并行准备）
  - **Blocks**: Task 2-4（修复必须使这些测试通过）
  - **Blocked By**: None

  **References**:
  - `tradingagents/default_config.py:14-27` — LLM 配置段位置
  - `tradingagents/bootstrap.py:91-150` — `_create_llms()` 实现
  - `tradingagents/llm_clients/openai_client.py:204-207` — `_PASSTHROUGH_KWARGS` 当前内容
  - `tests/conftest.py:34-42` — `mock_llm_client` fixture 模式
  - `tests/test_resilient_llm.py` — LLM 客户端测试的代表性模式

  **Acceptance Criteria**:
  - [ ] `tests/test_llm_config.py` 创建并包含 5 个 test functions
  - [ ] `pytest tests/test_llm_config.py -v` 初始运行（实现前）显示 5 个 FAIL
  - [ ] 所有测试断言使用具体值（`assert == 0.0`，不是 `assert is not None`）

  **QA Scenarios**:

  ```
  Scenario: TDD RED 阶段验证
    Tool: Bash (pytest)
    Preconditions: 未实现 temperature 注入（仅运行测试）
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_llm_config.py -v
    Expected Result: 5 个测试全部 FAIL（AttributeError 或 KeyError）
    Failure Indicators: 测试 PASS 或 SKIPPED（说明实现已经做过了）
    Evidence: .omo/evidence/task-1-tdd-red-phase.txt
  ```

- [x] 2. default_config.py 添加 llm_temperature/llm_max_tokens/llm_debate_temperature 配置

  **What to do**:
  - 在 `tradingagents/default_config.py:14-27`（LLM 配置段）后插入：
    ```python
    # 全局 LLM 采样控制（v0.2.15-cn 新增）
    "llm_temperature": 0.0,              # 0 = 完全确定（工业级基线）
    "llm_max_tokens": 4096,              # 防止 LLM 输出无限长
    "llm_debate_temperature": 0.3,       # 辩论 agent 例外温度（保留观点多样性）
    "llm_risk_temperature": 0.2,         # 风控辩论例外温度
    "llm_decision_temperature": 0.1,      # 决策层（trader/PM）例外温度
    ```
  - 确保 `get_config()` 和 `DEFAULT_CONFIG` 都包含这些键
  - 环境变量覆盖：如 `LLM_TEMPERATURE` 可覆盖 `llm_temperature`（参考现有 `LLM_PROVIDER` 模式）

  **Must NOT do**:
  - 不要修改 DEFAULT_CONFIG 中其他已存在的键
  - 不要移除任何已存在的配置项

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-0 Wave 1（与 Task 1, 3, 4 并行）
  - **Blocks**: Task 3-5
  - **Blocked By**: None

  **References**:
  - `tradingagents/default_config.py:5-106` — 完整 `DEFAULT_CONFIG` 结构
  - `tradingagents/default_config.py` — 查找 `LLM_PROVIDER` 环境变量覆盖模式

  **Acceptance Criteria**:
  - [ ] `llm_temperature`, `llm_max_tokens`, `llm_debate_temperature`, `llm_risk_temperature`, `llm_decision_temperature` 5 个新键存在
  - [ ] 默认值分别为 0.0, 4096, 0.3, 0.2, 0.1
  - [ ] 现有测试 `tests/test_a_share.py`、`tests/test_a_stock_data.py` 等不因配置变更而失败

  **QA Scenarios**:

  ```
  Scenario: 配置键存在性验证
    Tool: Bash (python -c)
    Preconditions: 修复已应用
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "from tradingagents.default_config import DEFAULT_CONFIG; assert 'llm_temperature' in DEFAULT_CONFIG; assert DEFAULT_CONFIG['llm_temperature'] == 0.0; assert 'llm_debate_temperature' in DEFAULT_CONFIG; assert DEFAULT_CONFIG['llm_debate_temperature'] == 0.3; print('PASS')"
    Expected Result: 输出 "PASS"
    Failure Indicators: KeyError, AssertionError
    Evidence: .omo/evidence/task-2-config-keys.txt

  Scenario: 现有测试不受影响
    Tool: Bash (pytest)
    Preconditions: 配置变更已应用
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_a_share.py tests/test_a_stock_data.py -v --no-header
    Expected Result: 所有现有测试 PASS（无新 FAIL）
    Failure Indicators: 任何 FAIL 或 ERROR
    Evidence: .omo/evidence/task-2-no-regression.txt
  ```

- [x] 3. bootstrap.py:_create_llms() 注入温度参数

  **What to do**:
  - 在 `tradingagents/bootstrap.py:91-150` 中：
    - 第 95 行 `llm_kwargs = {}` 后注入：
      ```python
      from tradingagents.default_config import get_config
      _cfg = get_config()
      llm_kwargs = {
          "temperature": _cfg.get("llm_temperature", 0.0),
          "max_tokens": _cfg.get("llm_max_tokens", 4096),
      }
      ```
    - 第 139-140 行 `deep_client.get_llm()` 和 `quick_client.get_llm()` 调用前，将 `llm_kwargs` 合并到 `create_llm_client` 的 kwargs 中
    - 添加辩论 agent 差异化温度：在 `bootstrap.py` 暴露辩论 agent 用的 LLM 创建接口（参考 FIX-3 模式）

  **Must NOT do**:
  - 不要修改 `_create_llms()` 之外的函数
  - 不要改变 deep_client/quick_client 的实例化流程

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-0 Wave 1（与 Task 1, 2, 4 并行）
  - **Blocks**: Task 5
  - **Blocked By**: None

  **References**:
  - `tradingagents/bootstrap.py:91-150` — `_create_llms()` 完整实现
  - `tradingagents/bootstrap.py:143-149` — `ResilientLLM` 包装逻辑
  - `tradingagents/llm_clients/factory.py:15-63` — `create_llm_client` 工厂

  **Acceptance Criteria**:
  - [ ] Task 1 的 `test_bootstrap_injects_temperature` 测试 PASS
  - [ ] `_create_llms()` 创建的 LLM 实例 `temperature == 0`
  - [ ] 不破坏现有 `test_resilient_llm.py` 测试

  **QA Scenarios**:

  ```
  Scenario: bootstrap 注入温度验证
    Tool: Bash (pytest)
    Preconditions: Task 1 测试已编写，Task 2-3 已实现
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_llm_config.py::test_bootstrap_injects_temperature -v
    Expected Result: PASS
    Failure Indicators: FAIL
    Evidence: .omo/evidence/task-3-bootstrap-injection.txt
  ```

- [x] 4. 4 个 LLM 客户端添加 temperature 和 max_tokens 到 _PASSTHROUGH_KWARGS

  **What to do**:
  - `tradingagents/llm_clients/openai_client.py:204-207`：
    ```python
    _PASSTHROUGH_KWARGS = (
        "timeout", "max_retries", "reasoning_effort",
        "api_key", "callbacks", "http_client", "http_async_client",
        "temperature", "max_tokens",  # ← 新增
    )
    ```
  - `tradingagents/llm_clients/anthropic_client.py:8-11`：
    ```python
    _PASSTHROUGH_KWARGS = (
        "timeout", "max_retries", "api_key", "max_tokens",
        "callbacks", "http_client", "http_async_client", "effort",
        "temperature",  # ← 新增
    )
    ```
  - `tradingagents/llm_clients/azure_client.py:9-12`：
    ```python
    _PASSTHROUGH_KWARGS = (
        "timeout", "max_retries", "api_key", "reasoning_effort",
        "callbacks", "http_client", "http_async_client",
        "temperature", "max_tokens",  # ← 新增
    )
    ```
  - `tradingagents/llm_clients/google_client.py:34`（内联 tuple）：
    ```python
    ("timeout", "max_retries", "callbacks", "http_client", "http_async_client", "temperature", "max_tokens")
    ```

  **Must NOT do**:
  - 不要修改 `get_llm()` 方法本身
  - 不要添加新参数到 ChatOpenAI/ChatAnthropic/etc 构造函数

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-0 Wave 1（与 Task 1, 2, 3 并行）
  - **Blocks**: Task 5
  - **Blocked By**: None

  **References**:
  - `tradingagents/llm_clients/openai_client.py:204-207`
  - `tradingagents/llm_clients/anthropic_client.py:8-11`
  - `tradingagents/llm_clients/azure_client.py:9-12`
  - `tradingagents/llm_clients/google_client.py:34`

  **Acceptance Criteria**:
  - [ ] 4 个 LLM 客户端的 `_PASSTHROUGH_KWARGS`（或 Google 的内联 tuple）都包含 `temperature` 和 `max_tokens`
  - [ ] Task 1 的 `test_openai_client_passes_temperature` 测试 PASS
  - [ ] 现有 `test_resilient_llm.py` 仍通过

  **QA Scenarios**:

  ```
  Scenario: 4 客户端 temperature 透传验证
    Tool: Bash (grep)
    Preconditions: 4 个 client 修复已应用
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -n "temperature" tradingagents/llm_clients/openai_client.py
      3. grep -n "temperature" tradingagents/llm_clients/anthropic_client.py
      4. grep -n "temperature" tradingagents/llm_clients/azure_client.py
      5. grep -n "temperature" tradingagents/llm_clients/google_client.py
    Expected Result: 4 个文件都包含 "temperature" 字样（且在 _PASSTHROUGH_KWARGS 或内联 tuple 内）
    Failure Indicators: 任何文件 grep 无输出
    Evidence: .omo/evidence/task-4-passthrough-kwargs.txt

  Scenario: Client temperature 传递测试
    Tool: Bash (pytest)
    Preconditions: Task 1-4 全部实现
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_llm_config.py -v
    Expected Result: 5 个测试全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-4-test-llm-config.txt
  ```

- [x] 5. 冒烟测试：5 次同输入端到端验证确定性

  **What to do**:
  - 编写 `tests/test_determinism.py`：
    - 用 mock LLM client（conftest 已有 fixture）
    - 同一 ticker "600418"、同一日期 "2026-06-03"、同一 config
    - 调用 5 次 graph 执行（或最低层 analyst 函数）
    - 比对 5 次 `market_report` / `fundamentals_report` 文本的 MD5 hash
  - 断言：5 个 MD5 全部相同（temperature=0 下应完全确定）

  **Must NOT do**:
  - 不要调用真实 LLM（用 mock）
  - 不要依赖外部数据源

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（端到端测试编排）
  - **Skills**: `[]`
  - **Reason**: 需协调 mock、state、多次调用、对结果

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: 单独（依赖 Task 1-4）
  - **Blocks**: PR-1 启动
  - **Blocked By**: Task 1, 2, 3, 4

  **References**:
  - `tests/test_causal_tracer.py:29-53` — `_MockLLM` 自定义 mock 模式
  - `tests/conftest.py:34-42` — `mock_llm_client` fixture
  - `tests/test_debate_routing.py:168-192` — `_make_state` state 构造模式

  **Acceptance Criteria**:
  - [ ] `tests/test_determinism.py` 创建
  - [ ] 5 次同输入调用产出相同 MD5 hash
  - [ ] pytest 通过

  **QA Scenarios**:

  ```
  Scenario: 端到端确定性验证
    Tool: Bash (pytest)
    Preconditions: Task 1-4 实现 + mock LLM 已配置
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_determinism.py -v
    Expected Result: PASS，5 次 MD5 全部相同
    Failure Indicators: FAIL 或 MD5 不一致
    Evidence: .omo/evidence/task-5-determinism.txt
  ```

- [x] 6. 删除 dynamic_graph_builder.py:31 macro_analyst 死代码映射

  **What to do**:
  - `tradingagents/graph/dynamic_graph_builder.py:26-32` 找到 `TOOL_KEY_MAP` 字典
  - 移除 `"macro_analyst": "market"` 条目
  - 同步检查 `ANALYST_AGENTS` 列表（第 44 行附近）是否也包含 `"macro_analyst"`，如有则一并删除
  - 同步搜索：整个代码库 `grep -rn "macro_analyst"` 确认无其他引用

  **Must NOT do**:
  - 不要删除 `"market_analyst": "market"` 等有效映射
  - 不要修改 `TOOL_KEY_MAP` 的其他条目

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-0 Wave 2（与 Task 5 并行，Task 5 是端到端测试可独立）
  - **Blocks**: None
  - **Blocked By**: None（独立清理任务）

  **References**:
  - `tradingagents/graph/dynamic_graph_builder.py:26-32` — TOOL_KEY_MAP
  - `tradingagents/graph/dynamic_graph_builder.py:44` — ANALYST_AGENTS 列表

  **Acceptance Criteria**:
  - [ ] `TOOL_KEY_MAP` 不含 `macro_analyst` 条目
  - [ ] `ANALYST_AGENTS` 不含 `macro_analyst`
  - [ ] `grep -rn "macro_analyst" tradingagents/` 仅返回修复后的代码（如有 graph 引用则不删）

  **QA Scenarios**:

  ```
  Scenario: 死代码删除验证
    Tool: Bash (grep)
    Preconditions: 修复已应用
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rn "macro_analyst" tradingagents/ --include="*.py"
    Expected Result: 仅在文档/注释中可能存在（不应有运行时引用）
    Failure Indicators: TOOL_KEY_MAP 或 ANALYST_AGENTS 中仍存在 macro_analyst 键
    Evidence: .omo/evidence/task-6-dead-code-removed.txt

  Scenario: 现有图构建测试通过
    Tool: Bash (pytest)
    Preconditions: 死代码已删除
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_debate_routing.py -v
    Expected Result: 所有测试 PASS
    Failure Indicators: 任何 FAIL（可能因死代码删除暴露隐藏依赖）
    Evidence: .omo/evidence/task-6-no-graph-regression.txt
  ```

### PR-1：bind_tools / ToolNode 对齐（依赖 PR-0）

- [x] 7. TDD: 编写 failing test 验证 bind_tools/ToolNode 对齐

  **What to do**:
  - 在 `tests/test_agent_tool_binding.py` 新建测试
  - 编写测试：`test_fundamentals_bind_tools_match_toolnode` — 验证 `fundamentals_analyst.py` 的 tools 列表与 `bootstrap.py:193-200` ToolNode 完全一致
  - 编写测试：`test_news_bind_tools_match_toolnode` — 验证 `news_analyst.py` 的 tools 列表与 `bootstrap.py:188-192` ToolNode 完全一致
  - 编写测试：`test_market_bind_tools_match_toolnode` — 验证 market
  - 编写测试：`test_social_bind_tools_match_toolnode` — 验证 social
  - 编写测试：`test_no_hallucinated_tool_calls` — mock LLM 输出 `get_balance_sheet` 工具调用，验证 `filter_valid_tool_calls` 过滤后无错误

  **Must NOT do**:
  - 不要 mock 整个 graph
  - 不要写 e2e 测试（单元 + 集成足够）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-1 Wave 1（与 Task 8, 9 并行）
  - **Blocks**: Task 8, 9
  - **Blocked By**: Task 1-6（PR-0）

  **References**:
  - `tradingagents/agents/analysts/fundamentals_analyst.py:32-34` — 当前 1 工具
  - `tradingagents/agents/analysts/news_analyst.py:29-32` — 当前 2 工具
  - `tradingagents/bootstrap.py:175-201` — ToolNode 注册表
  - `tradingagents/agents/utils/agent_utils.py:303-331` — `filter_valid_tool_calls`

  **Acceptance Criteria**:
  - [ ] `tests/test_agent_tool_binding.py` 创建
  - [ ] 初始 pytest 5 个测试 FAIL（实现前）

  **QA Scenarios**:

  ```
  Scenario: TDD RED 阶段
    Tool: Bash (pytest)
    Preconditions: 测试已写但实现未做
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_agent_tool_binding.py -v
    Expected Result: ≥ 4 个 FAIL
    Failure Indicators: 测试 PASS（说明对齐已就位）
    Evidence: .omo/evidence/task-7-tdd-red.txt
  ```

- [x] 8. 编写 AST 验证脚本 scripts/verify_tool_alignment.py

  **What to do**:
  - 新建 `scripts/verify_tool_alignment.py`：
    - 用 `ast` 模块解析 `tradingagents/agents/analysts/*.py`
    - 提取每个 analyst 的 `tools = [...]` 列表
    - 解析 `tradingagents/bootstrap.py:175-201` 的 ToolNode 注册
    - 对比两者，输出不匹配的工具名
  - 脚本应可独立运行：`python scripts/verify_tool_alignment.py`
  - 退出码：0（无不匹配）/ 1（有不匹配）

  **Must NOT do**:
  - 不要修改其他脚本
  - 不要添加复杂依赖（只用 stdlib + ast）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-1 Wave 1
  - **Blocks**: Task 9
  - **Blocked By**: Task 1-6（PR-0）

  **References**:
  - Python `ast` 模块文档（stdlib）
  - `tradingagents/bootstrap.py:175-201` — ToolNode 模式

  **Acceptance Criteria**:
  - [ ] 脚本创建并可执行
  - [ ] 退出码 0 = 完全对齐
  - [ ] 退出码 1 = 有不匹配 + 输出不匹配详情

  **QA Scenarios**:

  ```
  Scenario: 验证脚本正确性
    Tool: Bash (python script)
    Preconditions: 脚本已编写
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python scripts/verify_tool_alignment.py
      3. echo "Exit code: $?"
    Expected Result: 当前 exit 1（有不匹配），输出显示 fundamentals/news 不匹配详情
    Failure Indicators: exit 0（说明已经对齐了，task 7 测试也会通过）
    Evidence: .omo/evidence/task-8-verify-script.txt
  ```

- [x] 9. bootstrap.py 缩减 ToolNode 至 bind_tools 实际使用（方案 A）

  **What to do**:
  - `tradingagents/bootstrap.py:193-200` 缩减为：
    ```python
    "fundamentals": ToolNode([get_fundamentals]),  # 与 bind_tools 一致
    ```
  - `tradingagents/bootstrap.py:188-192` 缩减为：
    ```python
    "news": ToolNode([get_news, get_global_news]),  # 移除 get_insider_transactions
    ```
  - 移除导入：`get_balance_sheet, get_cashflow, get_income_statement, get_margin_trading, get_institutional_holdings, get_insider_transactions`（如果不再使用）
  - 验证：bootstrap.py 不再 import 已删除的工具

  **Must NOT do**:
  - 不要改 market / social 的 ToolNode（已对齐）
  - 不要在 analysts/*.py 中恢复工具（方案 A 是删 ToolNode，不是扩 bind_tools）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 7, 8）
  - **Parallel Group**: 单独
  - **Blocks**: PR-2 启动
  - **Blocked By**: Task 7, 8

  **References**:
  - `tradingagents/bootstrap.py:175-201` — 完整 ToolNode 段
  - `tradingagents/agents/analysts/fundamentals_analyst.py:32-34` — bind_tools 列表
  - `tradingagents/agents/analysts/news_analyst.py:29-32` — bind_tools 列表

  **Acceptance Criteria**:
  - [ ] `bootstrap.py:193-200` 只剩 `get_fundamentals`
  - [ ] `bootstrap.py:188-192` 只剩 `get_news`, `get_global_news`
  - [ ] Task 7 的 5 个测试全部 PASS
  - [ ] `python scripts/verify_tool_alignment.py` 退出码 0

  **QA Scenarios**:

  ```
  Scenario: 对齐脚本通过
    Tool: Bash (python script)
    Preconditions: bootstrap.py 已修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python scripts/verify_tool_alignment.py
      3. echo "Exit code: $?"
    Expected Result: Exit code: 0
    Failure Indicators: Exit code: 1 或有错误输出
    Evidence: .omo/evidence/task-9-alignment-pass.txt

  Scenario: 单元测试通过
    Tool: Bash (pytest)
    Preconditions: Task 7-9 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_agent_tool_binding.py -v
    Expected Result: 全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-9-binding-tests.txt
  ```

### PR-2：indicator_registry.py 单一真理源（依赖 PR-1）

- [x] 10. TDD: 编写 failing test 验证 indicator_registry

  **What to do**:
  - 在 `tests/test_indicator_registry.py` 新建测试
  - 编写测试：`test_registry_has_all_indicators` — 验证注册表含 `close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr, vwma`（12 个核心）
  - 编写测试：`test_get_indicator_description` — 验证每个指标有 description 字段
  - 编写测试：`test_canonical_name` — 验证 `canonical_name("BB_UPPER") == "boll_ub"`（处理大小写）
  - 编写测试：`test_invalid_indicator_raises` — 验证 `get_indicator("nonexistent")` 抛 ValueError

  **Must NOT do**:
  - 不要引入 vendor 特定映射（akshare vs a_stock_data）— 那是 task 12 的事
  - 不要修改任何数据 vendor 文件

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-2 Wave 1
  - **Blocks**: Task 11, 12, 13
  - **Blocked By**: Task 1-9（PR-0 + PR-1）

  **References**:
  - `tradingagents/dataflows/akshare.py:202-272` — `_INDICATOR_DESCRIPTIONS` (13 个)
  - `tradingagents/dataflows/a_stock_data.py:409-460` — `col_map` (22 个)
  - `tradingagents/agents/analysts/market_analyst.py:46-54` — system prompt 中的 12 指标名
  - `tradingagents/agents/utils/technical_indicators_tools.py:6-32` — get_indicators schema

  **Acceptance Criteria**:
  - [ ] `tests/test_indicator_registry.py` 创建
  - [ ] 初始 4 个测试 FAIL（实现前）

  **QA Scenarios**:

  ```
  Scenario: TDD RED 阶段
    Tool: Bash (pytest)
    Preconditions: 测试已写但实现未做
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_indicator_registry.py -v
    Expected Result: 4 个 FAIL
    Failure Indicators: 测试 PASS（说明注册表已就位）
    Evidence: .omo/evidence/task-10-tdd-red.txt
  ```

- [x] 11. 新建 indicator_registry.py 单一真理源

  **What to do**:
  - 新建 `tradingagents/agents/utils/indicator_registry.py`：
    ```python
    """指标名注册表 — 4 个分散位置的单一真理源。
    
    解决问题：market_analyst system prompt、technical_indicators_tools schema、
    akshare._INDICATOR_DESCRIPTIONS、a_stock_data.col_map 各自硬编码指标名。
    改一个名字需同步 4 处，极易遗漏。注册表统一来源。
    """
    from typing import Dict, NamedTuple
    
    class IndicatorInfo(NamedTuple):
        canonical: str          # 规范名（如 "boll_ub"）
        description: str        # 给 LLM 看的描述
        category: str           # 类别：moving_avg / momentum / volatility / volume
        akshare_key: str        # akshare 实际列名
        a_stock_key: str        # a_stock_data 实际列名
    
    INDICATOR_REGISTRY: Dict[str, IndicatorInfo] = {
        "close_50_sma": IndicatorInfo("close_50_sma", "50 SMA", "moving_avg", "close_50_sma", "close_50_sma"),
        "close_200_sma": IndicatorInfo("close_200_sma", "200 SMA", "moving_avg", "close_200_sma", "close_200_sma"),
        "close_10_ema": IndicatorInfo("close_10_ema", "10 EMA", "moving_avg", "close_10_ema", "close_10_ema"),
        "macd": IndicatorInfo("macd", "MACD line", "momentum", "macd", "macd"),
        "macds": IndicatorInfo("macds", "MACD Signal", "momentum", "macds", "macds"),
        "macdh": IndicatorInfo("macdh", "MACD Histogram", "momentum", "macdh", "macdh"),
        "rsi": IndicatorInfo("rsi", "Relative Strength Index", "momentum", "rsi", "rsi"),
        "boll": IndicatorInfo("boll", "Bollinger Middle", "volatility", "boll", "boll"),
        "boll_ub": IndicatorInfo("boll_ub", "Bollinger Upper", "volatility", "boll_ub", "boll_ub"),
        "boll_lb": IndicatorInfo("boll_lb", "Bollinger Lower", "volatility", "boll_lb", "boll_lb"),
        "atr": IndicatorInfo("atr", "Average True Range", "volatility", "atr", "atr"),
        "vwma": IndicatorInfo("vwma", "Volume-Weighted MA", "volume", "vwma", "vwma"),
    }
    
    def get_indicator(name: str) -> IndicatorInfo:
        """按规范名（不区分大小写）查询。"""
        if not name:
            raise ValueError("indicator name required")
        key = name.lower().strip()
        if key not in INDICATOR_REGISTRY:
            raise ValueError(f"Unknown indicator: {name}. Valid: {list(INDICATOR_REGISTRY.keys())}")
        return INDICATOR_REGISTRY[key]
    
    def list_indicators() -> list[str]:
        """返回所有规范名列表。"""
        return list(INDICATOR_REGISTRY.keys())
    
    def format_indicator_choices() -> str:
        """生成给 LLM 看的"可用指标"清单（用于 system prompt 拼接）。"""
        lines = []
        for name, info in INDICATOR_REGISTRY.items():
            lines.append(f"- {name} ({info.description})")
        return "\n".join(lines)
    ```

  **Must NOT do**:
  - 不要让其他文件硬编码指标名（在 task 12-13 改）
  - 不要引入复杂继承或抽象类（保持简单）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 10）
  - **Parallel Group**: 单独
  - **Blocks**: Task 12, 13
  - **Blocked By**: Task 10

  **References**:
  - `tradingagents/dataflows/akshare.py:202-272` — 当前 13 个指标
  - `tradingagents/dataflows/a_stock_data.py:409-460` — 当前 22 个映射

  **Acceptance Criteria**:
  - [ ] `tradingagents/agents/utils/indicator_registry.py` 创建
  - [ ] 12 个核心指标全部入册
  - [ ] `get_indicator()`, `list_indicators()`, `format_indicator_choices()` 三个函数可用
  - [ ] Task 10 的 4 个测试 PASS

  **QA Scenarios**:

  ```
  Scenario: 注册表查询验证
    Tool: Bash (python -c)
    Preconditions: 注册表已实现
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "from tradingagents.agents.utils.indicator_registry import get_indicator, list_indicators; assert len(list_indicators()) == 12; info = get_indicator('boll_ub'); assert info.canonical == 'boll_ub'; print('PASS')"
    Expected Result: 输出 "PASS"
    Failure Indicators: ImportError, AssertionError
    Evidence: .omo/evidence/task-11-registry-queries.txt

  Scenario: 注册表测试通过
    Tool: Bash (pytest)
    Preconditions: Task 10-11 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_indicator_registry.py -v
    Expected Result: 全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-11-registry-tests.txt
  ```

- [x] 12. akshare 和 a_stock_data 改为从注册表导入

  **What to do**:
  - `tradingagents/dataflows/akshare.py:202-272`：
    - 移除 `_INDICATOR_DESCRIPTIONS` 硬编码 dict
    - 改为：
      ```python
      from tradingagents.agents.utils.indicator_registry import INDICATOR_REGISTRY
      _INDICATOR_DESCRIPTIONS = {k: v.description for k, v in INDICATOR_REGISTRY.items()}
      ```
  - `tradingagents/dataflows/a_stock_data.py:409-460`：
    - 移除 `col_map` 硬编码 dict
    - 改为：
      ```python
      from tradingagents.agents.utils.indicator_registry import INDICATOR_REGISTRY
      col_map = {k: v.a_stock_key for k, v in INDICATOR_REGISTRY.items()}
      ```
  - 验证：a_stock_data 还有 22 个映射（其他 10 个是非核心指标），保留但**不通过注册表管理**（仅这 12 个核心走注册表）

  **Must NOT do**:
  - 不要删除 a_stock_data 的非核心映射（kdj_*, sma_* 等）
  - 不要改动 get_indicators 的实际数据获取逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 13 并行）
  - **Parallel Group**: PR-2 Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 11

  **References**:
  - `tradingagents/dataflows/akshare.py:202-272` — 现状
  - `tradingagents/dataflows/a_stock_data.py:409-460` — 现状

  **Acceptance Criteria**:
  - [ ] `_INDICATOR_DESCRIPTIONS` 和 `col_map` 12 个核心键来自注册表
  - [ ] 现有 `test_a_stock_data.py` 测试仍通过
  - [ ] 现有 `test_akshare.py`（如有）通过

  **QA Scenarios**:

  ```
  Scenario: 数据 vendor 回归
    Tool: Bash (pytest)
    Preconditions: Task 12 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_a_stock_data.py tests/test_a_share.py -v
    Expected Result: 全部 PASS（无新 FAIL）
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-12-vendor-regression.txt
  ```

- [x] 13. system prompt 和 tool schema 改为从注册表读取

  **What to do**:
  - `tradingagents/agents/analysts/market_analyst.py:46-54`：
    - 替换硬编码 12 个指标名为：
      ```python
      from tradingagents.agents.utils.indicator_registry import format_indicator_choices
      system_message = (
          f"""You are a trading assistant...from the following list:
      {format_indicator_choices()}
      ..."""
      )
      ```
  - `tradingagents/agents/utils/technical_indicators_tools.py:6-32`：
    - 修改 `get_indicators` 工具的 `indicator` 参数 description：
      ```python
      indicator: Annotated[str, f"technical indicator to query. Valid: {', '.join(list_indicators())}"]
      ```

  **Must NOT do**:
  - 不要改动 `get_indicators` 的函数签名（除 description）
  - 不要改动 market_analyst 的其他 prompt 内容

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 12 并行）
  - **Parallel Group**: PR-2 Wave 2
  - **Blocks**: PR-3 启动
  - **Blocked By**: Task 11

  **References**:
  - `tradingagents/agents/analysts/market_analyst.py:46-54` — 现状
  - `tradingagents/agents/utils/technical_indicators_tools.py:6-32` — 现状

  **Acceptance Criteria**:
  - [ ] market_analyst 的 system prompt 不含硬编码指标名
  - [ ] get_indicators 工具 description 含 12 个核心指标
  - [ ] 现有 `test_a_share.py` 等通过

  **QA Scenarios**:

  ```
  Scenario: System prompt 改造验证
    Tool: Bash (grep)
    Preconditions: Task 13 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -c "close_50_sma\|close_200_sma" tradingagents/agents/analysts/market_analyst.py
    Expected Result: 0（说明已从注册表读取，不再硬编码）
    Failure Indicators: > 0（说明仍硬编码）
    Evidence: .omo/evidence/task-13-no-hardcoded.txt
  ```

### PR-3：全局防幻觉指令（依赖 PR-2 的 indicator_registry）

- [x] 14. TDD: 编写 failing test 验证中英双语防幻觉指令

  **What to do**:
  - 在 `tests/test_anti_hallucination.py` 新建测试
  - 编写测试：`test_chinese_anti_hallucination_nonempty` — 验证 `get_anti_hallucination_instruction(lang="Chinese")` 返回非空字符串
  - 编写测试：`test_english_anti_hallucination_nonempty` — 验证 English 模式也返回非空字符串（**关键修复点**）
  - 编写测试：`test_contains_keyword_data_unavailable` — 验证防幻觉文本含 `[数据不可用]` / `[Data Unavailable]`
  - 编写测试：`test_contains_tool_only_constraint` — 验证含"only use tools" / "只使用"
  - 编写测试：`test_degradation_english_nonempty` — 验证 `get_degradation_instruction()` 在 English 模式下也返回非空（关键修复）

  **Must NOT do**:
  - 不要测试 LLM 的实际推理行为
  - 不要在测试中构造完整 prompt

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-3 Wave 1
  - **Blocks**: Task 15, 16, 17, 18
  - **Blocked By**: Task 1-13（PR-0+PR-1+PR-2）

  **References**:
  - `tradingagents/agents/utils/agent_utils.py:52-67` — 当前 `get_degradation_instruction`
  - `docs/工业级质量差距全面诊断.md:480-517` — 5.3 防幻觉指令示例代码

  **Acceptance Criteria**:
  - [ ] `tests/test_anti_hallucination.py` 创建
  - [ ] 5 个测试初始 FAIL

  **QA Scenarios**:

  ```
  Scenario: TDD RED 阶段
    Tool: Bash (pytest)
    Preconditions: 测试已写但实现未做
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_anti_hallucination.py -v
    Expected Result: ≥ 4 个 FAIL（English 模式当前返回空字符串是已知 bug）
    Failure Indicators: 全部 PASS（说明已经修复了）
    Evidence: .omo/evidence/task-14-tdd-red.txt
  ```

- [x] 15. 新建 prompt_constants.py 全局常量文件

  **What to do**:
  - 新建 `tradingagents/agents/utils/prompt_constants.py`：
    ```python
    """全局 prompt 常量 — 防幻觉、结构化输出约束。
    
    关键修复：English 模式下也返回防幻觉文本（原 get_degradation_instruction 仅中文模式生效）。
    """
    from tradingagents.dataflows.config import get_config
    from tradingagents.agents.utils.indicator_registry import list_indicators
    
    INDICATOR_CHOICES = ", ".join(list_indicators())
    
    def get_anti_hallucination_instruction(agent_type: str = "analyst") -> str:
        """全局防幻觉指令，注入所有 12 个 agent 的 system_message。
        
        Args:
            agent_type: "analyst" / "debate" / "decision"（控制约束强度）
        """
        cfg = get_config()
        lang = cfg.get("output_language", "Chinese")
        
        if lang == "Chinese":
            base = """
    **【防幻觉约束 — 必须严格遵守】**
    
    1. **只使用 bind_tools 列出的工具**。禁止调用未列出的工具名。
    2. **数据缺失必须明确标注**。如果某项数据未获取到，写"[数据不可用]"而非编造。
    3. **每个结论必须有工具输出引用**。在报告末尾的"数据来源"部分列出引用的工具名。
    4. **不得编造财务指标**。所有数字必须来自工具的真实输出。
    5. **A 股分析禁止引用非中国市场的行业术语**。如出现 EPA 2027/Class 8/ACT Research 等美股/欧股术语，立即修正为 A 股对应概念。
    """
        else:
            base = """
    **【Anti-Hallucination Constraints — MANDATORY】**
    
    1. Use ONLY tools listed in bind_tools. Never invent tool names.
    2. If data is missing, state "[Data Unavailable]" — never fabricate.
    3. Every claim must reference specific tool output.
    4. Never fabricate financial metrics. All numbers must come from tool outputs.
    5. Do not inject non-target-market industry knowledge.
    """
        
        # 辩论 agent 用轻量化版（ADR 选项 B）
        if agent_type == "debate":
            if lang == "Chinese":
                base += "\n6. **不要发明新数字**，只引用分析师报告中的数据。\n"
            else:
                base += "\n6. **Do not invent new numbers**; only cite analyst reports.\n"
        
        return base
    
    def get_language_instruction() -> str:
        """报告语言指令。"""
        cfg = get_config()
        lang = cfg.get("output_language", "Chinese")
        if lang == "Chinese":
            return "\n**【报告语言】**：整篇报告必须用中文书写，禁止中英文混用。\n"
        return "\n**【Report Language】**: Write entire report in English.\n"
    ```

  **Must NOT do**:
  - 不要让 `agent_type` 参数影响中英双语的语言选择（语言由 config 决定）
  - 不要在此文件中导入任何业务 agent（只导入纯工具/常量）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-3 Wave 1
  - **Blocks**: Task 16, 17, 18
  - **Blocked By**: Task 14

  **References**:
  - `docs/工业级质量差距全面诊断.md:480-517` — 模板代码
  - `tradingagents/agents/utils/indicator_registry.py` — INDICATOR_CHOICES 来源

  **Acceptance Criteria**:
  - [ ] `tradingagents/agents/utils/prompt_constants.py` 创建
  - [ ] 中英双语都有防幻觉文本
  - [ ] `agent_type="debate"` 触发轻量化版
  - [ ] Task 14 的 5 个测试 PASS

  **QA Scenarios**:

  ```
  Scenario: 双语防幻觉非空验证
    Tool: Bash (python -c)
    Preconditions: 文件已实现
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
    from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
    cn = get_anti_hallucination_instruction('analyst')
    en = get_anti_hallucination_instruction('analyst') if False else get_anti_hallucination_instruction('analyst')
    # 临时切换 lang
    import os; os.environ['OUTPUT_LANGUAGE']='English'
    en = get_anti_hallucination_instruction('analyst')
    assert len(cn) > 50 and len(en) > 50, f'cn={len(cn)} en={len(en)}'
    assert '数据不可用' in cn or '编造' in cn
    assert 'fabricate' in en or 'Data Unavailable' in en
    print('PASS')
    "
    Expected Result: 输出 "PASS"
    Failure Indicators: AssertionError, KeyError
    Evidence: .omo/evidence/task-15-bilingual.txt
  ```

- [x] 16. 修复 get_degradation_instruction() 中英双语

  **What to do**:
  - `tradingagents/agents/utils/agent_utils.py:52-67` 重构为：
    ```python
    def get_degradation_instruction() -> str:
        """降级策略 + 防幻觉约束（v0.2.15-cn 修复 English 模式）。"""
        from tradingagents.dataflows.config import get_config
        lang = (get_config().get("output_language") or "Chinese")
        
        if lang.strip().lower() == "english":
            return (
                " Degradation policy: If a data source returns empty or is unavailable, "
                "explicitly mark the data limitation in the report and provide limited analysis based on available information. "
                "Do not fabricate data or invent information that was not obtained. "
                "If critical data is missing and effective conclusion cannot be formed, "
                "be honest and recommend deferring the decision."
            )
        return (
            " 降级策略：若数据源返回空或不可用，请在报告中明确标注数据局限性，"
            "并基于已有信息提供有限分析。不得编造数据或虚构未获取到的信息。"
            "若关键数据缺失导致无法形成有效结论，应坦诚告知并建议延后决策。"
        )
    ```
  - 关键：English 模式也必须返回完整约束

  **Must NOT do**:
  - 不要删除现有中文模式的行为
  - 不要改变函数签名

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（跨语言语义一致性要求高）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 15）
  - **Parallel Group**: 单独
  - **Blocks**: Task 17, 18
  - **Blocked By**: Task 14, 15

  **References**:
  - `tradingagents/agents/utils/agent_utils.py:52-67` — 现状

  **Acceptance Criteria**:
  - [ ] English 模式返回非空字符串（关键修复点）
  - [ ] 中文模式行为不变
  - [ ] Task 14 的 `test_degradation_english_nonempty` PASS

  **QA Scenarios**:

  ```
  Scenario: English 模式非空
    Tool: Bash (python -c)
    Preconditions: Task 16 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
    import os; os.environ['OUTPUT_LANGUAGE']='English'
    from tradingagents.agents.utils.agent_utils import get_degradation_instruction
    result = get_degradation_instruction()
    assert len(result) > 50, f'too short: {len(result)}'
    assert 'fabricate' in result.lower() or 'unavailable' in result.lower()
    print('PASS')
    "
    Expected Result: 输出 "PASS"
    Failure Indicators: 短字符串（<50）或缺关键词
    Evidence: .omo/evidence/task-16-english-degradation.txt
  ```

- [x] 17. 7 个非辩论 agent 注入防幻觉指令（4 分析师 + RM + Trader + PM）

  **What to do**:
  - `tradingagents/agents/analysts/market_analyst.py`、`fundamentals_analyst.py`、`news_analyst.py`、`social_media_analyst.py`：
    - 找到 `system_message` 拼接位置
    - 在 `get_degradation_instruction()` 之前或之后加入：
      ```python
      from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
      system_message = base + get_anti_hallucination_instruction("analyst") + get_degradation_instruction() + industry_guidance
      ```
  - 同样处理 `research_manager.py`、`trader.py`、`portfolio_manager.py`
  - 删除 `fundamentals_analyst.py:37` 和 `news_analyst.py:35` 的 `"Make sure to include as much detail as possible"`（鼓励幻觉措辞）
  - 同样处理 `market_analyst.py:54` 的 `"Write a very detailed and nuanced report"`

  **Must NOT do**:
  - 不要修改 `system_message` 的非防幻觉部分
  - 不要重复拼接（只能调用一次 get_anti_hallucination_instruction）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（7 个文件改动，需保持一致性）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（4 个 analyst 可并行）
  - **Parallel Group**: PR-3 Wave 2
  - **Blocks**: Task 18
  - **Blocked By**: Task 15, 16

  **References**:
  - `tradingagents/agents/analysts/fundamentals_analyst.py:37` — "Make sure to include"
  - `tradingagents/agents/analysts/news_analyst.py:35` — 同上
  - `tradingagents/agents/analysts/market_analyst.py:54` — "Write a very detailed"
  - `tradingagents/agents/managers/research_manager.py:14` — system_message 位置
  - `tradingagents/agents/trader/trader.py:20` — system_message 位置
  - `tradingagents/agents/managers/portfolio_manager.py:32` — system_message 位置

  **Acceptance Criteria**:
  - [ ] 7 个 agent 文件全部 import `get_anti_hallucination_instruction`
  - [ ] 3 个"鼓励幻觉"措辞被删除
  - [ ] 现有测试不破坏

  **QA Scenarios**:

  ```
  Scenario: 7 agent 防幻觉注入验证
    Tool: Bash (grep)
    Preconditions: Task 17 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rln "get_anti_hallucination_instruction" tradingagents/agents/{analysts,researchers,risk_mgmt,managers,trader}/*.py | wc -l
    Expected Result: ≥ 7（4 分析师 + 2 manager + 1 trader；辩论 agent 在 task 18）
    Failure Indicators: < 7
    Evidence: .omo/evidence/task-17-seven-agents.txt

  Scenario: 鼓励幻觉措辞已删除
    Tool: Bash (grep)
    Preconditions: Task 17 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -n "Make sure to include as much detail" tradingagents/agents/analysts/*.py
      3. grep -n "Write a very detailed and nuanced" tradingagents/agents/analysts/*.py
    Expected Result: 无输出
    Failure Indicators: 任何匹配
    Evidence: .omo/evidence/task-17-no-encouraging.txt
  ```

- [x] 18. 5 个辩论/风控 agent 加轻量防幻觉（ADR 选项 B）

  **What to do**:
  - `tradingagents/agents/researchers/bull_researcher.py`、`bear_researcher.py`：
    - 找到 system_message 拼接处
    - 在末尾加入：
      ```python
      from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
      system_message = base + get_anti_hallucination_instruction("debate") + industry_guidance
      ```
  - 同样处理 `aggressive_debator.py`、`conservative_debator.py`、`neutral_debator.py`
  - 关键：使用 `"debate"` 参数触发轻量化版

  **Must NOT do**:
  - 不要对辩论 agent 应用 Pydantic schema（**必须遵守**）
  - 不要删除现有 `bull_researcher.py:44` 的 industry 锚定和 `行 48-49` 的反模式约束

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（5 个文件，需轻量约束保持辩论质量）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-3 Wave 2（与 Task 17 并行）
  - **Blocks**: PR-4 启动
  - **Blocked By**: Task 15, 16

  **References**:
  - `tradingagents/agents/researchers/bull_researcher.py:51-86` — system_message
  - `tradingagents/agents/researchers/bear_researcher.py:51-78` — system_message
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py` — system_message
  - `docs/工业级质量差距全面诊断.md:154-204` — ADR 选项 B 决策分析

  **Acceptance Criteria**:
  - [ ] 5 个辩论/风控 agent 注入 `get_anti_hallucination_instruction("debate")`
  - [ ] 不删除 industry 锚定和反模式约束
  - [ ] 测试通过

  **QA Scenarios**:

  ```
  Scenario: 5 辩论 agent 防幻觉注入
    Tool: Bash (grep)
    Preconditions: Task 18 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rln 'get_anti_hallucination_instruction."debate"\|get_anti_hallucination_instruction..debate..' tradingagents/agents/{researchers,risk_mgmt}/*.py | wc -l
    Expected Result: ≥ 5
    Failure Indicators: < 5
    Evidence: .omo/evidence/task-18-debate-agents.txt
  ```

### PR-4：IndustryVerifier 扩展（依赖 PR-3 的稳定 prompt 拼接）

- [x] 19. TDD: 编写 failing test 验证 industry benchmark 和数字溯源

  **What to do**:
  - 在 `tests/test_verifier_extended.py` 新建测试
  - 编写测试：`test_industry_benchmark_unreferenced` — 报告含"行业平均 PE 50"等 benchmark 但 tool 输出无此数据，应返回 WARN
  - 编写测试：`test_financial_metric_traced_to_tool_output` — 报告含"PE 30.5" 且 tool 输出确实有 30.5，应 PASS
  - 编写测试：`test_financial_metric_not_in_tool_output` — 报告含"PE 25" 但 tool 输出无此数据，应 WARN
  - 编写测试：`test_english_mode_hallucination_terms` — 报告含"EPA 2027"，应 FAIL（与 `test_industry_classifier.py` 集成）
  - 编写测试：`test_cross_report_contradiction` — market_report 看涨 + fundamentals_report 看跌，应 WARN

  **Must NOT do**:
  - 不要 mock IndustryVerifier 自身（要测真实逻辑）
  - 不要把 verifier 改成会抛出异常（应优雅降级）

  **Recommended Agent Profile**:
  - **Category**: `deep`（多维度验证逻辑）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-4 Wave 1
  - **Blocks**: Task 20, 21
  - **Blocked By**: Task 1-18（PR-0+PR-1+PR-2+PR-3）

  **References**:
  - `tradingagents/industry/verifier.py:38-106` — `verify_industry_consistency` 现状
  - `tests/test_industry_classifier.py` — 现有验证器测试模式

  **Acceptance Criteria**:
  - [ ] `tests/test_verifier_extended.py` 创建
  - [ ] 5 个测试初始 FAIL

  **QA Scenarios**:

  ```
  Scenario: TDD RED
    Tool: Bash (pytest)
    Preconditions: 测试已写但实现未做
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_verifier_extended.py -v
    Expected Result: ≥ 4 个 FAIL
    Failure Indicators: 全部 PASS
    Evidence: .omo/evidence/task-19-tdd-red.txt
  ```

- [x] 20. verifier.py 添加 industry benchmark 检查

  **What to do**:
  - `tradingagents/industry/verifier.py:38-106` 扩展 `verify_industry_consistency`：
    - 在 Tier 1（规则层）后增加 Tier 1.5：行业 benchmark 检测
    - 检测模式：报告含"行业平均 X"、"industry average X"、"market PE is ~X" 等无来源断言
    - 对比：与 `state` 中所有 tool_message 内容比对
    - 命中但未在 tool_message 中出现 → 返回 `severity="warning"`, `method="benchmark_unreferenced"`
  - 返回结构增加 `benchmarks_unreferenced: List[str]` 字段

  **Must NOT do**:
  - 不要删除现有 Tier 1/2 逻辑
  - 不要让 LLM 调用成为 Tier 1.5 的必要部分（保持规则层快速）

  **Recommended Agent Profile**:
  - **Category**: `deep`（需要正则 + state 比对逻辑）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 21 并行）
  - **Parallel Group**: PR-4 Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 19

  **References**:
  - `tradingagents/industry/verifier.py:38-106` — 现状
  - LangGraph state structure（参考 `graph/state.py`）

  **Acceptance Criteria**:
  - [ ] `verify_industry_consistency` 返回结构含 `benchmarks_unreferenced` 字段
  - [ ] Tier 1.5 不调用 LLM（保持快速）
  - [ ] Task 19 的 `test_industry_benchmark_unreferenced` PASS

  **QA Scenarios**:

  ```
  Scenario: Benchmark 检测
    Tool: Bash (pytest)
    Preconditions: Task 20 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_verifier_extended.py::test_industry_benchmark_unreferenced -v
    Expected Result: PASS
    Failure Indicators: FAIL
    Evidence: .omo/evidence/task-20-benchmark.txt
  ```

- [x] 21. verifier.py 添加数字溯源检查

  **What to do**:
  - `tradingagents/industry/verifier.py:38-106` 扩展：
    - 在 Tier 1.5 之后增加 Tier 1.6：数字溯源
    - 提取报告中的所有数字（PE、营收、净利润等）
    - 在 `state["messages"]` 的所有 `ToolMessage.content` 中搜索该数字
    - 未找到 → 加入 `untraced_numbers` 列表
    - 返回 `severity="warning"`, `method="number_untraced"`
  - 注意：避免过度敏感（"2026"年份不应被标记）
  - 用正则 `\b\d+\.?\d*\b` 提取数字，过滤年份、百分比、整数 ID

  **Must NOT do**:
  - 不要把年份（2024-2030）和整数 ID 标记为 untraced
  - 不要修改 Tier 1 行业术语检测

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（正则 + 上下文过滤）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 20 并行）
  - **Parallel Group**: PR-4 Wave 2
  - **Blocks**: PR-5 启动
  - **Blocked By**: Task 19

  **References**:
  - `tradingagents/industry/verifier.py:38-106` — 现状
  - LangChain `ToolMessage` 文档（用于 content 提取）

  **Acceptance Criteria**:
  - [ ] 数字溯源检测可用
  - [ ] 年份和整数 ID 不被误报
  - [ ] Task 19 的 `test_financial_metric_traced_to_tool_output` 和 `test_financial_metric_not_in_tool_output` PASS

  **QA Scenarios**:

  ```
  Scenario: 数字溯源测试
    Tool: Bash (pytest)
    Preconditions: Task 21 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_verifier_extended.py::test_financial_metric_traced_to_tool_output tests/test_verifier_extended.py::test_financial_metric_not_in_tool_output -v
    Expected Result: 全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-21-number-trace.txt
  ```

### PR-5：Pydantic Schema 扩展到 4 个分析师（依赖 PR-4）

- [x] 22. TDD: 编写 failing test 验证 Pydantic schema 化

  **What to do**:
  - 在 `tests/test_analyst_schemas.py` 新建测试
  - 编写测试：`test_market_schema_exists` — 验证 `MarketReport` schema 在 `schemas.py` 定义
  - 编写测试：`test_market_analyst_uses_structured_output` — 验证 `market_analyst.py` 使用 `with_structured_output(MarketReport)` 或 `bind_structured`
  - 编写测试：`test_debate_agents_no_structured_output` — **关键 Guardrail**：验证 5 个辩论/风控 agent **不**使用 `with_structured_output`
  - 编写测试：`test_schema_validation` — 验证 MarketReport 接受合法输入并拒绝非法

  **Must NOT do**:
  - 不要为辩论 agent 添加 Pydantic schema（**关键 Guardrail**）
  - 不要改动 trader / RM / PM 的现有 schema（已在 task 5.x 实施）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: PR-5 Wave 1
  - **Blocks**: Task 23, 24
  - **Blocked By**: Task 1-21（PR-0 ~ PR-4）

  **References**:
  - `tradingagents/agents/schemas.py:32-242` — 现有 Pydantic models
  - `tradingagents/agents/utils/structured.py` — `bind_structured` 工具
  - `tradingagents/agents/managers/portfolio_manager.py:32` — `bind_structured` 使用示例

  **Acceptance Criteria**:
  - [ ] `tests/test_analyst_schemas.py` 创建
  - [ ] 4 个测试初始 FAIL

  **QA Scenarios**:

  ```
  Scenario: TDD RED
    Tool: Bash (pytest)
    Preconditions: 测试已写但实现未做
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_analyst_schemas.py -v
    Expected Result: ≥ 3 个 FAIL
    Failure Indicators: 全部 PASS
    Evidence: .omo/evidence/task-22-tdd-red.txt
  ```

- [x] 23. schemas.py 添加 4 个分析师 Pydantic schema

  **What to do**:
  - `tradingagents/agents/schemas.py` 末尾添加：
    ```python
    class MarketReport(BaseModel):
        """技术面分析师结构化输出。"""
        ticker: str
        analysis_date: str
        trend: Literal["bullish", "bearish", "neutral"]
        indicators_used: List[str]
        key_findings: List[str]
        markdown_body: str
    
    class FundamentalsReport(BaseModel):
        ticker: str
        analysis_date: str
        financial_health: Literal["strong", "moderate", "weak"]
        key_metrics: Dict[str, float]
        key_findings: List[str]
        markdown_body: str
    
    class NewsReport(BaseModel):
        ticker: str
        analysis_date: str
        sentiment: Literal["positive", "negative", "neutral"]
        key_events: List[str]
        markdown_body: str
    
    class SocialReport(BaseModel):
        ticker: str
        analysis_date: str
        sentiment: Literal["bullish", "bearish", "neutral"]
        hot_topics: List[str]
        markdown_body: str
    ```
  - 添加 `render_market_report()`、`render_fundamentals_report()` 等 markdown 渲染函数

  **Must NOT do**:
  - 不要修改 `ResearchPlan`、`TraderProposal`、`PortfolioDecision` 现有 schema
  - 不要让 schema 过于严格（应允许部分字段为空）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 22）
  - **Parallel Group**: 单独
  - **Blocks**: Task 24
  - **Blocked By**: Task 22

  **References**:
  - `tradingagents/agents/schemas.py:32-105` — 现有 `ResearchPlan` 模式
  - `tradingagents/agents/schemas.py:97-105` — `render_research_plan` 模式

  **Acceptance Criteria**:
  - [ ] 4 个 Pydantic schema 定义
  - [ ] 4 个 render 函数
  - [ ] Task 22 的 `test_market_schema_exists` 和 `test_schema_validation` PASS

  **QA Scenarios**:

  ```
  Scenario: Schema 定义验证
    Tool: Bash (pytest)
    Preconditions: Task 23 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_analyst_schemas.py::test_market_schema_exists tests/test_analyst_schemas.py::test_schema_validation -v
    Expected Result: 全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-23-schemas.txt
  ```

- [x] 24. 4 个分析师接入 with_structured_output

  **What to do**:
  - `tradingagents/agents/analysts/market_analyst.py:94`：
    - 替换 `chain = prompt | llm.bind_tools(tools)` 为：
      ```python
      from tradingagents.agents.utils.structured import bind_structured
      from tradingagents.agents.schemas import MarketReport
      structured_llm = bind_structured(llm, MarketReport)
      chain = prompt | structured_llm
      ```
    - 保留 `bind_tools` 但移到不同的链：`tools_chain = prompt | llm.bind_tools(tools)` 用于工具调用
  - 同样处理 `fundamentals_analyst.py`、`news_analyst.py`、`social_media_analyst.py`
  - **关键**：处理 fallback 路径（DeepSeek V4 Pro 在 `with_structured_output` 失败时回退到 free-text parsing，参考 `structured.py` 的 `invoke_structured_or_freetext`）

  **Must NOT do**:
  - 不要删除 `bind_tools` 调用（两套机制并存：tools_chain 和 structured_chain）
  - 不要对辩论 agent 做同样修改（**Guardrail**）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`（schema 迁移 + fallback 处理）
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO（依赖 Task 23）
  - **Parallel Group**: 单独
  - **Blocks**: Final Verification Wave
  - **Blocked By**: Task 22, 23

  **References**:
  - `tradingagents/agents/utils/structured.py` — `bind_structured`, `invoke_structured_or_freetext`
  - `tradingagents/agents/managers/portfolio_manager.py:32` — 现有 bind_structured 用法
  - `tests/test_structured_agents.py` — 结构化输出测试模式

  **Acceptance Criteria**:
  - [ ] 4 个 analyst 文件使用 `bind_structured(llm, <Schema>)`
  - [ ] 保留 `bind_tools` 调用（两套机制并存）
  - [ ] Task 22 的 `test_market_analyst_uses_structured_output` 和 `test_debate_agents_no_structured_output` PASS
  - [ ] 现有 `test_structured_agents.py` 通过

  **QA Scenarios**:

  ```
  Scenario: 4 分析师结构化输出
    Tool: Bash (pytest)
    Preconditions: Task 24 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_analyst_schemas.py tests/test_structured_agents.py -v
    Expected Result: 全部 PASS
    Failure Indicators: 任何 FAIL
    Evidence: .omo/evidence/task-24-structured-output.txt

  Scenario: 辩论 agent 无 schema（Guardrail 验证）
    Tool: Bash (grep)
    Preconditions: Task 24 完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rln "bind_structured\|with_structured_output" tradingagents/agents/{researchers,risk_mgmt}/*.py
    Expected Result: 无输出（辩论/风控 agent 不应有 schema）
    Failure Indicators: 任何文件含 bind_structured
    Evidence: .omo/evidence/task-24-no-debate-schema.txt
  ```

---

## Final Verification Wave (MANDATORY)

- [x] F1. **Plan Compliance Audit** — `oracle`

  **What to do**:
  - 通读 `.omo/plans/industrial-quality-fix.md` 全部 24 个 TODO
  - 对每个 "Must Have" 项验证实现存在（读文件、grep 命令、运行 pytest）
  - 对每个 "Must NOT Have" 项搜索代码库验证未引入（grep 反模式）
  - 检查 24 个任务的 evidence 文件存在：`.omo/evidence/task-{1..24}-*.{txt,log}`
  - 输出结构化报告：`Must Have [N/6] | Must NOT Have [N/8] | Tasks [N/24] | VERDICT`

  **Must NOT do**:
  - 不要修改任何代码（oracle 是 read-only）
  - 不要批准任何 Must Have 不达标的任务

  **Recommended Agent Profile**:
  - **Category**: `oracle`
  - **Skills**: `[]`
  - **Reason**: 只读审计 + 规则对照检查

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 F2/F3/F4 同时）
  - **Parallel Group**: Final Wave
  - **Blocks**: 交付给用户
  - **Blocked By**: 全部 24 个 TODO 完成

  **References**:
  - `.omo/plans/industrial-quality-fix.md:84-101` — Must Have / Must NOT Have 列表
  - `.omo/evidence/` — 全部任务的 evidence 文件目录

  **Acceptance Criteria**:
  - [ ] Must Have 6 项全部 PASS（temperature/bind_tools/防幻觉/Pydantic schema/测试覆盖/差异温度）
  - [ ] Must NOT Have 8 项全部 PASS（无辩论 schema/无跳过 English/无无 TDD 实现/无基线未稳修改/无单一温度/无 passthrough 遗漏/无硬编码指标/无回滚粒度混淆）
  - [ ] 24 个任务的 evidence 文件全数存在
  - [ ] 输出 VERDICT: APPROVE

  **QA Scenarios**:

  ```
  Scenario: Must Have 6 项全检查
    Tool: Bash (组合命令)
    Preconditions: 全部 24 个 TODO 已完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "from tradingagents.default_config import DEFAULT_CONFIG; assert DEFAULT_CONFIG['llm_temperature']==0.0"
      3. python scripts/verify_tool_alignment.py; echo "Exit: $?"
      4. grep -rln "get_anti_hallucination_instruction" tradingagents/agents/ | wc -l
      5. grep -rln "bind_structured" tradingagents/agents/analysts/ | wc -l
      6. pytest --cov=tradingagents --cov-fail-under=70 tests/ -v | tail -20
      7. grep -n "llm_debate_temperature" tradingagents/default_config.py
    Expected Result: 全部命令成功（exit 0 / 计数 ≥ 7 / 覆盖率 ≥ 70%）
    Failure Indicators: 任何命令失败或计数不达标
    Evidence: .omo/evidence/f1-compliance-check.txt

  Scenario: Must NOT Have 8 项全检查
    Tool: Bash (组合命令)
    Preconditions: 全部 24 个 TODO 已完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rln "bind_structured\|with_structured_output" tradingagents/agents/{researchers,risk_mgmt}/*.py
      3. python -c "import os; os.environ['OUTPUT_LANGUAGE']='English'; from tradingagents.agents.utils.agent_utils import get_degradation_instruction; r=get_degradation_instruction(); assert len(r)>50"
      4. grep -c "Make sure to include as much detail" tradingagents/agents/analysts/*.py
      5. grep -n "temperature" tradingagents/llm_clients/google_client.py
      6. grep -n "macro_analyst" tradingagents/graph/dynamic_graph_builder.py
    Expected Result: 步骤 2、4、6 无输出；步骤 3、5 成功
    Failure Indicators: 任何反模式出现
    Evidence: .omo/evidence/f1-must-not-have.txt
  ```

- [x] F2. **Code Quality Review** — `unspecified-high`

  **What to do**:
  - 运行 `pytest --cov=tradingagents --cov-fail-under=70 tests/ -v` 确认全绿
  - 运行 `ruff check tradingagents/` 和 `mypy tradingagents/`（如有）
  - 审查 24 个任务涉及的所有改动文件：
    - 搜索 `as any` / `@ts-ignore`（Python 风格：`# type: ignore` 无理由）
    - 搜索空 `except:` 子句
    - 搜索生产代码 `print()` 调试语句
    - 搜索 `TODO` / `FIXME` 残留
    - 搜索未使用 import
  - AI slop 检测：过度注释、过度抽象、通用名（`data`/`result`/`item`/`temp`）
  - 输出报告：`Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

  **Must NOT do**:
  - 不要修改代码（reviewer 只读）
  - 不要批准任何 lint 错误或测试失败

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`
  - **Reason**: 多维度代码质量审查

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 F1/F3/F4 同时）
  - **Parallel Group**: Final Wave
  - **Blocks**: 交付给用户
  - **Blocked By**: 全部 24 个 TODO 完成

  **References**:
  - `pyproject.toml:56-66` — pytest 配置
  - `.github/workflows/test.yml:29-31` — CI 命令基线

  **Acceptance Criteria**:
  - [ ] pytest 全套通过，覆盖率 ≥ 70%
  - [ ] ruff check 0 错误
  - [ ] 无空 except / 无 print 调试 / 无未使用 import
  - [ ] 24 个任务文件无 AI slop

  **QA Scenarios**:

  ```
  Scenario: 完整测试 + 覆盖率验证
    Tool: Bash (pytest)
    Preconditions: 24 个 TODO 已完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest --cov=tradingagents --cov-fail-under=70 tests/ -v 2>&1 | tee /tmp/pytest-f2.log
      3. tail -30 /tmp/pytest-f2.log
    Expected Result: "X passed in Ys"，coverage ≥ 70%
    Failure Indicators: 任何 FAILED 或覆盖率 < 70%
    Evidence: .omo/evidence/f2-pytest-coverage.log

  Scenario: AI slop 扫描
    Tool: Bash (grep)
    Preconditions: 24 个 TODO 已完成
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. grep -rn "# type: ignore" tradingagents/ --include="*.py" | wc -l
      3. grep -rn "except:" tradingagents/ --include="*.py" | wc -l
      4. grep -rn "^print(" tradingagents/ --include="*.py" | wc -l
    Expected Result: 计数在合理范围（type: ignore ≤ 5，except: ≤ 2）
    Failure Indicators: 任何异常高的计数
    Evidence: .omo/evidence/f2-ai-slop.txt
  ```

- [x] F3. **Real Manual QA** — `unspecified-high`

  **What to do**:
  - 从干净状态（git stash 或新 worktree）启动
  - 执行所有 24 个任务的 QA Scenarios，捕获 evidence
  - 重点集成测试：
    - 端到端运行 600418 江淮汽车，捕获完整 report
    - English 模式运行同一标的，验证不出现 EPA/Class 8/ACT
    - 5 次同输入运行，对比报告 Jaccard 相似度（应 ≥ 0.85）
  - 边界测试：
    - 空输入（空 ticker）
    - 不存在 ticker（"000000"）
    - 极长输入（重复 100 次 ticker）
  - 保存所有 evidence 到 `.omo/evidence/final-qa/`

  **Must NOT do**:
  - 不要使用生产 API key（用 mock 或 test key）
  - 不要执行破坏性操作（git reset --hard 等）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` + `playwright` skill（如有 UI 涉及）
  - **Skills**: `[]`
  - **Reason**: 端到端执行 + 边界测试

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 F1/F2/F4 同时）
  - **Parallel Group**: Final Wave
  - **Blocks**: 交付给用户
  - **Blocked By**: 全部 24 个 TODO 完成

  **References**:
  - `.omo/plans/industrial-quality-fix.md` — 24 个任务的 QA Scenarios 段
  - `tests/test_e2e_600418.py`（如有）— 端到端参考

  **Acceptance Criteria**:
  - [ ] 24 个任务的 QA Scenarios 全部执行
  - [ ] 600418 端到端 1 次成功
  - [ ] 5 次同输入 Jaccard ≥ 0.85
  - [ ] English 模式 0 次 EPA/Class 8/ACT 命中
  - [ ] 边界测试 3 个全通过

  **QA Scenarios**:

  ```
  Scenario: 端到端 600418 测试
    Tool: Bash (python)
    Preconditions: mock LLM 已配置或 test API key 可用
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
    from tradingagents.graph.executor import GraphExecutor
    executor = GraphExecutor()
    result = executor.run(ticker='600418', date='2026-06-03')
    assert 'market_report' in result
    assert 'fundamentals_report' in result
    assert len(result['market_report']) > 100
    print('PASS')
    "
    Expected Result: 输出 "PASS"
    Failure Indicators: KeyError, AssertionError, 异常堆栈
    Evidence: .omo/evidence/f3-e2e-600418.txt

  Scenario: 5 次同输入确定性
    Tool: Bash (python)
    Preconditions: 端到端可运行
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
    import hashlib
    from tradingagents.graph.executor import GraphExecutor
    hashes = set()
    for i in range(5):
        result = GraphExecutor().run(ticker='600418', date='2026-06-03')
        h = hashlib.md5(result['market_report'].encode()).hexdigest()
        hashes.add(h)
    assert len(hashes) == 1, f'Non-deterministic: {hashes}'
    print('PASS: 5/5 identical MD5')
    "
    Expected Result: 输出 "PASS: 5/5 identical MD5"
    Failure Indicators: len(hashes) > 1
    Evidence: .omo/evidence/f3-determinism-5x.txt

  Scenario: English 模式幻觉检查
    Tool: Bash (python)
    Preconditions: English 模式可运行
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. OUTPUT_LANGUAGE=English python -c "
    from tradingagents.graph.executor import GraphExecutor
    result = GraphExecutor().run(ticker='600418', date='2026-06-03')
    report = result['market_report'] + result['fundamentals_report']
    for term in ['EPA 2027', 'Class 8', 'ACT Research', 'Class A RV']:
        assert term not in report, f'Hallucination found: {term}'
    print('PASS: 0 hallucination terms')
    "
    Expected Result: 输出 "PASS: 0 hallucination terms"
    Failure Indicators: AssertionError 提示具体术语
    Evidence: .omo/evidence/f3-no-english-hallucination.txt
  ```

- [x] F4. **Scope Fidelity Check** — `deep`

  **What to do**:
  - 对每个任务 (1-24)：
    - 读 "What to do"
    - 读 git log/diff 实际改动
    - 验证 1:1（spec 提到的都做了，没多没少）
  - 检查 "Must NOT do" 合规性
  - 检测跨任务污染：Task N 是否改动了 Task M 的文件
  - 标记未入账的改动（diff 中未在 plan 提及的文件）
  - 输出报告：`Tasks [N/24 compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

  **Must NOT do**:
  - 不要批准任何 contamination 案例
  - 不要忽略 unaccounted 改动

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`
  - **Reason**: 深度逐任务 diff 比对

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 F1/F2/F3 同时）
  - **Parallel Group**: Final Wave
  - **Blocks**: 交付给用户
  - **Blocked By**: 全部 24 个 TODO 完成

  **References**:
  - `.omo/plans/industrial-quality-fix.md:214-1650` — 24 个任务的 What to do
  - `git log --oneline -50` — 实际 commit 列表
  - `git diff main...HEAD --stat` — 全部改动文件

  **Acceptance Criteria**:
  - [ ] 24 个任务全部 1:1 合规
  - [ ] 0 个 contamination
  - [ ] 0 个 unaccounted 改动
  - [ ] Must NOT do 全数遵守

  **QA Scenarios**:

  ```
  Scenario: 逐任务 diff 合规检查
    Tool: Bash (git)
    Preconditions: 24 个 TODO 已完成并 commit
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. git log --oneline -30
      3. git diff main...HEAD --stat
      4. for commit in $(git log --oneline -30 | awk '{print $1}'); do echo "=== $commit ==="; git show --stat $commit | head -10; done
    Expected Result: 6 个 commit（PR-0 ~ PR-5 各 1 个），每个改动文件数与 plan 描述一致
    Failure Indicators: 改动文件数超出 plan 描述，或 commit 数不匹配
    Evidence: .omo/evidence/f4-scope-diff.txt

  Scenario: 跨任务污染检测
    Tool: Bash (git)
    Preconditions: 6 个 commit 已存在
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. PR=0; for file in $(git diff main...HEAD --name-only); do
           expected_pr=$(git log --oneline -- $file | head -1 | grep -oP 'PR-\K\d+' || echo "?")
           echo "$file -> first touched in $expected_pr"
         done | sort
    Expected Result: 每个文件只在预期的 PR 中首次出现
    Failure Indicators: 同一文件在多个 PR 中被修改
    Evidence: .omo/evidence/f4-no-contamination.txt
  ```

> 4 个 reviewer 全部 APPROVE 后才向用户呈现最终结果。

---

## Commit Strategy

每个 PR 单独一个 commit，按 PR 编号 commit message：

- `PR-0`：`feat(llm-config): add global temperature control for deterministic LLM calls`
- `PR-1`：`fix(agent-binding): align bind_tools and ToolNode registrations`
- `PR-2`：`refactor(indicators): introduce indicator_registry as single source of truth`
- `PR-3`：`feat(anti-hallucination): add global anti-hallucination instructions (12 agents, bilingual)`
- `PR-4`：`feat(verifier): add industry benchmark and financial trace validation`
- `PR-5`：`feat(structured-output): add Pydantic schemas for 4 analysts`

每个 commit 前必须 `pytest --cov=tradingagents tests/ -v` 通过。

---

## Success Criteria

### Verification Commands

```bash
# 1. 全部测试通过
pytest --cov=tradingagents --cov-fail-under=70 tests/ -v
# Expected: all pass, coverage ≥ 70%

# 2. 温度配置生效
grep -rn "temperature" tradingagents/llm_clients/ | grep -v "^#"
# Expected: 4 files (openai/anthropic/azure/google) contain "temperature" in _PASSTHROUGH_KWARGS

# 3. 防幻觉指令注入
grep -rn "anti_hallucination\|ANTI_HALLUCINATION" tradingagents/agents/ | wc -l
# Expected: ≥ 12 agent files reference anti_hallucination

# 4. bind_tools 对齐
python scripts/verify_tool_alignment.py
# Expected: 0 mismatches across 4 analysts

# 5. 端到端确定性（agent 内部执行）
python -c "
import os; os.environ['TEST_MODE']='1'
# 调用 graph.run() 5 次，记录 market_report 的 MD5
"
# Expected: ≥ 95% of MD5 hashes identical
```

### Final Checklist

- [ ] 所有 "Must Have" 已实现
- [ ] 所有 "Must NOT Have" 已被避免
- [ ] pytest 全套通过，coverage ≥ 70%
- [ ] 5 次同输入端到端 run 报告 MD5 一致率 ≥ 95%
- [ ] bind_tools 对齐脚本输出 0 不匹配
- [ ] 4 个 LLM 客户端的 `_PASSTHROUGH_KWARGS` 含 `temperature`
- [ ] 12 个 agent 文件包含防幻觉指令引用
- [ ] English 模式运行 600418，0 次 EPA/Class 8/ACT 关键词命中
- [ ] 4 个分析师接入 `with_structured_output`
- [ ] `macro_analyst` 死代码已从 `dynamic_graph_builder.py` 删除
