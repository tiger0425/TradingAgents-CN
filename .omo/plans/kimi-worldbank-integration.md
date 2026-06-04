# Kimi World Bank Macro Data Integration

## TL;DR

> **Quick Summary**: Integrate `world_bank_open_data` from Kimi Code Gateway API into TradingAgents as a new `"kimi"` data vendor for the `macro_economic` category, supplementing/replacing the guosen `get_macro_data()` dependency.
> 
> **Deliverables**:
> - `tradingagents/dataflows/kimi_gateway.py` — Kimi Gateway HTTP client with token management and API discovery
> - `tradingagents/dataflows/interface.py` — Register `"kimi"` vendor + `get_world_bank_data` tool
> - `tradingagents/dataflows/macro_context.py` — Add world bank section to `fetch_macro_context()`
> - `tests/test_kimi_gateway.py` — Unit tests with mocked HTTP
> - Config updates: `.env.example`, `tradingagents/dataflows/config.py`
> 
> **Estimated Effort**: Short
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1 → Task 2 → Task 3

---

## Context

### Original Request
User asked to analyze whether `kimi-datasource` (Kimi Code CLI official plugin) can provide data to the current TradingAgents-cn project, then requested a work plan to integrate `world_bank_open_data` — the most valuable and non-overlapping data source.

### Interview Summary
**Key Discussions**:
- kimi-datasource is a thin plugin wrapping the Kimi Code Gateway REST API (`POST https://api.kimi.com/coding/v1/tools`)
- 6 data sources available behind the gateway; only `world_bank_open_data` is in scope
- OAuth Bearer token authentication from `~/.kimi/credentials/kimi-code.json`
- API discovery pattern: call `get_data_source_desc` first, then `call_data_source_tool`
- Billed per-call — opt-in only, not default vendor
- World Bank covers 189 countries, 50+ years, dozens of indicators

**Research Findings**:
- Project uses `route_to_vendor()` pattern in `interface.py` — adding a new vendor is straightforward
- `macro_economic` category currently only has `guosen` vendor with `get_macro_data()` tool
- `macro_context.py` aggregates 6 sections (US indices, USD/CNY, commodities, VIX, northbound, bond yield) — world bank data would add a 7th section
- Existing test infrastructure: pytest, mock-based testing pattern in `test_macro_context.py`
- Project already depends on `requests` library

### Gap Analysis (self-performed)
- **API schema instability**: World Bank APIs are discovered dynamically via `get_data_source_desc` — plan must handle schema changes gracefully
- **Token expiry**: OAuth tokens expire — need detection + clear error messaging
- **Rate limiting**: Per-call billing means we should cache desc responses
- **Scope creep guard**: Only `world_bank_open_data`, NOT stock_finance_data/tianyancha/etc.

---

## Work Objectives

### Core Objective
Add `world_bank_open_data` as a `"kimi"` vendor in the `macro_economic` data category, enabling TradingAgents to fetch World Bank macroeconomic indicators (GDP, CPI, trade, population, carbon, etc.) via the Kimi Code Gateway API, with guosen retained as fallback.

### Concrete Deliverables
- `tradingagents/dataflows/kimi_gateway.py` — reusable Kimi Gateway HTTP client
- `tradingagents/dataflows/interface.py` — new `"kimi"` vendor registration + `get_world_bank_data` tool
- `tradingagents/dataflows/macro_context.py` — new `_fetch_world_bank()` section
- `tests/test_kimi_gateway.py` — unit tests with mocked gateway responses
- `.env.example` — new `KIMI_OAUTH_ENABLED` env var

### Definition of Done
- [ ] `pytest tests/test_kimi_gateway.py -v` → ALL PASS (no real network)
- [ ] `pytest tests/test_macro_context.py -v` → ALL PASS (existing tests unbroken)
- [ ] `python -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient; print('import OK')"` → success
- [ ] `curl` smoke test with real Kimi account returns valid world bank data (manual, opt-in)

