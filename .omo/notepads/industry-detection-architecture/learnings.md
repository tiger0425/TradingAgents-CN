# Industry Detection Architecture — Learnings

## 2026-06-02: Wave 1 — Extend `build_instrument_context` with industry parameter

### Changes Made

**File: `tradingagents/agents/utils/agent_utils.py`**
- Added `industry: str = ""` keyword argument to `build_instrument_context()`
- When non-empty: appends `\n\n**行业背景：** 该股票属于 {industry} 行业。分析时请关注该行业的核心指标和竞争格局。`
- When empty: behavior is identical to original (no extra text)
- Updated docstring to document the new parameter

**File: `tradingagents/graph/context_manager.py`**
- Added `"industry": state.get("industry", "")` to the return dict of `inject_context()`
- This feeds industry context into the bull/bear debate agents via `ContextWindowManager`

### Verification Results

| Test | Result |
|------|--------|
| `build_instrument_context("600418", industry="商用载货车")` contains "商用载货车" + "行业背景" | ✅ |
| `build_instrument_context("600418")` does NOT contain "行业背景" | ✅ |
| `inject_context()` return dict contains "industry" key | ✅ |
| Existing callers with single positional arg | ✅ no breakage |
| All 252 tests pass (111 unit + 141 structured) | ✅ |

### Key Design Decisions

1. **Optional keyword arg only** — All 7 existing call sites pass a single positional `ticker` arg. Adding `industry=...` after required params preserves full backward compatibility.
2. **No get_industry() call inside** — Industry must be passed in by the caller, keeping the function a pure string helper.
3. **Chinese prompt style** — Matches existing `get_language_instruction()` and `get_degradation_instruction()` style of `**粗体标题：** ...` format.
4. **Appended after ticker hint** — Industry context is an additive layer on top of the existing ticker format info, not a replacement.

## 2026-06-02: Wave 2 — Inject industry context into 5 agent prompts

### Changes Made

**File: `tradingagents/agents/analysts/news_analyst.py`**
- Added `industry = state.get("industry", "")` after `build_instrument_context()`
- If non-empty: appends `\n\n**行业政策关注：** ...` to `instrument_context`
- Since `instrument_context` is injected via `{.partial()}`, the industry sentence flows naturally into the prompt template

**File: `tradingagents/agents/analysts/social_media_analyst.py`**
- Same pattern as `news_analyst.py`, different sentence: `\n\n**行业舆情特征：** ...`
- Uses `instrument_context` injection via `.partial()`

**File: `tradingagents/agents/managers/portfolio_manager.py`**
- Added `industry = state.get("industry", "")` before the `# Add market context` block
- If non-empty: `prompt += \n\n**行业基准参考：** ...`
- Placed alongside existing `market_context` injection for logical grouping

**File: `tradingagents/agents/trader/trader.py`**
- Added `industry_note` string constructed from `state.get("industry", "")`
- If non-empty: `\n\n**行业交易特征：** ...`
- Appended to system message content via `+ industry_note` after `get_degradation_instruction()`

**File: `tradingagents/agents/managers/research_manager.py`**
- Added `industry = state.get("industry", "")` after the main `prompt = f"""..."""`
- If non-empty: `prompt += \n\n**行业对标框架：** ...`

### Design Decisions

1. **Two injection patterns**: Analysts (`.partial()`) get industry injected into `instrument_context`; f-string based agents get standalone `prompt +=` blocks. Both achieve the same result — ONE sentence appended when industry is non-empty.
2. **Zero behavior change when empty**: `state.get("industry", "")` returns empty by default, `if ""` is falsy, so all 5 agents behave identically to before when no industry is detected.
3. **trader.py `industry_note` approach**: Unlike the other 4, trader uses a dict-based `messages` list. Adding `industry_note` as a variable set before the list and concatenated into `system_message["content"]` keeps the message list construction clean.
4. **portfolio_manager.py placement**: Industry injection sits before market_context injection (both are calibration references). No interference between the two.

### Verification

| File | Industry="商用载货车" contains industry text | Industry="" has no extra text |
|------|:---:|:---:|
| news_analyst.py | ✅ | ✅ |
| social_media_analyst.py | ✅ | ✅ |
| portfolio_manager.py | ✅ | ✅ |
| trader.py | ✅ | ✅ |
| research_manager.py | ✅ | ✅ |

## 2026-06-02: Wave 2 — Inject industry context into market_analyst system prompt

### Changes Made

**File: `tradingagents/agents/analysts/market_analyst.py`**
- Added `industry = state.get("industry", "")` after existing state reads (line 21)
- Built `industry_section` as a conditional f-string — empty string when industry is empty, `"\n\n**行业技术面特征：** ..."` when non-empty (lines 22-28)
- Inserted `+ industry_section` into the system_message concatenation chain after `get_language_instruction()` and `get_degradation_instruction()` (line 63)
- Existing A-Share Technical Focus block (lines 49-60) is completely untouched

