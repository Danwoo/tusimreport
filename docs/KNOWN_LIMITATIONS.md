# Known limitations

This document tracks the honest gaps a senior reviewer would still find,
ordered by how badly they would bite production. Items move out as they
get addressed.

## Resolved since the first audit

- ✅ ~~Agent-level smoke-only tests~~ — `tests/agents/` now covers 9 of the
  9 agents (technical, comparative, financial_react, sentiment, context,
  esg, community, institutional, investment_opinion) with PyKRX / FDR /
  Naver / Tavily / LLM monkeypatching. **39 agent tests** total.
- ✅ ~~No cache invalidation / no LRU eviction~~ —
  `BaseAPIClient.get_cached(force_refresh=True)` bypasses live cache, and
  `_evict_if_over_limit()` LRU-trims when `MAX_CACHE_ENTRIES=256` is
  exceeded. `TUSIM_CACHE_DIR` env var lets operators point cache at a
  persistent volume.
- ✅ ~~Partial `datetime.now()` migration~~ — ~50 sites migrated. The only
  `datetime.now()` left is in `BaseAPIClient.get_cached` for mtime
  comparison (intentional — the OS writes file mtimes in system clock).
- ✅ ~~Streamlit `session_state` race~~ — verified that no code outside
  `main.py` writes to `session_state`. The earlier worry was theoretical.
- ✅ ~~LLM thread-safety assumed but not documented~~ — documented in
  `config/llm_factory.py` docstring with the requests.Session pool argument.
- ✅ ~~Timestamp datatype inconsistency~~ — all `timestamp` /
  `last_updated` keys now come from `kst_isoformat()` (+09:00 KST offset).
- ✅ ~~PyKRX / DART responses not schema-validated~~ —
  `data/external_schemas.py` introduces `DartStatusEnvelope`,
  `DartCorpInfo`, and `PykrxFundamentalRow` Pydantic models with
  `extra="ignore"`. Applied to `dart_api_client.get_company_info` and
  `korean_financial_react_agent.get_pykrx_market_data`. Column-rename
  regressions now raise `DataQualityError` instead of silent fallback.
- ✅ ~~No cost / load numbers~~ — `utils/cost.py` provides `count_tokens`,
  `estimate_cost_usd`, and `track_llm_call`. Per-call cost is logged as a
  greppable structured line (`llm_call agent=X model=Y in_tok=N
  cost_usd=...`). 2025-11 pricing table for the four models we use.

## Tier 1 — would block production but not yet fully fixed

### 1. Coverage uneven across `agents/`

Per-agent coverage averages ~50% on average now (function-level), but the
LangChain ReAct loop in each `create_*_agent()` factory is still
untested — those need full LLM streaming mocking, which has not been
written yet. The CI gate is at 30% (current measured: ~40%); reaching
50% is still the next milestone.

### 2. Pydantic validators applied to only 2 sites

`validate_dart_envelope` is used on `company.json` only. The other 6
DART endpoints (`fnlttSinglAcnt.json` etc.) still parse with raw `.get()`
calls. Same applies to PyKRX: `get_market_fundamental` is validated,
but `get_market_trading_value_by_investor`, `get_index_ohlcv_by_date`,
`get_market_cap` are not. Roll-out is incremental; the helpers exist,
the call-sites haven't all been updated.

## Tier 2 — would be nice but not blocking

### 3. No transitive lockfile checked in

`requirements.in` / `requirements-dev.in` exist and `make lock` produces
`requirements.txt` via pip-compile. Run it on a developer machine with
PyPI access — the sandboxed CI container in this environment can't reach
PyPI, so the lockfile cannot be regenerated here. The direct deps are
still minor-pinned via `~=`, so the build is mostly deterministic.

### 4. ESG data source remains thin (DART filings only)

The ESG agent extracts governance / social / environmental signals from
DART corporate filings. It does **not** consume:

- **MSCI ESG ratings** — paid feed, ~$50K/year for retail-scale access
- **Sustainalytics ESG Risk Rating** — paid via Morningstar
- **CDP climate disclosures** — bulk download requires registration

For an MVP analysis tool this is acceptable; for a customer-facing ESG
product it isn't. The fix is not code, it's a budget line.

### 5. CI cannot regenerate the lockfile in the sandbox

This is an environment quirk: the sandbox the CI container runs in
doesn't allow outbound to PyPI. The Makefile target `make lock` works
fine on any developer machine. Adding an offline lockfile step into the
CI workflow would require giving the runner network egress, which is a
deployment decision, not a code one.

## Tier 3 — explicit non-goals (right now)

- **Real-time order book / 호가**: this is an *analysis report* tool,
  not a trading terminal.
- **Multi-tenant SaaS**: single Streamlit process. No user accounts,
  no per-user rate limiting, no quota tracking.
- **Global market expansion**: KR market only. The
  `global_market_agent` surfaces US/crypto context, but the analysis
  target is always a Korean ticker.
