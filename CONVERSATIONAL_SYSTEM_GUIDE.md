# 🤖 대화형 AI 채팅 시스템 - 완전 구현 가이드

## 📋 목차
1. [시스템 아키텍처](#시스템-아키텍처)
2. [핵심 컴포넌트](#핵심-컴포넌트)
3. [Streamlit UI 확장](#streamlit-ui-확장)
4. [구현 예제](#구현-예제)
5. [성능 최적화](#성능-최적화)
6. [FAQ](#faq)

---

## 1. 시스템 아키텍처

### 1.1 전체 구조

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit UI (main.py)                │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐ │
│  │ 초기 분석  │  │ 대화형 UI  │  │ 세션 관리         │ │
│  └────────────┘  └────────────┘  └────────────────────┘ │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         ConversationalSupervisor (LangGraph)            │
│  ┌────────────────────────────────────────────────────┐ │
│  │              StateGraph Workflow                   │ │
│  │                                                    │ │
│  │  START → determine_type                           │ │
│  │           ├─ Initial → run_full_analysis          │ │
│  │           │                ↓                       │ │
│  │           │          generate_report → END        │ │
│  │           │                                        │ │
│  │           └─ Follow-up → route_question           │ │
│  │                              ↓                     │ │
│  │                    execute_selected_agents        │ │
│  │                              ↓                     │ │
│  │                      synthesize_answer → END      │ │
│  └────────────────────────────────────────────────────┘ │
└───────────────────────────┬─────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│ Question     │  │ 10 Expert        │  │ Checkpointer │
│ Router (LLM) │  │ Agents           │  │ (State 저장) │
└──────────────┘  └──────────────────┘  └──────────────┘
```

### 1.2 워크플로우 설명

#### **초기 분석 (Initial Analysis)**
1. 사용자가 종목 선택 및 분석 시작
2. ConversationalSupervisor가 10개 전문가 에이전트 순차 실행
3. 각 에이전트 결과를 State에 저장
4. 투자 의견 생성
5. 종합 보고서 생성 및 표시
6. **State를 Checkpointer에 저장** (세션 유지)

#### **추가 질문 (Follow-up Question)**
1. 사용자가 추가 질문 입력
2. Question Router가 질문 분석
   - LLM 기반 의도 파악
   - 필요한 전문가 에이전트 선택 (1개 이상)
3. 선택된 에이전트만 실행 (비용 절감)
   - 기존 분석 결과를 컨텍스트로 제공
   - 실시간 데이터 필요 시 API 재호출
4. Supervisor가 결과 종합하여 답변 생성
5. State 업데이트 및 저장

---

## 2. 핵심 컴포넌트

### 2.1 ConversationalAnalysisState

**파일**: `core/conversational_state.py`

**역할**: 전체 대화 세션의 상태 관리

**주요 필드**:
```python
{
    # 기본 정보
    "stock_code": "005930",
    "company_name": "삼성전자",

    # 대화 히스토리
    "messages": [
        {"role": "user", "content": "BUY 의견인 이유는?", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
    ],

    # 에이전트 분석 결과 (영구 보존)
    "agent_results": {
        "context_expert": "시장 환경 분석 내용...",
        "sentiment_expert": "뉴스 여론 분석 내용...",
        # ... 10개 에이전트 결과
    },

    # 투자 의견
    "investment_opinion": {
        "decision": "BUY",
        "confidence": 78,
        "target_prices": {...}
    },

    # 라우팅 결과
    "router_decision": {
        "selected_agents": ["sentiment_expert", "financial_expert"],
        "reasoning": "사용자가 최근 뉴스와 재무에 대해 질문..."
    },

    # 최종 답변
    "final_answer": "...",

    # 메타 정보
    "initial_analysis_completed": True,
    "session_id": "uuid...",
    "created_at": "2025-11-18T10:00:00",
    "last_updated": "2025-11-18T10:15:00"
}
```

### 2.2 QuestionRouter

**파일**: `core/question_router.py`

**역할**: 사용자 질문 분석 및 에이전트 선택

**동작 방식**:
1. **LLM 기반 라우팅** (메인):
   - 질문 의도 파악
   - 10개 전문가 에이전트 중 관련된 에이전트 선택
   - 선택 근거 제공

2. **키워드 매칭** (Fallback):
   - LLM 실패 시 키워드 기반 선택
   - 각 에이전트별 전문 키워드 목록 사용

**예시**:
```python
router = get_question_router()

result = router.route_question(
    question="최근 뉴스 분위기가 어떤가요?",
    available_agents=["context_expert", "sentiment_expert", "financial_expert", ...],
    existing_results={"sentiment_expert": "이전 분석 결과..."}
)

# 결과:
{
    "selected_agents": ["sentiment_expert"],
    "reasoning": "사용자가 최근 뉴스에 대해 질문했으므로 뉴스 여론 전문가를 선택합니다.",
    "needs_fresh_data": True,  # "최근" 키워드 포함
    "can_use_cache": False
}
```

### 2.3 ConversationalSupervisor

**파일**: `core/conversational_supervisor.py`

**역할**: LangGraph StateGraph 기반 워크플로우 관리

**핵심 메서드**:

#### `analyze()` - 동기 실행
```python
supervisor = get_conversational_supervisor()

# 초기 분석
final_state = supervisor.analyze(
    stock_code="005930",
    company_name="삼성전자",
    question=None,  # 초기 분석
    session_id=None  # 신규 세션
)

# 추가 질문
final_state = supervisor.analyze(
    stock_code="005930",
    company_name="삼성전자",
    question="왜 BUY 의견인가요?",
    session_id=final_state["session_id"]  # 기존 세션 재사용
)
```

#### `stream_analyze()` - 스트리밍 실행
```python
for event in supervisor.stream_analyze(
    stock_code="005930",
    company_name="삼성전자",
    question="재무 상태는 어떤가요?",
    session_id=session_id
):
    if event["type"] == "progress":
        print(f"진행 중: {event['message']}")

    elif event["type"] == "final_answer":
        print(f"최종 답변: {event['content']}")
```

---

## 3. Streamlit UI 확장

### 3.1 main.py 수정 사항

**기존 UI**: 일회성 분석 → 결과 표시 → 끝

**새로운 UI**: 일회성 분석 → 결과 표시 → **대화형 채팅 UI 추가**

### 3.2 구현 단계

#### Step 1: Session State 초기화

```python
# main.py 상단
import streamlit as st
from core.conversational_supervisor import get_conversational_supervisor

# 세션 초기화
if "analysis_sessions" not in st.session_state:
    st.session_state.analysis_sessions = {}

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
```

#### Step 2: 초기 분석 후 세션 저장

```python
def run_analysis(symbol, company_name):
    """분석 실행 (기존 함수 수정)"""

    # ... 기존 분석 코드 ...

    # 🆕 대화형 Supervisor 사용
    supervisor = get_conversational_supervisor()

    # 초기 분석 실행
    final_state = supervisor.analyze(
        stock_code=symbol,
        company_name=company_name,
        question=None,  # 초기 분석
        session_id=None  # 신규 세션
    )

    # 🆕 세션 저장
    session_id = final_state["session_id"]
    st.session_state.analysis_sessions[symbol] = final_state
    st.session_state.current_session_id = session_id

    # 결과 표시 (기존 코드)
    st.markdown(final_state["final_answer"])

    # 🆕 추가 질문 UI 표시
    show_chat_interface(symbol, company_name, session_id)
```

#### Step 3: 대화형 채팅 UI 추가

```python
def show_chat_interface(stock_code: str, company_name: str, session_id: str):
    """
    대화형 채팅 인터페이스

    사용자가 추가 질문을 입력하고 AI가 답변
    """

    st.markdown("---")
    st.markdown("### 💬 추가 질문하기")
    st.markdown("분석 결과에 대해 궁금한 점을 질문해보세요!")

    # 대화 히스토리 표시
    if session_id in st.session_state.analysis_sessions:
        state = st.session_state.analysis_sessions[session_id]
        messages = state.get("messages", [])

        # 대화 히스토리 렌더링
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                st.markdown(f"**👤 질문**: {content}")
            elif role == "assistant":
                st.markdown(f"**🤖 답변**: {content}")

            st.markdown("---")

    # 질문 입력 폼
    with st.form("chat_form", clear_on_submit=True):
        user_question = st.text_area(
            "질문을 입력하세요:",
            placeholder="예: 왜 BUY 의견인가요?\n예: 최근 뉴스 분위기는 어떤가요?\n예: 재무 상태는 건전한가요?",
            height=100
        )

        submitted = st.form_submit_button("질문하기", use_container_width=True)

        if submitted and user_question:
            handle_chat_question(stock_code, company_name, session_id, user_question)


def handle_chat_question(
    stock_code: str,
    company_name: str,
    session_id: str,
    question: str
):
    """
    사용자 질문 처리

    Args:
        stock_code: 종목 코드
        company_name: 회사명
        session_id: 세션 ID
        question: 사용자 질문
    """

    supervisor = get_conversational_supervisor()

    # 진행 상황 표시
    with st.spinner("🤔 질문을 분석하고 관련 전문가에게 문의하고 있습니다..."):

        # 대화형 분석 실행
        final_state = supervisor.analyze(
            stock_code=stock_code,
            company_name=company_name,
            question=question,
            session_id=session_id
        )

        # 세션 업데이트
        st.session_state.analysis_sessions[session_id] = final_state

        # 답변 표시
        st.markdown("**🤖 AI 답변:**")
        st.markdown(final_state["final_answer"])

        # 라우팅 정보 표시 (디버깅용)
        with st.expander("🔍 선택된 전문가 에이전트"):
            router_decision = final_state.get("router_decision", {})
            selected_agents = router_decision.get("selected_agents", [])
            reasoning = router_decision.get("reasoning", "N/A")

            st.markdown(f"**선택된 에이전트**: {', '.join(selected_agents)}")
            st.markdown(f"**선택 이유**: {reasoning}")

    # 페이지 리프레시하여 대화 히스토리 업데이트
    st.rerun()
```

#### Step 4: main() 함수에 통합

```python
def main():
    # ... 기존 코드 ...

    # 분석 시작 버튼
    if st.button("🚀 AI 분석 시작", type="primary", use_container_width=True):
        if symbol:
            run_analysis(symbol.strip(), company_name.strip() if company_name else None)
        else:
            st.error("종목코드를 입력해주세요!")

    # 🆕 기존 분석이 있으면 대화 UI 표시
    if st.session_state.current_session_id:
        current_symbol = None
        for code, state in st.session_state.analysis_sessions.items():
            if state["session_id"] == st.session_state.current_session_id:
                current_symbol = code
                break

        if current_symbol:
            state = st.session_state.analysis_sessions[current_symbol]
            show_chat_interface(
                state["stock_code"],
                state["company_name"],
                state["session_id"]
            )
```

---

## 4. 구현 예제

### 4.1 시나리오: 삼성전자 분석 및 대화

#### **Step 1: 초기 분석**

```python
# 사용자: Streamlit UI에서 삼성전자(005930) 선택 → 분석 시작

supervisor = get_conversational_supervisor()

state = supervisor.analyze(
    stock_code="005930",
    company_name="삼성전자",
    question=None,
    session_id=None
)

# 결과:
# - 10개 전문가 에이전트 실행 완료
# - 투자 의견: BUY (신뢰도 78%)
# - 종합 보고서 생성
# - session_id: "abc-123-def"
```

#### **Step 2: 추가 질문 1 - "왜 BUY인가요?"**

```python
# 사용자: 대화 UI에서 "왜 BUY 의견인가요?" 입력

state = supervisor.analyze(
    stock_code="005930",
    company_name="삼성전자",
    question="왜 BUY 의견인가요?",
    session_id="abc-123-def"  # 기존 세션 재사용
)

# 내부 동작:
# 1. Question Router 실행
#    → "투자 의견"에 대한 질문 → investment_opinion 데이터 참조
#    → 선택된 에이전트: ["financial_expert", "sentiment_expert", "comparative_expert"]
#
# 2. 선택된 3개 에이전트만 재실행 (비용 절감)
#    → 기존 분석 결과를 컨텍스트로 제공
#    → 필요 시 실시간 API 재호출
#
# 3. Supervisor가 답변 종합
#    → "BUY 의견의 주요 근거는 다음과 같습니다:
#       1. 재무 건전성: 영업이익률 15% 증가...
#       2. 뉴스 여론: 최근 AI 칩 수주 호재...
#       3. 밸류에이션: PER 10배로 동종업계 대비 저평가..."

# 결과:
state["final_answer"]  # 위 답변 내용
state["messages"]  # 대화 히스토리에 추가됨
```

#### **Step 3: 추가 질문 2 - "최근 뉴스는?"**

```python
# 사용자: "최근 뉴스 분위기는 어떤가요?"

state = supervisor.analyze(
    stock_code="005930",
    company_name="삼성전자",
    question="최근 뉴스 분위기는 어떤가요?",
    session_id="abc-123-def"
)

# 내부 동작:
# 1. Question Router 실행
#    → "최근", "뉴스" 키워드 감지
#    → 선택된 에이전트: ["sentiment_expert"]
#    → needs_fresh_data: True (실시간 데이터 필요)
#
# 2. sentiment_expert 재실행
#    → Naver News API + Tavily API 재호출
#    → 최신 70-90개 뉴스 분석
#
# 3. 답변 생성
#    → "최근 24시간 내 뉴스 분위기는 긍정적입니다.
#       주요 헤드라인: 'AI 메모리 반도체 수주 확대'..."
```

---

## 5. 성능 최적화

### 5.1 비용 절감 전략

#### **1. 선택적 에이전트 실행**
- ✅ **Before**: 추가 질문마다 10개 에이전트 모두 재실행
- ✅ **After**: Question Router가 필요한 1-3개만 선택 실행
- 💰 **비용 절감**: 약 70-90% (평균 2개 에이전트만 실행)

#### **2. State 캐싱**
- ✅ 초기 분석 결과를 State에 저장
- ✅ 추가 질문 시 기존 결과 재사용
- 💰 **비용 절감**: 에이전트별 API 재호출 최소화

#### **3. 실시간 데이터 선택적 갱신**
```python
def _needs_fresh_data(self, question: str) -> bool:
    """실시간 데이터 필요 여부 판단"""
    time_keywords = ["최근", "현재", "지금", "오늘", "어제", "이번"]

    for keyword in time_keywords:
        if keyword in question.lower():
            return True  # 실시간 API 재호출

    return False  # 기존 결과 재사용
```

### 5.2 응답 속도 개선

#### **1. 병렬 에이전트 실행** (Future Enhancement)
```python
# 현재: 순차 실행
for agent in selected_agents:
    result = agent.invoke(...)

# 개선: 병렬 실행
import asyncio

async def execute_agents_parallel(agents):
    tasks = [agent.ainvoke(...) for agent in agents]
    return await asyncio.gather(*tasks)
```

#### **2. Progressive Streaming**
```python
# Streamlit UI에서 실시간 진행 상황 표시
for event in supervisor.stream_analyze(...):
    if event["type"] == "progress":
        st.write(event["message"])  # "sentiment_expert 실행 중..."
```

### 5.3 메모리 관리

#### **1. Checkpointer 선택**

**개발 환경**:
```python
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()  # 메모리 기반 (간단)
```

**프로덕션 환경**:
```python
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver("./checkpoints.db")  # SQLite 기반 (영구 저장)

# 또는
from langgraph.checkpoint.redis import RedisSaver
checkpointer = RedisSaver(redis_client)  # Redis 기반 (고성능)
```

#### **2. 세션 만료 관리**
```python
# 24시간 후 자동 삭제
import time

def cleanup_old_sessions(checkpointer, max_age_hours=24):
    """오래된 세션 정리"""
    cutoff_time = time.time() - (max_age_hours * 3600)

    for session_id in checkpointer.list():
        state = checkpointer.get(session_id)
        created_at = datetime.fromisoformat(state["created_at"]).timestamp()

        if created_at < cutoff_time:
            checkpointer.delete(session_id)
            logger.info(f"Deleted expired session: {session_id}")
```

---

## 6. FAQ

### Q1: 기존 시스템과 호환되나요?

**A**: 네, 완전히 호환됩니다.

- `ConversationalSupervisor`는 기존 `korean_supervisor_langgraph.py`의 함수들을 재사용합니다
- 기존 10개 에이전트 그대로 사용
- 기존 `main.py`에 대화형 UI만 추가하면 됩니다

### Q2: 추가 질문 시 API 비용이 얼마나 드나요?

**A**: 질문 유형에 따라 다릅니다.

- **간단한 질문** (기존 데이터로 답변 가능): LLM 비용만 (약 $0.001)
- **실시간 데이터 필요** (예: "최근 뉴스"): 1-2개 에이전트 재실행 (약 $0.01-0.02)
- **복잡한 질문** (3개 이상 에이전트): 약 $0.03-0.05

초기 전체 분석 대비 **70-90% 비용 절감**

### Q3: 세션은 얼마나 유지되나요?

**A**: Checkpointer 설정에 따릅니다.

- **MemorySaver**: 서버 재시작 시 삭제
- **SqliteSaver**: 영구 저장 (수동 삭제 필요)
- **RedisSaver**: TTL 설정 가능 (예: 24시간)

권장: 24시간 TTL + 주기적 정리

### Q4: 동시 사용자가 많으면 성능이 떨어지나요?

**A**: LangGraph의 Checkpointing은 세션별로 독립적입니다.

- 각 사용자별 별도 `session_id`
- 병렬 처리 가능
- Redis Checkpointer 사용 시 고성능 보장

### Q5: 질문 라우팅 정확도를 높이려면?

**A**: 다음 방법들을 시도하세요.

1. **Few-shot 프롬프팅**:
   ```python
   # question_router.py의 routing_prompt에 예시 추가
   """
   예시 1:
   질문: "왜 BUY인가요?"
   선택: [financial_expert, sentiment_expert, comparative_expert]

   예시 2:
   질문: "최근 뉴스는?"
   선택: [sentiment_expert]
   """
   ```

2. **에이전트 설명 개선**:
   ```python
   AGENT_EXPERTISE = {
       "sentiment_expert": {
           "keywords": [...],
           "description": "최근 24시간 내 뉴스 및 시장 심리 분석 (실시간 데이터)",
           "use_cases": ["최근 뉴스 확인", "시장 분위기 파악", "여론 추이"]
       }
   }
   ```

3. **피드백 루프**:
   ```python
   # 사용자가 답변에 "도움됨/안됨" 버튼 클릭
   # → 라우팅 결과 로깅
   # → 주기적으로 프롬프트 개선
   ```

---

## 📊 구현 완료 체크리스트

### Phase 1: 핵심 구현
- [x] ConversationalAnalysisState 정의
- [x] QuestionRouter 구현
- [x] ConversationalSupervisor 구현
- [ ] Streamlit UI 확장
- [ ] 테스트 및 검증

### Phase 2: 최적화
- [ ] 병렬 에이전트 실행
- [ ] Redis Checkpointer 적용
- [ ] 세션 만료 관리
- [ ] 라우팅 정확도 개선

### Phase 3: 프로덕션
- [ ] 로깅 및 모니터링
- [ ] 에러 핸들링 강화
- [ ] 성능 벤치마크
- [ ] 사용자 피드백 수집

---

## 🎯 다음 단계

1. **Streamlit UI 확장 구현**:
   - `main.py`에 `show_chat_interface()` 추가
   - 대화 히스토리 렌더링
   - 질문 입력 폼 구현

2. **테스트**:
   - 삼성전자로 초기 분석 테스트
   - 다양한 추가 질문 테스트
   - 세션 유지 확인

3. **배포**:
   - Streamlit Cloud 또는 자체 서버
   - Redis Checkpointer 설정
   - 모니터링 도구 연동

---

## 📚 참고 자료

- [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/)
- [StateGraph 가이드](https://langchain-ai.github.io/langgraph/how-tos/state-graph/)
- [Checkpointing 가이드](https://langchain-ai.github.io/langgraph/how-tos/persistence/)
- [Streamlit 세션 관리](https://docs.streamlit.io/library/api-reference/session-state)

---

**이 가이드로 대화형 AI 채팅 시스템을 완전히 구현할 수 있습니다.**

질문이 있으시면 언제든지 문의하세요! 🚀