### Must Have
- Token reading from `~/.kimi/credentials/kimi-code.json`
- `get_data_source_desc` caching (call once, reuse)
- `call_data_source_tool` method with error handling
- `get_world_bank_data(query)` tool function matching the `macro_economic` tool interface
- Opt-in configuration (`KIMI_OAUTH_ENABLED=true`)
- Graceful degradation when token missing or expired
- Unit tests with mocked HTTP

### Must NOT Have (Guardrails)
- NO integration of `stock_finance_data`, `yahoo_finance`, `tianyancha`, `arxiv`, `scholar`
- NO breaking changes to existing `route_to_vendor` behavior
- NO hard dependency on Kimi credentials — API server must start without them
- NO auto-enabling — `"kimi"` must never be the default vendor for any category
- NO real HTTP calls in unit tests
- NO changes to guosen.py or a_stock_data.py

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (after)
- **Framework**: pytest (already configured)
- **If TDD**: N/A — tests written after implementation

### QA Policy
Every task MUST include agent-executed QA scenarios (see TODO template below).
Evidence saved to `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API/Backend**: Use Bash (curl + python) — Send requests, assert status + response fields
- **Library/Module**: Use Bash (python REPL) — Import, call functions, compare output

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - foundation):
├── Task 1: KimiGatewayClient module [unspecified-high]
└── Task 2: interface.py registration [quick]

Wave 2 (After Wave 1 - parallel integration + tests + config):
├── Task 3: macro_context.py world_bank section [quick]
├── Task 4: Unit tests for kimi_gateway [unspecified-high]
└── Task 5: Config + env vars [quick]

Wave FINAL (After ALL tasks):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real manual QA [unspecified-high]
└── Task F4: Scope fidelity check [deep]
```

**Critical Path**: Task 1 → Task 2 → Task 3
**Parallel Speedup**: ~50% faster than sequential (Tasks 3, 4, 5 run in parallel)
**Max Concurrent**: 3 (Wave 2)

---

## TODOs

