# IndustryVerifier 接入 + _AUTO_GEN_PROMPT 动态化

## TL;DR

> **Quick Summary**: 将已测试完备的 IndustryVerifier 接入生产流程（Flag-and-continue），并将 _AUTO_GEN_PROMPT 的类型规则从硬编码切换为动态读取 _type_rules JSON，消除维护不一致风险。
>
> **Deliverables**:
> - `tradingagents/graph/executor.py` — IndustryVerifier 接入（L168-170 之间）
> - `tradingagents/api_server.py` — AnalyzeResponse 新增 `industry_verification` 字段
> - `tradingagents/industry/frameworks.py` — `_AUTO_GEN_PROMPT` 改为方法动态生成
>
> **Estimated Effort**: Short（~30 min）
> **Parallel Execution**: NO — sequential
> **Critical Path**: Executor wiring → API schema → Prompt dynamic → Tests

---

## Context

### Evaluation Results
前一个 plan（industry-framework-system）完成后评估发现两个剩余缺口：
1. **IndustryVerifier 未接入生产**（HIGH）— 13 个测试已通过但 executor 从未调用
2. **_AUTO_GEN_PROMPT 类型规则硬编码**（MEDIUM）— 与 _type_rules JSON 重复定义

### User Decisions
- Verifier on fail: **Flag-and-continue**（追加警告到报告 + 返回验证结果）
- API schema: **Add field**（AnalyzeResponse 新增 `industry_verification`）
- Dynamic prompt scope: **Include examples**（同时注入 anti_patterns 和 correct_metrics_examples）

### Pre-checks Confirmed
- `final_state["industry"]` 全程只读，无 Agent 节点修改
- `fw.lookup("商用载货车")` → automotive ✓（所有实际行业名称可解析）
- `executor.quick_llm` 始终可用

---

## Work Objectives

### Core Objective
将 IndustryVerifier 接入生产分析流程，形成"Prompt 约束 → Agent 分析 → Verifier 扫描"的完整保护链；同时将 _AUTO_GEN_PROMPT 的类型规则从硬编码切换为动态生成。

### Definition of Done
- [ ] Verifier 在每次成功分析后自动运行
- [ ] 分析响应包含 `industry_verification` 字段
- [ ] `_AUTO_GEN_PROMPT` 从 `self._type_rules` 动态生成
- [ ] 所有现有测试通过，无回归

### Must Have
- executor.py 接入 verifier（flag-and-continue）
- AnalyzeResponse 新增 industry_verification 字段
- `_build_auto_gen_prompt()` 方法，动态生成 prompt
- `_type_rules` 为空时回退到原硬编码 prompt

### Must NOT Have
- 不修改 IndustryVerifier 的校验逻辑
- 不修改 agent_utils.py
- 不修改 trading_graph.py（legacy 路径不接入）
- 不实现 auto-correction/retry 循环

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES（pytest）
- **Automated tests**: TDD（先写测试验证行为，再改代码）

### QA Policy
- API: Bash (curl) — 验证响应包含 industry_verification
- Backend: Bash (python -c) — 验证 prompt 动态生成
- Tests: Bash (python3 -m pytest) — 回归验证

---

## Execution Strategy

```
Step 1 → Step 2 → Step 3 → Step 4 (verification)
```

---

## TODOs

- [x] 1. **Wire IndustryVerifier into executor.py (flag-and-continue)**

  **What to do**:
  - Add import: `from tradingagents.industry.verifier import IndustryVerifier`
  - Between L168 (`report = self._extract_report(final_state)`) and L170 (`return {...}`), insert:
    ```python
    # IndustryVerifier: flag-and-continue
    industry = final_state.get("industry", "")
    verification = None
    if industry and report:
        try:
            verification = IndustryVerifier.verify_industry_consistency(
                industry=industry,
                report=report,
                quick_llm=self.quick_llm,
            )
            if not verification.get("consistent", True):
                logger.warning("IndustryVerifier: consistency check failed for %s: %s",
                               final_state.get("company_of_interest", "unknown"),
                               verification.get("issues", []))
                # Flag: append warning to report
                issues = "；".join(verification.get("issues", []))
                report += f"\n\n⚠️ **行业一致性警告**（{verification.get('method', 'unknown')}）：{issues}"
        except Exception as exc:
            logger.exception("IndustryVerifier: unexpected error during consistency check: %s", exc)
            verification = {"consistent": True, "issues": ["verifier error"], "severity": "warning", "method": "error"}
    ```
  - Add `"industry_verification": 1` to return dict if verification exists

  **Must NOT do**:
  - Do NOT crash execute() if verifier throws
  - Do NOT change report structure beyond appending warning
  - Do NOT add verifier to the error path（L146 early return 之后不执行）

  **Recommended Agent Profile**: `quick`
  - Single-file edit with known insertion point

  **Parallelization**: Sequential step 1, blocks all

  **QA Scenarios**:
  ```
  Scenario: Verifier runs on successful analysis
    Tool: Bash (curl)
    Steps:
      1. POST /analyze with valid ticker 600418
      2. Check response contains "industry_verification" key
    Expected: industry_verification dict with consistent, issues, severity, method
    Evidence: .omo/evidence/task-1-verifier-runs.json

  Scenario: Verifier does NOT crash on error
    Tool: Bash (curl)
    Steps:
      1. POST /analyze with invalid ticker
      2. Assert: no industry_verification key (early return before verifier)
    Expected: Error response without industry_verification
    Evidence: .omo/evidence/task-1-error-no-verify.txt
  ```

  **Commit**: YES
  - Files: `tradingagents/graph/executor.py`

