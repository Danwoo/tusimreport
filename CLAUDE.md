# TuSimReport — repo context for AI agents

This file is read by Claude Code / Cursor / other coding agents when
editing this repo. Keep it short, factual, and action-oriented. Human-
facing docs are `README.md` and `SECURITY.md`; everything else (notes,
limitations, todos) lives outside git via `.gitignore`.

## What this is

Streamlit app that analyses Korean (KOSPI/KOSDAQ) stocks with a
LangGraph supervisor coordinating 9 specialist agents, synthesises a
BUY/HOLD/SELL opinion, and exposes a chat over the result.

Single-process, single-user, research tool — not a trading terminal.

## Repo layout

```
agents/    9 expert agents + investment_opinion synthesiser
core/      supervisor, progressive engine, schemas, errors, signals,
           chat session, context manager, logging context,
           run_metrics (LLM/tool call + token callback),
           agent_status (per-agent grounded-data verdict)
config/    pydantic-settings, llm_factory
data/      external clients (DART, BOK, PyKRX, FDR, Naver, Tavily,
           Alpha Vantage, CoinGecko, paxnet, dcinside),
           base_client.BaseAPIClient (retry, atomic cache, LRU,
           force_refresh), external_schemas (Pydantic validators),
           cache_ttl (named TTL constants)
ui/        cards, styles, stock_database — split out of main.py
utils/     time (KST helpers), cost (token / USD), logging_context,
           helpers, agent_helpers
lab/       multi-agent topology comparison: tool registry, snapshot
           record/replay, single_agent / progressive / supervisor,
           numeric grounding, runner (docs/EXPERIMENTS.md)
scripts/   run_experiment.py, check_sources.py (CLI, no Streamlit)
tests/     agents/, lab/, core and data tests. responses-based
           HTTP mocks live in tests/conftest.py
main.py    Streamlit entry point
```

## Working agreements (do not break these)

- **No mock data.** Every analysis path reaches real upstream data or
  surfaces a Korean-language fallback message. Never silently fake a
  number; never auto-insert a missing completion signal to make a
  failed agent look successful.
- **KST first.** Trading-day arithmetic uses `utils.time.kst_*`. The
  only naive `datetime.now()` left is `BaseAPIClient.get_cached`'s
  mtime comparison; that one is intentional (OS clock alignment).
- **Errors are typed.** External failures raise into
  `core.errors.TusimError` subclasses (`RateLimitError`,
  `AuthenticationError`, `DataSourceUnavailableError`,
  `DataQualityError`, `ConfigurationError`). New `data/` clients
  follow this contract.
- **Cache is best-effort.** Atomic write via `tempfile + os.replace`;
  failures log warning, never raise. TTLs live in `data/cache_ttl.py`.
  LRU eviction at `MAX_CACHE_ENTRIES=256`. Cache root overridable
  with `TUSIM_CACHE_DIR` env var.
- **mypy strict is incremental.** Only the 8 modules listed in
  `pyproject.toml`'s overrides are strict. The rest is loose-tier on
  purpose — do not add untyped code to the strict list.
- **Tools return data, not analysis.** No LLM call inside a `@tool`
  function. A hidden call is invisible to the agent and to run metrics,
  and its output (e.g. a "sentiment score") looks like source data to
  the report and to `lab/grounding.py`. The agent's own LLM interprets.
- **Schema validation at the boundary.** PyKRX columns and DART
  envelopes are validated in `data/external_schemas.py`. New external
  clients should add their shape there, not propagate raw dicts.

## Conventions

- ruff handles lint + format. CI fails on either. `make format` fixes
  what it can.
- Imports follow isort default groups. Two files use `# noqa: E402`
  because `matplotlib.use("Agg")` must run before `pyplot` import — do
  not let isort resort those blocks.
- Korean comments are fine for user-facing labels and finance domain
  terms. Use English for infra / algorithm reasoning so a reviewer
  without Korean can follow.
- Commit messages: present-tense imperative subject; body explains
  *why* and what could break. No marketing language.

## Gotchas (real bugs found during audits)

