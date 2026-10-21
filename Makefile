.PHONY: help bootstrap data data-resume test test-int test-live test-all lint typecheck ci verify-p1 clean-data

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
PYTEST ?= $(VENV)/bin/pytest
RUFF ?= $(VENV)/bin/ruff
MYPY ?= $(VENV)/bin/mypy

help:
	@echo "RegulatorIQ Makefile Targets:"
	@echo "  bootstrap    - Set up venv and install dependencies"
	@echo "  data         - Run official RBI corpus acquisition"
	@echo "  data-resume  - Resume interrupted corpus acquisition"
	@echo "  test         - Run fast unit tests"
	@echo "  test-int     - Run integration tests (no network)"
	@echo "  test-live    - Run live tests against real RBI endpoints"
	@echo "  test-all     - Run all unit, property, and integration tests"
	@echo "  lint         - Run ruff linter and code formatting check"
	@echo "  typecheck    - Run mypy type checker"
	@echo "  ci           - Run lint, typecheck, and test-all (CI pipeline)"
	@echo "  verify-p1    - Run Phase 1 verification gate"
	@echo "  clean-data   - Clean local downloaded raw data"

bootstrap:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@if [ -f .git/hooks/pre-commit ]; then echo "Pre-commit hook already exists"; else $(VENV)/bin/pre-commit install 2>/dev/null || true; fi

data:
	$(PYTHON) -m ingest.cli acquire

data-resume:
	$(PYTHON) -m ingest.cli resume

test:
	$(PYTEST) -m "not integration and not live and not data" tests/

test-int:
	$(PYTEST) tests/integration/

test-live:
	$(PYTEST) -m live tests/live/

test-all:
	$(PYTEST) --cov=config --cov=ingest --cov=retrieval --cov=agent --cov=api --cov-report=term-missing tests/

lint:
	$(RUFF) check config/ ingest/ retrieval/ agent/ api/ evals/ scripts/ tests/
	$(RUFF) format --check config/ ingest/ retrieval/ agent/ api/ evals/ scripts/ tests/

typecheck:
	PYTHONPATH=. $(MYPY) config/ ingest/ scripts/

ci: lint typecheck test-all

verify-p1:
	$(PYTHON) scripts/verify_p1.py

clean-data:
	rm -rf data/raw/* data/interim/* data/manifests/*
