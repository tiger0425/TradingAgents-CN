.PHONY: test test-cov test-ci

PYTHON = python3

test:
	$(PYTHON) -m pytest tests/ -v

test-cov:
	$(PYTHON) -m pytest --cov=tradingagents --cov-report=term-missing tests/ -v

test-ci:
	$(PYTHON) -m pytest --cov=tradingagents --cov-fail-under=70 tests/ -v