- [ ] 1. Create `KimiGatewayClient` module (`tradingagents/dataflows/kimi_gateway.py`)

  **What to do**:
  - Create `tradingagents/dataflows/kimi_gateway.py` with class `KimiGatewayClient`
  - Constructor: reads OAuth token from `~/.kimi/credentials/kimi-code.json`, stores `_token`, `_base_url = "https://api.kimi.com/coding/v1/tools"`
  - Method `_ensure_token()`: re-reads credentials file if token missing, raises `RuntimeError` with clear message if file not found or token absent (user needs to run `kimi login`)
  - Method `_request(method, params)`: POST to `_base_url` with JSON body `{"method": method, "params": params}`, Bearer auth header, `Content-Type: application/json`, 30s timeout. Returns parsed JSON dict. Raises `RuntimeError` on HTTP errors with status code + body.
  - Method `get_data_source_desc(name: str) -> dict`: calls `_request("get_data_source_desc", {"name": name})`, caches result in `_desc_cache` dict keyed by name. Returns the raw response dict.
  - Method `call_data_source_tool(data_source_name: str, api_name: str, params: dict) -> str`: calls `_request("call_data_source_tool", {...})`, extracts text from response envelope (prefer `assistant` channel, fallback `user` channel, then raw JSON). Returns string.
  - Module-level convenience function: `get_world_bank_data(query: Annotated[str, "自然语言查询"]) -> str`:
    - Instantiates `KimiGatewayClient`
    - Calls `get_data_source_desc("world_bank_open_data")` to get available APIs
    - Maps natural language query to appropriate API call (for MVP, use a generic search/query API from the desc; document that desc must be checked for exact API names)
    - Calls `call_data_source_tool("world_bank_open_data", api_name, {"query": query})`
    - Returns formatted result string
  - Add `__all__ = ["KimiGatewayClient", "get_world_bank_data"]`

  **Must NOT do**:
  - Do NOT add dependencies beyond `requests`, `json`, `pathlib`, `os`, `uuid` (all already in project)
  - Do NOT hardcode API names — always discover via `get_data_source_desc`
  - Do NOT cache tokens beyond the current `KimiGatewayClient` instance lifetime
  - Do NOT import from any other tradingagents module (keep it self-contained)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires careful HTTP client design with error handling, token management, and API discovery pattern — not a trivial file creation
  - **Skills**: None specific — pure Python HTTP client

  **Parallelization**:
  - **Can Run In Parallel**: NO (Task 2 depends on this module's exports)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 2, Task 3, Task 4, Task 5
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):
  **Pattern References** (existing code to follow):
  - `tradingagents/dataflows/guosen.py:130-180` — `_make_request()` pattern for unified HTTP calls with timeout/error handling
  - `tradingagents/dataflows/guosen.py:105-113` — `_ensure_gs_api_key()` pattern for credential validation with clear error messages
  - `tradingagents/dataflows/guosen.py:407-424` — `get_macro_data()` signature and return format (natural language query → formatted string)
  **API/Type References** (contracts to implement against):
  - `/tmp/kimi-datasource-extracted/kimi-datasource/scripts/call_data_source_tool.py:24-61` — Gateway API endpoint, auth headers, request format
  - `/tmp/kimi-datasource-extracted/kimi-datasource/scripts/call_data_source_tool.py:92-117` — `extract_text()` response envelope parsing logic
  **Test References** (testing patterns to follow):
  - `tests/test_macro_context.py:1-50` — Mock-based testing with `unittest.mock.patch` and `MagicMock`
  - `tests/test_macro_context.py:89-98` — `test_graceful_degradation` pattern for error handling tests

  **Acceptance Criteria**:
  - [ ] File `tradingagents/dataflows/kimi_gateway.py` exists with `KimiGatewayClient` class
  - [ ] `python -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient, get_world_bank_data; print('import OK')"` → success
  - [ ] `KimiGatewayClient()` raises `RuntimeError` when `~/.kimi/credentials/kimi-code.json` does not exist
  - [ ] `_request()` method correctly formats JSON-RPC-style body and Bearer auth headers

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Import and instantiate with no credentials (error path)
    Tool: Bash (python REPL)
    Preconditions: ~/.kimi/credentials/kimi-code.json does NOT exist (or temporarily renamed)
    Steps:
      1. Run: python3 -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient; c = KimiGatewayClient()"
      2. Assert stderr or exit code indicates RuntimeError about missing credentials
    Expected Result: Clear error message telling user to run `kimi login`
    Failure Indicators: Silent success, ImportError, or generic "file not found" without guidance
    Evidence: .omo/evidence/task-1-no-creds-error.txt

  Scenario: Module import succeeds (happy path)
    Tool: Bash (python REPL)
    Preconditions: Module file exists, requests library available
    Steps:
      1. Run: python3 -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient, get_world_bank_data; print('OK')"
      2. Assert stdout contains "OK", exit code 0
    Expected Result: Clean import, no errors
    Failure Indicators: ImportError, ModuleNotFoundError, syntax errors
    Evidence: .omo/evidence/task-1-import-ok.txt
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-1-no-creds-error.txt` — error output
  - [ ] `.omo/evidence/task-1-import-ok.txt` — import success

  **Commit**: YES
  - Message: `feat(dataflows): add KimiGatewayClient for world bank macro data`
  - Files: `tradingagents/dataflows/kimi_gateway.py`

- [ ] 2. Register `"kimi"` vendor in `interface.py`

  **What to do**:
  - Add `"kimi"` to `VENDOR_LIST` in `tradingagents/dataflows/interface.py`
  - Import `get_world_bank_data` from `.kimi_gateway`
  - Add `"get_world_bank_data"` to `TOOLS_CATEGORIES["macro_economic"]["tools"]` list
  - Add entry in `VENDOR_METHODS`:
    ```python
    "get_world_bank_data": {
        "kimi": get_world_bank_data,
        "guosen": get_macro_data,  # fallback: use guosen as generic macro fallback
    },
    ```
  - Verify `route_to_vendor("get_world_bank_data")` resolves correctly

  **Must NOT do**:
  - Do NOT change default `data_vendors.macro_economic` to `"kimi"` — guosen stays default
  - Do NOT modify existing `get_macro_data` entry in VENDOR_METHODS
  - Do NOT add kimi to any category other than `macro_economic`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding a few lines to existing registration tables — straightforward, well-understood pattern
  - **Skills**: None needed

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 1 for the import)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References** (CRITICAL):
  **Pattern References** (existing code to follow):
  - `tradingagents/dataflows/interface.py:232-238` — `VENDOR_LIST` registration pattern
  - `tradingagents/dataflows/interface.py:310-312` — single-vendor method registration pattern (guosen `get_macro_data`)
  - `tradingagents/dataflows/interface.py:204-207` — `macro_economic` category tools list

  **Acceptance Criteria**:
  - [ ] `"kimi"` present in `VENDOR_LIST`
  - [ ] `"get_world_bank_data"` present in `macro_economic` tools
  - [ ] `route_to_vendor("get_world_bank_data", query="test")` calls `get_world_bank_data` when kimi is configured
  - [ ] Existing `get_macro_data` still works unchanged

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Vendor registration check (happy path)
    Tool: Bash (python REPL)
    Preconditions: Task 1 complete, kimi_gateway.py exists
    Steps:
      1. Run: python3 -c "from tradingagents.dataflows.interface import VENDOR_LIST, VENDOR_METHODS, TOOLS_CATEGORIES; assert 'kimi' in VENDOR_LIST; assert 'get_world_bank_data' in VENDOR_METHODS; assert 'get_world_bank_data' in TOOLS_CATEGORIES['macro_economic']['tools']; print('OK')"
      2. Assert exit code 0, stdout contains "OK"
    Expected Result: All three registrations confirmed
    Failure Indicators: KeyError, AssertionError, ImportError
    Evidence: .omo/evidence/task-2-registration-ok.txt

  Scenario: Existing route_to_vendor still works (regression)
    Tool: Bash (python REPL)
    Preconditions: Task 1 complete
    Steps:
      1. Run: python3 -c "from tradingagents.dataflows.interface import route_to_vendor; print('route_to_vendor imported OK')"
      2. Assert exit code 0
    Expected Result: No import errors, existing routing intact
    Failure Indicators: ImportError caused by new imports breaking existing code
    Evidence: .omo/evidence/task-2-no-regression.txt
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-2-registration-ok.txt`
  - [ ] `.omo/evidence/task-2-no-regression.txt`

  **Commit**: YES (groups with Task 1)
  - Message: `feat(dataflows): register kimi vendor for macro_economic category`
  - Files: `tradingagents/dataflows/interface.py`

