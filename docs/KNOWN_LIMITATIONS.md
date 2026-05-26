# Known limitations

This document tracks the honest gaps a senior reviewer would still find,
ordered by how badly they would bite production. The point of having this
file is that the gaps are *known*, not denied. Items move out as they get
addressed.

## Tier 1 — would block production but not yet fixed

### 1. Agent-level unit tests are still mostly smoke tests

We have unit tests for the data clients that go through `BaseAPIClient`
(`alpha_vantage`, `coingecko`, `fear_greed`) using `responses` to mock
HTTP. The 9 agents themselves, however, are exercised only by import-smoke
tests. We do not yet have:

- Per-agent tests that mock `pykrx` / `FinanceDataReader` (these are not
  HTTP — they are library calls — so `responses` alone does not cut it;
  needs `monkeypatch.setattr` against the library functions).
- A LangGraph supervisor end-to-end test that drives `stream_korean_stock_analysis`
  with a stubbed LLM and asserts the final report shape.
- Property-based tests (e.g. with Hypothesis) for `_clamp_price`,
  cache-key validation, and other pure helpers.

Until those land, "all 9 agents return sane outputs" is verified only by
manual Streamlit testing.

### 2. PyKRX / DART responses are not schema-validated

`pykrx.stock.get_market_fundamental(...)` returns a DataFrame whose
columns are Korean strings (`"시가총액"`, `"PER"`, ...). If the upstream
library changes those names (it has happened before) every downstream
agent silently degrades to fallback values without raising. The clean
fix is a Pydantic model per external response shape; we have not done
this and the cost is real.

### 3. Caching strategy is too coarse

`data/cache_ttl.py` defines per-data-class TTLs now, but the cache key
is `f"{symbol}_{period}"` style — there is no invalidation when a user
explicitly asks for "fresh data right now", and no LRU eviction. A
shared Streamlit deployment with hundreds of users would steadily grow
the cache directory without bound.

### 4. `datetime.now()` migration is partial

`utils/time.py` and the KST helpers exist. We migrated the
PyKRX-facing call sites (financial agent, BOK, DART, comparative,
context) but ~30 other call sites in `agents/`, `data/` and `core/`
still use the timezone-naive `datetime.now().isoformat()`. The ISO
strings end up in result dicts that flow to the UI and to the chat
context — inconsistent, but not actively broken.

### 5. Streamlit `session_state` race conditions

Streamlit isolates `session_state` per browser session, but our
analysis flow writes to keys like `chart_{symbol}` and
`news_sources_{symbol}` from helper threads spun up by
`ThreadPoolExecutor`. The current code relies on the assumption that
Streamlit's `session_state` is thread-safe enough for "write-from-one-
thread-read-from-main"; that assumption is undocumented. A reviewer
will rightly ask for either an explicit `threading.Lock` around the
write site or a switch to a queue.

### 6. LLM thread-safety is assumed but not verified

`progressive_supervisor` parallelises 7 agents and each call eventually
hits the same `ChatGoogleGenerativeAI` / `ChatOpenAI` instance built
once in `build_llm`. The LangChain docs are vague about whether sharing
one instance across threads is supported; in practice we have not seen
corruption but we also have not done concurrent stress testing.

## Tier 2 — would be nice but not blocking

### 7. Agent result timestamps are not uniform

Some agents return `datetime` objects, some return ISO strings, some
return epoch ints. Consumers (UI, chat context) coerce on read. A
TypedDict-driven schema (`core.schemas.AgentResponse`) exists but is
not strictly enforced across all agents.

### 8. Coverage gate is at 20%

CI fails on coverage <20%. Current measured coverage is ~23%. We move
this floor up by ~5%p per test-suite addition; reaching 50% is a stated
goal and requires the Tier-1 #1 work above.

### 9. No lockfile (only `~=` minor pins)

`requirements.in` / `requirements-dev.in` are checked in but no
pip-compile generated lockfile with transitive pins yet. The
sandboxed CI build couldn't reach PyPI to generate one; this needs to
run on a developer machine and be committed.

### 10. No load testing / cost monitoring

We have no numbers for "what does one analysis cost in LLM tokens"
or "at what concurrency does a single Streamlit process saturate". A
serious deployment plan would need both.

### 11. ESG agent's data source is thin

Only DART filings; doesn't compare against MSCI / Sustainalytics scores
or to peers. The "ESG score" displayed is more of a "disclosure
completeness score". Acceptable for an MVP, not for a customer-facing
ESG product.

## Tier 3 — explicit non-goals (right now)

- **Real-time order book / 호가**: this is an *analysis report* tool,
  not a trading terminal. KRX direct feed would change the product.
- **Multi-tenant SaaS**: single Streamlit process. No user accounts,
  no rate limiting per user, no quota tracking.
- **Global market expansion**: KR market only. The `global_market_agent`
  surfaces US/crypto context, but the analysis target is always a
  Korean ticker.
