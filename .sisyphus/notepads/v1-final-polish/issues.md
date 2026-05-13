# Issues — v1-final-polish

## F3: Portfolio Chat Endpoint (2026-05-14)

### Critical: .format() crash on PORTFOLIO_PARSE_PROMPT
- **File**: `tradingagents/api_server.py`, lines 63-84 (prompt), line 191 (usage)
- **Symptom**: `KeyError('\n  "action"')` at runtime
- **Root cause**: JSON schema in prompt uses `{` and `}` without escaping. Python's `str.format()` interprets them as format specifiers.
- **Fix needed**: Change all `{` and `}` in the JSON template to `{{` and `}}`, keeping `{message}` as-is.
- **Impact**: The endpoint will never successfully parse any user message.

### Warning: entry_date missing from PortfolioChatResponse
- **File**: `tradingagents/api_server.py`, line 53-60 (model), line 201 (usage)
- **Symptom**: `entry_date` parsed from LLM output and passed to `add_holding()`, but not included in the response model.
- **Fix needed**: Add `entry_date: str = ""` to `PortfolioChatResponse`.