- `matplotlib.use("Agg")` is a no-op once `pyplot` is imported. If
  isort moves it, the backend defaults to whatever the system has.
- `tiktoken` does a network download on first encoding request.
  `core.context_manager` uses a `@property` for lazy load + try/except
  fallback — preserve that pattern.
- LangGraph agent's `.invoke()` returns `{"messages": [...]}` with
  message objects that have `.content`. Tests stub this shape — see
  `tests/test_progressive_execute.py`.
- PyKRX returns Korean-keyed DataFrame columns (`'시가총액'`, `'PER'`,
  `'순매수'`, `'종가'`). Validators in `data/external_schemas.py`
  translate to English fields; do not bypass.
- pykrx ≥ 1.2.9 logs in to data.krx.co.kr with `KRX_ID` / `KRX_PW` read
  straight from `os.environ` (not `config.settings`); without them it
  prints a login-failure line on import.
- `requirements.lock` was compiled with `--pre` and pins pre-releases
  (pydantic 2.14.0a1); with it, importing `langchain_openai` after the
  agent modules raises `TypeError`. CI, Docker and the SessionStart hook
  install `requirements.txt` instead.
- ruff ≥ 0.17 also formats Python code blocks inside Markdown, so a doc
  edit can fail `ruff format --check`.
- OpenDART `reprt_code`: 11011 is the annual report (사업보고서), 11014
  is Q3. Use `data.dart_api_client.ANNUAL_REPORT`. `fnlttSinglAcnt`
  mixes consolidated (CFS) and separate (OFS) rows with the same
  account names; the client keeps one `fs_div`.
- ECOS table 722Y001 holds several policy rates; the base rate is item
  `0101000` and must be requested by item code.

## Report gating

The progressive engine separates "agent ran" (`status`) from "agent had
data" (`data_status`, from its ToolMessages via `core/agent_status.py`).
The final report is built only from agents with data and only when at
least `MIN_AGENTS_FOR_REPORT` (5 of 9) have it; the rest are listed in
`excluded` and named in the report prompt so the LLM does not invent
them. One agent failing is an `agent_error` card, not a stream error.

## LLM provider

`config.settings.get_llm_model()` picks, in order: `LLM_BASE_URL` +
`LLM_MODEL` + `LLM_API_KEY` (any OpenAI-compatible endpoint, built as
`ChatOpenAI(base_url=...)`), then Gemini / OpenAI keys. An incomplete
`LLM_BASE_URL` setup returns `None` instead of falling back to a paid
provider. `get_llm_model(raise_on_missing=False)` can pick a different
provider than the agents' `build_llm()` (USE_GEMINI=true without a Google
key falls through to OpenAI), so anything that reports LLM status —
sidebar, `check_minimum_requirements()`, `setup_check.py` — goes through
`resolve_llm_config()`, which uses the agents' path. Every agent is a `create_react_agent`, so the model must
support tool calling — `python setup_check.py --llm-probe` checks that
with one request. Key issuance: `docs/API_KEYS.md`.

## Claude Code cloud sessions

`.claude/hooks/session-start.sh` installs `.venv` from `requirements.txt`
+ `requirements-dev.txt` and puts it on `PATH`. Project skills:
`env-check` (key / LLM status) and `ci-check` (local CI gate — CI only
runs for `main` and PRs to `main`).

## Common commands

```
make install     # pip install -r requirements.txt -r requirements-dev.txt
make lint        # ruff check
make format      # ruff format + ruff check --fix
make test        # pytest with --cov-fail-under (CI gate)
make cov         # pytest with line-level missing report
make lock        # regenerate requirements.lock (uses --pre — see Gotchas)
make docker      # docker compose up --build
make run         # streamlit run main.py (local)
```

## Intentionally NOT in scope

- Real-time order book / 호가
- Multi-tenant SaaS (single Streamlit process; no user accounts)
- Markets other than KR (`global_market_agent` surfaces US/crypto
  *context*, but the analysis target is always a Korean ticker)
- Paid ESG feeds (MSCI / Sustainalytics)
- LLM output calibration vs. realised returns (this is a research
  tool, not a backtested signal generator)
