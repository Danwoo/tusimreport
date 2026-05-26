# 면접 예상 질문 및 코드 기반 답변

진짜 시니어가 물어볼 만한 질문을 카테고리별로 정리하고, 각 답변은
실제 코드/커밋/파일 위치로 뒷받침합니다. **"마이너스"가 될 답변은
포함하지 않습니다** — 답변이 약한 항목은 KNOWN_LIMITATIONS.md에
정직하게 명시했음을 안내하는 형태로 처리합니다.

---

## 1. 아키텍처 결정

### Q1.1. "왜 LangGraph supervisor 패턴인가요? 직접 OpenAI/Gemini API 호출하면 더 가볍지 않나요?"

A. 도구 호출(tool calling)이 핵심이라 그렇습니다. 9개 에이전트가 각자
다른 외부 데이터(PyKRX, DART, BOK, Naver News 등)를 fetch하는 ReAct
루프를 돌립니다. 직접 API 호출로 짜면 (a) 도구 호출 프로토콜을 직접
구현해야 하고, (b) 멀티턴 reasoning을 직접 관리해야 하며, (c) 9개
독립 에이전트를 supervisor 패턴으로 묶는 그래프 구조를 직접 만들어야
합니다. `langgraph_supervisor.create_supervisor`가 그 부분을 대체합니다.
대신 thread-safety / 비용 가시성 / 컨텍스트 압축 같은 운영적 wrapper는
직접 만들었습니다 (`core/progressive_supervisor.py`,
`config/llm_factory.py`, `utils/cost.py`).

### Q1.2. "Streamlit이 production-grade인가요? FastAPI + React가 더 낫지 않나요?"

A. 이 시스템은 single-user research tool이지 multi-tenant SaaS가
아닙니다. `docs/KNOWN_LIMITATIONS.md` Tier 3에 명시했습니다. Streamlit은
"분석 한 번 돌리고 리포트 보고 챗으로 후속 질문" 패턴에 데이터 시각화
포함하여 가장 빠르게 만들 수 있는 도구입니다. FastAPI + React로 가면
가치 대비 비용이 너무 큽니다. 만약 multi-user / 수익화 단계로 가면
그때 재설계 필요하다고 KNOWN_LIMITATIONS에 명시했습니다.

### Q1.3. "9개 에이전트가 다 필요한가요? 통합 못하나요?"

A. 각 에이전트가 다른 데이터 소스와 다른 reasoning을 담당해서 책임이
분리되어 있습니다. `core.signals.AgentSignal`이 9개를 enum으로 명시하고,
`agents/` 디렉토리 구조가 1:1 매핑입니다. 만약 한 LLM 호출에 9개
관점을 다 넣으면 (a) 토큰 비용 폭증, (b) LLM이 도구 호출에서 길을 잃어
환각 가능성, (c) 한 에이전트가 실패해도 다른 8개가 진행 가능한 graceful
degradation이 깨집니다 (`main.py:MIN_AGENTS_FOR_OPINION = len(AGENT_NAMES) // 2`).

### Q1.4. "왜 글로벌 시장 에이전트가 있나요? 한국 주식만 분석한다면서요?"

A. 한국 시장은 미국 증시 / 환율 / 비트코인 등에 매우 민감해서, 종목
자체 분석과 별개로 *외부 컨텍스트*가 필요합니다. `agents/korean_global_market_agent.py`는
분석 *대상*이 아니라 *환경*을 supplied합니다. KOSPI 종목 분석할 때
"오늘 S&P 어땠나, Fear&Greed 몇이었나"가 sentiment에 영향을 줍니다.

### Q1.5. "ReAct 대신 AutoGen, CrewAI는 검토했나요?"

A. 검토했고 LangGraph supervisor를 선택한 이유는 (1) LangChain
생태계 — Naver/Tavily/DART tool 어댑터가 가장 자연스럽게 결합, (2)
명시적 그래프 구조 — supervisor가 누구를 부를지 visible, (3)
streaming 응답 — `stream_korean_stock_analysis`가 Streamlit UI에
실시간 progress 표시. CrewAI는 더 가볍지만 streaming이 약하고
AutoGen은 dialog flow가 너무 자유로워서 9개 에이전트를 결정론적
순서로 묶기 어렵습니다.

