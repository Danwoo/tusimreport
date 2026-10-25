# Standardized dev / CI commands. Tab-indented (Make requires it).
#
# Why a Makefile in a Python project: contributors should not need to
# remember "pip-compile --resolver=backtracking --strip-extras requirements.in".
# `make lock` is enough.

.PHONY: help install lock lock-dev lock-all lint format test cov docker run

help:  ## list available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## install runtime + dev dependencies (exact pins, same as CI)
	pip install -r requirements.lock -r requirements-dev.lock

# ---- lockfile ----------------------------------------------------------------
#
# No --pre: it applies to every package, and once pinned alphas/rcs across the
# lock (pydantic 2.14.0a1 broke `import langchain_openai`). mplfinance, which
# only has betas on PyPI, names its beta in requirements.in instead.
#
# pip-compile keeps existing pins that still satisfy the .in file — including
# pre-release pins. To move pins forward, pass --upgrade:
#   make lock-all PIP_COMPILE_ARGS=--upgrade
#
# lock-dev reads requirements.lock as a constraint (-c in requirements-dev.in),
# so regenerate requirements.lock first (lock-all does).

PIP_COMPILE = pip-compile --resolver=backtracking --strip-extras $(PIP_COMPILE_ARGS)

lock:  ## regenerate requirements.lock (full transitive pin) from requirements.in
	$(PIP_COMPILE) --output-file=requirements.lock requirements.in

lock-dev:  ## regenerate requirements-dev.lock from requirements-dev.in
	$(PIP_COMPILE) --output-file=requirements-dev.lock requirements-dev.in

lock-all: lock lock-dev  ## regenerate both lockfiles

# ---- code quality ------------------------------------------------------------

lint:  ## ruff lint (no fix)
	ruff check .

format:  ## ruff format + ruff check --fix
	ruff format .
	ruff check --fix .

# ---- tests -------------------------------------------------------------------

test:  ## pytest with coverage gate from CI
	pytest -q --cov=core --cov=ui --cov=utils --cov=data --cov=agents --cov-fail-under=45

cov:  ## coverage with line-level missing report
	pytest -q --cov=core --cov=ui --cov=utils --cov=data --cov=agents --cov-report=term-missing

# ---- docker ------------------------------------------------------------------

docker:  ## docker compose build + up (detached)
	docker compose up --build -d

run:  ## local streamlit run (no docker)
	streamlit run main.py
