# Learnings — v1-final-polish

## F3: Portfolio Chat Endpoint Verification (2026-05-14)

- Pydantic models import and instantiate correctly
- Route registration works: POST /portfolio/chat
- Endpoint has comprehensive logic: empty check, LLM try/except, 4 action handlers, unknown fallback, LLM-unavailable fallback
- Pattern: Endpoint reads `entry_date` from LLM output but doesn't include it in the response model
- Testing pattern: Use `inspect.getsource()` for structural verification of endpoint logic without running the server
