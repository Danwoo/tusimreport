# TuSimReport

한국 주식 한 종목을 9개 전문 에이전트가 나눠 분석하고, 근거 데이터가 확인된 분석만으로 종합 보고서와 투자 의견을 만드는 멀티 에이전트 시스템이다. Streamlit 앱으로 실행하며, 같은 작업을 서로 다른 오케스트레이션 구조로 돌려 비교하는 실험 도구를 함께 둔다.

개인 연구용 도구다. 투자 권유가 아니며 실주문 기능은 없다.

## 하는 일

1. 종목 코드를 입력하면 9개 에이전트가 각자의 도구로 데이터를 받아 분석한다.
2. 에이전트마다 "실행이 끝났는가"와 "근거 데이터가 있었는가"를 따로 판정한다.
3. 근거 데이터가 있는 에이전트가 9개 중 5개 이상이면, 그 분석만 모아 종합 보고서를 쓴다. 빠진 영역은 보고서와 화면에 이유와 함께 표시한다.
4. 보고서를 바탕으로 BUY/HOLD/SELL 의견을 만들고, 분석 결과를 맥락으로 후속 질문에 답한다.

| 에이전트 | 분석 영역 | 주요 데이터 |
|---|---|---|
| `context_expert` | 시장 환경, 거시 지표 | 한국은행 ECOS, pykrx, FinanceDataReader |
| `sentiment_expert` | 뉴스 여론 | Tavily |
| `financial_expert` | 재무제표, 밸류에이션 | OpenDART, 한국은행 ECOS, pykrx, FinanceDataReader |
| `advanced_technical_expert` | 기술적 지표 | FinanceDataReader |
| `institutional_trading_expert` | 투자자별 매매 동향 | pykrx |
| `comparative_expert` | 동종업체 비교 | pykrx, FinanceDataReader |
| `esg_expert` | 공시 기반 ESG 단서 | OpenDART |
| `community_expert` | 종목토론 게시판 | Paxnet (Selenium, 기본 꺼짐) |
| `global_market_expert` | 미국 증시, 환율, 암호화폐 | Alpha Vantage, CoinGecko |

## 설계에서 다룬 문제

**근거 없는 분석이 보고서에 섞이는 문제.** 에이전트는 도구가 실패해도 오류 메시지를 바탕으로 그럴듯한 글을 쓴다. 그래서 응답이 돌아왔다는 사실만으로는 분석에 근거가 있었는지 알 수 없다. `core/agent_status.py`는 각 에이전트가 받은 도구 결과(ToolMessage)를 읽어 근거 데이터 유무를 판정한다. 보고서는 근거가 있는 에이전트만으로, 과반이 넘을 때만 만든다. 에이전트 하나가 예외로 끝나도 전체 분석은 멈추지 않고 해당 카드만 실패로 표시한다.

**데이터 소스가 실패했을 때 그럴듯한 숫자로 채우는 문제.** 외부 API가 실패하면 클라이언트는 기본값 대신 `None`과 한국어 사유를 돌려주고, 실패한 결과는 캐시하지 않는다. 도구는 데이터만 돌려주고 해석은 에이전트의 LLM이 한다. 도구 안에서 LLM을 다시 부르면 그 출력이 원천 데이터처럼 보이기 때문이다.

**오케스트레이션 구조의 효과를 재는 문제.** 9개로 나눈 구조가 도구를 모두 가진 단일 에이전트보다 나은지, 나은 만큼 무엇을 더 쓰는지를 같은 도구, 같은 데이터 스냅샷, 같은 보고서 형식 위에서 비교한다. 비교 대상은 단일 에이전트, 코드가 실행 순서를 정하는 구조(병렬 7개 후 순차 2개), LLM supervisor가 handoff로 일을 넘기는 구조다. 방법과 지표는 [docs/EXPERIMENTS.md](./docs/EXPERIMENTS.md)에 있다. 측정 결과는 아직 없다.

**외부 API의 실패 모드.** HTTP 상태와 응답 형태에 따라 실패를 타입별 예외(`core/errors.py`)로 나눈다. 일시적 실패는 지수 백오프로 재시도한다. 거래일 계산은 한국 시간 기준으로 한다. 로그와 도구 출력에서는 API 키를 가린다. `scripts/check_sources.py`는 소스마다 키, 요청, 데이터, 기준 시점을 따로 점검한다.

**무료 LLM으로 운용하는 문제.** OpenAI 호환 엔드포인트라면 어떤 제공자든 `LLM_BASE_URL`로 연결한다. 무료 등급의 분당 요청 한도에 맞춰 프로세스 전체가 하나의 요청 제한기를 함께 쓴다. 모델이 tool calling을 지원하는지는 `python setup_check.py --llm-probe`로 실제 요청 한 번을 보내 확인한다.

## 구조

```text
사용자 입력 (Streamlit)
  └─ ProgressiveAnalysisEngine
       ├─ 병렬 7개: context, sentiment, technical, institutional, esg, community, global_market
       ├─ 순차 2개: financial, comparative (병렬 결과 요약을 참고 정보로 받는다)
       ├─ 근거 판정: 에이전트별 status / data_status
       └─ 종합 보고서 (근거 있는 분석 5/9 이상일 때)
            └─ 투자 의견 (BUY/HOLD/SELL) → 후속 대화
```

