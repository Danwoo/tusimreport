# TuSimReport - 한국 주식 분석 AI 에이전트 시스템

> ⚠️ **프로젝트 상태: 개발 중** (v2.1 - 2025-11-16)
> 현재 기능 개발 및 안정화 작업 진행 중입니다.

LangGraph Supervisor 아키텍처 기반의 AI 멀티 에이전트 시스템으로, **8개 전문 에이전트**와 **6개 데이터 소스**를 활용한 한국 주식 시장 분석 시스템입니다.

---

## 📊 프로젝트 개요

TuSimReport는 실제 데이터를 우선으로 하는 한국 주식 분석 시스템입니다.

### 핵심 특징
- ✅ **8개 전문 에이전트**: 시장환경, 뉴스, 재무, 기술, 수급, 비교, ESG, 커뮤니티 분석
- ✅ **실제 데이터**: 한국은행, 금감원, 한국거래소, 네이버 뉴스 등 공식 데이터 소스
- ✅ **커뮤니티 분석**: Paxnet 종목토론 크롤링 (v2.1 신규)
- ✅ **No Mock Data**: 실제 API 데이터만 사용 - 샘플/Mock 데이터 절대 금지
- 🆕 **Graceful Degradation**: API 부족 시 명확한 한글 에러 안내 (Phase 3)
- 🆕 **한글 에러 메시지**: 사용자 친화적 한글 오류 안내 (Phase 3)
- 🆕 **API 상태 투명성**: 사이드바에서 실시간 API 키 상태 확인 (Phase 3)

### 현재 상태
| 항목 | 상태 | 비고 |
|------|------|------|
| 아키텍처 설계 | ✅ 완료 | 8개 에이전트, LangGraph Supervisor |
| 데이터 소스 연동 | ⚠️ 부분 완료 | 6개 소스 (API 키 필요) |
| 환경 설정 | ✅ 완료 | .env.example, setup_check.py |
| Graceful Degradation | ✅ 완료 | Phase 3 - 한글 에러, API 상태 |
| 테스트 | ✅ 기본 완료 | Smoke tests, Integration tests |
| 프로덕션 배포 | ❌ 미지원 | Docker 지원 예정 |

---

## 🏗️ 시스템 아키텍처

### 8개 전문 에이전트 (v2.1)

```
tusimreport/
├── agents/                    # 8개 전문 에이전트
│   ├── korean_context_agent.py          # 1. 시장 환경 분석
│   ├── korean_sentiment_agent.py        # 2. 뉴스 여론 분석
│   ├── korean_financial_react_agent.py  # 3. 재무 상태 분석
│   ├── korean_advanced_technical_agent.py # 4. 기술적 분석
│   ├── korean_institutional_trading_agent.py # 5. 기관 수급 분석
│   ├── korean_comparative_agent.py      # 6. 상대 가치 분석
│   ├── korean_esg_analysis_agent.py     # 7. ESG 분석
│   └── korean_community_agent.py        # 8. 커뮤니티 분석 (v2.1)
├── core/                      # 핵심 시스템
│   ├── korean_supervisor_langgraph.py   # LangGraph Supervisor
│   ├── progressive_supervisor.py        # 점진적 분석 엔진
│   └── context_manager.py               # 컨텍스트 관리
├── data/                      # 데이터 클라이언트
│   ├── bok_api_client.py                # 한국은행 API
│   ├── dart_api_client.py               # DART (금감원)
│   ├── naver_api_client.py              # 네이버 뉴스
│   ├── tavily_api_client.py             # Tavily (글로벌 뉴스)
│   ├── paxnet_crawl_client.py           # Paxnet 크롤링 (v2.1)
│   ├── chart_generator.py               # 차트 생성
│   └── sector_analysis_client.py        # 섹터 분석
└── main.py                    # Streamlit UI
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

**마지막 업데이트**: 2025-11-16
**버전**: v2.1 (개발 중)
**Python**: 3.11.14
