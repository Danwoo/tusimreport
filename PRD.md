
### 📊 한국 주식 분석 AI 에이전트 - PRD (Product Requirements Document)

**프로젝트 상태**: 🔄 **한국 주식 시장 대응 개발 중** (2025-08-27)

-----

### 📌 개요

**목적**

  - **한국 주식 시장(KRX, KOSPI, KOSDAQ)**의 재무 데이터와 뉴스 데이터를 **실시간**으로 수집 및 통합 분석합니다.
  - 특정 종목에 대한 **한국어 AI 분석 보고서**를 **자동으로 생성**하고, **상세 텍스트 보고서**를 즉시 표시합니다.
  - 복잡한 인프라 없이 **멀티 에이전트 시스템**과 **사용자 친화적인 한국어 인터페이스**에 집중합니다.

-----

### 🔄 한국 주식 시장 대응 핵심 기능

1.  **한국어 사용자 인터페이스**: Streamlit 기반 실시간 반응형 웹 UI
    - **한국 종목코드** 입력 및 분석 실행 (예: 005930-삼성전자, 035720-카카오)
    - 실시간 분석 진행상황 표시 (진행바, 한국어 상태 메시지)
    - **한국 주식 API** 연결 상태 모니터링
    - **한국어 상세 텍스트 분석 보고서** 자동 표시

2.  **LangGraph 기반 멀티 에이전트 시스템 (한국 주식 특화)**: 
    - **Supervisor Agent**: 전체 워크플로우 조율
    - **Korean Financial Agent**: 한국투자증권 KIS API + FinanceDataReader + PyKRX 통합
    - **KRX Data Agent**: 한국거래소 공식 데이터 수집
    - **Korean Sentiment Agent**: 네이버금융 뉴스 크롤링 + OpenAI GPT-4 한국어 감정 분석
    - **Korean Report Agent**: 한국어 종합 텍스트 보고서 자동 생성

3.  **한국 주식 데이터 수집 및 분석**:
    - **주가 데이터**: 한국투자증권 KIS API (실시간) + FinanceDataReader/PyKRX (히스토리)
    - **재무제표 데이터**: OpenDART API (손익계산서, 대차대조표, 현금흐름표) + 공공데이터포털 기업재무정보 🆕
    - **재무 지표**: PER, PBR, ROE, 매출액, 영업이익, 총자산, 부채비율, 자기자본이익률
    - **재무비율 분석**: 유동비율, 당좌비율, 부채비율, 총자산회전율, 매출액증가율 🆕
    - **기술적 분석**: 이동평균, RSI, MACD, 볼린저밴드
    - **한국어 뉴스 감정 분석**: 네이버금융/다음금융 뉴스 + GPT-4 한국어 처리

4.  **한국어 종합 분석 보고서 생성**:
    - **한국어 텍스트 보고서**: 기업 개요, 재무 분석, 시장 감정, 투자 의견
    - **한국 주식 시장 맞춤 분석**: 외국인/기관 투자자 동향, 업종 비교
    - **Notion 연동** (선택적): 한국어 보고서를 Notion 페이지로 저장
    - **차트 및 시각화**: Plotly 기반 한국어 라벨 차트

-----

### ⚙️ 한국 주식 특화 기술 스택 (Plan A - 이상적 구현)

  - **LLM**: OpenAI GPT-4o via LangGraph (한국어 처리 최적화)
  - **멀티 에이전트**: LangGraph StateGraph 기반 워크플로우 (4개 에이전트, 각 3개 Tool)
  - **프레임워크**: Streamlit (한국어 실시간 반응형 UI)
  - **한국 주식 데이터 소스**:
    - **한국투자증권 KIS OpenAPI** (실시간 주가, 호가, 체결)
    - **FinanceDataReader** (KRX 히스토리컬 데이터)
    - **PyKRX** (한국거래소 스크래핑 데이터)
    - **KRX OpenAPI** (공식 거래소 데이터)
    - **OpenDART API** (금융감독원 공식 재무제표) 🆕
    - **공공데이터포털** (금융위원회 기업재무정보) 🆕
  - **한국 뉴스 소스**:
    - **네이버금융 크롤링** (BeautifulSoup, requests)
    - **다음금융 크롤링** (종목별 뉴스)
  - **보고서 출력**: 한국어 실시간 텍스트 보고서 + Notion API (선택적)
  - **시각화**: matplotlib (한국어 라벨 차트, PNG 로컬 저장) 🆕
  - **개발환경**: Python 3.12+, pydantic, numpy
  - **한국어 처리**: OpenAI GPT-4 한국어 감정분석, 한국 주식 시장 도메인 지식

-----

### 🧩 한국 주식 특화 LangGraph Tool 설계 (Plan A)

한국 주식 시장에 최적화된 멀티 에이전트 시스템으로, 각 에이전트는 최대 3개의 Tool을 보유합니다.

