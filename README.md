# TuSimReport - 한국 주식 분석 AI 에이전트 시스템

LangGraph Supervisor 아키텍처 기반의 AI 멀티 에이전트 시스템. **9개 전문 에이전트**가
한국 주식의 펀더멘털·기술·수급·여론·글로벌 환경을 병렬 분석하고, 그 결과를
종합한 BUY/HOLD/SELL **투자 의견**과 분석 컨텍스트를 기억하는 **대화형 AI**를 제공합니다.

---

## 📊 핵심 기능

- **9개 전문 에이전트**: 시장환경·뉴스여론·재무·기술·수급·상대가치·ESG·커뮤니티·글로벌시장
- **AI 투자 의견**: 9개 분석을 종합해 BUY/HOLD/SELL + 신뢰도(0-100) + 목표가/손절가/R/R + 분할매수 전략 산출 (LLM 출력을 화이트리스트·범위 clamp로 검증)
- **대화형 AI**: 완성된 분석을 컨텍스트로 받아 후속 질문에 답변 (동시 입력 락 보호)
- **글로벌 시장 통합**: Alpha Vantage(S&P/NASDAQ/Dow/FX) + CoinGecko(BTC/ETH) + CNN Fear & Greed
- **병렬 실행**: 독립 에이전트 7개를 ThreadPoolExecutor로 동시 실행, 종속적 2개만 순차
- **실제 데이터만**: BOK ECOS, DART, PyKRX, FinanceDataReader, Naver News API, Paxnet 등 — Mock/샘플 데이터 절대 금지
- **XSS 방어**: 모든 LLM/외부 문자열은 ui.cards.escape_html을 거쳐 렌더링, javascript:/data: URL 차단
- **Graceful Degradation**: API 키 누락/외부 실패 시 한글 에러 메시지로 폴백, 분석 절반 이상 성공하면 의견 게이트 통과

## 🛡️ Production-grade 안전장치

- **도메인 예외 계층** (`core/errors.py`): RateLimitError / AuthenticationError / DataSourceUnavailableError 등으로 외부 실패를 타입화 — 재시도 정책을 호출자가 분기 가능
- **자동 retry/backoff**: `BaseAPIClient`가 urllib3 Retry로 429/5xx에 지수 백오프(0.5s, 1.0s, 2.0s) 3회 시도
- **상태→예외 매핑**: `request_json()`이 401/403→Auth, 429→RateLimit, 5xx→Unavailable로 자동 변환
- **KST 타임존 명시**: PyKRX/DART 거래일 인자는 `kst_yesterday_compact()` 등 `utils.time`을 통해 한국 시간 기준 산출 (UTC 컨테이너에서 9시간 어긋남 방지)
- **TLS verify 화이트리스트**: `verify=False`는 `_ALLOWED_INSECURE_HOSTS`에 명시된 호스트에만 적용 (RSS 인증서 깨진 매체 한정)
- **Path-safe 캐시 키**: `^[A-Za-z0-9_-][A-Za-z0-9_.-]*$` 화이트리스트 — NUL/UNC/hidden file 차단
- **Atomic cache write**: `tempfile.mkstemp + os.replace`로 동시 쓰기 race 방지
- **Structured logging**: `contextvars` 기반 `bind_session(stock_code=...)` — 모든 로그에 `[s=<sid> c=<symbol>]` 접두사 자동 주입, 멀티 사용자 환경에서 로그 demux
- **명시적 캐시 TTL** (`data/cache_ttl.py`): 시세 5분, 환율 1시간, F&G 6시간, BOK/DART 12시간 — 매직 넘버 제거
- **타입 검증**: `core.signals`, `core.schemas`, `core.errors`, `config.llm_factory`, `ui.cards`, `data.base_client`, `utils.time`, `utils.logging_context` 8개 모듈은 mypy strict
- **CI 게이트**: Python 3.11/3.12 matrix → ruff lint + format + mypy strict + pytest (커버리지 ≥20% baseline) + pip-audit + gitleaks 시크릿 스캔

## 🐳 Docker로 실행

```bash
cp .env.example .env   # API 키 채우기 (Gemini 또는 OpenAI 필수)
docker compose up --build
# → http://localhost:8501
```

Dockerfile은 multi-stage: builder는 wheel 빌드만, runtime은 chromium + 한글 폰트 + tini로 슬림. non-root user(uid=1000)로 실행. healthcheck는 `/_stcore/health`.

---

## 🏗️ 시스템 아키텍처

### 9개 전문 에이전트