- [ ] 3. Add world bank section to `macro_context.py`

  **What to do**:
  - Add new function `_fetch_world_bank() -> str` in `tradingagents/dataflows/macro_context.py`
  - Function logic:
    - Check env var `KIMI_OAUTH_ENABLED` — if not `"true"`, return empty string (graceful opt-out)
    - Try to instantiate `KimiGatewayClient` and call `get_data_source_desc("world_bank_open_data")`
    - Pick a few key indicators for the default query: China GDP growth, CPI, trade balance — or use a single generic query like "中国近五年GDP增速和CPI"
    - Call `get_world_bank_data(query)` from `kimi_gateway`
    - Format result as `"世行: {summary}"` (max ~200 chars, consistent with other sections)
    - On any error (token missing, network, API error), return empty string (never crash the aggregator)
  - Add `_fetch_world_bank()` call to `fetch_macro_context()` sections list, after `_fetch_bond_yield()`
  - Keep total output under 1400 chars (increase cap from 1200 to 1400 to accommodate new section)

  **Must NOT do**:
  - Do NOT change existing section logic or formats
  - Do NOT raise exceptions — `_fetch_world_bank` must always return a string
  - Do NOT make the presence of world bank data required — empty string on any failure

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding one function following existing pattern with minimal logic — straightforward
  - **Skills**: None needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 1, Task 2

  **References** (CRITICAL):
  **Pattern References** (existing code to follow):
  - `tradingagents/dataflows/macro_context.py:73-88` — `_fetch_us_indices()` pattern: try/except → formatted string or "——"
  - `tradingagents/dataflows/macro_context.py:263-289` — `fetch_macro_context()` sections list and length cap pattern
  - `tradingagents/dataflows/macro_context.py:52-66` — `_safe_float()` utility for safe value extraction
  **API/Type References**:
  - `tradingagents/dataflows/kimi_gateway.py` — `get_world_bank_data(query)` function signature (Task 1 deliverable)
  - `tradingagents/dataflows/kimi_gateway.py` — `KimiGatewayClient` class for direct use if needed

  **Acceptance Criteria**:
  - [ ] `_fetch_world_bank()` function exists and returns a string
  - [ ] When `KIMI_OAUTH_ENABLED != "true"`, returns `""` (no error)
  - [ ] `fetch_macro_context()` output includes world bank section when enabled
  - [ ] Total output ≤ 1400 chars
  - [ ] Existing tests in `test_macro_context.py` still pass (world bank section gracefully absent when no creds)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: World bank section absent when KIMI_OAUTH_ENABLED is not set (happy path - default behavior)
    Tool: Bash (python REPL)
    Preconditions: KIMI_OAUTH_ENABLED is NOT set in environment
    Steps:
      1. Run: python3 -c "import os; os.environ.pop('KIMI_OAUTH_ENABLED', None); from tradingagents.dataflows.macro_context import _fetch_world_bank; r = _fetch_world_bank(); print(f'result=|{r}|'); assert r == ''"
      2. Assert exit code 0, empty result
    Expected Result: Empty string returned, no error raised
    Failure Indicators: Exception raised, non-empty string returned, import error
    Evidence: .omo/evidence/task-3-disabled-empty.txt

  Scenario: Existing macro_context tests unbroken (regression check)
    Tool: Bash (pytest)
    Preconditions: Task 3 changes applied, KIMI_OAUTH_ENABLED not set
    Steps:
      1. Run: python3 -m pytest tests/test_macro_context.py -v --tb=short
      2. Assert all tests pass (exit code 0)
    Expected Result: All existing tests pass — no regressions
    Failure Indicators: Any test failure, especially in test_all_sections_present or test_output_length_cap
    Evidence: .omo/evidence/task-3-regression-pass.txt
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-3-disabled-empty.txt`
  - [ ] `.omo/evidence/task-3-regression-pass.txt`

  **Commit**: YES (groups with Tasks 4, 5)
  - Message: `feat(dataflows): add world bank section to macro context`
  - Files: `tradingagents/dataflows/macro_context.py`

- [ ] 4. Write unit tests (`tests/test_kimi_gateway.py`)

  **What to do**:
  - Create `tests/test_kimi_gateway.py`
  - Test class `TestKimiGatewayClient`:
    - `test_init_no_credentials_file` — mock `pathlib.Path.exists` to return False, assert RuntimeError with "kimi login" guidance
    - `test_init_bad_credentials_json` — mock file read to return invalid JSON, assert RuntimeError
    - `test_init_missing_token` — mock file read to return `{}`, assert RuntimeError about missing access_token
    - `test_init_success` — mock file read to return `{"access_token": "test-token-123"}`, verify `_token` set
    - `test_get_data_source_desc_cached` — mock `_request` to return `{"result": "cached"}`, call twice, assert `_request` called only once (cache hit)
    - `test_call_data_source_tool_extracts_assistant` — mock `_request` to return `{"is_success": true, "result": {"assistant": [{"type": "text", "text": "GDP data"}]}}`, assert returns "GDP data"
    - `test_call_data_source_tool_fallback_user` — mock to return user channel only, assert returns user text
    - `test_call_data_source_tool_failure` — mock `_request` to return `{"is_success": false, "error": {"user": [{"text": "API not found"}]}}`, assert error message in result
    - `test_request_http_error` — mock `urllib.request.urlopen` to raise `HTTPError(401, "Unauthorized", None, None, io.BytesIO(b"{}"))`, assert RuntimeError
    - `test_get_world_bank_data_function` — mock `KimiGatewayClient` methods, assert function returns formatted string
  - Use `unittest.mock.patch` extensively — ZERO real HTTP calls

  **Must NOT do**:
  - Do NOT make real HTTP calls to api.kimi.com
  - Do NOT require actual `~/.kimi/credentials/kimi-code.json` file
  - Do NOT test with real API keys

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires thorough mock setup covering 10+ test cases, edge cases, and error paths
  - **Skills**: None needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3, 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 1 (needs the module to test against)

  **References** (CRITICAL):
  **Pattern References** (existing code to follow):
  - `tests/test_macro_context.py:1-50` — Mock pattern with `@pytest.fixture(autouse=True)`, `MagicMock`, `patch`
  - `tests/test_macro_context.py:57-110` — Test class structure: test methods, assertions, import-in-test pattern
  **API/Type References**:
  - `tradingagents/dataflows/kimi_gateway.py` — `KimiGatewayClient` class API (Task 1 deliverable)

  **Acceptance Criteria**:
  - [ ] Test file `tests/test_kimi_gateway.py` exists with 10+ test methods
  - [ ] `pytest tests/test_kimi_gateway.py -v` → ALL PASS (0 failures)
  - [ ] No real HTTP calls in test output (verify via `--log-cli-level=DEBUG` or mock assertions)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: All tests pass
    Tool: Bash (pytest)
    Preconditions: Task 1 and Task 2 complete
    Steps:
      1. Run: python3 -m pytest tests/test_kimi_gateway.py -v --tb=short
      2. Assert exit code 0
      3. Assert no "PASSED" count >= 10
    Expected Result: All tests pass, no skipped or failed
    Failure Indicators: Any "FAILED" or "ERROR" in output
    Evidence: .omo/evidence/task-4-tests-pass.txt

  Scenario: Zero real network calls
    Tool: Bash (pytest + grep)
    Preconditions: Tests use mock, no network available
    Steps:
      1. Run with blocked network: python3 -m pytest tests/test_kimi_gateway.py -v
      2. Assert all pass even with no network connectivity
    Expected Result: Tests pass without network (mock isolation verified)
    Failure Indicators: ConnectionError, timeout, or urllib calls leaking through mocks
    Evidence: .omo/evidence/task-4-no-network.txt
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-4-tests-pass.txt`
  - [ ] `.omo/evidence/task-4-no-network.txt`

  **Commit**: YES (groups with Tasks 3, 5)
  - Message: `test(dataflows): add unit tests for KimiGatewayClient`
  - Files: `tests/test_kimi_gateway.py`

