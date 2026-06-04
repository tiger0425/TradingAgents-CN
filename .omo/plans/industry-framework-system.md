# 全行业框架体系实现

## TL;DR

> **Quick Summary**: 建立两层行业框架体系（类型规则 Layer 1 + 具体框架 Layer 2），使 LLM 分析时先判定行业类型、继承类型级反模式规则，消除因框架缺失或误匹配导致的跨行业指标错用问题（如"通信线缆"被错误注入 SaaS/光模块指标）。
>
> **Deliverables**:
> - `tradingagents/industry/config/industry_frameworks.json` — 新增 `_type_rules`（6种行业类型反模式规则）+ `comm_cable` 框架
> - `tradingagents/industry/frameworks.py` — 修复预存 bug + 修改 `_AUTO_GEN_PROMPT` + 适配新 JSON 结构
> - `tests/test_industry_framework.py` — 新增 ≥10 个 TDD 测试
>
> **Estimated Effort**: Short（~45 min）
> **Parallel Execution**: YES — Wave A (T2 ‖ T3) otherwise sequential
> **Critical Path**: Bug Fix → {Tests ‖ JSON} → Python → Verification

---

## Context

### Original Request
强化行业框架注入：当前 IndustryFramework 需要为"通信线缆及配套"定义正确的 correct_metrics 和 anti_patterns，显式阻止 Agent 讨论光模块/CPO 等不相关内容。问题本质：框架缺失导致 LLM 自由发挥到不相关的光模块逻辑。

### Interview Summary
**Key Discussions**:
- 根因分析：三层问题（L1 框架缺失、L2 错误匹配 tech_saas、L3 验证虚设）
- 不能只做单点修复，要建立全行业框架体系
- 方案：两层架构（行业类型规则 + 具体框架），6 种行业类型

**Research Findings**:
- 券商研报（华泰/国盛/中信建投/天风）提供了 comm_cable 完整行业分析框架
- `IndustryVerifier` 定义了但生产代码未接入
- `frameworks.py` 第 164-206 行存在预存重复代码 bug（NameError on import）

### Metis Review
**Identified Gaps** (addressed):
- 模糊匹配关键字过于宽泛（"通信"在 tech_saas 中导致劫持）→ 收窄 keywords
- `_AUTO_GEN_PROMPT` 缺少类型继承 → 新增类型判断与继承步骤
- `list_frameworks()` 会泄露 `_type_rules` → 加过滤
- `_load()` 向后兼容规则未定义 → 显式双 key 检测
- 冲突解决规则未定义 → 明确定义：框架 anti_patterns = 类型通用 ∪ 行业特有（合并，不覆盖）

---

## Work Objectives

### Core Objective
建立两层行业框架体系，使 LLM 能够先判定行业类型、继承类型级反模式规则，再匹配具体行业框架进行分析，消除因框架缺失或误匹配导致的跨行业指标错用问题。

### Concrete Deliverables
- `industry_frameworks.json` 重构为 `{_type_rules, frameworks}` 结构
- 6 种行业类型规则（每种包含 anti_patterns + correct_metrics_examples）
- `comm_cable` 通信线缆及配套框架（基于券商研报）
- `frameworks.py` bug 修复 + prompt 升级 + 结构适配
- `test_industry_framework.py` 新测试文件

### Definition of Done
- [ ] `python3 -c "from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework()"` 不报错
- [ ] `python -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py tests/test_industry_classifier.py -v` 全部通过
- [ ] `fw.lookup("通信线缆及配套")` 返回 `comm_cable` 框架，不返回 `tech_saas`
- [ ] `fw.list_frameworks()` 不包含 `_type_rules`
- [ ] 现有 5 个行业框架匹配不发生回归

### Must Have
- 6 种行业类型对应的通用 anti_patterns
- comm_cable 框架含正确 correct_metrics + 光模块 anti_patterns
- `_AUTO_GEN_PROMPT` 强制 LLM 先判断类型再继承 anti_patterns
- `_load()` 兼容新旧 JSON 格式
- `_fuzzy_match()` 适配新嵌套结构（仅格式适配，不改算法）

