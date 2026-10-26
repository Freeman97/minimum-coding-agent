SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ROOT := $(CURDIR)
UV := $(ROOT)/.tools/uv

# Keep the whole toolchain inside the repository (see docs/conventions.md).
export UV_CACHE_DIR := $(ROOT)/.uv-cache
export UV_PYTHON_INSTALL_DIR := $(ROOT)/.uv-python
export UV_PROJECT_ENVIRONMENT := $(ROOT)/.venv

.PHONY: help setup check lint test test-live run demo-llm

help:
	@printf '%s\n' \
		'make setup   Install the project-local uv, Python interpreter and dependencies' \
		'make check   Run ruff, pydoclint and the offline test suite' \
		'make lint    Run ruff and pydoclint only' \
		'make test    Run the offline test suite' \
		'make test-live  Run the env-gated live model smoke tests (needs MCA_LIVE_*)' \
		'make run     Start the interactive console (placeholder until M5)' \
		'make demo-llm   Run the offline model access layer demo (no network)'

setup:
	@bash scripts/bootstrap.sh

$(UV):
	@bash scripts/bootstrap.sh

check: lint test

lint: $(UV)
	$(UV) run ruff check src tests
	$(UV) run pydoclint --config pyproject.toml src

test: $(UV)
	$(UV) run pytest

test-live: $(UV)
	$(UV) run pytest -m live

demo-llm: $(UV)
	$(UV) run python scripts/demo_llm.py

run: $(UV)
	$(UV) run mca
