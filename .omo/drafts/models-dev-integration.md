# Draft: models.dev Integration Plan

## Requirements (confirmed)
- [Core]: Add models.dev as dynamic model catalog source for tradingagents-cn
- [Integration Level]: Level 2 (medium) - add fetcher, mapper, generator; modify model_catalog.py; keep factory unchanged
- [Fallback]: Hardcoded MODEL_OPTIONS remains as fallback when models.dev is unavailable
- [Scope Lock]: fetcher read-only; no auto-refresh scheduler; no pre-call cost estimation; no capability-aware dispatch

## Technical Decisions
- [Fetcher]: New `tradingagents/llm_clients/models_dev_fetcher.py` - fetch + disk cache with TTL
- [Mapper]: New `tradingagents/llm_clients/provider_mapper.py` - alibaba-cn→qwen, zhipuai→glm, rest identity
- [Generator]: New `tradingagents/llm_clients/dynamic_catalog.py` - produces ProviderModeOptions-compatible dict
- [Classification]: Composite heuristic (NOT reasoning=true alone) - cost + capability + name analysis
- [Hardcoded catalog]: Kept as classification authority; dynamic adds new models only
- [Validation]: Never tightened - unknown models still pass
- [Test Strategy]: Tests-after + Agent QA (pytest 8.0.0 with pytest-cov, 46 existing test files)
- [Provider Mappings - VERIFIED]: openai→openai(52), anthropic→anthropic(24), google→google(21), deepseek→deepseek(4), xai→xai(8), minimax→minimax(6), qwen→alibaba-cn(82), glm→zhipuai(12), ollama→N/A(local runner,expected)

## Metis Review Findings
- [Gap]: reasoning=true as sole deep/quick heuristic is DANGEROUS → composite approach
- [Gap]: Provider mappings need verification → must verify all 8 current providers
- [Gap]: Edge cases: malformed JSON, schema change, startup regression → addressed in plan
- [Scope]: Pre-call cost estimation → DEFERRED (separate feature)
- [Scope]: Capability-aware dispatch → DEFERRED (separate feature)
- [Scope]: Auto-refresh scheduler → DEFERRED (separate feature)
- [Bug Found]: `model_name=` in cli/research_report.py:30 and cli/notice.py:30 → included in plan
- [NOT Bug]: `_DEFAULT_ENV_OVERRIDES` empty → by design, excluded from plan

## Scope Boundaries
- INCLUDE: models_dev_fetcher, provider_mapper, dynamic_catalog, modified model_catalog, bug fixes, tests
- EXCLUDE: pre-call cost estimation, capability-aware dispatch, auto-refresh, factory changes, CostTracker changes
