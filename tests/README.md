# TuSimReport 테스트 스위트

Streamlit UI 없이 대화형 서비스를 테스트하고 검증하는 CLI 기반 테스트 시스템

---

## 📁 테스트 파일 구조

```
tests/
├── README.md                        # 테스트 가이드 (본 파일)
├── test_conversation_cli.py         # 메인 CLI 대화형 테스트
├── test_supervisor_unit.py          # pytest 단위 테스트
└── verify_agent_selection.py        # 에이전트 선택 검증
```

---

## 🚀 빠른 시작

### 1. CLI 대화형 테스트 (권장)

```bash
# tusimreport 디렉토리에서 실행
python tests/test_conversation_cli.py
```

**특징:**
- 실제 대화처럼 질문-답변 반복
- 멀티턴 대화 테스트 (대화 맥락 유지 확인)
- 에이전트 선택 로그 실시간 출력
- 3가지 모드 제공

**모드 선택:**
1. **자동 테스트** - 미리 정의된 시나리오 실행
2. **대화형 모드** - 직접 질문 입력
3. **모든 테스트** - 전체 시나리오 자동 실행

---

### 2. pytest 단위 테스트

```bash
# pytest 설치 (필요시)
pip install pytest

# 단위 테스트 실행
pytest tests/test_supervisor_unit.py -v
```

**테스트 항목:**
- ✅ 단일 질문 (대화 히스토리 없음)
- ✅ 멀티턴 대화 (대화 히스토리 포함)
- ✅ 하드코딩 함수 제거 확인
- ✅ 에러 처리
- ✅ 답변 품질 기본 검증

---

### 3. 에이전트 선택 검증

```bash
python tests/verify_agent_selection.py
```

**특징:**
- 질문 유형별 에이전트 선택 패턴 분석
- 예상 에이전트 vs 실제 선택 비교
- 불필요한 에이전트 호출 감지

**테스트 케이스:**
- 단순 정보 조회 (예: "주가는?")
- 재무 분석 (예: "재무 상태는?")
- 비교 분석 (예: "SK하이닉스와 비교하면?")
- 투자 판단 (예: "지금 매수해도 될까?")
- 뉴스 분석, 기술적 분석, 수급 분석 등

---

## 📊 테스트 시나리오

### 시나리오 1: 멀티턴 대화 (대화 맥락 유지)

```
Turn 1: "삼성전자 주가가 어떤가요?"
→ 답변: 삼성전자 주가 정보 제공

Turn 2: "그럼 SK하이닉스와 비교하면 어떤가요?"
→ 답변: 삼성전자와 SK하이닉스 비교 (이전 대화 맥락 참조)

Turn 3: "지금 매수해도 될까요?"
→ 답변: 투자 판단 (앞선 분석 내용 활용)
```

**검증 포인트:**
- ✅ 대화 히스토리가 제대로 전달되는지
- ✅ 이전 대화 맥락을 참조하는지
- ✅ "그럼", "그게" 등의 대명사 처리

---

### 시나리오 2: 에이전트 선택 (하드코딩 제거 확인)

```
질문: "주가는?"
예상 에이전트: financial_expert만
검증: 불필요한 에이전트 호출 없음

질문: "기아차와 비교하면?"
예상 에이전트: comparative + financial + technical
검증: 3개 에이전트가 선택되는지

질문: "최근 뉴스는?"
예상 에이전트: sentiment + community
검증: 뉴스 관련 에이전트만 선택
```

**검증 포인트:**
- ✅ Supervisor가 질문에 맞는 에이전트만 선택
- ✅ 하드코딩 키워드 매칭 함수 호출 안 됨
- ✅ 과도한 에이전트 호출 방지

---

## 🧪 테스트 체크리스트

### Phase 1: 기본 기능
- [ ] CLI 스크립트 실행 가능
- [ ] 단일 질문 답변 생성
- [ ] 에러 없이 완료

### Phase 2: 멀티턴 대화
- [ ] 2턴 대화: "삼성전자" → "그럼 기아차는?"
- [ ] 3턴 대화: 질문1 → 질문2 → 질문3
- [ ] 대화 맥락 유지 (이전 대화 참조)