### Design Decisions
1. **Post-instruction insertion** — Placed after language + degradation instructions, before the "Remember: you are" reminder. This ensures industry context is fresh in the LLM's attention window when it begins analysis.
2. **Zero footprint when empty** — `industry_section` is `""` when `industry` is empty, producing identical behavior to original code with no extra concatenation overhead.
3. **Technical-angle wording** — The injected text uses technical-analysis-specific language (技术形态, 交易活跃度, 板块联动, 行业轮动, 板块排名) to match the market_analyst's role as technical analysis specialist.

### Verification
- ✅ `industry = ""` → `industry_section` is `""`, system_message unchanged
- ✅ `industry = "商用载货车"` → system_message includes "**行业技术面特征：** 当前分析的股票属于 商用载货车 行业。..."
- ✅ A-Share Technical Focus block preserved verbatim
- ✅ No new imports added
- ✅ LSP diagnostics: clean (0 errors)

## 2026-06-02: Wave 2 — Inject industry into fundamentals_analyst system_message

### Changes Made

**File: `tradingagents/agents/analysts/fundamentals_analyst.py`**
- Added `industry = state.get("industry", "")` after `instrument_context` assignment (line 23)
- Added conditional `industry_guidance` string (lines 24-27) — resolves to either a Chinese industry analysis framework prompt or empty string
- Inserted `+ industry_guidance` into the `system_message` concatenation chain after `get_degradation_instruction()` (line 56)
- A-Share context block (lines 41-53) completely untouched
- No new imports added
- ChatPromptTemplate + MessagesPlaceholder pattern unchanged

### Behavior Matrix

| `state["industry"]` | system_message includes industry block? |
|---|---|
| `""` (empty) | ❌ — exact same prompt as before |
| `"商用载货车"` | ✅ — appends `**行业分析框架：** 该公司属于 商用载货车 行业...` |
| Missing key | ✅ — `state.get("industry", "")` returns `""`, no injection |

### Verification

| Check | Result |
|---|---|---|
| LSP diagnostics — no new warnings | ✅ (all pre-existing) |
| Existing A-Share block unmodified | ✅ |
| No new imports | ✅ |
| Empty industry → same prompt | ✅ (empty string concatenation is no-op) |

## 2026-06-02: Wave 2 — Activate industry scoring in TemplateMatcher

### Problem
`_extract_features()` at line 72 already returned `"industry": context.industry or ""`, but `_score_template()` (lines 75-96) completely ignored the industry feature. Dead code from an abandoned feature attempt.

### Changes Made

**File: `tradingagents/planner/template_matcher.py`**
- Added industry scoring block in `_score_template()` between the `required_context` check and the `use_count`/`success_rate` computation:
  - `features.get("industry")` and `patterns.get("industry_keywords")` must both be truthy
  - Inner match: `industry in keywords` (exact) or `any(kw in industry for kw in keywords)` (substring)
  - Boost: **+0.15** to score
  - Capped at 1.0 by existing `max(0.0, min(1.0, score))` on line 95
- No changes to existing scoring weights (keyword hits: 0.4, use_count: 0.1, success_rate: 0.1)
- No changes to `_extract_features()` or any other method

**File: `tradingagents/templates/tpl_standard_analysis.json`**
- Added `"industry_keywords": ["行业", "板块", "业"]` to `match_patterns`
- This template uses `{industry}` in workflow steps 2 and 3

**File: `tradingagents/templates/tpl_breakeven_recovery.json`**
- Added `"industry_keywords": ["行业", "板块", "业"]` to `match_patterns`
- This template uses `{industry}` in workflow steps 2 and 3

**File: `tradingagents/templates/tpl_weekly_screening.json`**
- Added `"industry_keywords": ["行业", "板块", "业"]` to `match_patterns`
- This template involves industry rotation scanning in workflow step 2

### Not Updated (no `{industry}` in workflow)
- `tpl_morning_briefing.json` — portfolio-level, no per-ticker industry context
- `tpl_midday_review.json` — portfolio-level, no per-ticker industry context
- `tpl_closing_review.json` — portfolio-level, no per-ticker industry context

### Scoring Behavior Matrix

| Industry | Template has `industry_keywords` | Industry matches keyword | Score change |
|---|---|---|---|
| `""` (empty) | ✅ | N/A | +0.0 |
| `"银行"` | ✅ | `"业" in "银行"` → ✅ | +0.15 |
| `"证券行业"` | ✅ | `"行业" in "证券行业"` → ✅ | +0.15 |
| `"商用载货车"` | ✅ | `any(kw in "商用载货车")` → ❌ | +0.0 |
| any non-empty | ❌ (no key) | N/A | +0.0 |

