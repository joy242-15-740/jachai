# Jachai developer commands. Run `make help` to list them.
# Works with the GNU Make 3.81 that ships with macOS.

# First Python 3.12+ found on PATH. Override with: make install PYTHON=/path/to/python
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || echo python3)
VENV   := .venv
BIN    := $(VENV)/bin
# Stamp file: reinstall only when a pyproject changes.
STAMP  := $(VENV)/.installed

.PHONY: help install world train eval eval-final sim api-fast web web-install web-build web-check demo-json world-fast train-fast sim-fast demo-data validate-full api web test lint format clean

help:
	@echo "make install  create .venv and install ml + backend packages"
	@echo "make world    generate synthetic data into data/world, summary into reports/"
	@echo "make train    train the payment model into models/ (needs make world)"
	@echo "make eval     baselines + leakage check into reports/ (needs make world)"
	@echo "make api / api-fast  run FastAPI on :8000 (docs at /docs)"
	@echo "make web / web-build / web-check   dashboard dev server, build, type check"
	@echo "make demo-json  dashboard demo-mode JSON from the fast-profile API"
	@echo "make world-fast / train-fast / demo-data   fast profile (small world, ~2 min each)"
	@echo "make sim / sim-fast  policy simulator A-E into reports/simulator/ (needs train)"
	@echo "make validate-full  multi-seed validation + full ablation (LONG, 15-30+ min)"
	@echo "make eval-final  ONE-TIME frozen-system test evaluation; refuses overwrite"
	@echo "make test     ruff lint + format check, then pytest"
	@echo "make format   auto-fix lint and formatting"
	@echo "make clean    remove .venv and caches"

install: $(STAMP)

$(STAMP): ml/pyproject.toml backend/pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e "ml[dev]" -e "backend[dev]"
	@touch $(STAMP)

# Extra flags, e.g. make world WORLD_ARGS="--p2p --seed 7"
WORLD_ARGS ?=

world: $(STAMP)
	$(BIN)/python -m jachai.world $(WORLD_ARGS)

eval: $(STAMP)
	$(BIN)/python -m jachai.eval

train: $(STAMP)
	$(BIN)/python -m jachai.models

# --- Fast development profile (configs/profiles/fast.yaml) ---------------------------
# Small world, one seed; writes to data/fast, models/fast, reports/fast. Each ~2 min or less.
FAST := JACHAI_PROFILE=fast

world-fast: $(STAMP)
	$(FAST) $(BIN)/python -m jachai.world

train-fast: $(STAMP)
	$(FAST) $(BIN)/python -m jachai.models

sim-fast: $(STAMP)
	$(FAST) $(BIN)/python -m jachai.simulate $(SIM_ARGS)

# Everything the API / dashboard needs for a local demo, on the fast profile.
demo-data: world-fast train-fast sim-fast
	$(MAKE) demo-json

# Policy simulator on the reference world (needs make train). Overrides:
# make sim SIM_ARGS="--set limit_level=50000 --set analyst_capacity_per_day=10"
sim: $(STAMP)
	$(BIN)/python -m jachai.simulate $(SIM_ARGS)

# --- Long jobs: multi-seed validation and full ablation (15-30+ min). ---------------
# Not part of everyday development; run only when explicitly decided.
validate-full: $(STAMP)
	$(BIN)/python -m jachai.eval.ablation
	$(BIN)/python -m jachai.eval.system_eval

# Single-use final test access. Run only after the full system and thresholds are frozen.
eval-final: $(STAMP)
	$(BIN)/python -m jachai.eval.final_test

# API on :8000 (docs at /docs). Uses MODEL_DIR / data from the active profile;
# for a local demo: make demo-data && make api-fast
api: $(STAMP)
	$(BIN)/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

api-fast: $(STAMP)
	$(FAST) $(BIN)/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# docs/report.md -> docs/report.pdf (A4, max 3 pages; needs Google Chrome)
report-pdf: $(STAMP)
	$(BIN)/pip install --quiet -e "ml[docs]"
	$(BIN)/python scripts/report_pdf.py

# --- Frontend (Next.js in frontend/) ---------------------------------------------
web-install:
	cd frontend && npm install --no-audit --no-fund

web: ## dev server on :3000 (uses NEXT_PUBLIC_API_URL, falls back to demo JSON)
	cd frontend && npm run dev

web-build:
	cd frontend && npm run build

web-check: ## TypeScript type check
	cd frontend && npm run typecheck

# Demo-mode JSON for the dashboard, from the real API on fast-profile artifacts.
demo-json: $(STAMP)
	$(FAST) $(BIN)/python -m app.export_demo

test: lint
	$(BIN)/pytest

lint: $(STAMP)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: $(STAMP)
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name "*.egg-info" -type d -prune -exec rm -rf {} +
