---
name: env-check
description: Check which API keys / LLM endpoint this tusimreport environment has and whether the configured LLM supports tool calling. Use at the start of a session that will run real analyses, after the user says they added or changed keys, or when an analysis fails with a missing-key / 401 / 429 error.
---

# Environment check

1. Run the static check (no network, no quota):
   ```bash
   .venv/bin/python setup_check.py
   ```
   Section 4 lists every key as set / missing and which LLM provider, model and endpoint host will be used. It never prints key values — keep it that way; do not echo env vars yourself.

2. Only if an LLM is configured, confirm it can drive the ReAct agents (sends exactly one chat request with one tool attached, so it uses a little free-tier quota):
   ```bash
   .venv/bin/python setup_check.py --llm-probe
   ```
   - `✅ tool call 수신` → the endpoint/model works with `create_react_agent`.
   - `응답은 왔지만 tool call이 없습니다` → this model cannot run the 9 agents; pick another model from `docs/API_KEYS.md`.
   - `호출 실패` with 401 → wrong key; 404 → wrong `LLM_BASE_URL` or `LLM_MODEL`; 429 → free-tier rate limit, wait and retry once.

3. When something is missing, tell the user the exact env var names and point to the matching section of `docs/API_KEYS.md` (issuance links and steps). In a Claude Code cloud session keys go in the environment settings (session title bar → cloud environment menu → Edit → Network secrets, or environment variables) and are picked up by the next session.

Never ask the user to paste a key, token or password into the chat, and never write one to a tracked file.

Key → agents that read it (from the imports in `agents/`; details in `docs/API_KEYS.md`):
- `LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY` (or `GOOGLE_API_KEY` / `OPENAI_API_KEY`): all 9 agents, the final report, the opinion and the chat.
- `DART_API_KEY`: `financial_expert`, `esg_expert`.
- `ECOS_API_KEY`: `context_expert`, `financial_expert`.
- `KRX_ID` + `KRX_PW` (pykrx login): `context_expert` (index OHLCV), `financial_expert` (fundamentals), `institutional_trading_expert` (investor flows), `comparative_expert` (fundamentals, market cap).
- `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET`, `TAVILY_API_KEY`: `sentiment_expert`.
- `ALPHA_VANTAGE_API_KEY`: `global_market_expert` (also uses CoinGecko and CNN Fear & Greed).
- No key: FinanceDataReader (`advanced_technical_expert` and others), Paxnet via Selenium/Chrome (`community_expert`).

An agent whose tools fail still returns text, so the progressive engine counts it as completed; a missing key shows up as weaker analysis, not as a failed agent.