- [x] 2. **Add industry_verification field to AnalyzeResponse**

  **What to do**:
  - In `tradingagents/api_server.py` L33-39, add to `AnalyzeResponse`:
    ```python
    industry_verification: dict | None = None
    ```
  - No other field changes

  **Must NOT do**:
  - Do NOT change any existing field definitions
  - Do NOT modify the analyze endpoint logic

  **Recommended Agent Profile**: `quick`
  - Single-line schema addition

  **Parallelization**: Sequential step 2, blocked by T1

  **QA Scenarios**:
  ```
  Scenario: Response includes industry_verification
    Tool: Bash (curl)
    Steps:
      1. POST /analyze with ticker 600519
      2. Assert response.industry_verification is dict or None
    Expected: Dict with consistent/issues/severity/method keys, or None
    Evidence: .omo/evidence/task-2-api-response.json
  ```

  **Commit**: YES
  - Files: `tradingagents/api_server.py`

- [x] 3. **Make _AUTO_GEN_PROMPT dynamic from _type_rules**

  **What to do**:
  - Add `_build_auto_gen_prompt(industry_name: str) -> str` method to IndustryFramework:
    ```python
    def _build_auto_gen_prompt(self, industry_name: str) -> str:
        """Build auto-generation prompt dynamically from _type_rules."""
        # If _type_rules is empty, fall back to hardcoded constant
        if not self._type_rules:
            return _AUTO_GEN_PROMPT.format(industry=industry_name)

        # Build Step 1: type list
        type_names = {
            "manufacturing": "制造业", "financial": "金融", "consumer": "消费品",
            "pharma": "医药", "tech_saas": "科技/SaaS", "telecom_operator": "运营商/通信基础设施"
        }
        type_list = "、".join(f"{k}({type_names.get(k, k)})" for k in sorted(self._type_rules.keys()))

        # Build Step 2: type rules with anti_patterns + correct_metrics_examples
        rules_lines = []
        for key in sorted(self._type_rules.keys()):
            rule = self._type_rules[key]
            name = rule.get("name", key)
            anti = rule.get("anti_patterns", [])
            metrics = rule.get("correct_metrics_examples", [])
            anti_str = "、".join(anti) if anti else "（无）"
            metrics_str = "、".join(metrics) if metrics else "（无）"
            rules_lines.append(f"- {key}({name}): 禁止指标={anti_str}；示例正确指标={metrics_str}")
        rules_block = "\n".join(rules_lines)

        return f"""你是A股行业分析专家。请为【{industry_name}】行业生成分析框架。

## 第一步：判断行业类型
从以下类型中选择最匹配的一个：{type_list}

## 第二步：继承类型通用规则
根据你判断的行业类型，必须继承该类型的所有通用规则。每个类型对应的规则为（禁止指标=绝对不能用于该行业的指标，示例正确指标=该行业常用的正确分析指标）：
{rules_block}

## 第三步：追加行业特有anti_patterns + 生成correct_metrics
在继承的类型规则基础上，追加该行业特有的跨行业误用指标。然后生成该行业最重要的8-10个分析指标。

按以下JSON格式返回（只返回JSON）：
{{{{
  "name": "{industry_name}",
  "name_en": "",
  "industry_type": "判断出的行业类型key",
  "keywords": ["{industry_name}", "列举5-10个同义词或子行业"],
  "correct_metrics": ["列举8-10个该行业最重要的分析指标"],
  "anti_patterns": ["继承的类型规则中的禁止指标" + "该行业特有的禁止指标（并集合并，不覆盖）"],
  "peer_companies": ["列举5-8家A股龙头公司"],
  "context_instruction": "50-80字中文分析指导"
}}}}

要求：
- anti_patterns必须是：类型规则禁止指标 ∪ 行业特有禁止指标（并集合并，不覆盖）
- correct_metrics必须是该行业真实使用的核心指标
- peer_companies必须是A股真实上市公司"""
    ```
  - Update `_auto_generate()` L139: change `_AUTO_GEN_PROMPT.format(industry=industry_name)` → `self._build_auto_gen_prompt(industry_name)`
  - Keep `_AUTO_GEN_PROMPT` constant as fallback (when `_type_rules` is empty)

  **Must NOT do**:
  - Do NOT delete _AUTO_GEN_PROMPT constant（保留作为回退）
  - Do NOT modify _type_rules JSON structure
  - Do NOT change the 3-step prompt flow

  **Recommended Agent Profile**: `deep`
  - Multi-method refactoring with prompt engineering and backward compat

  **Parallelization**: Sequential step 3, blocked by T2

  **QA Scenarios**:
  ```
  Scenario: Dynamic prompt includes type rules from JSON
    Tool: Bash (python -c)
    Steps:
      1. python3 -c "from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework(); p = fw._build_auto_gen_prompt('测试'); assert 'manufacturing' in p; assert '禁止指标' in p; assert '示例正确指标' in p; print('OK')"
    Expected: "OK"
    Evidence: .omo/evidence/task-3-dynamic-prompt.txt

  Scenario: Fallback when _type_rules empty
    Tool: Bash (python -c)
    Steps:
      1. python3 -c "from tradingagents.industry.frameworks import IndustryFramework, _AUTO_GEN_PROMPT; fw = IndustryFramework.__new__(IndustryFramework); fw._type_rules = {}; p = fw._build_auto_gen_prompt('测试'); exp = _AUTO_GEN_PROMPT.format(industry='测试'); assert p == exp; print('OK')"
    Expected: "OK"
    Evidence: .omo/evidence/task-3-fallback.txt

  Scenario: Existing tests still pass
    Tool: Bash (python3 -m pytest)
    Steps:
      1. python3 -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py -v
    Expected: 21 passed
    Evidence: .omo/evidence/task-3-regression.txt
  ```

  **Commit**: YES
  - Files: `tradingagents/industry/frameworks.py`