### Must NOT Have (Guardrails)
- 不修改 `agent_utils.py` 注入逻辑（类型级注入不在此范围）
- 不接入 `IndustryVerifier` 到生产代码
- 不添加 `comm_cable` 之外的行业框架
- 不修改 `_fuzzy_match()` 匹配算法逻辑
- comm_cable keywords 不得包含孤立的"通信"（防止反向劫持）
- 不在生成过程中写入 `generated_frameworks.json`

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES（pytest）
- **Automated tests**: TDD
- **Framework**: pytest（项目已有 `tests/` 目录）

### QA Policy
All verification via Python script execution. Evidence saved to `.omo/evidence/`.
- **API/Library**: Use Bash (python -c) — Import, call functions, compare output
- **Tests**: Use Bash (python -m pytest) — Assert pass/fail counts

---

## Execution Strategy

### Sequential Execution

> This task is inherently sequential — each step depends on the previous.
> Bug fix must come first (nothing works without it).
> Tests must be written before code (TDD).

```
Step 1 → Step 2 → Step 3 → Step 4 → Step 5
```

---

## TODOs

- [x] 1. **Fix pre-existing duplicate code in `frameworks.py`**

  **What to do**:
  - Delete lines 164-206 of `tradingagents/industry/frameworks.py` (duplicate `_fuzzy_match` body orphaned inside `_load_generated()`)
  - These lines are a copy-paste artifact — lines 80-118 is the canonical `_fuzzy_match`
  - Verify: `python3 -c \"from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework(); print('import OK')\"`

  **Must NOT do**:
  - Do NOT touch lines 80-118 (canonical `_fuzzy_match`)
  - Do NOT modify any other method

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file deletion, trivial fix

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential step 1 — blocks everything
  - **Blocks**: All subsequent tasks
  - **Blocked By**: None

  **References**:
  - `tradingagents/industry/frameworks.py:80-118` — Canonical `_fuzzy_match` (keep)
  - `tradingagents/industry/frameworks.py:153-206` — Bug location (lines 164-206 to delete)

  **Acceptance Criteria**:
  - [ ] `python3 -c \"from tradingagents.industry.frameworks import IndustryFramework\"` → no NameError
  - [ ] `python3 -c \"from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework(); print(list(fw._frameworks.keys()))\"` → prints framework keys

  **QA Scenarios**:
  ```
  Scenario: Import succeeds after fix
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c \"from tradingagents.industry.frameworks import IndustryFramework\"
      2. Assert: exit code 0, no output (successful import)
    Expected Result: Exit code 0, no NameError
    Failure Indicators: NameError traceback mentioning 'industry_name'
    Evidence: .omo/evidence/task-1-import-fix.txt

  Scenario: Framework loading works
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c \"from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework(); print(len(fw._frameworks))\"
      2. Assert: output is a positive integer (5 or more)
    Expected Result: Prints integer >= 5
    Failure Indicators: NameError, or output < 5
    Evidence: .omo/evidence/task-1-framework-count.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-1-import-fix.txt` — successful import output
  - [ ] `task-1-framework-count.txt` — framework count

  **Commit**: YES
  - Message: `fix(industry): remove duplicate _fuzzy_match code in _load_generated`
  - Files: `tradingagents/industry/frameworks.py`

- [x] 2. **Write `test_industry_framework.py` — bug confirmation tests (RED)**

  **What to do**:
  - Create `tests/test_industry_framework.py`
  - Write failing tests that prove the bug: \"通信线缆及配套\" incorrectly matches `tech_saas`
  - Test: `fw.lookup(\"通信线缆及配套\")` should NOT return `tech_saas`
  - Test: `fw.lookup(\"通信线缆及配套\")` should return `None` (no framework exists yet)
  - Write tests for: backward compatibility of all 5 existing frameworks
  - Run: `python -m pytest tests/test_industry_framework.py -v` → expect RED (1+ failures)

  **Must NOT do**:
  - Do NOT add tests for comm_cable yet (framework not created)
  - Do NOT modify other test files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard test file creation, following existing test patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave A (with Task 3)
  - **Blocks**: Wave A completion
  - **Blocked By**: Task 1

  **References**:
  - `tests/test_industry_verifier.py` — Test patterns to follow (pytest, fixtures)
  - `tradingagents/industry/frameworks.py:IndustryFramework.lookup()` — Method under test
  - `tradingagents/industry/config/industry_frameworks.json` — Framework definitions to verify

  **Acceptance Criteria**:
  - [ ] `tests/test_industry_framework.py` file exists
  - [ ] `python -m pytest tests/test_industry_framework.py -v` → RED (at least 1 failure showing wrong match)
  - [ ] All existing tests still pass: `python -m pytest tests/test_industry_verifier.py tests/test_industry_classifier.py -v`

  **QA Scenarios**:
  ```
  Scenario: Bug confirmed — comm cable matches tech_saas (RED)
    Tool: Bash (python -m pytest)
    Steps:
      1. Run: python -m pytest tests/test_industry_framework.py::test_comm_cable_rejects_saas -v
      2. Assert: test FAILS (because \"通信线缆及配套\" currently matches tech_saas)
    Expected Result: Test fails with assertion error showing framework is tech_saas
    Failure Indicators: Test passes (bug already fixed?)
    Evidence: .omo/evidence/task-2-red-test.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-2-red-test.txt` — pytest RED output

  **Commit**: YES
  - Message: `test(industry): add TDD tests proving comm_cable mismatch bug`
  - Files: `tests/test_industry_framework.py`