- [ ] 5. Add configuration support

  **What to do**:
  - Add `KIMI_OAUTH_ENABLED` to `.env.example`:
    ```bash
    # Kimi OAuth 集成（可选，用于接入世界银行宏观经济数据）
    # 设置为 true 前需先运行 `kimi login` 完成 OAuth 登录
    # 按次计费，每次调用消耗 Kimi 账户额度
    KIMI_OAUTH_ENABLED=false
    ```
  - In `tradingagents/dataflows/config.py` (or wherever `DEFAULT_CONFIG` lives), add to `data_vendors`:
    ```python
    # kimi is available as a macro_economic vendor but NOT default
    # Users opt in via KIMI_OAUTH_ENABLED=true env var
    ```
  - Ensure `route_to_vendor` correctly reads `KIMI_OAUTH_ENABLED` before attempting kimi vendor — or rely on the `_fetch_world_bank` function's own guard (Task 3 already handles this)
  - Add a comment in `interface.py` near the `"kimi"` vendor registration explaining the opt-in nature

  **Must NOT do**:
  - Do NOT make `"kimi"` the default for any category
  - Do NOT add kimi to `.env` (only `.env.example`)
  - Do NOT require `KIMI_OAUTH_ENABLED` for API server to start

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding env var documentation and config comments — trivial, well-understood
  - **Skills**: None needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3, 4)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 2

  **References** (CRITICAL):
  **Pattern References** (existing code to follow):
  - `.env.example:1-6` — Existing env var documentation format
  - `tradingagents/dataflows/guosen.py:12-16` — Env var documentation comments pattern

  **Acceptance Criteria**:
  - [ ] `.env.example` contains `KIMI_OAUTH_ENABLED` with documentation
  - [ ] Code comments in `interface.py` explain kimi vendor is opt-in

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Env var documented in .env.example
    Tool: Bash (grep)
    Preconditions: Task 5 complete
    Steps:
      1. Run: grep -A3 "KIMI_OAUTH_ENABLED" .env.example
      2. Assert output contains "KIMI_OAUTH_ENABLED=false" and documentation about kimi login
    Expected Result: Env var present with clear documentation
    Failure Indicators: Missing from .env.example, no documentation comments
    Evidence: .omo/evidence/task-5-env-var-documented.txt

  Scenario: API server starts without KIMI_OAUTH_ENABLED (regression)
    Tool: Bash (python)
    Preconditions: KIMI_OAUTH_ENABLED not set
    Steps:
      1. Run: python3 -c "from tradingagents.dataflows.interface import VENDOR_LIST; print('OK')"
      2. Assert exit code 0
    Expected Result: Import succeeds without env var — no hard dependency
    Failure Indicators: ImportError or RuntimeError about missing env var
    Evidence: .omo/evidence/task-5-no-hard-dep.txt
  ```

  **Evidence to Capture**:
  - [ ] `.omo/evidence/task-5-env-var-documented.txt`
  - [ ] `.omo/evidence/task-5-no-hard-dep.txt`

  **Commit**: YES (groups with Tasks 3, 4)
  - Message: `config: add KIMI_OAUTH_ENABLED for world bank data opt-in`
  - Files: `.env.example`, `tradingagents/dataflows/interface.py` (comments only)

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. Verify all Must Have items implemented. Search for Must NOT Have violations. Check evidence files exist.

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient"` + `pytest tests/test_kimi_gateway.py tests/test_macro_context.py -v`. Check for AI slop.

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Execute all QA scenarios from every task. Test cross-task integration.

- [ ] F4. **Scope Fidelity Check** — `deep`
  Verify no unintended changes to guosen.py, a_stock_data.py, or existing vendor behavior.

---

## Commit Strategy

- **1**: `feat(dataflows): add KimiGatewayClient for world bank macro data` - tradingagents/dataflows/kimi_gateway.py
- **2**: `feat(dataflows): register kimi vendor for macro_economic category` - tradingagents/dataflows/interface.py
- **3-5**: `feat(dataflows): integrate world bank data into macro context + tests + config` - tradingagents/dataflows/macro_context.py, tests/test_kimi_gateway.py, .env.example

---

## Success Criteria

### Verification Commands
```bash
# Unit tests
pytest tests/test_kimi_gateway.py -v

# Existing tests unbroken
pytest tests/test_macro_context.py -v

# Import check
python -c "from tradingagents.dataflows.kimi_gateway import KimiGatewayClient; print('OK')"

# Interface registration check
python -c "from tradingagents.dataflows.interface import VENDOR_LIST, VENDOR_METHODS; assert 'kimi' in VENDOR_LIST; print('OK')"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Existing macro_context tests unbroken
