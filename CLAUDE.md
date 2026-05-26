# TuSimReport — AI assistant context

This file is consumed by Claude Code / Cursor when editing this repo.
Keep it factual and short. Human-facing docs live in `README.md`,
`SECURITY.md`, and `docs/KNOWN_LIMITATIONS.md`.

## What this is

A Streamlit app that analyses Korean (KOSPI/KOSDAQ) stocks via a
LangGraph supervisor coordinating 9 specialist agents, then synthesises
a BUY/HOLD/SELL opinion and exposes a chat over the result.

## Layout

```
agents/    # 9 expert agents + investment opinion synthesiser
core/      # supervisor, progressive engine, schemas, errors, signals,
           # chat session, context manager, logging context
config/    # pydantic-settings, llm_factory
data/      # external clients (DART, BOK, PyKRX, FDR, Naver, Tavily,
           # Alpha Vantage, CoinGecko, Fear&Greed, paxnet, dcinside).
           # base_client.BaseAPIClient has retry, atomic file cache,
           # LRU, force_refresh.
           # external_schemas.py validates upstream responses.
           # cache_ttl.py centralises TTL constants.
ui/        # cards, styles, stock_database — split out of main.py
utils/     # time (KST helpers), cost (token / USD), logging_context
tests/     # 230 tests; agents/, core/, data/ split
docs/      # KNOWN_LIMITATIONS.md, INTERVIEW_QA.md
```

## Working agreements

- **No mock data**. Every analysis path either reaches real upstream data
  or surfaces a Korean-language fallback message — never silently fakes a
  number.
- **KST first**. Trading-day arithmetic uses `utils.time.kst_*`. The only
  `datetime.now()` left is `BaseAPIClient.get_cached`'s mtime comparison
  (system-clock aligned by design).
- **Errors are typed**. External failures raise into
  `core.errors.TusimError` (RateLimit / Authentication /
  DataSourceUnavailable / DataQuality / Configuration). New `data/`
  code should follow.
- **Cache is best-effort**. File cache writes use atomic `tempfile +
  os.replace`. Failures log warning, do not raise. TTLs live in
  `data/cache_ttl.py`.
- **LLM thread-safety is documented, not enforced** —
  `config/llm_factory.py` docstring explains why sharing one instance is
  safe under our `ThreadPoolExecutor`.
- **Type checking is incremental**. mypy strict on the 8 fully-typed
  modules listed in `pyproject.toml`'s `[[tool.mypy.overrides]]`; the
  rest is loose-tier.
- **Tests are the spec**. 230 tests including end-to-end supervisor
  stream and ReAct execution. Coverage gate 45% (current ~46%).

## Conventions

- ruff handles lint and format. CI fails on either.
- Imports follow isort default groups (stdlib / 3rd-party / local).
  Two files use `# noqa: E402` because `matplotlib.use("Agg")` must run
  before pyplot import — do not let isort re-sort those blocks.
- Korean comments are fine where the audience is Korean-domain
  (financial labels, user-facing messages). English comments for
  infra / algorithm reasoning.
- Commit messages: subject in present-tense imperative, body explains
  *why* and what could break.

## Running

```
make install     # pip install -r requirements.txt -r requirements-dev.txt
make lint        # ruff check
make test        # pytest + coverage gate
make run         # streamlit run main.py (local)
make docker      # docker compose up --build
```

## What is intentionally NOT here

- Real-time order book (this is a research tool, not a trading terminal)
- Multi-tenant SaaS (single Streamlit process)
- Markets other than KR (`global_market_agent` only surfaces context)
- Paid ESG feeds (MSCI / Sustainalytics — out of scope)