- [x] 3. **Restructure `industry_frameworks.json` — add `_type_rules` + wrap frameworks**

  **What to do**:
  - Read `tradingagents/industry/config/industry_frameworks.json`
  - Restructure to: `{"_type_rules": {...}, "frameworks": {existing 5 frameworks}}`
  - Add `_type_rules` with 6 industry types: manufacturing, financial, consumer, pharma, tech_saas, telecom_operator
  - Each type has: `name`, `anti_patterns` (list of forbidden metrics), `correct_metrics_examples` (guide examples)
  - Wrap existing 5 frameworks under the `"frameworks"` key
  - For `tech_saas`, add anti_patterns to `_type_rules` (currently tech_saas has empty anti_patterns in the framework)
  - Verify JSON is valid: `python3 -c "import json; json.load(open('tradingagents/industry/config/industry_frameworks.json'))"`

  **Must NOT do**:
  - Do NOT change existing framework field names or values
  - Do NOT add `comm_cable` framework yet (Task 4)
  - Do NOT remove `"通信"` from tech_saas keywords (it's a valid SaaS keyword)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: JSON editing, deterministic structure change

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave A (with Task 2)
  - **Blocks**: Task 4, Task 5
  - **Blocked By**: Task 1

  **References**:
  - `tradingagents/industry/config/industry_frameworks.json` — Current flat structure
  - `tradingagents/industry/frameworks.py:_load()` — Consumer of JSON structure
  - `tradingagents/industry/frameworks.py:_fuzzy_match()` — Iterates self._frameworks

  **Acceptance Criteria**:
  - [ ] `industry_frameworks.json` is valid JSON
  - [ ] Contains top-level keys: `_type_rules`, `frameworks`
  - [ ] `_type_rules` has exactly 6 entries
  - [ ] `frameworks` has exactly 5 entries (existing automotive, banking, tech_saas, consumer, pharma)
  - [ ] Each `_type_rules` entry has: `name`, `anti_patterns` (non-empty list), `correct_metrics_examples`

  **QA Scenarios**:
  ```
  Scenario: JSON is valid and has correct structure
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c "
         import json
         data = json.load(open('tradingagents/industry/config/industry_frameworks.json'))
         assert '_type_rules' in data
         assert 'frameworks' in data
         assert len(data['_type_rules']) == 6
         assert len(data['frameworks']) == 5
         for t in data['_type_rules'].values():
             assert len(t['anti_patterns']) > 0, f'{t[\"name\"]} has empty anti_patterns'
         print('PASS: structure valid')
         "
      2. Assert: output contains "PASS: structure valid"
    Expected Result: "PASS: structure valid"
    Failure Indicators: AssertionError, KeyError
    Evidence: .omo/evidence/task-3-json-structure.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-3-json-structure.txt` — validation output

  **Commit**: NO (group with Task 4)

- [x] 4. **Add `comm_cable` framework to JSON**

  **What to do**:
  - Add `"comm_cable"` entry under `"frameworks"` in `industry_frameworks.json`
  - Framework definition based on brokerage research (华泰/国盛/中信建投):
    - `correct_metrics`: G.652.D散纤现货价、运营商年度光缆集采价格及招标量、光棒产能利用率、光棒自给率、铜/铝原材料成本占比、分业务毛利率拆分、运营商集采市场份额排名、经营活动现金流/净利润比率、海外业务收入占比、特种光纤收入占比、海缆及电力电缆在手订单覆盖月数、存货周转天数
    - `anti_patterns`: 1.6T光模块ASP、光模块出货量、CPO技术路线、光模块产能利用率、AI服务器出货量、GPU需求、算力集群规模、续约率、LTV/CAC、ACV、ARR、NRR、月活跃用户、云端订阅、客单价、GMV、DAU
    - `keywords`: 通信线缆、光纤光缆、光缆制造、电缆制造、电力电缆、光纤预制棒、海缆、线缆、永鼎股份、亨通光电、中天科技、长飞光纤、烽火通信
    - `peer_companies`: 永鼎股份、亨通光电、中天科技、长飞光纤、烽火通信、富通信息、通鼎互联、特变电工、东方电缆、中航光电
    - `context_instruction`: 基于券商研报框架的50-80字中文指导
  - Ensure keywords are specific enough to NOT match "通信设备" alone

  **Must NOT do**:
  - Do NOT include "通信" as a standalone keyword (to prevent reverse hijacking of telecom equipment)
  - Do NOT modify other frameworks

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: JSON editing with known content

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential step 4
  - **Blocks**: Task 5
  - **Blocked By**: Task 3

  **References**:
  - `tradingagents/industry/config/industry_frameworks.json` — Target file (after Task 3 restructure)
  - Broker reports: 华泰证券《光纤光缆进入历史大周期》(2026/4/24), 国盛证券《AI驱动下的新周期》(2026/3/15)

  **Acceptance Criteria**:
  - [ ] `frameworks` key now has 6 entries
  - [ ] `comm_cable` entry has all required fields: name, name_en, keywords, correct_metrics, anti_patterns, peer_companies, context_instruction
  - [ ] `comm_cable.anti_patterns` includes: '1.6T光模块ASP', 'CPO技术路线', 'ARR', 'NRR'
  - [ ] `"通信"` is NOT a standalone keyword in comm_cable

  **QA Scenarios**:
  ```
  Scenario: comm_cable framework is complete
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c "
         import json
         data = json.load(open('tradingagents/industry/config/industry_frameworks.json'))
         fw = data['frameworks']['comm_cable']
         assert fw['name'] == '通信线缆及配套'
         assert 'G.652.D' in str(fw['correct_metrics']) or '光纤现货价' in str(fw['correct_metrics'])
         assert '1.6T光模块ASP' in fw['anti_patterns']
         assert 'CPO技术路线' in fw['anti_patterns']
         assert 'ARR' in fw['anti_patterns']
         assert '通信' not in fw['keywords']  # no standalone 通信
         print('PASS: comm_cable framework complete')
         "
      2. Assert: output contains "PASS: comm_cable framework complete"
    Expected Result: "PASS: comm_cable framework complete"
    Failure Indicators: AssertionError, KeyError
    Evidence: .omo/evidence/task-4-comm-cable.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-4-comm-cable.txt` — validation output

  **Commit**: YES (group with Task 3)
  - Message: `feat(industry): restructure JSON + add _type_rules + comm_cable framework`
  - Files: `tradingagents/industry/config/industry_frameworks.json`

- [x] 5. **Modify `frameworks.py` — adapt to new JSON + upgrade `_AUTO_GEN_PROMPT`**

  **What to do**:
  - Update `_load()` to detect new nested format (`_type_rules` + `frameworks` keys) vs old flat format
    - New format: `self._frameworks = raw["frameworks"]`; `self._type_rules = raw["_type_rules"]`
    - Old format: `self._frameworks = raw`; `self._type_rules = {}` (backward compat)
  - Update `_fuzzy_match()` to iterate over `self._frameworks` (already does — no change needed since `_load()` handles the nesting)
  - Update `list_frameworks()` to filter out `_type_rules`:
    - Change to: `return [v for k, v in self._frameworks.items() if k != "_type_rules"]`
  - Replace `_AUTO_GEN_PROMPT` with version that:
    - Forces LLM to first classify the industry into one of 6 types
    - Inherits all anti_patterns from that type
    - Adds industry-specific anti_patterns on top (union merge)
    - Generates correct_metrics specific to the industry
  - Update `_auto_generate()` to pass `_type_rules` context to the prompt
  - Run existing tests to confirm no regression

  **Must NOT do**:
  - Do NOT change `_fuzzy_match()` algorithm logic — only format adaptation
  - Do NOT modify `agent_utils.py`
  - Do NOT wire up `IndustryVerifier` to production

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Multi-method refactoring with backward compat and LLM prompt engineering; needs careful review

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential step 5
  - **Blocks**: Task 6
  - **Blocked By**: Task 4

  **References**:
  - `tradingagents/industry/frameworks.py:24-41` — Current `_AUTO_GEN_PROMPT` (to replace)
  - `tradingagents/industry/frameworks.py:214-229` — `_load()` method (to update)
  - `tradingagents/industry/frameworks.py:80-118` — `_fuzzy_match()` (to verify no change needed)
  - `tradingagents/industry/frameworks.py:208-210` — `list_frameworks()` (to update)
  - `tradingagents/industry/frameworks.py:120-136` — `_auto_generate()` (to update prompt usage)
  - `tradingagents/industry/config/industry_frameworks.json` — New JSON structure (after Task 3+4)

  **Acceptance Criteria**:
  - [ ] `python3 -c "from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework()"` — import OK
  - [ ] `fw.lookup("通信线缆及配套")` returns `comm_cable` framework, NOT `tech_saas`
  - [ ] `fw.lookup("汽车制造")` returns `automotive` framework (backward compat)
  - [ ] `fw.lookup("银行")` returns `banking` framework (backward compat)
  - [ ] `fw.list_frameworks()` returns list of 6, does NOT contain `_type_rules`
  - [ ] `fw._type_rules` has 6 entries
  - [ ] `python -m pytest tests/test_industry_framework.py -v` → GREEN

  **QA Scenarios**:
  ```
  Scenario: comm_cable matches correctly (THE bug fix)
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c "
         from tradingagents.industry.frameworks import IndustryFramework
         fw = IndustryFramework()
         result = fw.lookup('通信线缆及配套')
         assert result is not None, 'No framework matched'
         assert result['name_en'] == 'comm_cable', f'Wrong framework: {result[\"name_en\"]}'
         assert '1.6T光模块ASP' in result['anti_patterns'], 'Missing optical module anti-pattern'
         assert 'ARR' in result['anti_patterns'], 'Missing SaaS anti-pattern'
         print('PASS: comm_cable matched correctly')
         "
      2. Assert: output contains "PASS: comm_cable matched correctly"
    Expected Result: "PASS: comm_cable matched correctly"
    Failure Indicators: tech_saas returned, or None, or missing anti_patterns
    Evidence: .omo/evidence/task-5-comm-cable-match.txt

  Scenario: Existing frameworks still work (backward compat)
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c "
         from tradingagents.industry.frameworks import IndustryFramework
         fw = IndustryFramework()
         tests = [
             ('汽车制造', 'automotive'),
             ('银行', 'banking'),
             ('白酒', 'consumer'),
             ('SaaS', 'tech_saas'),
             ('医药', 'pharma'),
         ]
         for query, expected in tests:
             result = fw.lookup(query)
             assert result is not None, f'{query} returned None'
             assert result['name_en'] == expected, f'{query} matched {result[\"name_en\"]} instead of {expected}'
         print('PASS: all 5 frameworks backward compatible')
         "
      2. Assert: output contains "PASS: all 5 frameworks backward compatible"
    Expected Result: "PASS: all 5 frameworks backward compatible"
    Failure Indicators: AssertionError on any framework
    Evidence: .omo/evidence/task-5-backward-compat.txt

  Scenario: list_frameworks excludes _type_rules
    Tool: Bash (python -c)
    Steps:
      1. Run: python3 -c "
         from tradingagents.industry.frameworks import IndustryFramework
         fw = IndustryFramework()
         frameworks = fw.list_frameworks()
         names = [f['name_en'] for f in frameworks]
         assert '_type_rules' not in names, f'type_rules leaked: {names}'
         assert len(frameworks) == 6, f'Expected 6, got {len(frameworks)}'
         print('PASS: list_frameworks filtered')
         "
      2. Assert: output contains "PASS: list_frameworks filtered"
    Expected Result: "PASS: list_frameworks filtered"
    Failure Indicators: _type_rules in output, or wrong count
    Evidence: .omo/evidence/task-5-list-frameworks.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-5-comm-cable-match.txt` — comm_cable match result
  - [ ] `task-5-backward-compat.txt` — backward compat result
  - [ ] `task-5-list-frameworks.txt` — list_frameworks result

  **Commit**: YES
  - Message: `feat(industry): adapt to new JSON + upgrade _AUTO_GEN_PROMPT with type rules`
  - Files: `tradingagents/industry/frameworks.py`

- [x] 6. **Run full test suite + verify no regression**

  **What to do**:
  - Run all industry-related tests: `python -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py tests/test_industry_classifier.py -v`
  - Confirm all tests pass (green)
  - Run a broader regression check: `python -m pytest tests/ -v --timeout=60 -x` (or at minimum the industry tests)
  - Verify import chain: `python3 -c "from tradingagents.industry import IndustryFramework, IndustryClassifier, IndustryVerifier"`

  **Must NOT do**:
  - Do NOT skip any test file
  - Do NOT modify tests to make them pass

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Test execution only, no code changes

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential step 6
  - **Blocks**: Final Verification Wave
  - **Blocked By**: Task 5

  **References**:
  - `tests/test_industry_framework.py` — New tests (Task 2)
  - `tests/test_industry_verifier.py` — Existing verifier tests
  - `tests/test_industry_classifier.py` — Existing classifier tests

  **Acceptance Criteria**:
  - [ ] All tests in `test_industry_framework.py` pass (GREEN)
  - [ ] All tests in `test_industry_verifier.py` pass
  - [ ] All tests in `test_industry_classifier.py` pass
  - [ ] Full test suite has zero new failures

  **QA Scenarios**:
  ```
  Scenario: All industry tests pass
    Tool: Bash (python -m pytest)
    Steps:
      1. Run: python -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py tests/test_industry_classifier.py -v
      2. Assert: exit code 0, no failures, no errors
    Expected Result: All tests pass, exit code 0
    Failure Indicators: Any FAILED or ERROR in output
    Evidence: .omo/evidence/task-6-full-test.txt
  ```

  **Evidence to Capture**:
  - [ ] `task-6-full-test.txt` — full pytest output

  **Commit**: NO (verification only)



---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden changes — reject with file:line if found. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py tests/test_industry_classifier.py -v`. Verify JSON is valid. Check: no dead code, no print statements, proper error handling. Check `comm_cable` keywords for "通信" standalone.
  Output: `Tests [N pass/N fail] | JSON [VALID/INVALID] | Keywords [CLEAN/WARN] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute ALL QA scenarios from ALL tasks. Verify: import works, comm_cable matches correctly, backward compat maintained, `list_frameworks()` clean. Check edge case: "通信设备" should NOT match `comm_cable`.
  Output: `Scenarios [N/N pass] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Regression Sweep** — `unspecified-high`
  Run `python -m pytest tests/ -v --timeout=60 -x` to verify no test regressions outside the industry module. Check `agent_utils.py` has no accidental changes. Verify `generated_frameworks.json` is untouched.
  Output: `Full Suite [N pass/N fail] | agent_utils [CLEAN/DIRTY] | generated_frameworks [UNTOUCHED/MODIFIED] | VERDICT`

---

## Commit Strategy

- **1**: `fix(industry): remove duplicate _fuzzy_match code in _load_generated` — `tradingagents/industry/frameworks.py`
- **2**: `test(industry): add TDD tests proving comm_cable mismatch bug` — `tests/test_industry_framework.py`
- **3+4**: `feat(industry): restructure JSON + add _type_rules + comm_cable framework` — `tradingagents/industry/config/industry_frameworks.json`
- **5**: `feat(industry): adapt to new JSON + upgrade _AUTO_GEN_PROMPT with type rules` — `tradingagents/industry/frameworks.py`

---

## Success Criteria

### Verification Commands
```bash
# Import must work
python3 -c "from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework()"

# comm_cable must match correctly
python3 -c "
from tradingagents.industry.frameworks import IndustryFramework
result = IndustryFramework().lookup('通信线缆及配套')
assert result['name_en'] == 'comm_cable', f'Got {result[\"name_en\"]}'
assert '1.6T光模块ASP' in result['anti_patterns']
print('OK')
"

# All tests pass
python -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py tests/test_industry_classifier.py -v
```

### Final Checklist
- [ ] All "Must Have" present (6 type rules, comm_cable, upgraded prompt, backward compat)
- [ ] All "Must NOT Have" absent (no agent_utils.py changes, no verifier wiring, no extra frameworks)
- [ ] All tests pass
- [ ] Import chain works
"
