# 🚀 새로운 리더를 위한 빠른 시작 가이드

**환영합니다!** 이 문서는 tusimreport 프로젝트를 빠르게 이해하고 시작하는 데 도움을 드립니다.

---

## 📌 첫 30분 체크리스트

### 1. 프로젝트 상태 파악 (5분)

```bash
# 현재 브랜치 확인
git status

# 최근 커밋 확인
git log --oneline -10

# 프로젝트 구조 확인
tree -L 2 -I '__pycache__|*.pyc'
```

**예상 브랜치**: `claude/handover-documentation-01XRU4A4cnQpE3iQ5f8C5TYM`

---

### 2. 주요 문서 읽기 (10분)

읽어야 할 문서 (우선순위 순):

1. **HANDOVER.md** (이 세션의 작업 내용) - **필수 ⭐**
2. **CLAUDE.md** (전체 프로젝트 개요) - **필수 ⭐**
3. **P2_1_B_VERIFICATION_REPORT.md** (최신 기능 검증 보고서)
4. **README.md** (프로젝트 설명)

```bash
# 문서 확인
cat HANDOVER.md | head -100
cat CLAUDE.md | head -100
```

---

### 3. 환경 설정 (10분)

#### Step 1: .env 파일 생성

```bash
# 템플릿 복사
cp .env.example .env

# 편집기로 열기
nano .env  # 또는 vim .env
```

#### Step 2: API 키 설정

**필수 API 키** (없으면 작동 안 함):

| API | 발급 사이트 | 용도 |
|-----|-----------|------|
| **GOOGLE_API_KEY** | https://aistudio.google.com/ | 메인 LLM |
| **OPENAI_API_KEY** | https://platform.openai.com/ | Fallback LLM |
| **NAVER_CLIENT_ID/SECRET** | https://developers.naver.com/ | 한국 뉴스 |
| **TAVILY_API_KEY** | https://tavily.com/ | 글로벌 뉴스 |
| **DART_API_KEY** | https://opendart.fss.or.kr/ | 기업 공시 |
| **ECOS_API_KEY** | https://ecos.bok.or.kr/ | 경제 지표 |

**선택 API 키** (나중에 설정 가능):
- LangSmith (디버깅)
- Notion (문서 연동)

#### Step 3: LLM 선택

**옵션 A: Google Gemini (권장)**
```env
USE_GEMINI=true
GEMINI_MODEL=gemini-2.0-flash-lite
```

**옵션 B: OpenAI**
```env
USE_GEMINI=false
OPENAI_MODEL=gpt-4o
```

---

### 4. 첫 테스트 실행 (5분)

#### 코드 검증 테스트

```bash
# Python 환경 확인
python3 --version  # 3.11.14 권장

# 필수 패키지 설치
pip install -r requirements.txt

# 멀티 쿼리 클라이언트 import 테스트
python3 -c "
from data.multi_query_naver_client import MultiQueryNaverClient
from data.multi_query_tavily_client import MultiQueryTavilyClient
print('✅ Import 성공!')
"
```

**예상 결과**: `✅ Import 성공!`

#### 실제 API 테스트 (HANDOVER.md의 핵심)

```bash
# P2-1-B 테스트 스크립트 실행
python3 test_p2_1_b_option_b.py
```

**예상 결과** (로컬 환경):
```
✅ Naver 뉴스: 30-50개 수집
✅ Tavily 뉴스: 40-50개 수집
✅ 총 수집: 70-90개 (중복 제거 후)
🎯 목표 달성률: 70-90%
```

**실패 시**:
- API 키 확인
- 네트워크 연결 확인
- HANDOVER.md의 "트러블슈팅" 섹션 참조

---

## 🎯 현재 상황 요약

### 프로젝트 버전: v2.2 → v2.3 (진행 중)

**완료된 것** ✅:
- 8개 전문 에이전트 시스템
- LangGraph Supervisor 아키텍처
- 20개 뉴스 분석 (기존)
- **멀티 쿼리 전략 구현 완료** (P2-1-B)

**당신이 할 일** 🔄:
- [ ] **Step 1**: 실제 API 테스트 (위의 4번)
- [ ] **Step 2**: `korean_sentiment_agent.py` 통합
- [ ] **Step 3**: 성능 측정
- [ ] **Step 4**: Git commit & push
- [ ] **Step 5**: `CLAUDE.md` 업데이트

---

## 📊 핵심 기능: P2-1-B (뉴스 커버리지 확장)

### 목표
**20개 → 100개 뉴스 분석** (5배 확장)

### 전략
**Option B: API 멀티 쿼리 전략** (선택된 방법)

### 구현 완료
1. ✅ **MultiQueryNaverClient** (217줄)
   - 5개 다각화 쿼리로 50개 목표

2. ✅ **MultiQueryTavilyClient** (250줄)
   - 5개 카테고리별 쿼리로 50개 목표

3. ✅ **통합 테스트 스크립트**
   - `test_p2_1_b_option_b.py`

### 실제 예상 결과
**70-90개** (중복 10-30% 고려)

### 왜 이 방법인가?
- ✅ 100% 실제 API 사용 (Mock 데이터 없음)
- ✅ 웹 스크래핑 없이 안정적
- ✅ RSS/크롤링은 2025년 현실에서 모두 차단됨 (HANDOVER.md 참조)

---

## 🔧 다음 단계 (상세 가이드)

### Step 2: korean_sentiment_agent.py 통합

**파일**: `agents/korean_sentiment_agent.py`

**수정 위치**: 2곳

#### 수정 1: `_fetch_naver_news()` 함수 (line 70-99)

**Before**:
```python
def _fetch_naver_news(company_name: str) -> Dict[str, Any]:
    # 기존: 단일 쿼리, 10개 수집
```

