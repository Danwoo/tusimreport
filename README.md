# 📊 TuSimReport - 한국 주식 분석 AI 시스템

**v3.0 - 프로덕션 완성 버전**

LangGraph Supervisor 기반의 전문급 AI 멀티 에이전트 시스템으로, 8개 전문 에이전트와 6개의 검증된 실시간 데이터 소스를 활용한 종합 한국 주식 시장 분석 시스템입니다.

---

## ✨ 주요 특징

- **8개 전문 에이전트**: 시장환경, 뉴스여론, 재무, 기술적분석, 기관수급, 상대가치, ESG, 커뮤니티
- **Supervisor 대화형 시스템**: 복잡한 질문을 여러 에이전트가 협력하여 처리
- **SQLite 영구 저장**: 모든 분석 보고서 및 대화 히스토리 자동 저장
- **멀티턴 대화**: 스트리밍 출력 지원 (ChatGPT 스타일)
- **실제 데이터 100%**: Mock 데이터 제로, 투명한 뉴스 소스 공개
- **한국 시장 특화**: 한국 투자자를 위한 맞춤 설계

---

## 🚀 빠른 시작

### 필수 요구사항
- Python 3.10+
- Conda 환경

### 설치 및 실행
```bash
# 1. Conda 환경 생성
conda create -n tusimreport python=3.11
conda activate tusimreport

# 2. 의존성 설치
pip install -r requirements.txt

# 3. .env 파일 생성 (API 키 설정)
# 샘플:
# GOOGLE_API_KEY=your_key
# DART_API_KEY=your_key
# ECOS_API_KEY=your_key
# NAVER_CLIENT_ID=your_id
# NAVER_CLIENT_SECRET=your_secret

# 4. 실행
streamlit run main.py
```

---

## 🤖 시스템 아키텍처

### 8개 전문 에이전트

| 에이전트 | 역할 | 데이터 소스 |
|----------|------|-------------|
| **Context Expert** | 시장 환경 분석 | FinanceDataReader, PyKRX, BOK ECOS |
| **Sentiment Expert** | 뉴스 여론 분석 | Naver News, Tavily Search |
| **Financial Expert** | 재무 상태 분석 | DART, PyKRX, FinanceDataReader |
| **Technical Expert** | 기술적 분석 | FinanceDataReader, PyKRX |
| **Institutional Expert** | 기관 수급 분석 | PyKRX |
| **Comparative Expert** | 상대 가치 분석 | FinanceDataReader, PyKRX |
| **ESG Expert** | ESG 분석 | DART |
| **Community Expert** | 커뮤니티 여론 분석 | Paxnet 크롤링 |

### Supervisor 시스템
- 8개 에이전트 조율 및 통합
- 대화형 질문 처리 (1-3개 에이전트 자동 선택)
- 복잡한 비교 분석 (예: "기아차와 비교하면?")
- 실시간 최신 데이터 재수집

---

## 💾 주요 기능

### 1️⃣ 종목 분석
- 8개 에이전트가 순차/병렬로 분석
- 차트 + 8개 개별 보고서 + 종합 보고서
- 실시간 진행 상황 표시

### 2️⃣ 대화형 Q&A
- **복잡한 질문**: Supervisor가 여러 에이전트 조율
  - "기아차와 비교하면?" → comparative + financial + technical
- **간단한 질문**: 기존 보고서에서 빠른 답변
- **멀티턴 대화**: 무제한 질문 가능
- **스트리밍 출력**: ChatGPT처럼 실시간 텍스트

### 3️⃣ 영구 저장 (SQLite)
- 모든 분석 보고서 자동 저장
- 대화 히스토리 자동 저장
- 사이드바에서 이전 보고서 조회
- 브라우저 닫아도 데이터 유지

---

## 📊 데이터 소스

### 실제 데이터 API (6개)
- **FinanceDataReader** - 한국 주가 데이터
- **PyKRX** - 한국거래소 공식 데이터
- **BOK ECOS API** - 한국은행 경제통계
- **DART API** - 금융감독원 기업공시
- **Naver News API** - 네이버 뉴스
- **Paxnet** - 커뮤니티 크롤링

### LLM
- **Google Gemini 2.0 Flash Lite** - 메인
- **OpenAI GPT-4o** - Fallback

---

## 📁 프로젝트 구조

```
tusimreport/
├── agents/           # 8개 전문 에이전트
├── core/             # Supervisor + 대화형 관리
├── data/             # 데이터 클라이언트 + SQLite
├── config/           # 환경 설정
├── utils/            # 유틸리티
├── main.py           # Streamlit UI
├── tusimreport.db    # SQLite DB
└── requirements.txt  # 의존성
```

상세 구조는 [CLAUDE.md](./CLAUDE.md) 참조

---

## 🎯 사용 예시

### 종목 분석
```
1. 종목 선택 (예: 삼성전자 005930)
2. 분석 방법 선택 (순차/병렬)
3. 8개 에이전트 분석 실행
4. 보고서 확인
```

### 대화형 질문
```
Q: "기아차와 비교하면 투자 가치는?"
→ Supervisor가 3개 에이전트 동원하여 심층 비교 분석

Q: "현재 주가는?"
→ 보고서에서 빠른 답변
```

---

## 🔒 보안 및 원칙

### 실제 데이터 우선 정책
- ❌ Mock 데이터 완전 금지
- ✅ 100% 실제 API 사용
- ✅ 뉴스 소스 완전 투명 공개

### 보안
- API 키는 `.env` 파일로 관리
- 민감 정보 로깅 방지
- HTTPS 통신만 사용

---

## 📝 라이센스

이 프로젝트는 개인 연구/학습 목적으로 제작되었습니다.

---

## 📖 문서

- 상세 문서: [CLAUDE.md](./CLAUDE.md)
- 프로젝트 구조, Supervisor 시스템, SQLite DB 등 전체 정보 포함

---

**TuSimReport** - 한국 주식 분석을 위한 프로덕션 완성 AI 시스템
