# 跨标的报告一致性修复

## TL;DR

> **Quick Summary**: 基于 `docs/工业级质量差距全面诊断.md` Section 十一（v0.2.15-cn）的 4 个跨标的特异性根因，完成行业框架注入标准化、ReportRenderer 接线、行业字段白名单文档化、Planner 模板 report_skeleton 扩展，使跨标的报告长度标准差 ≤100 字、章节顺序一致性 ≥90%、段落结构 Jaccard ≥0.80。
>
> **Deliverables**:
> - `tradingagents/industry/injection_contract.py`（注入契约，标准化 anti_patterns 裁剪）
> - `executor.py` 接入 `ReportRenderer.render()`（强制三段式骨架）
> - `docs/industry-fields-whitelist.md`（6 行业字段白名单）
> - 6 个模板文件添加 `report_skeleton` 字段
> - `build_instrument_context()` 集成白名单引用
> - `template_matcher.py` 集成 `report_skeleton` 匹配权重
> - `framework.py` lookup() 调用 `normalize_injection()`
>
> **Estimated Effort**: Medium（约 10 文件改动，1-2 天净工作时间）
> **Parallel Execution**: YES - 3 waves（Wave 1=4 RED, Wave 2=4 GREEN, Wave 3=3 INTEGRATE, Wave FINAL=4 REVIEW）
> **Critical Path**: Wave 1 (TDD) → Wave 2 (implement) → Wave 3 (integrate) → FINAL

---

## Context

### Original Request
按 `docs/工业级质量差距全面诊断.md` Section 十一（v0.2.15-cn）完成跨标的分析报表一致性修复。

### Interview Summary
**Key Discussions**（5 项决策已确认）：
- 跨1 注入契约：硬编码约束（≤5 条 anti_patterns, ≤30 字, ≤8 correct_metrics）
- 跨2 ReportRenderer：接入 executor.py，替换 `_extract_report`
- 跨3 白名单：覆盖所有 6 个已有行业框架（automotive/banking/comm_cable/consumer/pharma/tech_saas）
- 跨4 report_skeleton：所有 6 个模板都加
- 测试策略：TDD（RED-GREEN-REFACTOR）

**Research Findings**:
- ReportRenderer 类代码已存在于 `tradingagents/graph/report_renderer.py`（446 行），但 executor.py 未调用
- executor.py:299 `_extract_report()` 仍使用 `"\n\n".join()` 拼接
- IndustryFramework 位于 `tradingagents/industry/frameworks.py`（非 framework.py）
- `build_instrument_context()` 在 agent_utils.py:134 是注入点
- 模板目录：`tradingagents/templates/`，6 个 JSON 文件
- 所有 4 个分析师已有 Pydantic schema + `with_structured_output`（v0.2.16-cn 完成）
- macro_analyst 死代码已完全删除（零引用）

### Metis Review
**Identified Gaps**（已纳入计划）:
- 跨4 核心待澄清：`report_skeleton` 是上游 prompt 约束还是下游渲染后处理？→ **决定：上游 prompt 约束（inject 到 system_message）+ 下游 ReportRenderer 后处理双重保障**
- 跨1 调用位置：`normalize_injection()` 在 `lookup()` **外部**调用，不污染 framework 数据源
- ≤30 字以 Python `len(string)` 计（字符数），非词数
- 跨4 需要先修复损坏的源模板 JSON（3 个文件 JSON 格式错误）
- llm_full 模式生成的 plan 需添加默认 report_skeleton（防止模板未命中时漂移）
- 跨2 需处理 error flow（executor.py:148-157）的一致性

---

## Work Objectives

### Core Objective
完成跨1（注入契约）、跨2（接线）、跨3（白名单）、跨4（模板扩展），使跨标的报告长度标准差 ≤100 字、章节顺序一致性 ≥90%、段落结构 Jaccard ≥0.80。

### Concrete Deliverables
1. `tradingagents/industry/injection_contract.py`（新建：标准化注入契约，含 `normalize_injection()`）
2. `tradingagents/industry/frameworks.py`（修改：`lookup()` 输出后调用 `normalize_injection()`）
3. `tradingagents/graph/executor.py`（修改：`_extract_report` 替换为 `ReportRenderer.render()`）
4. `docs/industry-fields-whitelist.md`（新建：6 行业必含/可选字段 + anti_patterns 交叉引用）
5. `tradingagents/agents/utils/agent_utils.py`（修改：`build_instrument_context()` 集成白名单引用）
6. `tradingagents/templates/tpl_*.json`（修改：6 个模板添加 `report_skeleton` 字段）
7. `tradingagents/planner/template_matcher.py`（修改：匹配时按 `report_skeleton` 优先复用）
8. `tradingagents/planner/llm_planner.py`（修改：`llm_full` 模式添加默认 report_skeleton）
9. 测试文件：`tests/test_injection_contract.py`, `tests/test_report_renderer_integration.py`, `tests/test_whitelist.py`, `tests/test_template_report_skeleton.py`