**After**:
```python
def _fetch_naver_news(company_name: str, stock_code: str) -> Dict[str, Any]:
    """네이버 뉴스 API 멀티 쿼리 수집"""
    from data.multi_query_naver_client import MultiQueryNaverClient

    naver_client = MultiQueryNaverClient(client_id, client_secret)
    news_list = naver_client.fetch_multi_query(
        company_name=company_name,
        stock_code=stock_code,
        target_count=50  # 10개 → 50개
    )
    # ... 형식 변환 코드
```

#### 수정 2: `_fetch_tavily_news()` 함수 (line 102-112)

**Before**:
```python
def _fetch_tavily_news(company_name: str) -> Dict[str, Any]:
    # 기존: 단일 쿼리, 10개 수집
```

**After**:
```python
def _fetch_tavily_news(company_name: str, stock_code: str) -> Dict[str, Any]:
    """Tavily Search API 멀티 쿼리 수집"""
    from data.multi_query_tavily_client import MultiQueryTavilyClient

    tavily_client = MultiQueryTavilyClient(api_key)
    news_list = tavily_client.fetch_multi_query(
        company_name=company_name,
        stock_code=stock_code,
        target_count=50  # 10개 → 50개
    )
    # ... 형식 변환 코드
```

**전체 코드 예시**: HANDOVER.md의 "Step 2" 섹션 참조

---

### Step 3: 성능 측정

```bash
# 통합 후 테스트
python3 -c "
from agents.korean_sentiment_agent import get_enhanced_news_sentiment
result = get_enhanced_news_sentiment.invoke({
    'company_name': '삼성전자',
    'stock_code': '005930'
})
print(f'Naver: {result[\"data_sources\"][\"naver_news_count\"]}개')
print(f'Tavily: {result[\"data_sources\"][\"tavily_news_count\"]}개')
print(f'Total: {result[\"data_sources\"][\"total_analyzed\"]}개')
"
```

**목표**: 70-90개

---

### Step 4: Git Commit & Push

```bash
# 통합 완료 후
git add agents/korean_sentiment_agent.py
git commit -m "feat(P2-1-B): integrate multi-query strategy into sentiment agent

✨ 통합 내용:
- MultiQueryNaverClient: 10→50개
- MultiQueryTavilyClient: 10→50개
- 실제 수집: X개 (측정 결과)

Related: P2-1-B (Stage 3)
"

# 푸시
git push -u origin claude/handover-documentation-01XRU4A4cnQpE3iQ5f8C5TYM
```

---

## 🚨 중요 주의사항

### 1. 절대 금지 ❌
- Mock 데이터 사용
- 하드코딩된 샘플 데이터
- 웹 스크래핑 (2025년 현실: 모두 차단됨)

### 2. 반드시 지킬 것 ✅
- 100% 실제 API 사용
- 데이터 소스 투명성 보장
- Rate limit 준수

### 3. API 할당량 주의 ⚠️
- **Tavily**: 1,000건/월 (무료)
  - 50개/종목 × 20종목 = **한 달 제한**
  - 프리미엄 플랜 검토 필요

---

## 📚 참고 문서

| 문서 | 내용 | 우선순위 |
|-----|------|---------|
| **HANDOVER.md** | 이번 세션 작업 내용 | ⭐⭐⭐ |
| **CLAUDE.md** | 전체 프로젝트 개요 | ⭐⭐⭐ |
| **P2_1_B_VERIFICATION_REPORT.md** | 검증 보고서 | ⭐⭐ |
| **README.md** | 프로젝트 설명 | ⭐ |

---

## 💡 자주 묻는 질문

### Q1: API 키가 없으면 어떻게 되나요?
**A**: 해당 기능이 작동하지 않습니다. 최소한 다음 4개는 필수입니다:
- GOOGLE_API_KEY (또는 OPENAI_API_KEY)
- NAVER_CLIENT_ID/SECRET
- TAVILY_API_KEY
- DART_API_KEY

### Q2: 왜 100개가 아니라 70-90개인가요?
**A**: API 간 중복 제거 때문입니다.
- Naver 50개 중 일부와 Tavily 50개 중 일부가 동일한 뉴스
- 중복률 10-30% 예상
- 실제 측정 후 최적화 가능

### Q3: 속도가 너무 느린데요?
**A**: 현재는 순차 실행입니다.
- 10개 쿼리 × 0.5-1초 대기 = 5-10초
- 향후 병렬 실행으로 개선 가능 (HANDOVER.md의 "Issue 3" 참조)

### Q4: Tavily 할당량이 부족한데요?
**A**: 프리미엄 플랜 검토 또는 Naver만 사용
- Naver 단독: 50개 (기존 대비 5배)
- 프리미엄: $150/월 (무제한)

---

## 🎯 성공 기준

**v2.3 완성**을 위한 체크리스트:

- [ ] 실제 API 테스트 통과 (70-90개)
- [ ] `korean_sentiment_agent.py` 통합 완료
- [ ] 성능 측정 완료
- [ ] Git commit & push
- [ ] `CLAUDE.md` 업데이트 (v2.3)
- [ ] UI에 "70-90개 뉴스 분석" 표시

**완료 시 달성**:
- ✅ 네이버 증권 대비 3.5-4.5배 커버리지
- ✅ "왜 이 서비스를 써야 하는가?"에 대한 명확한 답
- ✅ 더 많은 데이터 = 더 정확한 AI 분석

---

**환영합니다! 프로젝트를 잘 부탁드립니다.** 🚀

궁금한 점이 있으면 HANDOVER.md의 트러블슈팅 섹션을 참조하세요.
