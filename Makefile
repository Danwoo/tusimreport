# Standardized dev / CI commands. Tab-indented (Make requires it).
#
# Why a Makefile in a Python project: contributors should not need to
# remember "pip-compile --resolver=backtracking --strip-extras requirements.in".
# `make lock` is enough.

.PHONY: help install lock lock-dev lock-all lint format test cov docker run

help:  ## list available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## install runtime + dev dependencies
	pip install -r requirements.txt -r requirements-dev.txt

# ---- lockfile ----------------------------------------------------------------
#
# --pre is required because mplfinance 0.12 is only released as 0.12.10b0 on
# PyPI (beta). Without --pre pip-compile refuses to consider it and the
# resolve fails.

lock:  ## regenerate requirements.lock (full transitive pin) from requirements.in
	pip-compile --resolver=backtracking --strip-extras --pre --output-file=requirements.lock requirements.in

lock-dev:  ## regenerate requirements-dev.lock from requirements-dev.in
	pip-compile --resolver=backtracking --strip-extras --output-file=requirements-dev.lock requirements-dev.in

lock-all: lock lock-dev  ## regenerate both lockfiles

# ---- code quality ------------------------------------------------------------

lint:  ## ruff lint (no fix)
	ruff check .

format:  ## ruff format + ruff check --fix
	ruff format .
	ruff check --fix .

# ---- tests -------------------------------------------------------------------

test:  ## pytest with coverage gate from CI
	pytest -q --cov=core --cov=ui --cov=utils --cov=data --cov=agents --cov-fail-under=30

cov:  ## coverage with line-level missing report
	pytest -q --cov=core --cov=ui --cov=utils --cov=data --cov=agents --cov-report=term-missing

# ---- docker ------------------------------------------------------------------

docker:  ## docker compose build + up (detached)
	docker compose up --build -d

run:  ## local streamlit run (no docker)
	streamlit run main.py
