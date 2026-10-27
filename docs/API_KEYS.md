# API 키 발급 안내

무료로 운영하는 것을 기준으로, 각 키를 어디서 어떻게 받는지와 받지 않으면 무엇이 빠지는지를 정리한다. 기준일은 2026-10-25다. 요금, 한도, 약관은 자주 바뀌므로 실제 화면과 다르면 실제 화면을 따른다.

## 1. 요약

| 환경변수 | 구분 | 쓰는 에이전트 | 무료 조건 | 발급 |
|---|---|---|---|---|
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | 필수 | 9개 전부, 최종 보고서, 투자 의견, 대화 | 제공자별로 다르다 (3절) | 3절 |
| `LLM_MAX_REQUESTS_PER_MINUTE` | 권장 | 모든 LLM 호출 | — | 제공자 한도보다 조금 낮게 |
| `DART_API_KEY` | 필수 | `financial_expert`, `esg_expert` | 무료, 하루 약 20,000건 | [OpenDART](https://opendart.fss.or.kr) |
| `ECOS_API_KEY` | 필수 | `context_expert`, `financial_expert` | 무료 | [ECOS Open API](https://ecos.bok.or.kr/api/) |
| `KRX_ID`, `KRX_PW` | 권장 | `context_expert`, `financial_expert`, `institutional_trading_expert`, `comparative_expert` | 무료 회원가입 | [KRX 정보데이터시스템](https://data.krx.co.kr/contents/MMC/COMS/client/MMCCOMS002.cmd) |
| `TAVILY_API_KEY` | 선택 | `sentiment_expert` | 월 1,000 크레딧 | [Tavily](https://app.tavily.com) |
| `ALPHA_VANTAGE_API_KEY` | 선택 | `global_market_expert` | 하루 25건 | [Alpha Vantage](https://www.alphavantage.co/support/#api-key) |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 사용하지 않음 | — | 4.4절 | — |

키 없이 동작하는 소스는 FinanceDataReader, CoinGecko, Paxnet이다. Paxnet 크롤링은 기본으로 꺼져 있다(4.7절).

데이터 키가 없으면 해당 도구가 오류를 돌려주고, 그 에이전트는 "근거 데이터 없음"으로 판정돼 최종 보고서에서 빠진다. 근거 데이터가 있는 에이전트가 9개 중 5개 미만이면 보고서를 만들지 않는다. 어떤 소스가 빠졌는지는 `python scripts/check_sources.py`로 확인한다.

## 2. 키를 넣는 곳

로컬에서는 `cp .env.example .env` 후 값을 채운다. `.env`는 `.gitignore` 대상이다. Claude Code 클라우드 세션에서는 환경 설정의 환경 변수(또는 secrets)에 같은 이름으로 넣는다.

- 키와 비밀번호를 이슈, 커밋, 로그에 남기지 않는다.
- `KEY=`처럼 빈 값은 설정하지 않은 것으로 취급한다.
- 넣은 뒤 `python setup_check.py`로 상태를 확인한다(5절).

## 3. LLM

### 3.1 조건

9개 에이전트가 모두 LangGraph `create_react_agent`이므로 **tool calling(function calling)을 지원하는 모델**이어야 한다. `python setup_check.py --llm-probe`가 도구 하나를 붙인 요청을 한 번 보내 이를 확인한다.

분석 1회에 LLM 요청이 수십 건 나가고, 시작 직후 7개 에이전트가 동시에 요청한다. 무료 등급에서는 분당 요청 한도가 가장 먼저 걸리므로 `LLM_MAX_REQUESTS_PER_MINUTE`를 한도보다 조금 낮게 둔다. 이 값은 프로세스 전체가 하나의 제한기를 함께 쓴다.

`LLM_BASE_URL`을 설정하면 Gemini·OpenAI 설정보다 우선한다. `LLM_MODEL`이나 `LLM_API_KEY`가 비어 있으면 다른(유료일 수 있는) 제공자로 넘어가지 않고 멈춘다.

### 3.2 OpenAI 호환 제공자

| 제공자 | `LLM_BASE_URL` | tool calling 모델 예 | 무료 조건 | 키 발급 |
|---|---|---|---|---|
| Google AI Studio (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash` | 무료 등급 있음. 한도 수치는 AI Studio 화면에서 확인 | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| KiraAI | `https://kiraai.vn/api/v1` | `kira-mini-1.0` | 모델 목록에서 `is_free: true`. 분당 30회 | [kiraai.vn](https://kiraai.vn) |
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` | 분당 30회, 분당 8K 토큰, 하루 200K 토큰 | [console.groq.com/keys](https://console.groq.com/keys) |
| OpenRouter `:free` 모델 | `https://openrouter.ai/api/v1` | 모델 이름 끝이 `:free`인 모델 | 분당 20회, 하루 50회 | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |

예시 설정(KiraAI):

```dotenv
LLM_BASE_URL=https://kiraai.vn/api/v1
LLM_MODEL=kira-mini-1.0
LLM_API_KEY=<발급받은 키>
LLM_MAX_REQUESTS_PER_MINUTE=25
```

제공자별 주의점은 다음과 같다.

- **KiraAI**: 한도를 넘으면 429 대신 HTTP 500 "Rate limit exceeded"를 돌려주는 경우가 있다. 분당 30회보다 낮은 25 정도로 맞춘다. 시스템 프롬프트 없이 보내면 베트남어로 답할 수 있으나, 이 프로젝트의 에이전트는 모두 한국어 시스템 프롬프트를 쓴다.
- **Groq**: 분당 8K 토큰 제한이 7개 동시 요청에 바로 걸린다. 하루에 분석 몇 회 정도가 현실적인 한도다.
- **OpenRouter**: 하루 50회는 분석 1~2회 분량이다.

Gemini는 `GOOGLE_API_KEY`와 `USE_GEMINI=true`로도 쓸 수 있다. 다만 `langchain_google_genai`는 Gemini 3 이상에서 응답 `content`를 문자열이 아닌 리스트로 돌려주므로, 위 표의 OpenAI 호환 주소로 쓰는 편이 안전하다.

## 4. 데이터 소스

### 4.1 OpenDART — `DART_API_KEY`

1. [opendart.fss.or.kr](https://opendart.fss.or.kr) 상단 「인증키 신청/관리」 → 「인증키 신청」으로 들어간다. 키 신청이 곧 회원가입이다.
2. 약관에 동의하고 「사용자 구분」에서 「개인」을 고른다.
3. 이메일(로그인 ID)과 비밀번호, 「API 사용환경」과 「API 사용용도」를 적고 등록한다.
4. 개인은 즉시 발급된다. 키(40자리)는 로그인 후 「인증키 관리」에서 본다.

한도는 하루 약 20,000건이며 초과하면 오류 020이 난다. 개인정보 이용 동의를 2년마다 갱신하지 않으면 계정이 해지되고 오류 901이 난다.

### 4.2 한국은행 ECOS — `ECOS_API_KEY`

1. [ecos.bok.or.kr/api](https://ecos.bok.or.kr/api/) → 「OPEN API 인증키 신청」으로 들어간다.
2. NICE 본인인증을 거친다. 본인 명의의 한국 휴대폰이 필요하다.
3. 약관 동의, 정보 입력(이메일, 비밀번호, 이용목적 「비영리」) 순으로 진행한다.
4. 마이페이지 「인증키 현황」에서 키와 만료일을 확인한다. 만료 전에 「인증키 연장」을 한다.

키 없이 `sample`로 최대 10건까지 시험해 볼 수 있다.

### 4.3 KRX 정보데이터시스템 — `KRX_ID`, `KRX_PW`

이 프로젝트는 [pykrx](https://github.com/sharebook-kr/pykrx)로 지수, 투자 지표, 투자자별 매매 동향을 받는다. data.krx.co.kr은 2025-12-27부터 회원제로 바뀌어, 로그인하지 않은 요청은 빈 결과를 받는다. pykrx는 1.2.9 기준으로 `KRX_ID`·`KRX_PW` 환경변수가 있으면 그 계정으로 로그인한다.

1. [회원가입 페이지](https://data.krx.co.kr/contents/MMC/COMS/client/MMCCOMS002.cmd)에서 개인회원으로 가입한다.
2. 아이디·비밀번호 방식으로 가입한다. 네이버·카카오 간편가입만 한 계정은 pykrx 로그인에 쓰지 못할 수 있다.

주의할 점:

- `import pykrx`만 해도 즉시 로그인하고 로그인 ID를 표준출력에 찍는다. 같은 계정으로 이미 로그인돼 있으면 기존 세션을 끊는다. 브라우저에서 같은 계정을 쓰는 중이라면 그 세션이 끊길 수 있다.
- 로그인을 이용한 자동 수집은 KRX가 공식으로 허용한 경로가 아니다. 공식 경로는 [KRX OPEN API](https://openapi.krx.co.kr/contents/OPP/MAIN/main/index.cmd)다. 무료이고 키당 하루 10,000건이지만, 인증키와 API마다 관리자 승인이 필요하고 받은 정보를 제3자에게 제공할 수 없다. 이 경로로 옮기는 작업은 6절의 남은 과제다.

### 4.4 Naver 검색 API — 사용하지 않음

코드에는 Naver 뉴스 검색 클라이언트가 남아 있지만, 다음 두 이유로 키를 발급하지 않는다.

- 신규 발급 경로가 바뀌었다. developers.naver.com의 신규 Search API 신청은 2026-07-30에 마감됐고, 이제 NAVER Cloud Platform의 [NAVER API HUB](https://www.ncloud.com/product/applicationService/naverApiHub)에서만 받을 수 있다. 호출 주소와 인증 헤더도 달라져 현재 코드로는 새 키가 동작하지 않는다.
- 2026-09-07 시행 「NAVER API 서비스 이용약관」이 데이터를 AI에 입력하는 행위를 금지한다. `sentiment_expert`는 뉴스를 LLM에 넣어 분석하므로 이 조항과 충돌한다.

뉴스는 Tavily(4.5절)로 받는다.

### 4.5 Tavily — `TAVILY_API_KEY` (선택)

- [app.tavily.com](https://app.tavily.com)에서 가입하면 키(`tvly-`로 시작)가 나온다.
- 무료 등급은 월 1,000 크레딧이다. 기본 검색 한 번이 1크레딧이다.
- 한도를 넘으면 HTTP 432(요금제 사용 한도 초과) 또는 433(종량제 한도 초과)을 받는다 ([Tavily 오류 코드](https://help.tavily.com/articles/8645538886-understanding-http-errors)).

### 4.6 Alpha Vantage — `ALPHA_VANTAGE_API_KEY` (선택)

- [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)에서 이메일을 넣으면 무료 키가 나온다.
- 한도는 하루 25건이다. 분석 1회에 최대 4건(지수 추종 ETF 3건, 환율 1건)을 쓰며, 받은 시세는 종목별로 캐시해 다시 요청하지 않는다.
- 키가 없거나 한도에 걸리면 해당 값은 `데이터 없음`과 사유로 LLM에 전달된다. 실패한 결과는 캐시하지 않는다.

### 4.7 키 없이 쓰는 소스

| 소스 | 비고 |
|---|---|
| FinanceDataReader | 종목 시세. 계정이 필요 없다 |
| CoinGecko | 공개 API. 같은 IP 기준 분당 수십 회 수준의 제한이 있다 |
| Paxnet 종목토론 (Selenium) | 기본으로 꺼져 있다. robots.txt는 게시판 경로를 허용하지만(2026-10-27 확인) 이용약관 원문을 확인하지 못했다. 약관을 직접 확인한 뒤 `ENABLE_PAXNET_CRAWL=true`로 켠다. Chrome 또는 Chromium이 필요하다. 꺼져 있으면 커뮤니티 분석은 근거 없음으로 빠진다 |

CNN Fear & Greed 지수는 쓰지 않는다. 공개 API가 아니며, CNN 이용약관이 자동 수집과 AI 입력용 추출을 금지한다.

## 5. 등록 후 확인

```bash
python setup_check.py                  # 키 설정 상태와 에이전트가 쓸 LLM (외부 호출 없음)
python setup_check.py --llm-probe      # LLM tool calling 확인 (요청 1회)
python scripts/check_sources.py        # 소스별 키·요청·데이터·기준 시점 확인
```

`--llm-probe` 결과는 다음과 같이 읽는다.

| 결과 | 뜻 |
|---|---|
| `tool call 수신` | 에이전트를 돌릴 수 있다 |
| `tool call이 없습니다` | 이 모델로는 에이전트를 돌릴 수 없다 |
| 401 | 키가 틀렸다 |
| 404 | 주소나 모델 이름이 틀렸다 |
| 429 | 한도에 걸렸다 |

`scripts/check_sources.py`는 키가 없는 소스에는 요청을 보내지 않는다. Alpha Vantage(하루 25건)와 Paxnet 크롤링은 각각 `--include-alpha-vantage`, `--crawl-paxnet`을 줄 때만 실제로 호출한다. DART, ECOS, FinanceDataReader 시세가 모두 정상일 때만 종료 코드 0을 돌려준다.

## 6. 남은 과제

코드에서 확인했고 아직 해결하지 않은 항목이다.

| 항목 | 위치 | 영향 |
|---|---|---|
| pykrx 로그인 방식에 의존한다 | `KRX_ID`·`KRX_PW` | 공식 허용 경로가 아니다. KRX OPEN API로 옮겨야 한다. 로그인 정보가 없으면 수급·지수·밸류에이션 데이터가 비어 관련 에이전트가 보고서에서 빠진다 |
| 재무제표는 최근 사업보고서(연간)만 쓴다 | `data/dart_api_client.py` | 분기·반기 실적이 반영되지 않는다. 시점에 따라 1년 넘게 지난 수치일 수 있다 |
| 업종·동종업체 매핑이 14개 종목뿐이다 | `agents/korean_comparative_agent.py` | 나머지 종목은 동종업체 비교가 "매핑 없음"으로 나온다 |
| ESG는 DART 공시 제목의 키워드 분류뿐이다 | `agents/korean_esg_analysis_agent.py` | 점수나 등급은 만들지 않는다. 근거가 얇다 |
| 뉴스·수급·커뮤니티 결과에 데이터 시점이 없다 | `data/tavily_api_client.py`(게시일을 받지 않는다), pykrx 기간 합계, Paxnet | 보고서가 언제 기준의 정보인지 밝히기 어렵다 |
| ECOS·Tavily·CoinGecko 응답 형태 검증이 앱 경로에 없다 | `data/external_schemas.py` | 응답 형태가 바뀌면 `scripts/check_sources.py`로만 알아챈다 |