```
tusimreport/
├── agents/                              # 9개 전문 에이전트 + 투자 의견 합성
│   ├── korean_context_agent.py            # 시장 환경 (BOK, FDR)
│   ├── korean_sentiment_agent.py          # 뉴스 여론 (Naver, Tavily)
│   ├── korean_financial_react_agent.py    # 재무 (DART, PyKRX)
│   ├── korean_advanced_technical_agent.py # 기술적 (FDR, PyKRX)
│   ├── korean_institutional_trading_agent.py # 기관 수급 (PyKRX)
│   ├── korean_comparative_agent.py        # 상대 가치 (섹터)
│   ├── korean_esg_analysis_agent.py       # ESG (DART)
│   ├── korean_community_agent.py          # 커뮤니티 (Paxnet, DC)
│   ├── korean_global_market_agent.py      # 글로벌 시장 (Alpha Vantage, CoinGecko, Fear&Greed)
│   └── korean_investment_opinion_agent.py # 9개 결과 종합 → BUY/HOLD/SELL
├── core/
│   ├── korean_supervisor_langgraph.py   # LangGraph Supervisor + 프롬프트 빌드
│   ├── progressive_supervisor.py        # 병렬 실행 엔진 + lock
│   ├── context_manager.py               # tiktoken lazy + 토큰 예산
│   ├── chat_session.py                  # 분석 결과 컨텍스트 채팅 (lock)
│   ├── signals.py                       # 완료 신호 enum (single source)
│   └── schemas.py                       # TypedDicts (InvestmentOpinion, AgentResponse)
├── config/
│   ├── settings.py                      # pydantic-settings v2
│   └── llm_factory.py                   # build_llm() - 프로바이더 통합
├── data/                                # 외부 클라이언트 + BaseAPIClient(atomic cache)
│   ├── base_client.py                   # 공통 베이스 (atomic write, path-safe key)
│   ├── bok_api_client.py, dart_api_client.py, naver_api_client.py
│   ├── paxnet_crawl_client.py, dcinside_crawler.py
│   ├── alpha_vantage_client.py, coingecko_client.py, fear_greed_client.py
│   └── chart_generator.py, sector_analysis_client.py
├── ui/                                  # main.py에서 분리한 프레젠테이션
│   ├── cards.py                         # HTML 카드 빌더 + escape_html
│   ├── styles.py                        # PAGE_CSS
│   └── stock_database.py                # 종목 메타데이터
├── utils/agent_helpers.py               # graceful fallback, korean 에러 변환
└── main.py                              # Streamlit UI 엔트리
```

### 데이터 소스 (6개)

| 데이터 소스 | API 키 필요 | 용도 |
|------------|-----------|------|
| FinanceDataReader | ❌ | 주가 데이터 |
| PyKRX | ❌ | 한국거래소 데이터 |
| BOK ECOS | ✅ | 거시경제 지표 |
| DART | ✅ | 기업 공시/재무 |
| Naver News | ✅ | 한국 뉴스 |
| Paxnet (Selenium) | ❌ | 커뮤니티 토론 |

---

## ✨ 새로운 기능 (Phase 3 - 2025-11-16)

### 🛡️ Graceful Degradation (우아한 성능 저하)
API 키가 부족할 때 명확한 안내를 제공합니다.

- ✅ **한글 에러 메시지**: 어떤 API가 필요한지 명확히 안내
- ✅ **API 상태 표시**: 사이드바에서 현재 설정 상태 확인
- ✅ **단계별 안내**: 문제 해결 방법을 이모지와 함께 제공
- ✅ **Fallback 메커니즘**: 에러 발생 시 명확한 원인과 해결법 제시

**중요**: 이 시스템은 실제 API 데이터만 사용합니다. API 키가 없으면 분석을 실행할 수 없습니다.

### 🔧 개선된 사용자 경험
- **API 키 상태 사이드바**: 실시간으로 어떤 API가 설정되었는지 확인
- **종목 코드 검증**: 잘못된 입력 시 즉시 한글로 피드백
- **데이터 소스 투명성**: 어떤 데이터를 사용했는지 명시
- **에러 명확화**: 모든 에러를 한글로 친절하게 안내

---

## 💬 대화형 AI 기능

### 🤖 ChatSession - 분석 결과 기반 대화

분석이 완료된 후, **8개 에이전트의 분석 결과를 컨텍스트로** 하여 AI와 자유롭게 대화할 수 있습니다.

#### 주요 기능
- ✅ **컨텍스트 기반 대화**: 8개 에이전트 분석 결과를 모두 이해하고 답변
- ✅ **상태 유지**: 대화 히스토리를 기억하고 맥락 있는 답변 제공
- ✅ **투자자 친화적**: 초보자도 이해하기 쉽게 설명
- ✅ **추가 질문 가능**: "왜 이렇게 분석했어?", "더 자세히 설명해줘" 등

