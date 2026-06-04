# 辩论 + 风控 Agent 行业反模式注入

## TL;DR

> **Quick Summary**: 修复辩论 Agent（bull/bear）和风控 Agent（aggressive/conservative/neutral）的行业上下文缺口——当前仅收到行业名无 anti_patterns。通过 `IndustryFramework.lookup()` 注入禁止指标列表，形成完整 Prompt 约束链。
>
> **Deliverables**:
> - `bull_researcher.py` + `bear_researcher.py` — 注入 anti_patterns
> - `context_manager.py` — `inject_context()` 增加 framework lookup
> - `aggressive_debator.py` + `conservative_debator.py` + `neutral_debator.py` — 新增行业锚定

> **Estimated Effort**: Short（~25 min）

---

## Context

### 根因
辩论和风控 Agent 未收到 anti_patterns，只有行业名。LLM 看到"通信线缆及配套"但没被告知"禁止讨论光模块/CPO"，自由发挥到不相关领域。

### 当前保护 vs 缺口

| Agent | 行业名 | anti_patterns | 来源 |
|-------|:-----:|:------------:|------|
| 4 analysts | ✅ | ✅ | `build_instrument_context()` |
| bull/bear researcher | ✅ | ❌ | `inject_context()` |
| 3 risk debaters | ❌ | ❌ | 直接读 state |

---

## Work Objectives

### Core Objective
将 IndustryFramework 的 anti_patterns 注入到辩论和风控 Agent 的 prompt 中，消除全链路最后一个行业错配缺口。

### Must Have
- bull/bear 收到 anti_patterns 列表
- `inject_context()` 返回 `anti_patterns`
- 3 risk debaters 收到行业锚定约束

### Must NOT Have
- 不修改 IndustryVerifier 逻辑
- 不修改 analyst prompt 结构
- 不修改 JSON 框架定义

---

## TODOs

- [x] 1. **`inject_context()` 增加 framework lookup（context_manager.py）**

  **What to do**:
  - 在 `inject_context()` 的 return dict 前，新增 framework lookup：`from tradingagents.industry.frameworks import IndustryFramework`
  - 当 `state.get("industry")` 非空时，调用 `IndustryFramework().lookup(industry)` 获取 anti_patterns
  - return dict 新增字段：`"anti_patterns": anti_patterns_list`

  **Recommended Agent Profile**: `quick`

  **Acceptance Criteria**:
  - [ ] `python3 -c "from tradingagents.graph.context_manager import ContextWindowManager; print('import OK')"`

  **Commit**: YES
  - Files: `tradingagents/graph/context_manager.py`

- [x] 2. **bull_researcher 注入 anti_patterns**

  **What to do**:
  - 从 `ctx["anti_patterns"]` 获取反模式列表（由 Task 1 的 inject_context 返回）
  - 当 anti_patterns 非空时，在 `industry_info` 后追加具体禁止术语
  - 格式：``**⚠️ 严格禁止使用以下不适用于{industry}行业的术语：** {anti_patterns}``

  **Recommended Agent Profile**: `quick`

  **Acceptance Criteria**:
  - [ ] `ctx["anti_patterns"]` 非空时 prompt 包含具体禁止术语
  - [ ] 不改变现有 prompt 结构

  **Commit**: YES
  - Files: `tradingagents/agents/researchers/bull_researcher.py`

- [x] 3. **bear_researcher 注入 anti_patterns**

  **What to do**: 同 Task 2，修改 bear_researcher.py

  **Recommended Agent Profile**: `quick`

  **Commit**: YES
  - Files: `tradingagents/agents/researchers/bear_researcher.py`

- [x] 4. **3 risk debaters 注入行业锚定**

  **What to do**:
  - 从 `state.get("industry")` 获取行业名
  - 当 industry 非空时，在 prompt 开头注入行业锚定约束
  - 格式：``**⚠️ 行业锚定约束：** 你正在评估的交易标的属于【{industry}】行业。评估风险时必须基于该行业实际的商业模式和关键驱动因素。``
  - 同时查找 framework 注入 anti_patterns

  **Recommended Agent Profile**: `quick`

  **Acceptance Criteria**:
  - [ ] 3 个 risk debater prompt 包含行业锚定约束

  **Commit**: YES
  - Files: `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`

- [x] 5. **Run full verification and regression**

  **What to do**: `python3 -m pytest tests/test_industry_framework.py tests/test_industry_verifier.py -v`

  **Commit**: NO（verification only）

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Verify: context_manager returns anti_patterns, bull/bear inject them, risk debaters have industry block
  Output: `CWM [PASS/FAIL] | BullBear [PASS/FAIL] | Risk [PASS/FAIL] | VERDICT`

- [x] F2. **Code Quality + Tests** — `unspecified-high`
  Run 21 industry tests, check import chain, verify no hardcoded values
  Output: `Tests [N/N] | Imports [OK/FAIL] | VERDICT`

- [x] F3. **Regression Sweep** — `unspecified-high`
  Non-network tests, agent_utils.py untouched check
  Output: `Full Suite [N/N] | agent_utils [CLEAN/DIRTY] | VERDICT`

---

## Commit Strategy

- **1**: `feat(context): add anti_patterns lookup to inject_context()` — context_manager.py
- **2**: `feat(bull): inject anti_patterns into debate prompt` — bull_researcher.py
- **3**: `feat(bear): inject anti_patterns into debate prompt` — bear_researcher.py
- **4**: `feat(risk): add industry anchoring to risk debaters` — 3 risk_debator.py files

---

## Success Criteria

- [ ] bull/bear prompt 包含 anti_patterns 禁止术语
- [ ] risk debater prompt 包含行业锚定
- [ ] 21 tests pass, 0 regression