```text
agents/    9개 전문 에이전트와 투자 의견 생성
core/      실행 엔진, supervisor, 근거 판정, 실행 계측, 오류 타입, 대화 세션
config/    설정(pydantic-settings), LLM 생성
data/      외부 API 클라이언트, 공통 HTTP·캐시 베이스, 응답 스키마 검증
lab/       오케스트레이션 비교 실험 (도구 등록, 스냅샷 기록·재생, 숫자 근거 대조)
scripts/   run_experiment.py, check_sources.py
ui/        카드, 스타일, 종목 목록
utils/     한국 시간 도우미, 로깅, 키 가리기
tests/     단위·통합 테스트 (외부 호출 없음)
```

## 시작하기

Python 3.11 이상이 필요하다. 커뮤니티 분석(Paxnet 크롤링)은 이용약관을 확인하지 못해 기본으로 꺼 두었다. 켜려면 `ENABLE_PAXNET_CRAWL=true`와 Chrome 또는 Chromium이 필요하다.

```bash
git clone https://github.com/Danwoo/tusimreport.git
cd tusimreport
pip install -r requirements.txt
cp .env.example .env    # 키 입력
```

필수 키는 LLM 설정, `DART_API_KEY`, `ECOS_API_KEY`다. 모두 무료로 받을 수 있다. 발급 절차, 무료 한도, 키가 없을 때 빠지는 분석은 [docs/API_KEYS.md](./docs/API_KEYS.md)에 정리했다.

```bash
python setup_check.py                  # 키 설정 상태 (외부 호출 없음)
python setup_check.py --llm-probe      # LLM tool calling 확인 (요청 1회)
python scripts/check_sources.py        # 데이터 소스별 연결 상태
streamlit run main.py                  # http://localhost:8501
```

Dockerfile과 `docker-compose.yml`도 있다. 이미지에 Chromium과 CJK 폰트를 넣도록 구성했지만, 컨테이너 실행까지 검증하지는 않았다.

```bash
docker compose up --build
```

## 구조 비교 실험

```bash
# 실데이터로 한 번 돌려 도구 결과를 스냅샷으로 남긴다
python scripts/run_experiment.py --stocks 005930:삼성전자 --topologies progressive --snapshot-mode record

# 같은 스냅샷으로 세 구조를 비교한다 (데이터 API는 호출하지 않고 LLM만 호출한다)
python scripts/run_experiment.py --stocks 005930:삼성전자 --snapshot-mode replay --repeats 3
```

실행마다 성공 여부, 경과 시간, LLM 호출 수와 토큰, 도구 호출 수, 근거 데이터가 있는 영역 수, 보고서 숫자의 근거 일치율을 기록한다. 스냅샷과 실행 결과에는 외부 소스의 원자료가 들어 있어 `.gitignore` 대상이다.

## 테스트와 품질 기준

```bash
pip install -r requirements.lock -r requirements-dev.lock   # CI와 같은 고정 버전 (= make install)
pytest
```

테스트는 외부 API를 호출하지 않는다. HTTP는 `responses`로 대체하고, 에이전트 그래프 통합 테스트는 정해진 순서로 도구를 부르는 가짜 LLM을 쓴다. CI(GitHub Actions)는 Python 3.11과 3.12에서 lock 파일로 설치한 뒤 다음을 확인한다. Docker 이미지와 같은 `requirements.txt` 설치도 3.11에서 한 번 더 돌린다.

- ruff lint와 포맷
- 핵심 8개 모듈의 mypy 타입 검사 (타입 표기 없는 함수 금지, `Any` 반환 경고)
- 커버리지 45% 이상의 pytest
- gitleaks 시크릿 검사
- pip-audit 의존성 감사(실패해도 빌드를 막지 않는다)

## 한계

- 실데이터와 실제 LLM으로 측정한 결과가 아직 없다.
- 투자 의견의 신뢰도, 목표가, 손절가는 LLM이 쓴 값이다. 과거 수익률로 검증한 예측이 아니다.
- 지수·수급·밸류에이션 데이터는 pykrx를 통해 KRX에 로그인해서 받는다. KRX가 공식으로 허용한 경로는 KRX OPEN API이며, 이 경로로 옮기는 작업이 남아 있다.
- 데이터 소스별 남은 과제는 [docs/API_KEYS.md 6절](./docs/API_KEYS.md#6-남은-과제)에 있다.

## 문서

- [docs/API_KEYS.md](./docs/API_KEYS.md): API 키 발급과 무료 한도
- [docs/EXPERIMENTS.md](./docs/EXPERIMENTS.md): 구조 비교 실험의 방법과 지표
- [docs/PROJECT_PLAN.md](./docs/PROJECT_PLAN.md): 개발 계획과 진행 상황
- [SECURITY.md](./SECURITY.md): 보안 관련 안내
- [CLAUDE.md](./CLAUDE.md): 코딩 에이전트용 저장소 안내

## 라이선스

[MIT](./LICENSE)

이 소프트웨어가 내놓는 분석과 의견은 참고 자료이며 투자 권유가 아니다. 투자 판단과 그 결과는 사용자에게 있다.