---

## 2. 데이터 / 도메인

### Q2.1. "PER이 12.5라는 값이 어디서 왔는지 추적 가능한가요? (data lineage)"

A. 두 단계로 추적합니다. (1) PyKRX의 `get_market_fundamental`에서
한국어 컬럼 "PER"을 직접 읽고 (`agents/korean_financial_react_agent.py:147`),
(2) `data/external_schemas.py:PykrxFundamentalRow` Pydantic 모델로
검증합니다. 컬럼명이 바뀌면 `DataQualityError`가 raise됩니다. 결과
dict에 `"data_source": "PyKRX"`로 명시합니다. 다만 *LLM이 가공한
텍스트*에 들어간 PER 12.5는 자유 형식이라 다시 source까지 추적은
못 합니다 — 이건 KNOWN_LIMITATIONS에는 없지만, 일반적인 LLM 한계입니다.

### Q2.2. "장이 열리지 않은 날(주말/공휴일) 분석하면 어떻게 됩니까?"

A. PyKRX가 빈 DataFrame을 돌려주고 우리 코드는 (1) `if df.empty:
return {"error": ...}`로 명시적 처리 (`agents/korean_financial_react_agent.py:43`),
(2) `kst_yesterday_compact()`는 단순 -1일이라 휴일 보정은 하지 않습니다.
호출자가 빈 응답을 받으면 graceful degradation으로 fallback 메시지를
표시합니다. 휴일 보정 (자동으로 직전 거래일로 백오프)은 KNOWN_LIMITATIONS에
명시되지 않은 약점인데, 답할 때 "current behavior is to surface the empty
response as a known limitation rather than silently use stale data"라고
정직하게 답합니다.

### Q2.3. "이미 분석한 종목 재분석하면 캐시 hit하나요?"

A. `BaseAPIClient`의 file-level TTL 캐시가 외부 API 응답 단위로
적용됩니다 — Alpha Vantage 1시간, F&G 6시간 등 `data/cache_ttl.py`에
명시. 단, LLM 추론 결과 자체는 캐시 안 합니다 (deterministic하지
않아서). 즉 같은 종목 재분석은 외부 API 호출은 줄지만 LLM 호출은
그대로 발생합니다. 사용자가 "fresh data 강제" 원하면
`get_cached(..., force_refresh=True)`로 캐시 우회 가능.

### Q2.4. "Streamlit에서 동시 사용자 100명이면 어떻게 됩니까?"

A. 단일 process 단일 사용자 가정으로 설계됐습니다 (KNOWN_LIMITATIONS
Tier 3 명시). 100명 동시 접속하면 (a) 같은 LLM provider quota 공유,
(b) `ProgressiveAnalysisEngine` 인스턴스가 lazy singleton이라
ThreadPoolExecutor 워커 7개를 100명이 공유 → 큐 대기. 답: "scale-out은
multi-tenant 단계의 결정이고, 현재는 의도된 single-user research tool".

### Q2.5. "투자 의견 신뢰도가 78%라는 게 실제 정확도와 calibration 되어 있나요?"

A. 정직하게 — 안 되어 있습니다. 78%는 LLM 자기 보고입니다. 다만
화이트리스트(BUY/HOLD/SELL)와 범위 clamp(0-100)는 강제합니다
(`agents/korean_investment_opinion_agent.py:_clamp_price` 등). Calibration은
back-test 데이터셋이 필요해서 현재 범위 밖입니다. 면접에서 이걸 묻는다면
"이건 *분석 리포트 도구*이지 *예측 정확도 보장 도구*가 아닙니다.
신뢰도는 LLM의 confidence proxy일 뿐, 실제 정확도와 calibration은
별도 back-test 필요"라고 답합니다.

---

## 3. 신뢰성 / 운영

### Q3.1. "외부 API가 죽으면 사용자가 무엇을 보나요?"

A. 세 단계 방어선이 있습니다:
1. `urllib3 Retry`가 429/5xx에 0.5/1.0/2.0초 백오프로 3회 재시도
   (`data/base_client.py:RETRY_*`).
