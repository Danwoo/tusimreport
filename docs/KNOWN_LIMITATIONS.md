# Known limitations

What an honest senior reviewer would still raise. Items move to
"Resolved" as they close. The project is a Korean-stock analysis tool;
multi-market and SaaS expansion are explicit non-goals.

## Resolved

- ✅ Agent-level unit tests — 9 of 9 expert agents have dedicated test
  files in `tests/agents/` with PyKRX / FDR / Naver / Tavily / LLM
  monkeypatching (**39 agent tests**).
- ✅ Cache invalidation — `BaseAPIClient.get_cached(force_refresh=True)`
  bypasses live cache; `MAX_CACHE_ENTRIES=256` LRU eviction; cache root
  overridable via `TUSIM_CACHE_DIR` env var.
- ✅ `datetime.now()` migration — fully migrated. Only one
  `datetime.now()` remains in `BaseAPIClient.get_cached` for mtime
  comparison (intentional, system-clock alignment).
- ✅ Streamlit `session_state` race — verified theoretical; no concurrent
  writers outside main thread.
- ✅ LLM thread-safety — documented in `config/llm_factory.py` docstring.
- ✅ Timestamp datatype uniformity — every `timestamp` / `last_updated` /
  `created_at` field is now `kst_isoformat()` (+09:00 KST).
- ✅ External response schemas — `data/external_schemas.py` Pydantic
  models applied at the boundary:
  - DART envelope validated in `_make_request` → covers all 7 endpoints.
  - PyKRX fundamental row validated in `financial_react_agent`.
  - PyKRX column-rename guard (`assert_pykrx_columns`) applied to
    institutional trading and KOSPI/KOSDAQ index calls.
- ✅ Cost / load numbers — `utils/cost.py` with `count_tokens`,
  `estimate_cost_usd` (2025-11 pricing table), `track_llm_call`
  (greppable structured log line).
- ✅ Transitive lockfile — `requirements.lock` (496 lines) and
  `requirements-dev.lock` committed. `make lock` regenerates with the
  `--pre` flag needed for mplfinance's beta release.
- ✅ ChatSession / ContextManager / progressive supervisor —
  unit-tested for thread safety, completion-signal preservation, prompt
  compression, LRU cache.
- ✅ **ReAct loop end-to-end testing** — `stream_korean_stock_analysis`
  is fully covered by `tests/test_supervisor_stream.py` (10 tests) and
  `ProgressiveAnalysisEngine.execute_agent_with_context_control` plus
  the parallel/sequential phase orchestration by
  `tests/test_progressive_execute.py` (7 tests). The full 9-agent
  end-to-end runs against fake agents and asserts the final report
  yield.
- ✅ Latent bugs found and fixed during this audit (5):
  - `EnterpriseContextManager.compress_agent_output` was called but
    not defined; every progressive summary fell through to the except
    branch.
  - `_handle_running_signal` substring matching could never match —
    `current_stage` strings never contained the english agent key;
    replaced with explicit `running_agent` payload key.
  - `matplotlib.use("Agg")` was being called after `pyplot` import in
    the financial agent (no-op); fixed import order with `# noqa: E402`.
  - `verify=False` was unconditional on every RSS request; constrained
    to a `_ALLOWED_INSECURE_HOSTS` whitelist (currently empty).
  - DART API key was a hardcoded fallback string in the source; removed
    earlier in the audit (see `SECURITY.md` for rotation steps).

## Tier 2 — would still be nice but not blocking

### 1. Korean libraries are pinned to alpha/beta on PyPI

`mplfinance==0.12.10b0` and `altair==6.2.0.dev20260518` ended up in
`requirements.lock` because no stable release of those versions exists
on PyPI. They've been working in development, but a defensive operator
might want to pin to an older stable build (`mplfinance==0.12.9b1`).
This is an upstream-availability problem rather than a code one.

### 2. Coverage is at 46% — natural ceiling around here

`agents/*.py` averages above 50% function-level after the ReAct loop
tests landed, but many of the remaining uncovered lines are inside
LangChain prompt strings (which we deliberately don't unit-test for
content) and the `create_*_agent()` factory boilerplate (already covered
indirectly by the supervisor stream tests). Reaching 60% is possible
but would need testing prompt content, which is fragile against
intentional copy edits.

## Tier 3 — explicit non-goals

- **Real-time order book / 호가**: analysis report tool, not a trading
  terminal.
- **Multi-tenant SaaS**: single Streamlit process; no user accounts.
- **Global market expansion**: Korean stocks only. `global_market_agent`
  surfaces US / crypto context but the analysis target is always a
  Korean ticker.
- **MSCI / Sustainalytics paid ESG feeds**: licensing cost out of scope.
  ESG agent uses DART corporate filings exclusively, which is honest
  about being "disclosure completeness" rather than full ESG scoring.