### Definition of Done
- [ ] `pytest tests/test_injection_contract.py tests/test_report_renderer_integration.py tests/test_whitelist.py tests/test_template_report_skeleton.py -v` 全部通过
- [ ] 跨 5 标的报告长度标准差（统计字数）≤ 100 字
- [ ] 跨 5 标的章节顺序一致性（hash 比对）≥ 90%
- [ ] 跨 5 标的段落结构 Jaccard ≥ 0.80
- [ ] 行业字段白名单覆盖率 = 100%（6 行业全覆盖）
- [ ] executor API 响应格式不变（`final_report` 仍为 str，含三段式结构）

### Must Have
- injection_contract.py 的 `normalize_injection()` 函数（硬编码 ≤5/≤30/≤8 约束）
- executor.py 接入 ReportRenderer（保留 plan 参数传递）
- 6 行业白名单文档 + agent_utils 集成
- 6 个模板的 report_skeleton 字段
- TDD 流程全覆盖（4 个新测试文件）

### Must NOT Have（Guardrails）
- **不得**修改 ReportRenderer 类的内部实现（类代码已完成，只做接线）
- **不得**在 `lookup()` 内部调用 `normalize_injection()`（避免污染 framework 数据源）
- **不得**修改 DynamicGraphBuilder 的图拓扑结构
- **不得**在 `template_matcher.py` 中重写匹配算法（只加字段权重逻辑）
- **不得**新增 industry_frameworks.json 条目（白名单是文档化，非数据扩展）
- **不得**修改 4 个分析师的 Pydantic schema 或 `with_structured_output` 调用
- **不得**给辩论/风控 agent 添加结构化输出

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - 所有验证由 agent 执行。

### Test Decision
- **Infrastructure exists**: YES（pytest 已有，48 个测试文件）
- **Automated tests**: TDD（RED-GREEN-REFACTOR）
- **Framework**: pytest + unittest.mock

### QA Policy
每个 TODO 必须包含 Agent-Executed QA Scenarios：
- **API/Backend**: 使用 Bash（curl）验证 API 响应
- **Library/Module**: 使用 Bash（python -c）验证导入和函数调用
- **CLI**: 使用 Bash（pytest）验证测试通过
- **证据保存**: `.omo/evidence/task-{N}-{scenario-slug}.{ext}`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (RED — Start Immediately, MAX PARALLEL — 4 failing tests):
├── Task 1: TDD failing test for injection_contract [quick]
├── Task 2: TDD failing test for ReportRenderer wiring [quick]
├── Task 3: TDD failing test for whitelist [quick]
└── Task 4: TDD failing test for report_skeleton [quick]

Wave 2 (GREEN — After Wave 1, MAX PARALLEL — 4 implementations):
├── Task 5: Create injection_contract.py + integrate with framework.py [quick]
├── Task 6: Wire ReportRenderer into executor.py [unspecified-high]
├── Task 7: Create whitelist.md + integrate with agent_utils.py [writing + quick]
└── Task 8: Add report_skeleton to 6 templates [quick]

