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

## 2026-06-02: Disable DeepSeek thinking mode to prevent hallucination

### Problem
DeepSeek v4-pro's thinking mode generated creative chain-of-thought that hallucinated fictional companies when analyzing A-share tickers. v4-flash has no thinking mode — this is why it didn't hallucinate. MiniMax already had thinking disabled but DeepSeek did not.

### Changes Made

**File: `tradingagents/llm_clients/openai_client.py`**
- Added `thinking: {"type": "disabled"}` to `extra_body` in the DeepSeek provider block (before `return DeepSeekChatOpenAI(**llm_kwargs)`)
- Uses same `setdefault` chaining pattern as MiniMax at lines 274-276
- Comment: `# Disable thinking mode to prevent hallucination on opaque tickers`

### Behavior Matrix

| Provider | Before | After |
|----------|--------|-------|
| DeepSeek (v4-pro) | thinking enabled → hallucination on opaque tickers | thinking disabled → no hallucination |
| MiniMax | thinking disabled | thinking disabled (unchanged) |
| structured.py `bind_structured()` | temporarily enables/controls thinking | still works (no change) |

### Design Decision
1. **Same pattern as MiniMax** — `llm_kwargs.setdefault("model_kwargs", {}).setdefault("extra_body", {})` then set `thinking = {"type": "disabled"}`.
2. **Client-level fix** — Disabling at the client level is the correct layer because it affects all regular (non-structured) invocations uniformly. Structured output (via `structured.py`) temporarily overrides thinking settings per-call.
3. **No structued.py changes needed** — `bind_structured()` already handles thinking toggle correctly via `with_structured_output()` configuration.
4. **Reasoning split not needed** — `reasoning_split = True` is MiniMax-specific; DeepSeek doesn't use it.

## 2026-06-02: Add `get_company_name()` for entity grounding

### Changes Made

**File: `tradingagents/dataflows/a_stock_data.py`**
- Added `get_company_name(code: str) -> str` function (right after `get_current_price_a()`)
- Reuses the same Tencent Finance API pattern: `https://qt.gtimg.cn/q={prefix}{code}` → parse `~` delimited response → `vals[1]` is the company name
- Uses existing `UA`, `TIMEOUT`, and `_get_session()` infrastructure

### Design Decisions

1. **Same prefix logic as `get_current_price_a()`** — `"sh"` for codes starting with `"6"` or `"9"`, `"sz"` for others.
2. **Graceful degradation** — Returns `code` itself on any exception. A transient network failure must never crash the caller.
3. **16 lines** — Kept deliberately minimal. No new imports, no dependencies, no complexity.
4. **`resp.encoding = "gbk"`** — Tencent Finance uses GBK encoding; same pattern as `get_current_price_a()`.
5. **Name-only extraction** — Unlike `get_current_price_a()` which validates 50+ fields, this function only requires `vals[1]` to be non-empty. Minimal parsing.

### Verification

| Code | Expected | Actual |
|------|----------|--------|
| `600418` | 江淮汽车 | ✅ |
| `600519` | 贵州茅台 | ✅ |
| `000001` | 平安银行 | ✅ |

## 2026-06-02: Wave 4.5 — Inject company_name into AgentState and first human message

### Changes Made

**File: `tradingagents/graph/executor.py`**
- Added import: `from ..dataflows.a_stock_data import get_company_name`
- In `_build_init_state()`, after `ticker` resolution: wrapped `get_company_name(ticker)` in try/except, falling back to `ticker` itself on any failure
- Added `"company_name": company_name_str` to the returned state dict (after `"industry"` line) — all agents can now access `state["company_name"]`
- Enriched the first human message: when `company_name_str != ticker` (name lookup succeeded), appends `（公司：{company_name_str}，代码：{ticker}）` to the user message for entity grounding

