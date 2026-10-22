.PHONY: help bootstrap data data-resume test test-int test-live test-all lint typecheck ci verify-p1 verify-p2 parse chunk links process clean-data

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
	@echo "  process      - Run full parsing, cleaning, linking, and chunking"
	@echo "  parse        - Run document parsing and text cleaning"
	@echo "  links        - Extract references and supersession graph"
	@echo "  chunk        - Generate structured chunks"
	@echo "  test         - Run fast unit tests"
	@echo "  test-int     - Run integration tests (no network)"
	@echo "  test-live    - Run live tests against real RBI endpoints"
	@echo "  test-all     - Run all unit, property, and integration tests"
	@echo "  lint         - Run ruff linter and code formatting check"
	@echo "  typecheck    - Run mypy type checker"
	@echo "  ci           - Run lint, typecheck, and test-all (CI pipeline)"
	@echo "  verify-p1    - Run Phase 1 verification gate"
	@echo "  verify-p2    - Run Phase 2 verification gate"
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
	$(PYTEST) --cov=config --cov=ingest --cov=retrieval --cov=agent --cov=evals --cov=api --cov-report=term-missing tests/

lint:
	$(RUFF) check config/ ingest/ retrieval/ agent/ api/ evals/ scripts/ tests/
	$(RUFF) format --check config/ ingest/ retrieval/ agent/ api/ evals/ scripts/ tests/

typecheck:
	PYTHONPATH=. $(MYPY) config/ ingest/ retrieval/ agent/ scripts/

ci: lint typecheck test-all

verify-p1:
	$(PYTHON) scripts/verify_p1.py

verify-p2:
	$(PYTHON) scripts/verify_p2.py

process:
	$(PYTHON) -m ingest.process

parse: process
links: process
chunk: process

embed: index

index:
	$(PYTHON) -m retrieval.build_index

index-verify:
	$(PYTHON) -c "from retrieval.index_store import IndexStore; IndexStore.load(verify='full'); print('Index verified successfully!')"

index-package:
	$(PYTHON) -c "from retrieval.build_index import package_index; package_index()"

index-publish:
	$(PYTHON) -c "from retrieval.build_index import package_index; package_index()"

verify-p3:
	$(PYTHON) scripts/verify_p3.py

eval-gen:
	$(PYTHON) -c "from evals.generate import EvalSetGenerator, freeze_eval_set; from retrieval.index_store import IndexStore; s = IndexStore.load(verify='fast'); g = EvalSetGenerator(s); q, m = g.generate_eval_set(); freeze_eval_set(q, m); print('Evaluation set generated and frozen successfully!')"

eval:
	$(PYTHON) evals/run.py --system $(or $(SYSTEM),baseline) --split $(or $(SPLIT),all)

eval-gate:
	$(PYTHON) evals/gate.py --system $(or $(SYSTEM),baseline)

eval-compare:
	$(PYTHON) evals/compare.py $(A) $(B)

verify-p4:
	$(PYTHON) scripts/verify_p4.py

tune:
	$(PYTHON) scripts/tune_retrieval.py

ablate:
	$(PYTHON) scripts/run_ablation.py

verify-p5:
	$(PYTHON) scripts/verify_p5.py

agent-tune:
	$(PYTHON) scripts/tune_agent.py

agent-eval:
	$(PYTHON) scripts/run_agent_eval.py

agent-report:
	$(PYTHON) scripts/run_agent_eval.py

agent-demo:
	$(PYTHON) -m agent.demo --question "$(Q)"

verify-p6:
	$(PYTHON) scripts/verify_p6.py

openapi:
	$(PYTHON) scripts/dump_openapi.py

events-doc:
	$(PYTHON) scripts/generate_events_doc.py

api-dev:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

api-run:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

api-test:
	$(PYTEST) tests/unit/test_api_*.py --cov=api --cov-report=term-missing

api-security:
	$(PYTEST) tests/unit/test_api_security_*.py

mock-api:
	$(PYTHON) scripts/mock_api.py --port 8000

verify-p7:
	$(PYTHON) scripts/verify_p7.py

clean-data:
	rm -rf data/raw/* data/interim/* data/manifests/*