Wave 3 (INTEGRATE — After Wave 2, MAX PARALLEL — 3 integrations):
├── Task 9: Fix broken source template JSONs (pre-req for 跨4) [quick]
├── Task 10: Update template_matcher.py for report_skeleton [quick]
└── Task 11: Update llm_planner.py for default report_skeleton [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
```

Critical Path: Task 1 → Task 5 → (Wave 3 independent of 5 output) → F1-F4
Parallel Speedup: ~80% faster than sequential
Max Concurrent: 4 (Waves 1 & 2)

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1-4 | — | 5-8 | 1 |
| 5-8 | 1-4 | 9-11 | 2 |
| 9 | 8 (templates must exist) | — | 3 |
| 10 | 8 (templates must have report_skeleton) | — | 3 |
| 11 | 8 | — | 3 |
| F1-F4 | 9-11 | — | FINAL |

### Agent Dispatch Summary

| Wave | Task Count | Agent Profiles |
|------|:---:|---|
| 1 | 4 | T1-T4 → `quick`（单元测试编写） |
| 2 | 4 | T5 → `quick`, T6 → `unspecified-high`（executor 集成），T7 → `writing`（文档）+ `quick`（代码）, T8 → `quick` |
| 3 | 3 | T9-T11 → `quick`（JSON 修复 + 匹配逻辑） |
| FINAL | 4 | F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

### Wave 1: RED — TDD Failing Tests (4 并行)

- [x] 1. TDD: 编写 failing test 验证 injection_contract 标准化约束

  **What to do**:
  - 新建 `tests/test_injection_contract.py`
  - 编写 `test_normalize_injection_truncates_anti_patterns` — 传 7 条 anti_patterns，断言输出 ≤5 条
  - 编写 `test_normalize_injection_truncates_long_lines` — 每条 >30 字时截断到 30 字
  - 编写 `test_normalize_injection_handles_empty` — 空列表不抛异常，返回空字符串
  - 编写 `test_normalize_injection_output_starts_with_header` — 输出以 `##INDUSTRY_GUIDE##` 开头
  - `pytest tests/test_injection_contract.py -v` → 全部 FAIL（injection_contract 尚不存在）

  **Must NOT do**:
  - 不要预先创建 injection_contract.py（TDD RED 阶段必须 fail）

  **Recommended Agent Profile**:
  - **Category**: `quick` — 简单的 pytest 单元测试编写
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 2, 3, 4 完全独立）
  - **Parallel Group**: Wave 1

  **References**:
  - 诊断文档 §11.4 跨1 修复方案 — 约束规范（≤5 anti_patterns, ≤30 字, ≤8 metrics）
  - `tests/test_anti_hallucination.py` — 测试文件结构参考

  **Acceptance Criteria**:
  - [ ] `tests/test_injection_contract.py` 包含 ≥3 个 test functions
  - [ ] `pytest tests/test_injection_contract.py -v` → 全部 FAIL（ImportError 或 ModuleNotFoundError）

  **QA Scenarios**:
  ```
  Scenario: TDD RED 阶段 — injection_contract 不存在
    Tool: Bash (pytest)
    Preconditions: injection_contract.py 不存在
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_injection_contract.py -v
    Expected Result: 所有测试 FAIL（ImportError）
    Failure Indicators: 测试 PASS 或 SKIPPED
    Evidence: .omo/evidence/task-1-red-injection-contract.txt
  ```

- [ ] 2. TDD: 编写 failing test 验证 ReportRenderer 接入 executor

  **What to do**:
  - 新建 `tests/test_report_renderer_integration.py`
  - 编写 `test_executor_uses_report_renderer` — mock executor，验证 `_extract_report` 内部调用了 `ReportRenderer.render`
  - 编写 `test_report_renderer_handles_empty_state` — `ReportRenderer.render({}, None)` 返回空字符串
  - 编写 `test_report_renderer_handles_str_input` — `ReportRenderer.render_section("Test", "plain text")` 不抛异常
  - 编写 `test_report_renderer_output_has_three_sections` — 输出含 `核心结论` / `关键数据` / `风险提示`
  - `pytest tests/test_report_renderer_integration.py -v` → 全部 FAIL（executor 未接入）

  **Must NOT do**:
  - 不要修改 executor.py（先让测试 fail，Wave 2 再修复）

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 1, 3, 4 并行）
  - **Parallel Group**: Wave 1

  **References**:
  - `tradingagents/graph/report_renderer.py:393` — `ReportRenderer.render()` 签名
  - `tradingagents/graph/executor.py:299` — 当前 `_extract_report` 实现

  **Acceptance Criteria**:
  - [ ] `tests/test_report_renderer_integration.py` 包含 ≥4 个 test functions
  - [ ] `pytest tests/test_report_renderer_integration.py -v` → 至少 2 个 FAIL

  **QA Scenarios**:
  ```
  Scenario: TDD RED 阶段 — executor 未接入 ReportRenderer
    Tool: Bash (pytest)
    Preconditions: executor.py 未修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_report_renderer_integration.py -v
    Expected Result: 接入验证测试 FAIL
    Failure Indicators: 测试意外 PASS
    Evidence: .omo/evidence/task-2-red-renderer-integration.txt
  ```

- [ ] 3. TDD: 编写 failing test 验证行业字段白名单格式

  **What to do**:
  - 新建 `tests/test_whitelist.py`
  - 编写 `test_whitelist_file_exists` — `docs/industry-fields-whitelist.md` 存在
  - 编写 `test_whitelist_has_all_industries` — 6 个行业（automotive/banking/comm_cable/consumer/pharma/tech_saas）均有 section
  - 编写 `test_whitelist_each_has_required_fields` — 每个行业含"必含字段"列表
  - 编写 `test_agent_utils_reads_whitelist` — mock `build_instrument_context`，验证 industry 匹配时注入白名单内容
  - `pytest tests/test_whitelist.py -v` → 全部 FAIL（白名单尚不存在）

  **Must NOT do**:
  - 不要创建 industry-fields-whitelist.md（TDD RED 阶段）

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 1, 2, 4 并行）
  - **Parallel Group**: Wave 1

  **References**:
  - 诊断文档 §11.4 跨3 修复方案 — 白名单示例结构
  - `tradingagents/agents/utils/agent_utils.py:134` — `build_instrument_context` 注入点
  - `tradingagents/industry/config/industry_frameworks.json` — 6 个行业键名验证

  **Acceptance Criteria**:
  - [ ] `tests/test_whitelist.py` 包含 ≥4 个 test functions
  - [ ] `pytest tests/test_whitelist.py -v` → 全部 FAIL

  **QA Scenarios**:
  ```
  Scenario: TDD RED 阶段 — 白名单文件不存在
    Tool: Bash (pytest)
    Preconditions: docs/industry-fields-whitelist.md 不存在
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_whitelist.py::test_whitelist_file_exists -v
    Expected Result: FAIL（FileNotFoundError 或 AssertionError）
    Evidence: .omo/evidence/task-3-red-whitelist.txt
  ```

- [ ] 4. TDD: 编写 failing test 验证 report_skeleton 模板字段

  **What to do**:
  - 新建 `tests/test_template_report_skeleton.py`
  - 编写 `test_all_templates_have_report_skeleton` — 6 个模板含 `report_skeleton` 字段
  - 编写 `test_report_skeleton_has_required_sections` — `report_skeleton` 含 `required_sections` 和 `section_order`
  - 编写 `test_template_matcher_prefers_skeleton` — 模拟模板匹配，含 report_skeleton 的模板得分更高
  - 编写 `test_llm_full_adds_default_skeleton` — `llm_full` 模式生成的 plan 含默认 report_skeleton
  - `pytest tests/test_template_report_skeleton.py -v` → 全部 FAIL

  **Must NOT do**:
  - 不要修改任何模板文件（TDD RED 阶段）

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 1, 2, 3 并行）
  - **Parallel Group**: Wave 1

  **References**:
  - 诊断文档 §11.4 跨4 修复方案 — report_skeleton JSON schema
  - `tradingagents/templates/tpl_standard_analysis.json` — 模板结构参考
  - `tradingagents/planner/template_matcher.py:75` — `_score_template()` 评分逻辑

  **Acceptance Criteria**:
  - [ ] `tests/test_template_report_skeleton.py` 包含 ≥4 个 test functions
  - [ ] `pytest tests/test_template_report_skeleton.py -v` → 全部 FAIL

  **QA Scenarios**:
  ```
  Scenario: TDD RED 阶段 — 模板无 report_skeleton
    Tool: Bash (pytest)
    Preconditions: 6 个模板文件无 report_skeleton 字段
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_template_report_skeleton.py::test_all_templates_have_report_skeleton -v
    Expected Result: FAIL（KeyError 或 AssertionError）
    Evidence: .omo/evidence/task-4-red-skeleton.txt
  ```

### Wave 2: GREEN — 核心实现 (4 并行)

- [ ] 5. 跨1 GREEN：创建 injection_contract.py + framework.py 集成

  **What to do**:
  - 新建 `tradingagents/industry/injection_contract.py`
  - 实现 `DEFAULT_CONTRACT` 常量：`{"max_anti_patterns": 5, "max_line_length": 30, "max_correct_metrics": 8}`
  - 实现 `normalize_injection(anti_patterns: list[str], correct_metrics: list[str]) -> str`：
    - 截断 anti_patterns 到 ≤5 条，每条截断到 ≤30 字符
    - 截断 correct_metrics 到 ≤8 条
    - 空列表时返回空字符串
    - 非空时以 `##INDUSTRY_GUIDE##` 开头格式化输出
  - 修改 `tradingagents/industry/frameworks.py`：在 `lookup()` 的 **返回值** 处（第 88-94 行附近）调用 `normalize_injection()`，不改变内部存储
  - 确认 `pytest tests/test_injection_contract.py -v` → 全部 GREEN

  **Must NOT do**:
  - 不要在 `lookup()` 内部修改 framework 数据源（仅在其返回结果上调用 `normalize_injection`）
  - 不要修改 `IndustryFramework` 的类结构
  - 不要使用 ≥7 的阈值（严格硬编码 5/30/8）

  **Recommended Agent Profile**:
  - **Category**: `quick` — 新文件创建 + 单函数实现 + 单处集成点

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 6, 7, 8 并行）
  - **Parallel Group**: Wave 2
  - **Blocked By**: Task 1

  **References**:
  - `docs/工业级质量差距全面诊断.md:738-754` — 注入契约结构
  - `tradingagents/industry/frameworks.py:74-94` — `lookup()` 完整代码
  - `tests/test_injection_contract.py` — 本项目 TDD 测试

  **Acceptance Criteria**:
  - [ ] `tradingagents/industry/injection_contract.py` 存在并可导入
  - [ ] `normalize_injection(["a"*50, "b", "c", "d", "e", "f", "g"], ["m1","m2"])` 返回 ≤5 条、每条 ≤30 字的格式化文本
  - [ ] `lookup()` 调用后返回的 `anti_patterns` 保持原始值（外部截断不影响内部）
  - [ ] `pytest tests/test_injection_contract.py -v` → 5 PASS

  **QA Scenarios**:
  ```
  Scenario: Happy path — 正常截断
    Tool: Bash (python -c)
    Preconditions: injection_contract.py 已部署
    Steps:
      1. cd tradingagents
      2. python -c "from industry.injection_contract import normalize_injection; result = normalize_injection(['a'*50,'b','c','d','e','f','g'], ['m1','m2']); lines = [l for l in result.split(chr(10)) if l.strip()]; assert len(lines) <= 6; print('PASS: truncation works')"
    Expected Result: 输出 PASS: truncation works
    Failure Indicators: AssertionError
    Evidence: .omo/evidence/task-5-happy-path.txt

  Scenario: Edge case — 空输入
    Tool: Bash (python -c)
    Preconditions: injection_contract.py 已部署
    Steps:
      1. cd tradingagents
      2. python -c "from industry.injection_contract import normalize_injection; result = normalize_injection([], []); assert result == ''; print('PASS: empty')"
    Expected Result: PASS: empty
    Evidence: .omo/evidence/task-5-empty-input.txt
  ```

- [ ] 6. 跨2 GREEN：executor.py 接入 ReportRenderer

  **What to do**:
  - 修改 `tradingagents/graph/executor.py`:
    - 第 299-329 行：将 `_extract_report` 内部逻辑替换为调用 `ReportRenderer.render()`
    - 保留函数签名：`def _extract_report(self, final_state: dict) -> str`
    - 在方法顶部 `from tradingagents.graph.report_renderer import ReportRenderer`
    - 传递 `plan` 参数（从 `self` 获取或从调用方传入）
    - 处理 error flow（第 148-157 行）：错误场景也统一用 ReportRenderer 组装 `final_report`
  - 确认 `pytest tests/test_report_renderer_integration.py -v` → 全部 GREEN

  **Must NOT do**:
  - 不要修改 executor.py 的图结构（`trading_graph.py`、`dynamic_graph_builder.py`）
  - 不要修改 `ReportRenderer` 类本身（已稳定）
  - 不要删除旧的 `_extract_report` 方法（改为调用 renderer 的 adapter）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — executor 是核心管道，需要仔细处理 error flow 和状态传递
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 5, 7, 8 并行）
  - **Parallel Group**: Wave 2
  - **Blocked By**: Task 2

  **References**:
  - `tradingagents/graph/executor.py:299-329` — 完整 `_extract_report` 当前代码
  - `tradingagents/graph/executor.py:148-157` — error flow 处理
  - `tradingagents/graph/report_renderer.py:393-446` — `ReportRenderer.render()` 签名和逻辑

  **Acceptance Criteria**:
  - [ ] `grep "ReportRenderer.render" tradingagents/graph/executor.py` 命中
  - [ ] `_extract_report` 返回的三段式 Markdown 被正确组装到 `AnalyzeResponse.report`
  - [ ] API 端点 `POST /analyze` 返回 `final_report` 仍为合法 str
  - [ ] `pytest tests/test_report_renderer_integration.py -v` → 4 PASS

  **Commit**: YES — Message: `feat(executor): wire ReportRenderer into _extract_report`

  **QA Scenarios**:
  ```
  Scenario: API 端点返回三段式报告
    Tool: Bash (curl + grep)
    Preconditions: API server running on localhost:8000
    Steps:
      1. curl -s -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"user_id":"qa","message":"test","ticker":"000001"}'
      2. Extract "report" field, verify it contains "核心结论" and "关键数据"
    Expected Result: 输出含 "核心结论" 且含 "关键数据"
    Failure Indicators: 无 "核心结论" 或无 "关键数据"
    Evidence: .omo/evidence/task-6-api-report-response.json

  Scenario: 错误场景 — 空 final_state 不崩溃
    Tool: Bash (python -c)
    Preconditions: executor.py 已修改
    Steps:
      1. cd tradingagents
      2. python -c "from graph.report_renderer import ReportRenderer; result = ReportRenderer.render({}, None); assert result == ''; print('PASS')"
    Expected Result: PASS
    Evidence: .omo/evidence/task-6-empty-state.txt
  ```

- [ ] 7. 跨3 GREEN：创建行业字段白名单 + agent_utils 集成

  **What to do**:
  - 新建 `docs/industry-fields-whitelist.md`：
    - 为全部 6 个行业（automotive/banking/comm_cable/consumer/pharma/tech_saas）编写 section
    - 每个 section 含：**必含字段**（列表）、**可选字段**（列表）、**anti_patterns**（交叉引用）
    - 参考 `industry_frameworks.json` 中的 `correct_metrics` 和 `anti_patterns` 字段
  - 修改 `tradingagents/agents/utils/agent_utils.py`：
    - 在 `build_instrument_context()`（第 134 行注入点后）添加白名单读取逻辑
    - 匹配 industry 后，读取 `docs/industry-fields-whitelist.md` 对应 section
    - 将"必含字段"注入到 prompt 中的 `行业分析框架` 段落
    - 未匹配时静默跳过，不抛异常
  - 确认 `pytest tests/test_whitelist.py -v` → 全部 GREEN

  **Must NOT do**:
  - 不要用白名单的 anti_patterns 覆盖 IndustryFramework 的 anti_patterns（追加，不替换）
  - 不要新增 industry_frameworks.json 条目
  - 白名单缺失时不破坏现有功能（graceful degradation）

  **Recommended Agent Profile**:
  - **Category**: `writing` — 文档编写为主 + `quick` — 简单的 prompt 拼接
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 5, 6, 8 并行）
  - **Parallel Group**: Wave 2
  - **Blocked By**: Task 3

  **References**:
  - `docs/工业级质量差距全面诊断.md:796-822` — 白名单示例结构
  - `tradingagents/industry/config/industry_frameworks.json` — 6 行业框架数据（correct_metrics 来源）
  - `tradingagents/agents/utils/agent_utils.py:130-160` — `build_instrument_context` 注入逻辑
  - 诊断文档 §11.4 跨3 — 白名单与 anti_patterns 不覆盖关系

  **Acceptance Criteria**:
  - [ ] `docs/industry-fields-whitelist.md` 存在，含 6 个 `## `<industry>`` 级标题
  - [ ] 每个 section 至少含 `### 必含字段` 和 `### 可选字段`
  - [ ] `build_instrument_context("000001", "banking", ...)` 返回值含 "必含字段"
  - [ ] `build_instrument_context("000001", "nonexistent_industry", ...)` 不抛异常
  - [ ] `pytest tests/test_whitelist.py -v` → 5 PASS

  **QA Scenarios**:
  ```
  Scenario: 银行行业白名单注入
    Tool: Bash (python -c)
    Preconditions: whitelist.md 和 agent_utils.py 已修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
        from tradingagents.agents.utils.agent_utils import build_instrument_context
        ctx = build_instrument_context('000001', 'banking')
        assert '必含字段' in ctx or '行业分析框架' in ctx
        print('PASS: whitelist injected')
      "
    Expected Result: PASS: whitelist injected
    Failure Indicators: 关键字缺失或异常
    Evidence: .omo/evidence/task-7-banking-whitelist.txt

  Scenario: 未匹配行业静默跳过
    Tool: Bash (python -c)
    Preconditions: whitelist.md 不含 "unknown_industry_xyz"
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "
        from tradingagents.agents.utils.agent_utils import build_instrument_context
        ctx = build_instrument_context('000001', 'unknown_industry_xyz')
        print('PASS: no exception raised')
      "
    Expected Result: PASS: no exception raised（不因缺失白名单而崩溃）
    Evidence: .omo/evidence/task-7-missing-industry.txt
  ```

- [ ] 8. 跨4 GREEN：6 个模板添加 report_skeleton 字段

  **What to do**:
  - 修改 6 个模板文件（`tradingagents/templates/tpl_*.json`）：
    - 在每个模板文件最外层添加 `"report_skeleton"` 字段
    - 结构参照诊断文档：
      ```json
      "report_skeleton": {
        "market_analyst": {
          "required_sections": ["技术面总结", "关键指标", "短期走势"],
          "section_order": ["技术面总结", "关键指标", "短期走势"]
        },
        "fundamentals_analyst": {
          "required_sections": ["核心结论", "财务三表要点", "估值水平"],
          "section_order": ["核心结论", "财务三表要点", "估值水平"]
        }
      }
      ```
    - 不同模板适配不同 agent：含 news/social analyst 的模板需覆盖所有 analyst
    - `tpl_morning_briefing` / `tpl_midday_review` / `tpl_closing_review`：仅含使用的 analyst（3 个）
    - `tpl_standard_analysis`：含所有 4 个 analyst
    - `tpl_breakeven_recovery`：含 market + fundamentals（2 个）
    - `tpl_weekly_screening`：含使用的 3 个 analyst
  - 确认 `pytest tests/test_template_report_skeleton.py -v` → 全部 GREEN

  **Must NOT do**:
  - 不要修改模板文件的 `match_patterns` 或 `workflow` 字段
  - 不要为不含相应 analyst 的模板填写其 report_skeleton
  - 不要修改 DynamicGraphBuilder

  **Recommended Agent Profile**:
  - **Category**: `quick` — JSON 字段添加（6 个文件 × 1 处改动）

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 5, 6, 7 并行）
  - **Parallel Group**: Wave 2
  - **Blocked By**: Task 4

  **References**:
  - 诊断文档 §11.4 跨4 修复方案（第 827-844 行）— report_skeleton JSON schema
  - `tradingagents/templates/tpl_standard_analysis.json` — 模板结构
  - `tradingagents/templates/tpl_morning_briefing.json` — 简化模板结构参考

  **Acceptance Criteria**:
  - [ ] 6 个模板全部含 `report_skeleton` 字段
  - [ ] 每个 `report_skeleton` 含 `required_sections` 和 `section_order`
  - [ ] 字段中不包含该模板未使用的 agent
  - [ ] `pytest tests/test_template_report_skeleton.py -v` → 4 PASS

  **Commit**: YES — Message: `feat(templates): add report_skeleton to all 6 planner templates`

  **QA Scenarios**:
  ```
  Scenario: 所有模板含 report_skeleton
    Tool: Bash (python -c)
    Preconditions: 6 个模板文件已修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "import json, glob; templates = glob.glob('tradingagents/templates/tpl_*.json'); results = [json.load(open(f)).get('report_skeleton') for f in templates]; assert all(r is not None for r in results); print(f'PASS: {len(results)} templates all have report_skeleton')"
    Expected Result: PASS: 6 templates all have report_skeleton
    Failure Indicators: 任一模板缺失 report_skeleton 导致 AssertionError
    Evidence: .omo/evidence/task-8-all-skeletons.txt

  Scenario: JSON 格式有效
    Tool: Bash (python -c)
    Preconditions: 模板文件已修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "import json; [json.load(open(f)) for f in glob.glob('tradingagents/templates/tpl_*.json')]; print('All JSON valid')" (import glob first)
    Expected Result: All JSON valid
    Failure Indicators: json.JSONDecodeError
    Evidence: .omo/evidence/task-8-json-valid.txt
  ```

### Wave 3: Integration + REFACTOR (3 并行)

- [ ] 9. 跨4 前置修复：修复 3 个损坏的源模板 JSON

  **What to do**:
  - 修复 `tradingagents/templates/tpl_standard_analysis.json`：第 15-16 行 — 补齐缺失逗号 + 移除外层多余 `]`
  - 修复 `tradingagents/templates/tpl_breakeven_recovery.json`：同上问题
  - 修复 `tradingagents/templates/tpl_weekly_screening.json`：同上问题
  - 验证修复后：`python -c "import json; [json.load(open(f)) for f in glob('.../tpl_*.json')]"` 全部通过
  - 确认 `pytest tests/test_template_report_skeleton.py -v` 仍 GREEN

  **Must NOT do**:
  - 不要修改模板的业务数据（仅修复 JSON 语法）

  **Recommended Agent Profile**:
  - **Category**: `quick` — JSON 语法修复（仅插入逗号/删除括号）

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 10, 11 并行）
  - **Parallel Group**: Wave 3
  - **Blocked By**: Task 8（模板必须在修复前已添加 report_skeleton）

  **References**:
  - `tradingagents/templates/tpl_standard_analysis.json:13-16` — 损坏区域
  - `tradingagents/templates/tpl_morning_briefing.json` — 正确格式参考

  **Acceptance Criteria**:
  - [ ] 3 个文件可通过 `json.load()` 正常解析
  - [ ] `pytest tests/test_template_report_skeleton.py -v` → 仍全部 PASS

  **QA Scenarios**:
  ```
  Scenario: 全部 6 个模板 JSON 可解析
    Tool: Bash (python -c)
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python -c "import json, glob; [json.load(open(f)) for f in glob.glob('tradingagents/templates/tpl_*.json')]; print('All 6 valid')"
    Expected Result: All 6 valid
    Evidence: .omo/evidence/task-9-all-json-valid.txt
  ```

- [ ] 10. 跨4 INTEGRATE：template_matcher.py 使用 report_skeleton

  **What to do**:
  - 修改 `tradingagents/planner/template_matcher.py`：
    - 在 `_score_template()` 方法（第 75 行附近）添加 report_skeleton 匹配权重：
      - 若模板含 `report_skeleton` 且 target industry 匹配 → +0.1 加分
      - 若模板含 `report_skeleton` 但 industry 不匹配 → 不扣分
      - 若模板不含 `report_skeleton` → 不影响评分
    - 不修改核心匹配算法（关键词/负关键词/required_context 逻辑不变）
  - 修改 `tradingagents/planner/llm_planner.py`：
    - 在 `_generation_mode == "llm_full"` 路径（第 112-126 行）添加默认 `report_skeleton`
    - 默认 skeleton 使用 `tpl_standard_analysis` 的结构作为 fallback
  - 确认 `pytest tests/test_template_report_skeleton.py -v` → `test_template_matcher_prefers_skeleton` PASS

  **Must NOT do**:
  - 不要重写 `_score_template` 的评分逻辑
  - 不要修改 `TemplateEvolver` 类

  **Recommended Agent Profile**:
  - **Category**: `quick` — 评分函数加 1 个条件分支 + llm_planner 加 1 个 fallback

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 9, 11 并行）
  - **Parallel Group**: Wave 3
  - **Blocked By**: Task 8

  **References**:
  - `tradingagents/planner/template_matcher.py:75-103` — `_score_template()` 评分逻辑
  - `tradingagents/planner/llm_planner.py:112-126` — `llm_full` 模式路径

  **Acceptance Criteria**:
  - [ ] 含 report_skeleton 的模板匹配得分 ≥ 不含的（industry 匹配时）
  - [ ] `llm_full` 模式生成的 plan 含 `report_skeleton` 字段
  - [ ] `pytest tests/test_template_report_skeleton.py -v` → 4 PASS

  **QA Scenarios**:
  ```
  Scenario: report_skeleton 模板优先级更高
    Tool: Bash (pytest)
    Preconditions: template_matcher.py 已修改
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/test_template_report_skeleton.py::test_template_matcher_prefers_skeleton -v
    Expected Result: PASS
    Evidence: .omo/evidence/task-10-skeleton-preference.txt
  ```

- [ ] 11. 全局回归测试 + 最终验证

  **What to do**:
  - 运行完整测试套件：`pytest tests/ -v -x --timeout=60`
  - 确认 4 个新测试文件全部 PASS
  - 确认现有回归测试（48 个文件）不受影响
  - 运行 verify_tool_alignment.py：确认 0 不匹配
  - 验证 executor API：`curl` 确认三段式报告格式
  - 提交所有变更

  **Must NOT do**:
  - 不要跳过任何失败测试（必须全部 fix 或解释）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — 全量回归测试运行

  **Parallelization**:
  - **Can Run In Parallel**: YES（与 Task 9, 10 并行）
  - **Parallel Group**: Wave 3
  - **Blocked By**: Task 5-8（实现必须先完成）

  **Acceptance Criteria**:
  - [ ] `pytest tests/ -v -x` → 全部 PASS（含新测试 + 现有回归）
  - [ ] `python scripts/verify_tool_alignment.py` → 0 不匹配
  - [ ] `curl` 验证 API 返回三段式报告

  **QA Scenarios**:
  ```
  Scenario: 全量回归测试通过
    Tool: Bash (pytest)
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. pytest tests/ -v -x --timeout=120
    Expected Result: 全部 PASS（或已知允许的 xfail）
    Evidence: .omo/evidence/task-11-full-regression.txt

  Scenario: verify_tool_alignment 通过
    Tool: Bash (python)
    Steps:
      1. cd /home/six/YifuAIForge/tradingagents-cn
      2. python scripts/verify_tool_alignment.py
    Expected Result: 0 不匹配
    Evidence: .omo/evidence/task-11-tool-alignment.txt
  ```

---

---

## Final Verification Wave

> 4 个审查 agent **并行**运行。全部必须 APPROVE。整合结果呈现给用户，等待明确"ok"。

- [ ] F1. **Plan Compliance Audit** — `oracle`
  逐项核实所有"Must Have"和"Must NOT Have"。验证证据文件存在于 `.omo/evidence/`。
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  运行 `pytest tests/ -v` 全量测试。检查 AI slop。验证：injection_contract 截断阈值、ReportRenderer 接线、白名单完整性、模板 JSON 合法性。
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  执行每个任务的 QA Scenario。验证跨任务集成。测试边缘情况：null industry、空列表、缺失模板、超长文本。
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  逐任务对比"What to do"与实际 diff。验证 1:1 对应。检查"Must NOT do"合规性。
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `test(cross-ticker): add TDD failing tests for cross-ticker consistency` — 4 个测试文件
- **Wave 2**: `feat(cross-ticker): implement core fixes (injection_contract, ReportRenderer wiring, whitelist, report_skeleton)` — 8 个创建/修改文件
- **Wave 3**: `feat(cross-ticker): integrate glue layer (template_matcher, llm_planner, verification)` — 3 个集成文件
- **FINAL**: `chore(cross-ticker): final verification wave evidence` — 证据文件

---

## Success Criteria

### Verification Commands
```bash
# 全部新测试通过
pytest tests/test_injection_contract.py tests/test_report_renderer_integration.py tests/test_whitelist.py tests/test_template_report_skeleton.py -v

# 跨1 注入契约可导入
python -c "from tradingagents.industry.injection_contract import normalize_injection; print('OK')"

# 跨2 executor 使用 ReportRenderer
grep -q "ReportRenderer.render" tradingagents/graph/executor.py && echo "OK"

# 跨3 白名单存在且覆盖 6 行业
test -f docs/industry-fields-whitelist.md && python -c "import re; assert len(re.findall(r'^## \w+', open('docs/industry-fields-whitelist.md').read())) >= 6; print('OK')"

# 跨4 全部模板含 report_skeleton
python -c "import json,glob; assert all('report_skeleton' in json.load(open(f)) for f in glob.glob('tradingagents/templates/tpl_*.json')); print('OK')"

# 全量回归
pytest tests/ -v -x --tb=short
```

### Final Checklist
- [ ] 所有 "Must Have" 已实现
- [ ] 所有 "Must NOT Have" 未被违反
- [ ] pytest 全套通过（含 4 个新测试文件，约 860 tests）
- [ ] 6 个模板全部含 `report_skeleton` 字段
- [ ] executor.py 调用 `ReportRenderer.render()`
- [ ] `docs/industry-fields-whitelist.md` 覆盖 6 行业
- [ ] `tradingagents/industry/injection_contract.py` 存在且可导入
- [ ] 用户明确 "ok" 后方可标记完成
