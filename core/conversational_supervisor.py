#!/usr/bin/env python3
"""
Conversational Supervisor
대화형 주식 분석 시스템 - LangGraph StateGraph 기반

핵심 기능:
1. 초기 분석: 10개 전문가 에이전트 실행 → 결과 저장
2. 추가 질문: Question Router로 필요한 에이전트만 선택 → 실행 → 답변
3. State 영속성: 모든 분석 결과를 State에 저장하여 재사용
"""

import logging
from typing import Dict, Any, List, Generator
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from core.conversational_state import (
    ConversationalAnalysisState,
    create_initial_state,
    update_agent_result,
    add_user_message,
    add_assistant_message
)
from core.question_router import get_question_router
from core.korean_supervisor_langgraph import (
    create_all_agents,
    get_supervisor_llm,
    generate_comprehensive_report,
    AGENT_STAGES
)
from agents.korean_investment_opinion_agent import generate_investment_opinion

logger = logging.getLogger(__name__)


class ConversationalSupervisor:
    """
    대화형 주식 분석 Supervisor

    워크플로우:
    1. START → determine_analysis_type
    2. initial_analysis → run_full_analysis → generate_report → END
    3. follow_up_question → route_question → execute_selected_agents → synthesize_answer → END
    """

    def __init__(self):
        """Supervisor 초기화"""
        self.agents = create_all_agents()
        self.supervisor_llm = get_supervisor_llm()
        self.router = get_question_router()

        # LangGraph StateGraph 생성
        self.graph = self._create_graph()

        # Checkpointer (메모리 기반)
        # 🔧 프로덕션에서는 SqliteSaver나 RedisSaver 사용 권장
        self.checkpointer = MemorySaver()

        logger.info("ConversationalSupervisor initialized with StateGraph")

    def _create_graph(self) -> StateGraph:
        """LangGraph StateGraph 생성"""

        workflow = StateGraph(ConversationalAnalysisState)

        # ========== 노드 추가 ==========

        # 1. 분석 유형 판단 (초기 vs 추가 질문)
        workflow.add_node("determine_analysis_type", self._determine_analysis_type)

        # 2-A. 초기 분석 경로
        workflow.add_node("run_full_analysis", self._run_full_analysis)
        workflow.add_node("generate_report", self._generate_report)

        # 2-B. 추가 질문 경로
        workflow.add_node("route_question", self._route_question)
        workflow.add_node("execute_selected_agents", self._execute_selected_agents)
        workflow.add_node("synthesize_answer", self._synthesize_answer)

        # ========== Edge 추가 ==========

        # START → determine_analysis_type
        workflow.set_entry_point("determine_analysis_type")

        # determine_analysis_type → 조건부 분기
        workflow.add_conditional_edges(
            "determine_analysis_type",
            self._should_run_full_analysis,
            {
                "full_analysis": "run_full_analysis",
                "follow_up": "route_question"
            }
        )

        # 초기 분석 경로
        workflow.add_edge("run_full_analysis", "generate_report")
        workflow.add_edge("generate_report", END)

        # 추가 질문 경로
        workflow.add_edge("route_question", "execute_selected_agents")
        workflow.add_edge("execute_selected_agents", "synthesize_answer")
        workflow.add_edge("synthesize_answer", END)

        return workflow

    # ========== 노드 함수들 ==========

    def _determine_analysis_type(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """분석 유형 판단 (초기 분석 vs 추가 질문)"""

        if state["initial_analysis_completed"]:
            state["question_type"] = "follow_up_question"
            logger.info("Analysis type: Follow-up question")
        else:
            state["question_type"] = "initial_analysis"
            logger.info("Analysis type: Initial analysis")

        return state

    def _should_run_full_analysis(self, state: ConversationalAnalysisState) -> str:
        """조건부 edge: 전체 분석 vs 추가 질문"""
        if state["question_type"] == "initial_analysis":
            return "full_analysis"
        else:
            return "follow_up"

    def _run_full_analysis(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """
        전체 에이전트 실행 (초기 분석)

        10개 전문가 에이전트를 순차 실행하고 결과를 State에 저장
        """
        logger.info("Running full analysis with 10 expert agents")

        execution_order = [
            "context_expert",
            "sentiment_expert",
            "financial_expert",
            "advanced_technical_expert",
            "institutional_trading_expert",
            "comparative_expert",
            "esg_expert",
            "community_expert",
            "quantitative_expert",
            "advanced_chart_expert"
        ]

        for agent_name in execution_order:
            try:
                logger.info(f"Executing agent: {agent_name}")

                agent = self.agents.get(agent_name)
                if not agent:
                    logger.error(f"Agent not found: {agent_name}")
                    continue

                # 에이전트 실행
                analysis_request = (
                    f"종목 {state['stock_code']} ({state['company_name']})에 대한 "
                    f"전문 분석을 수행해주세요."
                )

                result = agent.invoke({
                    "messages": [{"role": "user", "content": analysis_request}]
                })

                # 결과 추출
                if 'messages' in result and result['messages']:
                    last_message = result['messages'][-1]
                    content = last_message.content if hasattr(last_message, 'content') else str(last_message)

                    # 완료 시그널 제거
                    completion_signals = {
                        "context_expert": "MARKET_CONTEXT_ANALYSIS_COMPLETE",
                        "sentiment_expert": "SENTIMENT_ANALYSIS_COMPLETE",
                        "financial_expert": "FINANCIAL_ANALYSIS_COMPLETE",
                        "advanced_technical_expert": "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
                        "institutional_trading_expert": "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
                        "comparative_expert": "COMPARATIVE_ANALYSIS_COMPLETE",
                        "esg_expert": "ESG_ANALYSIS_COMPLETE",
                        "community_expert": "COMMUNITY_ANALYSIS_COMPLETE",
                        "quantitative_expert": "QUANTITATIVE_ANALYSIS_COMPLETE",
                        "advanced_chart_expert": "ADVANCED_CHART_ANALYSIS_COMPLETE"
                    }

                    signal = completion_signals.get(agent_name, "")
                    clean_content = content.replace(signal, "").strip()

                    # State에 저장
                    state = update_agent_result(state, agent_name, clean_content)

                    logger.info(f"✅ {agent_name} completed ({len(clean_content)} chars)")

            except Exception as e:
                logger.error(f"Error executing {agent_name}: {str(e)}")
                state["errors"].append({
                    "agent": agent_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })

        # 투자 의견 생성
        try:
            logger.info("Generating investment opinion...")
            investment_opinion = generate_investment_opinion(
                company_name=state["company_name"],
                stock_code=state["stock_code"],
                all_agent_results=state["agent_results"]
            )

            if "error" not in investment_opinion:
                state["investment_opinion"] = investment_opinion
                logger.info("✅ Investment opinion generated")
            else:
                logger.error(f"Investment opinion error: {investment_opinion['error']}")

        except Exception as e:
            logger.error(f"Error generating investment opinion: {str(e)}")

        # 초기 분석 완료 플래그
        state["initial_analysis_completed"] = True
        logger.info("Full analysis completed")

        return state

    def _generate_report(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """최초 종합 보고서 생성"""

        logger.info("Generating comprehensive report...")

        try:
            # 투자 의견을 agent_results에 임시 추가
            all_analyses = state["agent_results"].copy()
            if state.get("investment_opinion"):
                all_analyses["investment_opinion"] = state["investment_opinion"]

            # Supervisor가 종합 보고서 생성
            final_report = generate_comprehensive_report(
                self.supervisor_llm,
                all_analyses,
                state["stock_code"],
                state["company_name"]
            )

            # State에 저장
            state = add_assistant_message(state, final_report)

            logger.info(f"✅ Report generated ({len(final_report)} chars)")

        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            error_message = f"종합 보고서 생성 중 오류가 발생했습니다: {str(e)}"
            state = add_assistant_message(state, error_message)

        return state

    def _route_question(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """사용자 질문을 라우팅하여 필요한 에이전트 선택"""

        logger.info(f"Routing question: {state['current_question'][:100]}...")

        try:
            # Question Router 실행
            routing_result = self.router.route_question(
                question=state["current_question"],
                available_agents=list(self.agents.keys()),
                existing_results=state["agent_results"]
            )

            # State 업데이트
            state["router_decision"] = routing_result
            state["agents_to_execute"] = routing_result["selected_agents"]

            logger.info(f"Selected agents: {routing_result['selected_agents']}")

        except Exception as e:
            logger.error(f"Error routing question: {str(e)}")
            # Fallback: 모든 에이전트 선택
            state["agents_to_execute"] = list(self.agents.keys())

        return state

    def _execute_selected_agents(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """선택된 에이전트만 실행 (비용 최적화)"""

        logger.info(f"Executing {len(state['agents_to_execute'])} selected agents")

        for agent_name in state["agents_to_execute"]:
            try:
                logger.info(f"Executing agent: {agent_name}")

                agent = self.agents.get(agent_name)
                if not agent:
                    logger.error(f"Agent not found: {agent_name}")
                    continue

                # 에이전트 실행 (사용자 질문 포함)
                # 기존 분석 결과도 컨텍스트로 제공
                previous_analysis = state["agent_results"].get(agent_name, "")
                context_info = f"이전 분석 결과:\n{previous_analysis}\n\n" if previous_analysis else ""

                analysis_request = (
                    f"{context_info}"
                    f"사용자 질문: {state['current_question']}\n\n"
                    f"종목: {state['stock_code']} ({state['company_name']})"
                )

                result = agent.invoke({
                    "messages": [{"role": "user", "content": analysis_request}]
                })

                # 결과 추출 및 저장
                if 'messages' in result and result['messages']:
                    last_message = result['messages'][-1]
                    content = last_message.content if hasattr(last_message, 'content') else str(last_message)

                    # State 업데이트 (덮어쓰기)
                    state = update_agent_result(state, agent_name, content)

                    logger.info(f"✅ {agent_name} updated ({len(content)} chars)")

            except Exception as e:
                logger.error(f"Error executing {agent_name}: {str(e)}")
                state["errors"].append({
                    "agent": agent_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })

        return state

    def _synthesize_answer(self, state: ConversationalAnalysisState) -> ConversationalAnalysisState:
        """선택된 에이전트 결과를 종합하여 답변 생성"""

        logger.info("Synthesizing answer from selected agents")

        try:
            # 선택된 에이전트의 분석 결과만 사용
            relevant_analyses = []
            for agent_name in state["agents_to_execute"]:
                analysis = state["agent_results"].get(agent_name, "")
                if analysis:
                    relevant_analyses.append(f"=== {agent_name} ===\n{analysis}")

            # Supervisor LLM으로 답변 생성
            synthesis_prompt = f"""
사용자 질문: {state['current_question']}

종목: {state['stock_code']} ({state['company_name']})

선택된 전문가 분석 결과:
{chr(10).join(relevant_analyses)}

위 전문가 분석 결과를 바탕으로 사용자 질문에 대해 명확하고 간결하게 답변해주세요.

답변 가이드:
1. 사용자 질문에 직접적으로 답변
2. 전문가 분석 내용을 근거로 제시
3. 구체적인 숫자나 데이터 포함
4. 투자자 관점에서 실용적인 인사이트 제공
5. 2,000자 이내로 간결하게 작성

답변:
"""

            llm_response = self.supervisor_llm.invoke(synthesis_prompt)
            answer = llm_response.content.strip()

            # State에 답변 저장
            state = add_assistant_message(state, answer)

            logger.info(f"✅ Answer synthesized ({len(answer)} chars)")

        except Exception as e:
            logger.error(f"Error synthesizing answer: {str(e)}")
            error_message = f"답변 생성 중 오류가 발생했습니다: {str(e)}"
            state = add_assistant_message(state, error_message)

        return state

    # ========== 외부 인터페이스 ==========

    def analyze(
        self,
        stock_code: str,
        company_name: str,
        question: str = None,
        session_id: str = None
    ) -> Dict[str, Any]:
        """
        주식 분석 실행 (동기 버전)

        Args:
            stock_code: 종목 코드
            company_name: 회사명
            question: 사용자 질문 (None이면 초기 분석)
            session_id: 세션 ID (None이면 신규 세션)

        Returns:
            최종 State
        """

        # 초기 State 생성 또는 로드
        if session_id and session_id in self.checkpointer.storage:
            # 기존 세션 로드
            state = self.checkpointer.get(session_id)
            logger.info(f"Loaded existing session: {session_id}")
        else:
            # 신규 세션
            state = create_initial_state(stock_code, company_name, session_id)
            logger.info(f"Created new session: {state['session_id']}")

        # 사용자 질문 추가
        if question:
            state = add_user_message(state, question)

        # Graph 실행
        compiled_graph = self.graph.compile(checkpointer=self.checkpointer)

        config = {"configurable": {"thread_id": state["session_id"]}}
        final_state = compiled_graph.invoke(state, config=config)

        return final_state

    def stream_analyze(
        self,
        stock_code: str,
        company_name: str,
        question: str = None,
        session_id: str = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        주식 분석 실행 (스트리밍 버전)

        Streamlit UI에서 실시간 진행 상황 표시에 사용

        Yields:
            {
                "type": "progress" | "agent_complete" | "final_answer" | "error",
                "agent_name": "...",
                "content": "...",
                "progress": 0.0 ~ 1.0
            }
        """

        # 초기 State 생성 또는 로드
        if session_id and session_id in self.checkpointer.storage:
            state = self.checkpointer.get(session_id)
            logger.info(f"Loaded existing session: {session_id}")
        else:
            state = create_initial_state(stock_code, company_name, session_id)
            logger.info(f"Created new session: {state['session_id']}")

        # 사용자 질문 추가
        if question:
            state = add_user_message(state, question)

        # Graph 실행 (스트리밍)
        compiled_graph = self.graph.compile(checkpointer=self.checkpointer)

        config = {"configurable": {"thread_id": state["session_id"]}}

        try:
            for event in compiled_graph.stream(state, config=config):
                # LangGraph stream event 형식:
                # {node_name: state_update}

                node_name = list(event.keys())[0] if event else "unknown"
                node_state = event.get(node_name, {})

                # 노드별 진행 상황 yield
                if node_name == "run_full_analysis":
                    # 전체 에이전트 실행 중
                    completed_agents = len(node_state.get("agent_results", {}))
                    yield {
                        "type": "progress",
                        "message": f"전체 분석 진행 중... ({completed_agents}/10)",
                        "progress": completed_agents / 10.0
                    }

                elif node_name == "generate_report":
                    yield {
                        "type": "progress",
                        "message": "종합 보고서 생성 중...",
                        "progress": 0.95
                    }

                elif node_name == "execute_selected_agents":
                    yield {
                        "type": "progress",
                        "message": f"선택된 에이전트 실행 중...",
                        "progress": 0.5
                    }

                elif node_name == "synthesize_answer":
                    yield {
                        "type": "progress",
                        "message": "답변 생성 중...",
                        "progress": 0.9
                    }

            # 최종 State
            final_state = self.checkpointer.get(state["session_id"])

            yield {
                "type": "final_answer",
                "content": final_state.get("final_answer", ""),
                "progress": 1.0,
                "state": final_state
            }

        except Exception as e:
            logger.error(f"Error in streaming analysis: {str(e)}")
            yield {
                "type": "error",
                "error": str(e)
            }


# ========== 전역 인스턴스 ==========

_supervisor_instance = None


def get_conversational_supervisor() -> ConversationalSupervisor:
    """전역 ConversationalSupervisor 인스턴스 반환 (싱글톤)"""
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = ConversationalSupervisor()
    return _supervisor_instance