2. 그래도 실패하면 HTTP status → 도메인 예외 변환:
   `BaseAPIClient.request_json`이 401/403→Auth, 429→RateLimit,
   5xx→Unavailable로 매핑.
3. 에이전트는 `utils.agent_helpers.format_error_message_korean`이
   예외를 한국어 fallback 메시지로 변환해서 dict로 돌려줍니다 —
   사용자는 "❌ {에이전트명} 분석이 제한적입니다" 같은 카드를 봅니다.
   분석 절반 이상 성공하면 투자 의견 게이트는 통과
   (`main.py:MIN_AGENTS_FOR_OPINION`).

### Q3.2. "PyKRX 라이브러리가 컬럼명을 바꾸면 어떻게 되나요?"

A. `data/external_schemas.py:assert_pykrx_columns`가 모든 PyKRX
컬럼이 사라지면 `DataQualityError(source='pykrx/...')`를 raise합니다.
DART도 envelope를 `_make_request`에서 한 곳에서 검증 — 7개 endpoint
전체에 자동 적용. 라이브러리 회귀 시 silent fallback이 아니라 typed
error로 surfaces됩니다. 단위 테스트 4개로 회귀 방지
(`tests/test_external_schemas.py:TestAssertPykrxColumns`).

### Q3.3. "한 번 분석에 LLM 토큰 비용이 얼마인가요?"

A. `utils/cost.py`의 `track_llm_call`이 호출마다 prompt/completion
토큰과 USD 비용을 greppable structured log로 남깁니다:
`llm_call agent=X model=Y in_tok=N out_tok=N cost_usd=...`.
2025-11 기준 단가 표 등록 모델 5개(gpt-4.1-nano / gpt-4o / gpt-4o-mini
/ gemini-2.0-flash / gemini-2.0-flash-lite). 일/주 단위 비용은
`grep llm_call logs/* | awk` 등으로 집계 가능. Prometheus exporter는
별도 PR로 명시.

### Q3.4. "데이터가 KST인지 UTC인지 어떻게 보장하나요?"

A. `utils/time.py`가 KST 헬퍼를 강제합니다. 모든 PyKRX/DART 거래일
인자는 `kst_today_compact()`, `kst_yesterday_compact()`,
`kst_year(-1)` 같은 함수를 통합니다. 코드 전체에 `datetime.now()`는
1군데 (`BaseAPIClient.get_cached` mtime 비교)만 남아 있고 그건
의도적 (OS 파일 mtime은 system clock 기준). 50개 사이트가 이미
마이그레이션됐고, "왜 1군데 남았나"는 docstring에 명시되어 있습니다.

### Q3.5. "ThreadPoolExecutor로 7개 에이전트가 같은 LLM 인스턴스를 공유하는데 thread-safe한가요?"

A. `config/llm_factory.py` 모듈 docstring에 명시했습니다: LangChain
ChatOpenAI/ChatGoogleGenerativeAI는 내부적으로 `requests.Session`을
들고 있고, requests 공식 문서가 `Session.request()`는 connection
pool에 대해 thread-safe하다고 보증합니다. 매 invoke가 새 HTTP
요청을 만들므로 instance 공유는 안전합니다. 다만 *문서화된 가정*임을
명시 — LangChain SDK가 향후 stateful client로 바뀌면 회귀할 수
있는 부분.

---

## 4. 보안

### Q4.1. "git history에 DART API 키가 있다고 들었습니다."

A. 네 — `SECURITY.md`에 명시하고 사용자에게 키 회전(opendart.fss.or.kr
revoke + reissue)을 안내했습니다. filter-repo 같은 history rewrite는
fork/clone 동기화 깨짐 위험이 있어 하지 않았습니다. 키 회전이 표준
mitigation입니다. 현재 코드에는 fallback 하드코딩 없음
(`fix(security): remove hardcoded credentials` 커밋 참조).

### Q4.2. "verify=False를 RSS 클라이언트에서 쓰던데요."