### Phase 3: 에이전트 선택
- [ ] "주가는?" → financial만
- [ ] "비교하면?" → comparative + financial + technical
- [ ] "최근 뉴스는?" → sentiment + community
- [ ] 불필요한 에이전트 호출 없음

### Phase 4: 하드코딩 제거
- [ ] analyze_question_for_agents() 호출 안 됨
- [ ] _classify_question_complexity() 호출 안 됨
- [ ] _identify_target_agent() 호출 안 됨

### Phase 5: 품질 검증
- [ ] 답변 길이 적절 (500자 이상)
- [ ] 증권사 리서치 보고서 톤
- [ ] 구체적 데이터 포함

---

## 🔍 로그 확인

테스트 실행 중 다음 로그를 확인하세요:

```
💬 Conversational Supervisor v2 처리 시작
📝 질문: 삼성전자 주가가 어떤가요?
🏢 종목: 005930 (삼성전자)
📜 대화 히스토리 포함: 2개 메시지 (멀티턴 대화 지원)
🤖 Conversational Supervisor 실행 (LLM 기반 동적 에이전트 선택)
⚡ 하드코딩 제거: Supervisor가 질문 분석하여 필요한 에이전트만 선택
⏱️ Supervisor 실행 시간: 3.24초
✅ Conversational Supervisor 답변 생성 완료
📊 답변 길이: 1,234자
⏱️ 총 실행 시간: 3.56초
🎯 멀티턴 대화: YES
```

**주요 로그 항목:**
- 📜 **대화 히스토리 포함**: 멀티턴 대화 지원 확인
- ⚡ **하드코딩 제거**: Supervisor 동적 라우팅 확인
- ⏱️ **실행 시간**: 성능 확인
- 🎯 **멀티턴 대화**: 대화 맥락 유지 확인

---

## 💡 트러블슈팅

### 문제: 테스트 실행 시 ModuleNotFoundError

**해결:**
```bash
# tusimreport 디렉토리에서 실행
cd C:\Users\danny\OneDrive\Desktop\code\agent_lab\TuSimReport\tusimreport
python tests/test_conversation_cli.py
```

---

### 문제: API 키 오류

**해결:**
`.env` 파일에 필요한 API 키가 설정되어 있는지 확인:
```
GOOGLE_API_KEY=your_key
DART_API_KEY=your_key
ECOS_API_KEY=your_key
NAVER_CLIENT_ID=your_id
NAVER_CLIENT_SECRET=your_secret
```

---

### 문제: 답변이 너무 느림

**원인:** API 호출 시간 소요

**해결:** 정상 동작입니다. Supervisor가 여러 에이전트를 실행하므로 시간이 걸릴 수 있습니다.

---

## 📈 기대 결과

### 성공적인 테스트

```
✅ 모든 테스트 PASS!

총 테스트: 7개
✅ PASS: 6개
⚠️ WARNING: 1개
❌ FAIL: 0개
```

### 검증 항목

1. **멀티턴 대화**: 대화 히스토리가 전달되고 맥락이 유지됨
2. **에이전트 선택**: 질문에 맞는 적절한 에이전트만 선택
3. **하드코딩 제거**: 키워드 매칭 함수 호출 안 됨
4. **답변 품질**: 500자 이상, 증권사 리서치 톤, 구체적 데이터 포함

---

## 🎯 다음 단계

1. **CLI 테스트 실행**: `python tests/test_conversation_cli.py`
2. **로그 확인**: 대화 히스토리 포함, 에이전트 선택 확인
3. **pytest 실행**: `pytest tests/test_supervisor_unit.py -v`
4. **에이전트 검증**: `python tests/verify_agent_selection.py`

---

## 📚 참고

- **LangGraph Supervisor 패턴**: 하드코딩 없이 LLM이 동적으로 에이전트 선택
- **Command 패턴**: `Command(goto=agent_name)`으로 동적 라우팅
- **MessagesState**: 대화 히스토리를 메시지 상태로 관리

---

**문의사항이나 버그 리포트:**
- 테스트 결과를 공유해주세요
- 예상과 다른 동작이 있다면 로그와 함께 보고

**Happy Testing!** 🎉
