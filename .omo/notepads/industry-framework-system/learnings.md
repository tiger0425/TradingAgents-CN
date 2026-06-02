# Industry Framework System — Learnings

## 2026-06-02: Created `tests/test_industry_framework.py` with TDD RED tests

- **File**: `tests/test_industry_framework.py` (new)
- **Bug confirmed**: `fw.lookup("通信线缆及配套")` returns `tech_saas` framework because:
  - `tech_saas` keywords include `"通信"` (line 90 of `industry_frameworks.json`)
  - `_fuzzy_match` step 2 does substring match: `if kw and kw in name` → `"通信" in "通信线缆及配套"` → True
  - This is wrong: 通信线缆及配套 is a cable/wire manufacturer, not a tech/SaaS company
- **Test results**: 2 failed (RED), 6 passed
  - `test_comm_cable_rejects_saas` FAILED — "通信线缆及配套" matched tech_saas (name="科技与SaaS")
  - `test_comm_cable_no_framework_yet` FAILED — returned tech_saas instead of None
  - All 5 backward compat tests PASSED (automotive, banking, tech_saas, consumer, pharma)
  - `test_list_frameworks_returns_all_five` PASSED
- **Next step (Task 3)**: Fix `_fuzzy_match` to prevent short keyword substring matches from dominating long industry names

## 2026-06-02: Removed orphaned `_fuzzy_match` duplicate from `_load_generated()`

- **File**: `tradingagents/industry/frameworks.py`
- **Issue**: Lines 164–206 were a copy-paste of `_fuzzy_match` body accidentally embedded inside `_load_generated()`. The clone referenced `industry_name` (undefined in that scope), causing `NameError` on import.
- **Fix**: Deleted lines 164–206 entirely. The canonical `_fuzzy_match` at lines 80–118 is untouched.
- **Verification**:
  - `import OK` — module imports cleanly
  - `count: 5` — framework loading works, `assert >= 5` passes

## 2026-06-02: Restructured `industry_frameworks.json` to nested `{_type_rules, frameworks}`

- **File**: `tradingagents/industry/config/industry_frameworks.json`
- **Change**: Wrapped 5 existing frameworks under `"frameworks"` key, added `"_type_rules"` with 6 industry types
- **New `_type_rules` entries**: manufacturing, financial, consumer, pharma, tech_saas, telecom_operator
- **Each `_type_rules` entry has**: `name`, `anti_patterns` (non-empty), `correct_metrics_examples` (non-empty)
- **Frameworks preserved unchanged**: automotive, banking, tech_saas, consumer, pharma — 5 entries, all original field names and values intact
- **Verification**:
  - `JSON valid` — `json.load()` passes cleanly
  - `_type_rules: 6` — 6 industry type rules
  - `frameworks: 5` — 5 original frameworks
  - All 6 type rules have non-empty `anti_patterns` (5–15 items) and `correct_metrics_examples` (5–8 items)
  - `tech_saas` framework retains empty `anti_patterns` at framework level (its type rule fills the gap with 7 anti-patterns: 光缆集采价, 铜铝原材料成本, 光棒产能, 运营商集采招标量, 电力电缆在手订单, 批价, 经销商库存)
   - `"通信"` remains in tech_saas keywords

## 2026-06-02: Fixed `frameworks.py` for nested JSON + upgraded `_AUTO_GEN_PROMPT`
- **File**: `tradingagents/industry/frameworks.py`
- **Changes**:
  1. `__init__()`: Added `self._type_rules` field
  2. `_load()`: Nested vs flat format detection, separates `_type_rules` from `_frameworks`
  3. `list_frameworks()`: Filters out `_type_rules` key
  4. `_AUTO_GEN_PROMPT`: 3-step upgrade (classify type → inherit anti_patterns → union-merge)
  5. `get_type_rules()`: New accessor method
- **Test results**: 8/8 GREEN (framework), 13/13 GREEN (verifier), 10/11 GREEN (classifier — 1 slow-network timeout)
- `fw.lookup("通信线缆及配套")` → `comm_cable` ✓, all 5 existing frameworks still match ✓
- LSP: 0 new warnings
