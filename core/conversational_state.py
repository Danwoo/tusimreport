#!/usr/bin/env python3
"""
Conversational Analysis State
대화형 주식 분석 시스템을 위한 State 관리
"""

from typing import TypedDict, List, Dict, Any, Annotated
from datetime import datetime
import operator


class ConversationalAnalysisState(TypedDict):
    """
    대화형 분석 State - LangGraph StateGraph에서 사용

    핵심 설계:
    - 초기 분석 결과를 agent_results에 영구 저장
    - 추가 질문 시 필요한 에이전트만 재실행
    - 전체 대화 히스토리 유지
    """

    # ========== 기본 정보 ==========
    stock_code: str  # 종목 코드 (예: "005930")
    company_name: str  # 회사명 (예: "삼성전자")

    # ========== 대화 관련 ==========
    messages: Annotated[List[Dict[str, str]], operator.add]  # 대화 히스토리 (누적)
    # 형식: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    current_question: str  # 현재 사용자 질문
    question_type: str  # 질문 유형: "initial_analysis" | "follow_up_question"

    # ========== 에이전트 분석 결과 (영구 저장) ==========
    agent_results: Dict[str, str]
    # {
    #   "context_expert": "전체 시장 환경 분석 내용...",
    #   "sentiment_expert": "뉴스 여론 분석 내용...",
    #   ...
    # }

    # 에이전트별 마지막 업데이트 시간
    agent_timestamps: Dict[str, str]
    # {"context_expert": "2025-11-18T10:30:00", ...}

    # ========== 투자 의견 (Phase 1) ==========
    investment_opinion: Dict[str, Any]  # generate_investment_opinion() 결과

    # ========== 라우팅 및 실행 제어 ==========
    router_decision: Dict[str, Any]
    # {
    #   "selected_agents": ["sentiment_expert", "financial_expert"],
    #   "reasoning": "사용자가 재무 상태와 최근 뉴스에 대해 질문했으므로..."
    # }

    agents_to_execute: List[str]  # 실행할 에이전트 목록

    # ========== 최종 답변 ==========
    final_answer: str  # Supervisor가 생성한 최종 답변

    # ========== 메타 정보 ==========
    initial_analysis_completed: bool  # 최초 10개 에이전트 분석 완료 여부
    session_id: str  # 세션 ID (Streamlit session_state와 연동)
    created_at: str  # 세션 생성 시간
    last_updated: str  # 마지막 업데이트 시간

    # ========== 에러 처리 ==========
    errors: List[Dict[str, str]]  # 에러 로그
    # [{"agent": "sentiment_expert", "error": "API 호출 실패", "timestamp": "..."}]


def create_initial_state(
    stock_code: str,
    company_name: str,
    session_id: str = None
) -> ConversationalAnalysisState:
    """
    초기 State 생성

    Args:
        stock_code: 종목 코드
        company_name: 회사명
        session_id: 세션 ID (None이면 자동 생성)

    Returns:
        초기화된 ConversationalAnalysisState
    """
    import uuid

    if session_id is None:
        session_id = str(uuid.uuid4())

    now = datetime.now().isoformat()

    return ConversationalAnalysisState(
        stock_code=stock_code,
        company_name=company_name,
        messages=[],
        current_question="",
        question_type="initial_analysis",
        agent_results={},
        agent_timestamps={},
        investment_opinion={},
        router_decision={},
        agents_to_execute=[],
        final_answer="",
        initial_analysis_completed=False,
        session_id=session_id,
        created_at=now,
        last_updated=now,
        errors=[]
    )


def update_agent_result(
    state: ConversationalAnalysisState,
    agent_name: str,
    analysis_content: str
) -> ConversationalAnalysisState:
    """
    에이전트 분석 결과 업데이트

    Args:
        state: 현재 State
        agent_name: 에이전트 이름
        analysis_content: 분석 내용

    Returns:
        업데이트된 State
    """
    state["agent_results"][agent_name] = analysis_content
    state["agent_timestamps"][agent_name] = datetime.now().isoformat()
    state["last_updated"] = datetime.now().isoformat()

    return state


def add_user_message(
    state: ConversationalAnalysisState,
    message: str
) -> ConversationalAnalysisState:
    """
    사용자 메시지 추가

    Args:
        state: 현재 State
        message: 사용자 메시지

    Returns:
        업데이트된 State
    """
    state["messages"].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.now().isoformat()
    })
    state["current_question"] = message
    state["last_updated"] = datetime.now().isoformat()

    return state


def add_assistant_message(
    state: ConversationalAnalysisState,
    message: str
) -> ConversationalAnalysisState:
    """
    AI 답변 추가

    Args:
        state: 현재 State
        message: AI 답변

    Returns:
        업데이트된 State
    """
    state["messages"].append({
        "role": "assistant",
        "content": message,
        "timestamp": datetime.now().isoformat()
    })
    state["final_answer"] = message
    state["last_updated"] = datetime.now().isoformat()

    return state
