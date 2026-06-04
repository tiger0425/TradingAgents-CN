# Draft: Kimi World Bank Data Integration

## Requirements (confirmed)
- Integrate `world_bank_open_data` from Kimi Code Gateway API into TradingAgents data layer
- Route: Kimi Gateway REST API → `tradingagents/dataflows/kimi_gateway.py` → `interface.py` route_to_vendor
- Replace guosen dependency for macro_economic category
- OAuth token from `~/.kimi/credentials/kimi-code.json`

## Technical Decisions
- New adapter file: `tradingagents/dataflows/kimi_gateway.py`
- Register as `"kimi"` vendor in `interface.py`
- Token managed via reading credentials file, with expiry detection
- Config: new env vars `KIMI_OAUTH_ENABLED` (default false, opt-in)
- API discovery pattern: call `get_data_source_desc("world_bank_open_data")` on init, cache the schema

## Research Findings
- Gateway API endpoint: `POST https://api.kimi.com/coding/v1/tools`
- Auth: Bearer token from `~/.kimi/credentials/kimi-code.json`
- Billed per-call
- Desc must be fetched before calling tools (dynamic schema)
- World Bank covers 189 countries, 50+ years of data

## Open Questions
- None blocking - all clear

## Scope Boundaries
- INCLUDE: world_bank_open_data integration via Kimi Gateway
- INCLUDE: Token management + config
- INCLUDE: Registration in interface.py router
- INCLUDE: Tests
- EXCLUDE: stock_finance_data, yahoo_finance, tianyancha, arxiv, scholar
- EXCLUDE: Existing data source modifications
