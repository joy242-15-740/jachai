# Jachai developer commands. Run `make help` to list them.
# Works with the GNU Make 3.81 that ships with macOS.

# First Python 3.12+ found on PATH. Override with: make install PYTHON=/path/to/python
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || echo python3)
VENV   := .venv
BIN    := $(VENV)/bin
# Stamp file: reinstall only when a pyproject changes.
STAMP  := $(VENV)/.installed

.PHONY: help install world train eval ablation api web test lint format clean

help:
	@echo "make install  create .venv and install ml + backend packages"
	@echo "make world    generate synthetic data into data/world, summary into reports/"
	@echo "make train    train the payment model into models/ (needs make world)"
	@echo "make eval     baselines + leakage check into reports/ (needs make world)"
	@echo "make api      run FastAPI on :8000              (not built yet)"
	@echo "make web      run Next.js on :3000              (not built yet)"
	@echo "make ablation label-source ablation on validation into reports/ (~2 min)"
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

ablation: $(STAMP)
	$(BIN)/python -m jachai.eval.ablation

# Stubs: fail loudly so nobody mistakes an empty run for real output.
api web:
	@echo "make $@: not implemented yet (see README, section 7)" >&2
	@exit 1

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