A. 한국 매체 일부 RSS 서버가 인증서 체인이 깨져 있어 필요했습니다.
현재는 `data/korean_news_rss_client.py:_ALLOWED_INSECURE_HOSTS`
화이트리스트 호스트에만 `verify=False`가 적용됩니다. 화이트리스트가
비어 있는 현재(Google News만 활성)에는 모든 요청이 `verify=True`로
나갑니다. 5개 단위 테스트로 회귀 방지
(`tests/test_rss_tls_whitelist.py`).

### Q4.3. "캐시 키가 사용자 입력이면 path traversal 가능한가요?"

A. `BaseAPIClient._validate_cache_key`가 `^[A-Za-z0-9_-][A-Za-z0-9_.-]*$`
화이트리스트로 차단합니다. NUL 바이트, 윈도우 예약 문자, UNC 경로,
hidden file 접두사(`.`)까지 한 줄로 막힙니다. 4개 단위 테스트로
회귀 방지 (`tests/test_base_client_concurrency.py`).

### Q4.4. "LLM 출력이 UI에 그대로 들어가면 XSS 가능 아닌가요?"

A. `ui/cards.py:escape_html`이 모든 LLM/외부 문자열을 HTML escape하고
`javascript:` / `data:` URL scheme을 차단합니다. Streamlit이
`unsafe_allow_html=True`로 렌더링하는 모든 카드에 이 함수를
거칩니다. 단위 테스트는 `tests/test_ui_cards.py`.

---

## 5. 테스트 / 코드 품질

### Q5.1. "테스트 커버리지가 46%인데 적지 않나요?"

A. 솔직히 답합니다. 9개 에이전트 모두 단위 테스트가 있고
(`tests/agents/`), supervisor stream end-to-end가 17개 통합 테스트로
커버되어 있습니다 (`tests/test_supervisor_stream.py`,
`tests/test_progressive_execute.py`). 남은 50%는 (a) LangChain
프롬프트 문자열 (의도적으로 content 테스트 안 함 — 카피 변경에
부서지기 쉬워서), (b) `create_*_agent()` factory boilerplate
(streaming 테스트로 indirect 커버), (c) 일부 데이터 클라이언트
세부 메서드. CI 게이트는 45%로 회귀 방지선만 잡고, 점진 60%까지
가능하다고 KNOWN_LIMITATIONS에 명시했습니다.

### Q5.2. "왜 mypy strict가 일부 모듈만인가요?"

A. 점진 도입입니다. `pyproject.toml`의 `[[tool.mypy.overrides]]`에
strict 대상 8개 모듈을 명시 — 내가 새로 작성하거나 완전히 타입
힌트가 있는 코드만. 나머지는 `ignore_missing_imports` + 느슨한
모드. 한 번에 전체 strict로 바꾸면 langchain/pykrx/finance-datareader
같은 stubs 없는 외부 라이브러리 때문에 노이즈만 폭증합니다.

### Q5.3. "테스트가 230개인데 진짜로 실수를 잡아냅니까?"

A. 이번 audit 중에 5개의 latent bug를 실제로 잡았습니다:
1. `EnterpriseContextManager.compress_agent_output` 메서드가
   호출되는데 정의가 없어 매번 except 절로 falling through →
   "기술적 문제로 요약을 생성할 수 없습니다" 반환. test_context_manager
   추가하면서 발견.
2. `_handle_running_signal`의 substring matching이 dead code였음 —
   `current_stage`에 영문 agent key가 절대 안 들어감. 명시적 키로 교체.
3. `matplotlib.use("Agg")`가 `pyplot` import 뒤에 있어 no-op이던 것을
   import 순서 fix.
4. `verify=False`가 모든 RSS 요청에 무차별 적용되던 것을 화이트리스트로 제한.
5. DART API 키가 fallback 상수로 하드코딩되어 있던 것을 제거 + SECURITY.md.

### Q5.4. "왜 Pydantic을 settings 외에는 안 썼다가 지금은 쓰나요?"

A. 처음엔 TypedDict만 썼습니다(`core/schemas.py`) — 호출자가 dict로
다루기 쉬워서. 외부 데이터(DART, PyKRX) 응답 검증이 필요해지면서
Pydantic을 `data/external_schemas.py`에 도입했습니다. 둘의 역할이
다릅니다: TypedDict는 *우리 코드 사이*의 계약, Pydantic은 *외부와의*
경계 검증. `extra="ignore"`로 외부 새 필드 추가를 non-breaking으로
받습니다.