### Key Design Decisions
1. **Graceful fallback** — `try/except Exception` ensures a transient network failure never blocks analysis. `company_name_str = ticker` means `company_name` in state will be the raw ticker, which all downstream code handles correctly.
2. **Conditional enrichment** — The `if company_name_str != ticker` guard prevents double-counting when the lookup fails (e.g., `company_name_str = "600418"` would not add a redundant suffix).
3. **Zero imports beyond one function** — Only `get_company_name` is imported, not the entire module.
4. **No signature changes** — `_build_init_state()` signature is untouched; all callers are unaffected.

### Verification
- ✅ LSP diagnostics: no new errors (all 12 pre-existing)
- ✅ `company_name` in state dict after `industry`
- ✅ `get_company_name("600418")` → `"江淮汽车"` injected into state and message
- ✅ `get_company_name()` failure → `company_name_str = ticker`, no enrichment
- ✅ Function signature unchanged

## 2026-06-02: Wave 4 — Extend `build_instrument_context` with company_name parameter

### Changes Made

**File: `tradingagents/agents/utils/agent_utils.py`**
- Added `company_name: str = ""` keyword argument to `build_instrument_context()` after `industry` parameter
- When non-empty: display name becomes `"{company_name} ({ticker})"` (e.g. `江淮汽车 (600418)`) instead of backtick-wrapped `` `{ticker}` ``
- When empty: behavior is identical to original (backtick-wrapped ticker)
- Updated docstring with company_name parameter description
- All other logic (exchange hint, industry appendix) completely unchanged

### Behavior Matrix

| company_name | industry | Output example |
|---|---|---|
| `""` (empty) | `""` | `The instrument to analyze is \`600418\`.` |
| `"江淮汽车"` | `""` | `The instrument to analyze is 江淮汽车 (600418).` |
| `"江淮汽车"` | `"商用载货车"` | `The instrument to analyze is 江淮汽车 (600418). ... **行业背景：** ...` |
| `""` | `"商用载货车"` | `The instrument to analyze is \`600418\`. ... **行业背景：** ...` |

### Design Decisions
1. **Optional keyword arg only** — `company_name=""` default ensures zero breakage for all 7 existing call sites that pass only ticker.
2. **Display name computed via conditional expression** — `f"{company_name} ({ticker})" if company_name else f"`{ticker}`"` keeps it simple, no branching in the f-string.
3. **No backticks on company_name version** — Natural language style (`江淮汽车 (600418)`) is more readable and LLM-friendly when the company name is known. The backtick emphasis is only needed for opaque numeric codes.
4. **Pure string helper** — No import changes, no side effects, no external lookup.

### Verification

| Test | Result |
|---|---|
| `build_instrument_context("600418")` unchanged | ✅ |
| `build_instrument_context("600418", company_name="江淮汽车")` contains "江淮汽车 (600418)" | ✅ |
| `build_instrument_context("600418", industry="商用载货车", company_name="江淮汽车")` contains both | ✅ |
| LSP diagnostics — no new errors | ✅ (only 3 pre-existing `list` type arg warnings) |

(End of file - total 321 lines)

## 2026-06-02: Wave 5 — Pass `industry` and `company_name` from all 7 agent call sites

### Problem
Wave 4 added `company_name=` and `industry=` params to `build_instrument_context()`, but none of the 7 call sites passed them — `build_instrument_context(state["company_of_interest"])` was called everywhere with only the ticker. The LLM never saw `江淮汽车 (600418)`, only `` `600418` ``.

### Changes Made

**All 7 agent files** — same pattern, two new reads + pass to `build_instrument_context`:

```python
company_name = state.get("company_name", "")
industry = state.get("industry", "")
instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name)
```

| File | Variable pattern | Special handling |
|---|---|---|
| `market_analyst.py` | standard | `industry` read **moved before** build call (was after) |
| `fundamentals_analyst.py` | standard | `industry` read moved before build call |
| `news_analyst.py` | standard | `industry` read moved before build call |
| `social_media_analyst.py` | standard | `industry` read moved before build call |
| `research_manager.py` | standard | Added reads (none existed); duplicate `industry = state.get()` at old location removed |
| `portfolio_manager.py` | standard | Added reads; duplicate industry read later removed (now uses the single read) |
| `trader.py` | `company_display` | `company_name` already used for ticker, so `company_display = state.get("company_name", "")` passed to `build_instrument_context`; duplicate `industry = state.get()` removed |

