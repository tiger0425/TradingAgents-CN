# Industry Framework System — Learnings

## 2026-06-02: Removed orphaned `_fuzzy_match` duplicate from `_load_generated()`

- **File**: `tradingagents/industry/frameworks.py`
- **Issue**: Lines 164–206 were a copy-paste of `_fuzzy_match` body accidentally embedded inside `_load_generated()`. The clone referenced `industry_name` (undefined in that scope), causing `NameError` on import.
- **Fix**: Deleted lines 164–206 entirely. The canonical `_fuzzy_match` at lines 80–118 is untouched.
- **Verification**:
  - `import OK` — module imports cleanly
  - `count: 5` — framework loading works, `assert >= 5` passes