```
사용자 (한국 종목코드 입력)
│
▼
Streamlit App (한국어 UI)
│
▼
LangGraph Supervisor Agent
│
├── Korean Financial Agent (3 Tools)
│   ├── @tool get_kis_stock_data    → KIS OpenAPI (실시간)
│   ├── @tool get_fdr_data          → FinanceDataReader (히스토리)
│   └── @tool get_pykrx_data        → PyKRX (KRX 스크래핑)
│
├── KRX Data Agent (3 Tools)
│   ├── @tool get_krx_market_data   → KRX OpenAPI (시장 데이터)
│   ├── @tool get_investor_data     → KRX 투자자별 매매 동향
│   └── @tool get_sector_data       → KRX 업종별 데이터
│
├── Korean Financial Statement Agent (3 Tools)
│   ├── @tool get_dart_statements   → OpenDART (재무제표)
│   ├── @tool get_financial_ratios  → 공공데이터포털 (재무비율)
│   └── @tool calculate_ratios      → 로컬 재무비율 계산
│
└── Korean Sentiment Agent (3 Tools)
    ├── @tool crawl_naver_news      → 네이버금융 뉴스
    ├── @tool crawl_daum_news       → 다음금융 뉴스
    └── @tool save_chart_image      → matplotlib 차트 저장
```

**Tool vs LLM 역할 분리**:
- **@tool 함수**: 순수 데이터 수집 및 저장만 담당
- **LLM Agent**: 모든 분석, 해석, 보고서 생성 담당

### 🔄 한국 주식 분석 워크플로우

  - **한국어 Streamlit App**: 한국 종목코드 입력 받고, 분석 과정을 한국어로 표시
  - **LangGraph Supervisor**: 한국 주식 시장 특화 워크플로우 조율
  - **Korean Financial Agent**: KIS API, FinanceDataReader, PyKRX 통합 데이터 수집
  - **KRX Data Agent**: 한국거래소 공식 API로 거래량, 외국인 투자 동향 수집
  - **Korean Sentiment Agent**: 네이버/다음 금융뉴스 크롤링 후 GPT-4 한국어 감정분석
  - **Korean Report Agent**: 모든 분석을 통합하여 한국어 투자 보고서 생성

-----

### 🔄 한국 주식 분석 동작 흐름

1.  **사용자**: Streamlit 웹페이지에 **한국 종목코드** 입력 (예: 005930, 035720) 후 '분석 시작'
2.  **한국어 Streamlit App**: 입력된 종목코드를 LangGraph Supervisor Agent에게 전달
3.  **LangGraph Supervisor**: 한국 주식 특화 워크플로우 시작
4.  **Korean Financial Agent**: KIS API + FinanceDataReader + PyKRX로 재무 데이터 수집
5.  **KRX Data Agent**: 한국거래소 공식 API로 외국인/기관 투자 동향 수집
6.  **Korean Sentiment Agent**: 네이버/다음금융 뉴스 크롤링 → GPT-4 한국어 감정분석
7.  **Korean Report Agent**: 모든 분석 결과를 통합하여 한국어 투자 보고서 생성
8.  **한국어 Streamlit App**: 상세 한국어 분석 보고서를 사용자에게 실시간 표시

-----

### 🔐 주요 고려사항

  - **Streamlit 성능**: Streamlit은 기본적으로 단일 스레드 구조이므로, **비동기 처리**가 필요한 복잡한 작업에는 한계가 있습니다. 그러나 이 프로젝트의 규모에서는 충분히 효율적으로 작동할 수 있습니다.
  - **사용자 경험**: 분석 시간이 3\~5분 소요될 수 있으므로, Streamlit의 **진행 표시줄**이나 상태 메시지를 활용하여 사용자에게 현재 진행 상황을 알려주는 것이 중요합니다.
  - **Notion 템플릿**: Notion에 보고서 차트나 표를 넣을 수 있는 템플릿을 미리 만들어두고, API를 통해 데이터를 동적으로 채우는 방식을 사용합니다.

-----

### 📦 파일 및 디렉터리 구조

Streamlit 기반으로 변경하여 파일 구조를 간결하게 정리했습니다. `main.py`가 Streamlit 앱의 진입점이 됩니다.

```
stock-ai-agent/
├── main.py                # Streamlit 앱 실행 및 UI 정의
├── agents/
│   ├── orchestrator.py    # 전체 흐름을 제어하는 메인 에이전트
│   ├── financial.py       # 재무 분석 담당 에이전트
│   ├── sentiment.py       # 감정 분석 담당 에이전트
│   └── report.py          # 보고서 생성 및 발행 담당 에이전트
├── notion/
│   └── publisher.py       # Notion API 호출 관련 로직
├── tools/
│   └── data_fetcher.py    # 외부 API 호출 로직을 캡슐화한 툴
└── config/
    └── settings.py        # API 키 등 환경 설정
```