Note: The substring matching `any(kw in industry)` rewards templates whose `industry_keywords` contain characters/terms that appear in real industry names. For best results, template authors should add industry-specific keywords (e.g., `"车"` for automotive, `"医"` for healthcare) when a template targets specific sectors.

### Design Decisions
1. **Boost only, never a blocker** — Industry is an additive scoring signal (like success_rate), not a required context. A template with zero industry match can still win on keyword hits alone.
2. **Double-gated** — Both the industry feature AND the template's `industry_keywords` list must be non-empty. Templates that don't declare `industry_keywords` are unaffected.
3. **Cap preserved** — The existing `max(0.0, min(1.0, score))` automatically handles the +0.15 boost without overflow.
4. **Zero behavior change for unmodified templates** — Templates without `industry_keywords` key see no change in scoring.

## 2026-06-02: Wave 3 — Layer 3 Consistency Verifier

### Changes Made

**File: `tradingagents/industry/verifier.py`**
- Added `verify_industry_consistency(industry, report, quick_llm=None) -> dict` static method
- Two-tier architecture:
  - **Tier 1 (rules, always runs)**: Looks up industry framework via `IndustryFramework.lookup()`, scans report for anti-pattern keywords (case-insensitive). If any match → `{"consistent": false, "severity": "error", "method": "rules"}`.
  - **Tier 2 (LLM fallback, optional)**: When a framework exists but no anti-patterns were found by rules, a single quick_llm call performs deeper semantic check. Only runs if `quick_llm` is passed.
- `_llm_check()` helper: wraps LLM invocation with graceful degradation on parse/network errors
- `_parse_json_response()` helper: 3-strategy JSON extraction (raw → fenced → regex) to handle varied LLM output formats
- Core philosophy: **LLM never called when rules give definitive answer**; **never exceeds 1 LLM call**; **transient LLM failure never produces false-positive mismatch**

**File: `tradingagents/industry/__init__.py`**
- No changes needed — `IndustryVerifier` was already exported

**File: `tests/test_industry_verifier.py`** (new)
- 13 TDD tests covering:
  - Rule layer: auto+SaaS anti-patterns, auto+correct metrics, banking+manufacturing anti-patterns, unknown industry, empty inputs
  - LLM layer: semantic issue detection, consistency confirmation, not-called-when-rules-definitive, graceful degradation on exception, not-called-when-no-framework
  - Edge case: tech_saas (empty anti_patterns list), multiple anti-patterns all reported

### Design Decisions

1. **LLM is optional dependency** — `quick_llm=None` by default. The verifier works perfectly without any LLM; the rule layer alone catches the primary class of bugs (SaaS metrics in automotive reports). LLM tier adds depth without fragility.
2. **LLM as semantic fallback, not override** — LLM results carry `severity="warning"` vs rules' `severity="error"`. The LLM refines rather than contradicts the rule layer.
3. **Graceful degradation** — Any LLM failure (exception, parse error, timeout) returns `{"consistent": true}` rather than raising. A transient LLM issue must never produce a false-positive industry mismatch that could cascade into wrong analyst behavior.
4. **`_parse_json_response` 3-pass strategy** — LLMs often wrap JSON in markdown fences or add commentary. The parser tries: (1) raw JSON parse if response starts with `{`, (2) extract from ` ```json ` fences, (3) regex for any `{...}` block. This avoids fragile `.strip().removeprefix().removesuffix()` chains.
5. **Framework-less industries are consistent by default** — If `IndustryFramework.lookup()` returns `None` for an industry name, no consistency checking is performed. This avoids false positives for novel or niche industry classifications.
6. **Zero behavior change for existing callers** — Existing `is_known()` and `is_confident()` methods, plus test_industry_classifier.py, are completely untouched.

### Verification

| Test | Result |
|------|--------|
| Auto report with SaaS anti-patterns → inconsistent (rules) | ✅ |
| Auto report with correct metrics → consistent (rules) | ✅ |
| Unknown industry → consistent (no framework) | ✅ |
| Banking report with manufacturing metrics → inconsistent (rules) | ✅ |
| Multiple anti-patterns all reported | ✅ |
| Empty industry/report → consistent | ✅ |
| tech_saas (no anti-patterns) → consistent (rules) | ✅ |
| LLM detects semantic issue (rules inconclusive) → inconsistent (LLM) | ✅ |
| LLM confirms consistency → consistent (LLM) | ✅ |
| LLM NOT called when rules definitive | ✅ |
| LLM exception → graceful degradation | ✅ |
| LLM NOT called when no framework | ✅ |
| All 23 industry tests pass (13 verifier + 10 classifier) | ✅ |