---

## 6. 비즈니스 / 가치

### Q6.1. "이걸 누구를 위해 만들었나요?"

A. 한국 주식을 분석하고 싶은데 (a) 증권사 리포트를 직접 읽기엔
시간 없고, (b) 9개 관점(재무/기술/수급/뉴스 등)을 매번 직접 찾기엔
귀찮은 개인 투자자. 분석 후 "이건 왜 BUY야?" 같은 후속 질문을
챗으로 받을 수 있다는 게 차별점입니다.

### Q6.2. "이미 네이버 증권, 키움 HTS가 있는데 왜 이게 필요한가요?"

A. 네이버 증권은 *데이터 나열*입니다 — 시세, PER, 뉴스 헤드라인이
따로 따로 있습니다. 이 도구는 *AI 해석 + 종합 의견*입니다.
KNOWN_LIMITATIONS에 "단순 시세 비교는 무료 도구로 충분, 종합 해석이
core value"라고 명시.

### Q6.3. "ESG 점수를 표시하는데 MSCI나 Sustainalytics 없이 가능한가요?"

A. 정직하게 — 우리 ESG 점수는 *DART 공시 완성도 점수*에 가깝습니다.
MSCI ESG Rating 같은 종합 점수가 아닙니다. KNOWN_LIMITATIONS Tier 3에
"MSCI/Sustainalytics는 paid feed(~$50K/년)라 의도적 제외"로 명시.
사용자가 도구를 무료로 쓰려면 이 한계를 알아야 합니다.

### Q6.4. "backtest 결과 있나요? 이 BUY 의견이 실제로 돈을 벌어줬나요?"

