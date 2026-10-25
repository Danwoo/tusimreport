# API 키 발급 안내 (무료 운영 기준)

기준일: 2026-10-25. 각 항목의 근거를 다음과 같이 표기한다.

- **[확인]** 공식 페이지를 직접 열었거나 실제 호출로 확인했다.
- **[실측]** 이 저장소 또는 소유자의 다른 저장소에서 실제로 돌려 본 기록이 있다.
- **[미확인]** 2차 자료이거나 로그인이 필요해 확인하지 못했다. 사용 전에 다시 확인한다.

요금·한도·약관은 자주 바뀐다. 이 문서와 실제 화면이 다르면 실제 화면을 따르고 이 문서를 고친다.

## 1. 요약

| 환경변수 | 구분 | 쓰는 에이전트 | 무료 조건 | 발급 |
|---|---|---|---|---|
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | 필수 | 9개 전부, 최종 보고서, 투자 의견, 대화 | 제공자별 (3절) | 3절 |
| `LLM_MAX_REQUESTS_PER_MINUTE` | 권장 | 모든 LLM 호출 | — | 제공자 한도보다 조금 낮게 |
| `DART_API_KEY` | 필수 | `financial_expert`, `esg_expert` | 무료, 일 20,000건 [확인] | [OpenDART](https://opendart.fss.or.kr) |
| `ECOS_API_KEY` | 필수 | `context_expert`, `financial_expert` | 무료, 공개 한도 없음 [확인] | [ECOS Open API](https://ecos.bok.or.kr/api/) |
| `KRX_ID`, `KRX_PW` | 권장 | `context_expert`, `financial_expert`, `institutional_trading_expert`, `comparative_expert` (pykrx) | 무료 회원가입 [확인] | [KRX 정보데이터시스템](https://data.krx.co.kr/contents/MMC/COMS/client/MMCCOMS002.cmd) |
| `TAVILY_API_KEY` | 선택 | `sentiment_expert` | 월 1,000 크레딧 [확인] | [Tavily](https://app.tavily.com) |
| `ALPHA_VANTAGE_API_KEY` | 선택 | `global_market_expert` | 일 25건 [확인] | [Alpha Vantage](https://www.alphavantage.co/support/#api-key) |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | **발급 보류** | `sentiment_expert` | 4.4절 — 약관상 LLM 입력 금지 | — |
| `TYPESAFE_API_KEY` | 선택 (현재 코드 미사용) | — | 유료, 입력 $0.042/100만 토큰 [확인] | [TypeSafe console](https://console.typesafe.ai/keys) |

키 없이 동작하는 소스: FinanceDataReader, CoinGecko, CNN Fear & Greed(비공식), Paxnet(Chrome 필요). 4.7절 참고.

데이터 키가 없어도 에이전트는 실패하지 않는다. 도구가 오류를 dict로 돌려주고 에이전트는 그 내용을 바탕으로 글을 쓰므로, 키 누락은 "분석이 얇아짐"으로 나타난다. 에이전트를 실패시키는 것은 LLM 설정과 LLM 호출 오류뿐이다.

## 2. 키를 넣는 곳

**Claude Code 클라우드 세션.** 세션 제목 표시줄의 클라우드 환경 메뉴 → Edit → **Network secrets**(없으면 환경 변수)에 위 이름 그대로 넣는다. 새 세션부터 적용된다.

**로컬.** `cp .env.example .env` 후 값을 채운다. `.env`는 gitignore 대상이다.

공통 규칙:

- 키·비밀번호를 채팅, 이슈, 커밋, 로그에 남기지 않는다.
- 넣은 뒤 `python setup_check.py`로 상태를 보고, LLM은 `python setup_check.py --llm-probe`로 tool calling까지 확인한다(실제 호출 1회).
- `KEY=`처럼 빈 값은 미설정으로 취급한다.

## 3. LLM

### 3.1 조건

9개 에이전트가 모두 LangGraph `create_react_agent`라서 **tool calling(function calling)을 지원하는 모델**이어야 한다. 텍스트만 생성하는 모델은 에이전트를 돌리지 못한다. `--llm-probe`가 이 조건을 확인한다.

분석 1회에 LLM 요청이 약 22~30건 나가고, 시작 직후 7개 에이전트가 동시에 요청한다(코드 감사 기준, 실측 전). 무료 등급의 분당 한도가 가장 먼저 걸리는 제약이므로 `LLM_MAX_REQUESTS_PER_MINUTE`로 전체 호출 속도를 한도 아래로 맞춘다. 이 값은 프로세스 전체가 하나의 limiter를 나눠 쓴다.

`LLM_BASE_URL`이 설정돼 있으면 Gemini·OpenAI 설정보다 우선한다. `LLM_MODEL`이나 `LLM_API_KEY`가 비어 있으면 다른(유료일 수 있는) 제공자로 넘어가지 않고 멈춘다.

### 3.2 권장: KiraAI `kira-mini-1.0`

```dotenv
LLM_BASE_URL=https://kiraai.vn/api/v1
LLM_MODEL=kira-mini-1.0
LLM_API_KEY=<KiraAI 키>
LLM_MAX_REQUESTS_PER_MINUTE=25
```

- **무엇인가.** 베트남 회사의 OpenAI 호환 게이트웨이다. 결제는 VND 지갑이다.
- **발급.** [kiraai.vn](https://kiraai.vn)에 가입하고 로그인한 뒤, 메뉴 「Quản lý API key」(API 키 관리)에서 키를 만든다. 키는 만들 때 한 번만 보인다("Bạn sẽ không thể xem lại khóa này") [확인].
- **무료 조건.**
  - 공개 모델 목록 `GET https://kiraai.vn/api/v1/models`에서 `kira-mini-1.0`은 `is_free: true`다 [확인, 2026-10-25].
  - 가입하면 50,000 tokens를 받는다. 단, `kira-` 접두어 모델에만 적용된다 [확인, 요금 페이지].
  - 2026-09-16에 지갑 잔액이 0 VND인 상태에서 `kira-mini-1.0`만 200으로 응답했다 [실측, 이전 시험 기록].
- **tool calling과 한국어.** 한국어 시스템 프롬프트를 주면 한국어로 답했고, `tool_calls`도 규격대로 돌려줬다. 왕복 시간 중앙값은 5.44초였다 [실측, 같은 기록].
  - 시스템 프롬프트 없이 보냈을 때 베트남어로 답한 사례가 있다. tusimreport의 에이전트는 모두 한국어 시스템 프롬프트를 쓴다.
- **한도.**
  - 분당 30회다. 초과하면 429 본문에 "30 yêu cầu/phút"가 온다 [실측, 2026-09-07].
  - 같은 제한을 HTTP 500 "Rate limit exceeded"로 돌려주기도 한다 [실측]. 그래서 25 정도로 낮춰 둔다.
- **다른 무료 모델.** `gpt-oss-120b-free`, `qwen3.8-27b-free`, `deepseek-v4-flash-free`, `nemotron-3.5-lightning-free` 등이 `is_free: true`로 올라와 있다 [확인]. 2026-09에는 429나 402 `pro_membership_required`로 막혔다 [실측]. 쓰기 전에 `--llm-probe`로 확인한다.

### 3.3 대안

| 제공자 | `LLM_BASE_URL` | tool calling 모델 예 | 무료 조건 | 주의 |
|---|---|---|---|---|
| Google AI Studio (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash`, `gemini-3.6-flash` | 무료 등급: 3.8/3.6 Flash, 3.5·3.1 Flash-Lite, 2.5 Pro/Flash/Flash-Lite [확인] | 무료 한도 수치를 공개하지 않는다(AI Studio 화면에서 확인). 키: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Groq | `https://api.groq.com/openai/v1` | `qwen/qwen3.8-27b`, `openai/gpt-oss-120b` | 분당 30회, 분당 8K 토큰, 일 200K 토큰 [확인] | 분당 8K 토큰은 7개 동시 요청에 바로 걸린다. 하루 1~3회 분석 수준으로 추정. 키: [console.groq.com/keys](https://console.groq.com/keys) |
| FPT AI Marketplace (베트남) | `https://mkp-api.fptcloud.com/v1` | `gpt-oss-120b`, `Qwen3.8-27B`, `DeepSeek-V4.1-Flash` | 체험 크레딧(최대 1억 토큰) [확인]. 영구 무료 아님 | 키별 기본 한도 비공개. 가입: [marketplace.fptcloud.com](https://marketplace.fptcloud.com/en) |
| OpenRouter `:free` | `https://openrouter.ai/api/v1` | `google/gemma-4-31b-it:free` 등 | 분당 20회, 일 50회 [확인] | 일 50회는 분석 1~2회 분량. 키: [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| NVIDIA API Catalog | `https://integrate.api.nvidia.com/v1` | 모델별 상이 | 개발용 무료 [확인] | 분당 약 40회라는 보고가 있다 [미확인]. [build.nvidia.com](https://build.nvidia.com) |

Gemini는 `GOOGLE_API_KEY` + `USE_GEMINI=true`의 기존 경로로도 쓸 수 있다. 다만 두 가지를 주의한다.

- `.env.example`의 기본 모델 `gemini-2.0-flash-lite`는 현재 무료 등급 목록에 없다 [확인].
- `langchain_google_genai`는 Gemini 3 이상에서 응답 `content`를 문자열이 아닌 list로 돌려준다. 문자열 처리를 하는 코드가 깨진다(코드 감사).

Gemini 3 이상은 위 표의 OpenAI 호환 주소로 쓰는 편이 안전하다.

### 3.4 Jev (TypeSafe) — 에이전트용 LLM이 아니다

- **무엇인가.** TypeSafe의 "System One" 모델이다(`jev-1.14.0`). 글을 생성하지 않는다. 판단할 자료(`state`)와 정해진 형식의 질문을 보내면, 범주 선택(Choice)·점수(Score)·예/아니오 확률(Noul)과 보정된 확률만 돌려준다 [확인, [docs.typesafe.ai](https://docs.typesafe.ai/models)].
- **API.** `POST https://api.typesafe.ai/v1/systemone`, 헤더 `Authorization: Bearer $TYPESAFE_API_KEY`. OpenAI 호환이 아니므로 `LLM_*`에 넣지 않는다.
- **가격.** 입력 100만 토큰당 $0.042, 출력 무료 [확인]. 공식 문서에서 무료 크레딧은 찾지 못했다.
  - KiraAI에도 `jev-1.14`가 있지만 무료 모델이 아니다(`is_free: false`) [확인].
- **현재 코드에서는 쓰지 않는다.** 활용 후보는 투자 의견 BUY/HOLD/SELL 분류, 보고서 문장과 원자료의 일치 채점, 요청 라우팅·가드레일이다. 도입은 설계 결정 사항이다.

## 4. 데이터 소스

### 4.1 OpenDART — `DART_API_KEY`

1. [opendart.fss.or.kr](https://opendart.fss.or.kr) 상단 「인증키 신청/관리」 → 「인증키 신청」으로 들어간다. 키 신청이 곧 회원가입이다.
2. 약관 두 개에 「동의」한다. 「사용자 구분」은 「개인」을 고른다.
3. 이메일(로그인 ID, 「중복확인」)과 비밀번호를 넣는다. 비밀번호는 영문·숫자·특수문자를 섞어 8~14자다.
4. 「API 사용환경」과 「API 사용용도」(예: 개인 투자 분석)를 적고 「등록」을 누른다.
5. **개인은 즉시 발급된다.** 기업은 승인에 1~2 영업일이 걸린다.
6. 키(40자리)는 로그인 후 「인증키 관리」에서 본다.

근거는 모두 [확인]이다. 한도는 대략 하루 20,000건이고, 초과하면 오류 020이 난다. 개인정보 동의를 2년마다 다시 해야 하며, 하지 않으면 계정이 해지되고 오류 901이 난다 [확인].

### 4.2 한국은행 ECOS — `ECOS_API_KEY`

1. [ecos.bok.or.kr/api](https://ecos.bok.or.kr/api/) → 「OPEN API 인증키 신청」으로 들어간다.
2. **NICE 본인인증**을 거친다. 본인 명의의 한국 휴대폰이 필요하다.
3. 「약관동의」 → 「정보입력」(이메일=로그인 ID, 비밀번호 9자 이상, 이용목적은 「비영리」) → 「신청완료」 순으로 진행한다.
4. 로그인 후 마이페이지 「인증키 현황」에서 키와 상태를 확인한다. 만료일이 있으므로 「인증키 연장」을 챙긴다.

근거는 사이트 코드로 확인한 것이다. 발급 소요 시간은 공개돼 있지 않다 [미확인]. 키 없이 `sample`로 최대 10건까지 시험할 수 있다 [확인].

### 4.3 KRX 정보데이터시스템 — `KRX_ID`, `KRX_PW` (pykrx)

**배경 [확인]**
- data.krx.co.kr은 2025-12-27부터 회원제로 바뀌었다. 밝힌 이유는 AI 봇의 무단 수집이다.
- 로그인하지 않은 요청은 400 `LOGOUT`을 받는다. 그러면 pykrx는 빈 DataFrame을 돌려주거나 `KeyError`를 낸다.
- pykrx 1.2.8 이상은 `KRX_ID`·`KRX_PW`로 로그인한다.

**발급**
1. [회원가입 페이지](https://data.krx.co.kr/contents/MMC/COMS/client/MMCCOMS002.cmd)에서 개인회원으로 가입한다.
2. **아이디·비밀번호 방식**으로 가입한다. pykrx는 ID와 비밀번호로 로그인하므로, 네이버·카카오 간편가입만 한 계정은 쓰지 못할 수 있다 [미확인].

**import 시점 동작 [확인, pykrx 1.2.9 소스]**
- `import pykrx`만 해도 즉시 로그인하고, 로그인 ID를 표준출력에 찍는다.
- 같은 계정으로 이미 로그인돼 있으면(CD011) `skipDup=Y`로 다시 보내 기존 세션을 밀어낸다.
- 브라우저에서 같은 계정을 쓰고 있다면 그 세션이 끊길 수 있다.
- `setup_check.py`는 import 확인 단계에서 이 변수들을 잠시 빼서 로그인하지 않는다.

**약관 [미확인]**
- 로그인한 자동 수집은 실제로는 통하지만, KRX가 공식적으로 허용한 경로는 아니다.
- 공식 키 방식인 [KRX OPEN API](https://openapi.krx.co.kr/contents/OPP/MAIN/main/index.cmd)가 있다. 무료이며, 서비스별 승인에 약 1일이 걸린다는 보고가 있다 [미확인].
- 어느 경로를 쓸지는 결정 사항이다.

### 4.4 Naver 검색 API — 발급 보류

**신규 발급 경로가 바뀌었다 [확인]**
- developers.naver.com의 신규 Search API 신청은 2026-07-30 24:00에 마감됐다.
- 지금은 NAVER Cloud Platform의 [NAVER API HUB](https://www.ncloud.com/product/applicationService/naverApiHub)에서만 받을 수 있다.
- 호출 주소(`naverapihub.apigw.ntruss.com/search/v1/news`)와 인증 헤더(`X-NCP-APIGW-API-KEY-ID`·`X-NCP-APIGW-API-KEY`)도 바뀌었다.
- 현재 코드는 옛 주소(`openapi.naver.com`)와 옛 헤더를 쓰므로 **새 키로는 동작하지 않는다**. 기존 키는 2027-06-30까지 쓸 수 있다.

**약관이 이 프로젝트의 사용 방식과 충돌한다 [확인]**
- 2026-09-07 시행 「NAVER API 서비스 이용약관」 특별 조항이 "데이터를 AI에 입력하거나 학습, 개선, 평가 및 노출 등에 활용하는 행위"를 금지한다.
- 같은 조항은 결과를 기기에 24시간, 서버에 21일 넘게 저장하는 것도 금지한다.
- `sentiment_expert`는 Naver 뉴스를 LLM에 넣어 감성 분석을 하므로 이 조항에 걸린다.

**결정 전까지 발급하지 않는다.** 대안은 Tavily(4.5절)와 언론사 RSS 등이다. 어느 쪽으로 갈지는 결정 사항이다.

### 4.5 Tavily — `TAVILY_API_KEY` (선택)

- [app.tavily.com](https://app.tavily.com)에서 가입하면 키(`tvly-...`)가 나온다.
- 무료 등급은 월 1,000 크레딧이다. 기본 검색이 1크레딧이고, 개발 키는 분당 100회다 [확인].
- Tavily에는 키 없는 모드도 있지만, 이 저장소의 클라이언트는 키가 없으면 요청을 보내지 않는다.

### 4.6 Alpha Vantage — `ALPHA_VANTAGE_API_KEY` (선택)

- [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)에서 사용자 유형과 이메일을 넣으면 무료 키가 나온다.
- 한도는 **하루 25건**이다 [확인]. 캐시가 없으면 분석 1회에 4건을 쓰고, 캐시는 1시간 유지된다.
- 키가 없으면 USD/KRW가 1320.0으로 하드코딩된 채 LLM에 들어간다(`data/alpha_vantage_client.py:171`, 6절).

### 4.7 키 없이 쓰는 소스

| 소스 | 상태 |
|---|---|
| FinanceDataReader | 0.9.110부터 KRX 데이터를 GitHub 캐시 저장소에서 받는다. 계정이 필요 없다 [확인, 2026-10-25 실호출] |
| CoinGecko | 키 없는 공개 API가 동작한다. 같은 IP 기준 분당 약 10~30회다 [확인] |
| CNN Fear & Greed | 공개 API가 아닌 내부 JSON이다. 브라우저가 아닌 클라이언트에 418을 돌려준다 [확인]. 실패하면 점수 50 "Neutral"이 들어간다(6절) |
| Paxnet (Selenium) | Chrome·Chromium이 PATH에 있어야 한다. 클라우드 세션 컨테이너에는 PATH에 없으므로 커뮤니티 데이터는 비어 있다 |

## 5. 등록 후 확인

```bash
python setup_check.py              # 키 상태, 에이전트가 쓸 LLM (호출 없음)
python setup_check.py --llm-probe  # tool calling 실제 호출 1회
```

`--llm-probe`의 결과는 다음과 같이 읽는다.

| 결과 | 뜻 |
|---|---|
| `✅ tool call 수신` | 에이전트를 돌릴 수 있다 |
| `tool call이 없습니다` | 이 모델로는 에이전트를 돌릴 수 없다 |
| 401 | 키가 틀렸다 |
| 404 | 주소나 모델 이름이 틀렸다 |
| 429 | 한도에 걸렸다 |

## 6. 알려진 문제 (다음 단계에서 다룬다)

코드에서 확인했고, 실데이터로 재현하기 전인 항목이다.

| 항목 | 위치 | 영향 |
|---|---|---|
| 최종 보고서는 9개 에이전트가 모두 성공해야 생성된다 | `core/progressive_supervisor.py:365` | 무료 등급에서 429가 하나만 나도 보고서가 없다 |
| 실패 시 기본값이 실제 값처럼 LLM에 들어간다 | `data/alpha_vantage_client.py:171`, `data/fear_greed_client.py` | USD/KRW 1320, F&G 50. 저장소 원칙("No mock data")과 충돌 |
| 키가 URL에 실려 요청 실패 시 로그에 남을 수 있다 | `data/bok_api_client.py:48` (ECOS 경로), DART `crtfc_key` 쿼리 | 로그 공유 시 키 노출 |
| ESG 도구가 DART 응답에 없는 키를 읽는다 | `agents/korean_esg_analysis_agent.py:44-62` | ESG 입력이 항상 비어 있다 |
| 업종 매핑 하드코딩과 오류 | `agents/korean_comparative_agent.py:33-48`, `:51`, `:166` | 14개 종목만 매핑되고, 그중 4개(셀트리온·LG에너지솔루션·기아·기업은행)의 업종이 틀렸다. `get_market_fundamental(today)` 결과(KOSPI만)에 없는 종목은 `peer_codes`가 정의되지 않아 `UnboundLocalError` 후 fallback으로 끝난다. KOSDAQ 종목과, KRX 로그인이 없어 결과가 빈 경우가 여기에 해당한다 |
| `save_stock_chart`에서 `chart_data`를 주면 `df`가 정의되지 않는다 | `agents/korean_financial_react_agent.py:194-203` | `NameError` |