### Design Decisions
1. **Read once, reuse** — For agents that already read `state["industry"]` for separate prompt injection, the read was moved before `build_instrument_context()` and reused, preventing duplicate dict lookups.
2. **`trader.py` uses `company_display`** — `company_name` was already bound to `state["company_of_interest"]` (the ticker), so a separate `company_display` variable holds the Chinese name.
3. **Backward compatible** — `state.get("company_name", "")` and `state.get("industry", "")` both default to empty string, producing identical output to pre-Wave-5 behavior when no company_name/industry is in state.

### Behavior Matrix

| company_name in state | industry in state | LLM sees |
|---|---|---|
| missing / `""` | missing / `""` | `` The instrument to analyze is `600418`. `` (identical to before) |
| missing / `""` | `"商用载货车"` | `` The instrument to analyze is `600418`. ... **行业背景：** ... `` |
| `"江淮汽车"` | missing / `""` | `The instrument to analyze is 江淮汽车 (600418).` |
| `"江淮汽车"` | `"商用载货车"` | `The instrument to analyze is 江淮汽车 (600418). ... **行业背景：** ...` |

### Verification
| Check | Result |
|---|---|
| All 7 agents pass `industry=` + `company_name=` to `build_instrument_context()` | ✅ |
| `state.get()` used (never `state[]`) — safe when key missing | ✅ |
| 0 duplicate `state.get("industry")` reads across all 7 files | ✅ |
| LSP diagnostics — 0 new errors (all warnings pre-existing) | ✅ |
| trader.py `company_display` vs `company_name` correctly scoped | ✅ |
| portfolio_manager.py industry read not duplicated | ✅ |
| research_manager.py duplicate read removed | ✅ |

## 2026-06-02: Wave 6 — Inject IndustryFramework metrics/anti-patterns into build_instrument_context

### Problem
`build_instrument_context()` injected only a weak single-sentence industry hint: `"分析时请关注该行业的核心指标和竞争格局"`. The LLM received no concrete guidance on *which* metrics to use or *which* to avoid.

### Changes Made

**File: `tradingagents/agents/utils/agent_utils.py`**
- Replaced the single `if industry:` sentence block with a data-driven pipeline:
  1. Lazy-import `IndustryFramework` inside the function (try/except for circular import safety)
  2. Call `IndustryFramework().lookup(industry)` when industry is non-empty
  3. If framework found AND has `correct_metrics` or `anti_patterns`: emit a **行业分析框架（必须遵守）** block
     - `- 核心指标：` joined with "、"
     - `- 不适用指标：` joined with "、"
     - Optional `分析指导：{context_instruction}` paragraph
  4. If framework not found or lists empty: fall back to the original single-sentence behavior
- Original **行业背景** sentence is always emitted when industry is non-empty (regardless of framework found)

### Design Decisions
1. **Lazy import inside function body** — `IndustryFramework` lives in `tradingagents.industry` which may not be importable at module level (circular dependency risk). `try/except Exception` ensures a missing/external module never crashes the function.
2. **Framework block always follows 行业背景** — The background sentence provides general context; the framework block provides specific, actionable guidance. Both are needed.
3. **`correct_metrics` and `anti_patterns` gating** — If both lists are empty/null, the entire framework block is suppressed. This avoids empty bullet points like `- 核心指标：`.
4. **"、" as list separator** — Chinese convention for separating items in a list (not commas).

### Behavior Matrix

| industry | Framework found | Framework has data | Output includes framework block |
|---|---|---|---|
| `""` | N/A | N/A | ❌ (no industry text at all) |
| `"未知行业"` | ❌ | N/A | ❌ (only **行业背景** sentence) |
| `"旅游综合"` | ❌ | N/A | ❌ (only **行业背景** sentence) |
| `"商用载货车"` | ✅ (automotive) | ✅ (8 metrics, 12 anti) | ✅ **行业分析框架** with data |
| `"银行"` | ✅ (banking) | ✅ (10 metrics, 11 anti) | ✅ **行业分析框架** with data |

