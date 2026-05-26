# Known limitations

This document tracks the honest gaps a senior reviewer would still find,
ordered by how badly they would bite production. The point of having this
file is that the gaps are *known*, not denied. Items move out as they get
addressed.

## Resolved since the first audit

- ✅ ~~Agent-level smoke-only tests~~ — `tests/agents/` now covers
  `technical_agent` (4), `comparative_agent` (3), `financial_react_agent` (5),
  and `investment_opinion` (10) with PyKRX / FDR / LLM monkeypatching.
- ✅ ~~No cache invalidation~~ — `BaseAPIClient.get_cached(force_refresh=True)`
  bypasses live cache, and `_evict_if_over_limit()` LRU-trims when
  `MAX_CACHE_ENTRIES=256` is exceeded. Tested in
  `test_base_client_cache_policy.py`.
- ✅ ~~Partial `datetime.now()` migration~~ — ~50 sites migrated to
  `kst_isoformat()` / `kst_today_compact()` / `kst_year()` /
  `kst_month_compact()`. The only `datetime.now()` left is in
  `BaseAPIClient.get_cached` for mtime comparison (intentional — the OS
  writes mtime in system clock, mixing it with KST would create negative
  deltas).
- ✅ ~~Streamlit `session_state` race~~ — verified that no code outside
  `main.py` (which is single-threaded under Streamlit's ScriptRunContext)
  writes to `session_state`. The `ThreadPoolExecutor` in
  `progressive_supervisor` only emits via generator yields, no shared
  mutable state. The earlier worry was theoretical.
- ✅ ~~LLM thread-safety assumed but not documented~~ — assumption is now
  documented in `config/llm_factory.py` docstring (requests.Session
  pool guarantees + LangChain creates per-call requests, so sharing one
  instance across threads is safe).
- ✅ ~~Timestamp datatype inconsistency~~ — all `timestamp` / `last_updated`
  / `created_at` keys in result dicts now come from `kst_isoformat()`,
  producing ISO 8601 strings with `+09:00` offset.

## Tier 1 — would block production but not yet fully fixed

### 1. PyKRX / DART responses are not schema-validated

`pykrx.stock.get_market_fundamental(...)` returns a DataFrame whose
columns are Korean strings (`"시가총액"`, `"PER"`, ...). If the upstream
library changes those names (it has happened before) every downstream
agent silently degrades to fallback values without raising. The agent
tests now pin the *expected* shape with stub DataFrames, but there is no
production-time validator. The clean fix is a Pydantic model per external
response shape with `strict=True`.

### 2. Coverage is 33% — `agents/` is barely 25%

Per-module coverage is uneven: pure helpers (`core.signals`, `ui.cards`,
`utils.time`) sit around 80-100%, but the 9 agent files average ~25%
because we only test their internal `_logic` functions and not their
LangChain ReAct loops (those need full LLM mocking, which has not been
written yet).

### 3. Coverage gate is at 30%

CI fails on coverage < 30%. Current measured coverage is ~33%. We move
this floor up by ~5%p per test-suite addition; reaching 50% is still a
stated goal.

## Tier 2 — would be nice but not blocking

### 4. No transitive lockfile

`requirements.in` / `requirements-dev.in` are checked in. The pip-compile
generated `requirements.txt` with transitive pins has not been generated
yet — the sandboxed CI build couldn't reach PyPI to produce one. The
direct deps are still minor-pinned via `~=`, so the build is mostly
deterministic, but a `pip install -r requirements.txt` two months from
now could pull a newer transitive dep.

### 5. No cost / load numbers

We have no numbers for "what does one analysis cost in LLM tokens"
or "at what concurrency does a single Streamlit process saturate". A
serious deployment plan would need both.

### 6. ESG agent's data source is thin

Only DART filings; doesn't compare against MSCI / Sustainalytics scores
or to peers. The "ESG score" displayed is more of a "disclosure
completeness score". Acceptable for an MVP, not for a customer-facing
ESG product.

### 7. Cache `cache_dir` lives in `tempfile.gettempdir()`

Containers usually mount `/tmp` as tmpfs (memory-backed). That's fine for
the small 256-entry cache but means a restart loses the working set. The
Docker compose recipe mounts a named volume at `/tmp` to survive
restarts, but a user not using compose loses the cache.

## Tier 3 — explicit non-goals (right now)

- **Real-time order book / 호가**: this is an *analysis report* tool,
  not a trading terminal. KRX direct feed would change the product.
- **Multi-tenant SaaS**: single Streamlit process. No user accounts,
  no rate limiting per user, no quota tracking.
- **Global market expansion**: KR market only. The `global_market_agent`
  surfaces US/crypto context, but the analysis target is always a
  Korean ticker.