- [x] 4. **Run full verification and regression**

  **What to do**:
  - Run: `python3 -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py -v`
  - Run: `python3 -m pytest tests/ -x -q --ignore=tests/test_industry_classifier.py`（skip slow network tests）
  - Verify: `python3 -c "from tradingagents.industry.frameworks import IndustryFramework; fw = IndustryFramework(); p = fw._build_auto_gen_prompt('测试行业'); assert len(p) > 500; print(f'Prompt length: {len(p)} chars')"`

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Sequential step 4

  **QA Scenarios**: Same as T1-T3 above, combined verification

  **Commit**: NO（verification only）

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Verify: executor.py has verifier import + call between L168-170, api_server.py has industry_verification field, frameworks.py has _build_auto_gen_prompt()
  Output: `Executor [WIRED/NOT WIRED] | API [FIELD/FIELD MISSING] | Prompt [DYNAMIC/HARDCODED] | VERDICT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run tests: 21 pass. Check: no hardcoded rules in prompt, fallback works, no new imports break anything.
  Output: `Tests [N/N] | Hardcoding [CLEAN/STALE] | Fallback [WORKS/BROKEN] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute: curl /analyze ×2 (valid ticker, invalid ticker), verify industry_verification presence/absence.
  Output: `Valid [VERIFIED/FAILED] | Invalid [SKIPPED/FAILED] | VERDICT`

- [x] F4. **Regression Sweep** — `unspecified-high`
  Full non-network test suite, agent_utils.py untouched check.
  Output: `Full Suite [N/N] | agent_utils [CLEAN/DIRTY] | VERDICT`

---

## Commit Strategy

- **1**: `feat(executor): wire IndustryVerifier into execute() with flag-and-continue` — executor.py
- **2**: `feat(api): add industry_verification field to AnalyzeResponse` — api_server.py
- **3**: `refactor(industry): make _AUTO_GEN_PROMPT dynamic from _type_rules JSON` — frameworks.py

---

## Success Criteria

- [ ] verifier 在成功分析后自动运行
- [ ] API response 包含 industry_verification 字段
- [ ] _AUTO_GEN_PROMPT 从 _type_rules 动态生成
- [ ] _type_rules 为空时回退到硬编码
- [ ] 21 tests pass, 0 regression
