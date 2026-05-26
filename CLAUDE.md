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
           chat session, context manager, logging context
config/    pydantic-settings, llm_factory
data/      external clients (DART, BOK, PyKRX, FDR, Naver, Tavily,
           Alpha Vantage, CoinGecko, Fear&Greed, paxnet, dcinside),
           base_client.BaseAPIClient (retry, atomic cache, LRU,
           force_refresh), external_schemas (Pydantic validators),
           cache_ttl (named TTL constants)
ui/        cards, styles, stock_database — split out of main.py
utils/     time (KST helpers), cost (token / USD), logging_context,
           helpers, agent_helpers
tests/     230 tests; agents/, core/, data/ split. responses-based
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

## Common commands

```
make install     # pip install -r requirements.txt -r requirements-dev.txt
make lint        # ruff check
make format      # ruff format + ruff check --fix
make test        # pytest with --cov-fail-under (CI gate)
make cov         # pytest with line-level missing report
make lock        # regenerate requirements.lock (uses --pre)
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