#### 사용 예시
```
사용자: "이 종목의 가장 큰 리스크는 뭐야?"
AI: 📊 분석 결과를 종합하면...
    1. 재무 분석: 부채비율 상승 추세
    2. 기술적 분석: 단기 과매수 구간
    3. 뉴스 여론: 최근 부정적 뉴스 증가
    ...

사용자: "그럼 지금 사야 해, 말아야 해?"
AI: ⚠️ 투자 판단은 본인의 책임이지만, 분석 결과를 바탕으로...
```

#### 기술 스택
- **ChatSession 클래스**: 대화 세션 관리
- **LangChain Messages**: SystemMessage, HumanMessage, AIMessage
- **Streamlit Chat UI**: 직관적인 채팅 인터페이스
- **Session State**: 분석 결과 및 대화 히스토리 유지

---

## 🚀 빠른 시작

### 1️⃣ **사전 요구사항**

```bash
Python 3.11+
Chrome/Chromium (Selenium 크롤링용)
```

### 2️⃣ **설치**

```bash
# 1. 저장소 복제
git clone https://github.com/Danwoo/tusimreport.git
cd tusimreport

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경 설정
cp .env.example .env
# .env 파일을 열어서 API 키 입력

# 4. 환경 검증 (선택)
python setup_check.py
```

### 3️⃣ **API 키 발급** (필수)

최소 요구사항 (3개):
1. **Google Gemini** 또는 **OpenAI**: https://aistudio.google.com/app/apikey
2. **DART**: https://opendart.fss.or.kr/
3. **ECOS**: https://ecos.bok.or.kr/

권장 (더 나은 분석):
4. **Naver News**: https://developers.naver.com/products/search/
5. **Tavily**: https://tavily.com/

### 4️⃣ **실행**

```bash
streamlit run main.py
```

브라우저에서 http://localhost:8501 접속

---

## ⚙️ 환경 설정

### .env 파일 설정

```env
# 필수 (최소 3개)
GOOGLE_API_KEY=your_google_api_key
DART_API_KEY=your_dart_api_key
ECOS_API_KEY=your_ecos_api_key

# 권장 (더 나은 분석)
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
TAVILY_API_KEY=your_tavily_api_key

# LLM 설정
USE_GEMINI=true
GEMINI_MODEL=gemini-2.0-flash-lite
```

자세한 설정은 `.env.example` 파일 참고

---

## 🧪 테스트

```bash
# 기본 테스트
pytest tests/

# 커버리지 포함
pytest tests/ --cov=agents --cov=core --cov=data

# 환경 검증
python setup_check.py
```

---

## 📚 문서

- **[CLAUDE.md](./CLAUDE.md)**: AI Assistant 개발 가이드 (상세)
- **[.env.example](./.env.example)**: 환경 설정 예제

---

## 🔧 알려진 문제

### 현재 제한사항
- ⚠️ **Selenium 의존성**: Chrome/Chromium 필요 (서버 환경에서 추가 설정)
- ⚠️ **API 호출 제한**: 무료 API는 일일 호출 제한 있음
- ⚠️ **Docker 미지원**: 현재 로컬 환경만 지원

### 해결 완료 (Phase 3 - 2025-11-16)
- [x] ✅ **에러 메시지 한글화** - 모든 에이전트에 한글 에러 메시지 적용
- [x] ✅ **Graceful Degradation** - API 부족 시 명확한 에러 안내
- [x] ✅ **API 상태 표시** - 사이드바에서 실시간 확인
- [x] ✅ **Fallback 메커니즘** - 에러 발생 시 해결 방법 제시

### 해결 예정
- [ ] Docker/Docker Compose 지원
- [ ] 설치 자동화 스크립트 (`install.sh`)
- [ ] 통합 테스트 확대

---

## 🤝 기여

프로젝트는 현재 활발히 개발 중입니다. 이슈 및 PR 환영합니다!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 라이선스

이 프로젝트는 개인 학습 및 연구 목적으로 제작되었습니다.

---

## ⚠️ 면책 조항

**이 시스템은 투자 참고 자료일 뿐, 투자 권유가 아닙니다.**

- 📊 AI 분석 결과는 절대적이지 않습니다
- 💰 실제 투자 결정은 본인의 판단과 책임입니다
- 🔍 추가적인 조사와 전문가 상담을 권장합니다
- ⚠️ 과거 데이터는 미래 수익을 보장하지 않습니다

---

**Python**: 3.11 / 3.12 (CI matrix)
**테스트**: 230개 (커버리지 ~46%)
**보안 정책**: [SECURITY.md](SECURITY.md)