### Verification

| Test | Result |
|---|---|
| `build_instrument_context("600418", "商用载货车", "江淮汽车")` contains "产能利用率" (correct_metrics) | ✅ |
| `build_instrument_context("600418", "商用载货车", "江淮汽车")` contains "续约率" (anti_patterns) | ✅ |
| `build_instrument_context("600418", "商用载货车", "江淮汽车")` contains "分析指导" (context_instruction) | ✅ |
| `build_instrument_context("600418")` no industry text at all | ✅ |
| `build_instrument_context("600418", "未知行业XXX")` has 行业背景 but no framework | ✅ |
| `build_instrument_context("600418", "商用载货车")` works without company_name | ✅ |
| LSP diagnostics — 0 new errors | ✅ |

## 2026-06-02: Wave 6 — Inject industry into bull_researcher / bear_researcher prompts

### Problem
`ContextWindowManager.inject_context()` already returned `"industry": state.get("industry", "")` (line 217), but neither `bull_researcher.py` nor `bear_researcher.py` read it. The debate agents — the **loudest** from token perspective (6+ rounds) — had no industry grounding, so they blindly accepted terminology from analyst reports.

### Changes Made

**File: `tradingagents/agents/researchers/bull_researcher.py`**
- Added `industry = ctx.get("industry", "")` after existing `ctx` reads (alongside `reports_text`, `debate_history`, `market_context`)
- Built conditional `industry_info` block — empty string when `industry` is empty, full Chinese anchoring block when non-empty:
  ```python
  f"""
  **⚠️ 行业锚定约束：** 你正在辩论的标的属于【{industry}】行业。所有论点必须基于该行业实际的商业模式、竞争格局和关键驱动因素。严禁使用与{industry}行业无关的术语或分析框架。
  """
  ```
- Inserted `{industry_info}` at the **TOP** of the prompt f-string, **BEFORE** "You are a Bull Analyst..."

**File: `tradingagents/agents/researchers/bear_researcher.py`**
- Same pattern: `industry = ctx.get("industry", "")`, `industry_info` conditional, `{industry_info}` at top of prompt before "You are a Risk Analyst..."

### Key Design Decisions
1. **Read from ctx, not state** — Unlike the 7 agent files (Wave 5) which read `state.get("industry")`, bull/bear researchers read from `ctx` because they use `ContextWindowManager.inject_context()` which already returns `industry`. This is consistent with how they read `reports_summary`, `debate_history`, and `market_context` — all from `ctx`.
2. **Prepend, not append** — Industry anchoring is placed at the TOP of the prompt as a hard constraint before any role description. This is deliberate: industry context must frame how the LLM interprets all subsequent instructions and data. Appending would let the role description settle in without the constraint.
3. **No new imports** — Both files only import `ContextWindowManager`, unchanged. No `IndustryFramework` import needed.
4. **Empty industry = zero footprint** — When `ctx.get("industry", "")` returns `""`, the `if industry:` guard produces `industry_info = ""`, and `f"""{industry_info}You are a ..."""` is identical to the original `f"""You are a ..."""`.

### Behavior Matrix

| `ctx["industry"]` | Prompt top has industry block? | Empty = no change? |
|---|---|---|
| `""` (empty) | ❌ | ✅ — exact same prompt as before |
| `"商用载货车"` | ✅ — `**⚠️ 行业锚定约束：** 你正在辩论的标的属于【商用载货车】行业...` | N/A |
| `"银行"` | ✅ — `**⚠️ 行业锚定约束：** 你正在辩论的标的属于【银行】行业...` | N/A |

### Verification
| Check | Result |
|---|---|
| LSP diagnostics — 0 new errors (all pre-existing) | ✅ |
| Industry anchoring at TOP of prompt (before role description) | ✅ |
| Empty industry → same prompt | ✅ |
| ContextWindowManager.inject_context() not touched | ✅ |
| bear_researcher.py same pattern | ✅ |
