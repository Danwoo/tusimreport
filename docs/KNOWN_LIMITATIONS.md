# Known limitations

What an honest senior reviewer would still raise. Items move to
"Resolved" as they close.

## Resolved

- ✅ Agent-level unit tests — 9 of 9 expert agents have dedicated test
  files in `tests/agents/` with PyKRX / FDR / Naver / Tavily / LLM
  monkeypatching. **39 agent tests total**.
- ✅ Cache invalidation — `BaseAPIClient.get_cached(force_refresh=True)`
  bypasses live cache; `MAX_CACHE_ENTRIES=256` LRU eviction; cache root
  overridable via `TUSIM_CACHE_DIR` env var for persistent volume mount.
- ✅ Partial `datetime.now()` migration — fully migrated; only one
  `datetime.now()` left in `BaseAPIClient.get_cached` for mtime
  comparison (intentional, OS clock alignment).
- ✅ Streamlit `session_state` race — verified theoretical; no concurrent
  writers outside main thread.
- ✅ LLM thread-safety — documented in `config/llm_factory.py` docstring
  (requests.Session pool is thread-safe by spec).
- ✅ Timestamp datatype uniformity — all `timestamp` / `last_updated` /
  `created_at` fields come from `kst_isoformat()` (+09:00 KST offset).
- ✅ External response schemas — `data/external_schemas.py`:
  `DartStatusEnvelope` applied at the `_make_request` boundary (covers
  all 7 DART endpoints), `validate_pykrx_fundamental` applied in
  `financial_react_agent`, `assert_pykrx_columns` applied in
  `institutional_trading_agent` (trading_value columns) and
  `context_agent` (index OHLCV columns). Column-rename regression
  raises `DataQualityError` instead of silent fallback.
- ✅ Cost / load numbers — `utils/cost.py` provides `count_tokens`,
  `estimate_cost_usd`, and `track_llm_call`. 2025-11 pricing table for
  the four models we use. Greppable structured log line per call.
- ✅ Lockfile — `requirements.lock` (full transitive pin, 496 lines) and
  `requirements-dev.lock` checked in. Regenerated with `make lock`.
  `--pre` flag required because mplfinance 0.12 is only released as a
  beta on PyPI.
- ✅ ChatSession / ContextManager / progressive supervisor helpers —
  unit-tested for thread safety, completion-signal preservation, prompt
  compression, LRU cache.
- ✅ Hidden bug — `EnterpriseContextManager.create_progressive_summary`
  was calling a non-existent `compress_agent_output` method; every call
  silently fell through to the except branch and returned "기술적 문제로
  요약을 생성할 수 없습니다". Method added with a head-and-tail compression
  strategy.

## Tier 1 — would still block production

### 1. Agent ReAct loop not end-to-end tested

We unit-test each agent's `*_logic` helper and tool functions, plus
the supervisor's progressive helpers separately. We do **not** test
`create_*_agent()` factories end-to-end (`langgraph_supervisor` +
`create_react_agent`) because that requires mocking LangChain's streaming
graph, which is a separate effort.

Coverage on `agents/` averages ~50% function-level. Most of the
uncovered lines are inside `create_*_agent()` prompt construction and
the supervisor wiring.

## Tier 2 — would be nice but not blocking

### 2. ESG data source remains thin (DART filings only)

The ESG agent extracts governance / social / environmental signals from
DART corporate filings. It does **not** consume MSCI ESG ratings or
Sustainalytics ESG Risk — those are paid feeds (~$50K/year for retail-
scale access). For an MVP analysis tool this is acceptable; for a
customer-facing ESG product, fixing it is a budget line, not a code
change.

### 3. Korean libraries are pinned to alpha/beta on PyPI

`mplfinance==0.12.10b0` and `altair==6.2.0.dev20260518` ended up in
`requirements.lock` because no stable release of those versions exists
on PyPI yet. They have been working for us in development, but a
defensive operator might want to pin to `mplfinance==0.12.9b1` (last
beta that has been around longer) instead.

## Tier 3 — explicit non-goals (right now)

- **Real-time order book / 호가**: this is an analysis report tool, not
  a trading terminal.
- **Multi-tenant SaaS**: single Streamlit process, no user accounts.
- **Global market expansion**: KR market only. `global_market_agent`
  surfaces US/crypto context, but the analysis target is always a
  Korean ticker.