A. 없습니다. 이건 *분석 리포트 도구*이지 *트레이딩 시그널 생성기*가
아닙니다. UI에도 "투자 권유가 아니라 분석 결과 기반 참고 의견"이라고
명시되어 있고
(`agents/korean_investment_opinion_agent.py` 시스템 프롬프트 #2),
KNOWN_LIMITATIONS Tier 3에 "real-time trading terminal이 아님"이
명시되어 있습니다. Backtest는 다른 제품의 일.

---

## 7. 인프라 / DevOps

### Q7.1. "Docker로 실제 띄워봤나요?"

A. Dockerfile은 multi-stage(builder가 wheel만 빌드, runtime은
chromium + KCJK 폰트 + tini). docker-compose.yml은 named volume
`api_cache`를 `/var/cache/tusim`에 마운트 + `TUSIM_CACHE_DIR` env로
지정. healthcheck는 `/_stcore/health`. `docker compose config`로
syntax 검증은 했지만, docker daemon이 sandbox CI 환경에서 안 돌아서
실제 빌드 검증은 호스트 머신에서 필요. KNOWN_LIMITATIONS에는 없는
부분이지만 정직하게 답합니다.

### Q7.2. "CI 파이프라인은 어떻게 되어 있나요?"

A. `.github/workflows/ci.yml`이 3개 job:
1. `lint-type-test` — Python 3.11 + 3.12 matrix, ruff(lint+format)
   + mypy strict + pytest 커버리지 ≥45%.
2. `audit` — `pip-audit -r requirements.txt`로 CVE 스캔. `continue-on-error`
   라 merge 차단은 안 하지만 PR에 표시.
3. `secret-scan` — gitleaks-action 전체 history 스캔.

### Q7.3. "lockfile이 있나요? 재현 가능한 빌드인가요?"

A. `requirements.lock` (496 라인, transitive pin) + `requirements-dev.lock`
이 committed. `make lock`이 `pip-compile --pre`로 재생성. `--pre`는
mplfinance 0.12가 PyPI에 베타로만 있어서 필요. 일반적인 마이너 핀은
`requirements.in`에 명시.

### Q7.4. "pre-commit hook을 강제하나요?"

A. 강제는 아닙니다 (사용자가 `pre-commit install` 해야 활성).
`.pre-commit-config.yaml`에 ruff, mypy strict, trailing-whitespace,
yaml check, large file check, merge conflict, private key
detection. CI가 같은 검증을 하니까 hook을 안 깔아도 PR에서 잡힙니다.

---

## 8. 솔직히 답하기 어려운 것들

이 카테고리는 "마이너스 답변"이 될 수 있는 부분입니다. 면접에서 들어오면
**KNOWN_LIMITATIONS.md를 펴서 보여줍니다** — "이건 의식하고 있고
정직하게 문서화했다"가 핵심 답변입니다.

### Q8.1. "공휴일 거래일 보정은요?"

A. `kst_yesterday_compact()`가 단순 -1일이라 일요일에 호출하면
토요일을 돌려줍니다. PyKRX가 빈 응답으로 graceful degradation으로
폴백하지만, *자동 -2/3일 backoff*는 없습니다. KNOWN_LIMITATIONS에
명시되지 않은 약점이라 면접에서 들어오면 즉시 "맞습니다, 이건 추가
작업이 필요한 부분입니다 — 보통 트레이딩 시스템에선 KRX 공휴일
캘린더를 들여와서 처리"라고 답합니다.

### Q8.2. "LLM 환각 감지는?"

A. 구조적 제약으로 부분 완화: BUY/HOLD/SELL whitelist
(`agents/korean_investment_opinion_agent.py:202`), 가격 0.5x-2.0x
clamp(`_clamp_price`), confidence 0-100 clamp, JSON parse 실패 시
한국어 fallback opinion. 자유 형식 텍스트의 환각(예: "삼성전자가
2024년에 LG디스플레이를 인수했다" 같은 거짓 fact)은 LLM provider
guardrail에 의존합니다. 이건 LLM 전반의 한계이지 우리 시스템 한계라기보단,
산업 전체의 미해결 문제입니다.

### Q8.3. "동시 사용자 100명 시 LLM provider quota?"

A. provider rate limit이 hit하면 `RateLimitError`가 raise됩니다
(`core/errors.py`). 도메인 예외라 caller가 backoff / 사용자에게
"잠시 후 다시 시도해주세요" 메시지 분기 가능. 다만 *큐 시스템*은
없습니다 — multi-tenant SaaS 단계의 작업.

### Q8.4. "왜 alpha/beta 버전 의존성이 lockfile에 있나요?"

A. `mplfinance 0.12.10b0`과 `altair 6.2.0.dev*`는 PyPI에 stable이
없어서 베타로 가져왔습니다. 개발 환경에서 안정적으로 동작했지만,
KNOWN_LIMITATIONS Tier 2에 "defensive operator는 `mplfinance==0.12.9b1`
같은 더 오래된 베타로 pin할 수 있다"고 명시했습니다. 우리 코드 책임이
아니라 *upstream availability* 문제.

---

## 한 줄 정리

| 영역 | 상태 |
|---|---|
| 아키텍처 정당화 | ✅ 명시적 답변 가능 |
| 데이터 lineage | ✅ Pydantic + source label |
| 신뢰성 (retry/backoff) | ✅ urllib3 + 도메인 예외 |
| 보안 (XSS / path traversal / TLS) | ✅ 화이트리스트 + escape |
| 테스트 (230개, 46% cov) | ✅ 9/9 agent + E2E supervisor |
| 비용 가시화 | ✅ `utils/cost.py` greppable log |
| 운영 (Docker / CI / lockfile) | ✅ 전부 갖춤 |
| LLM calibration / backtest | ⚠️ 의도적 비목표, 정직하게 답변 |
| 공휴일 backoff | ⚠️ 약점 인정 + 어떻게 고칠지 답변 가능 |
| Multi-tenant scale | ⚠️ Tier 3 non-goal로 명시 |
| 환각 감지 | ⚠️ 구조 제약 + LLM 전반 한계 |

⚠️ 항목은 *마이너스가 아니라 정직성*입니다. "이건 약점이고 우리는
알고 있다"고 답하는 게 면접관이 보고 싶은 것입니다. 변명하거나
모르는 척하는 게 마이너스입니다.
