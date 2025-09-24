#!/usr/bin/env python3
"""
Streamlit 최적화 병렬 처리 엔진
ThreadPoolExecutor + Session State 기반 병렬 에이전트 실행
"""

import logging
import streamlit as st
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from streamlit.runtime.scriptrunner import add_script_run_ctx

from core.korean_supervisor_langgraph import create_all_agents, get_supervisor_llm
from config.settings import settings

logger = logging.getLogger(__name__)

class StreamlitParallelEngine:
    """Streamlit 최적화 병렬 분석 엔진"""

    def __init__(self):
        """병렬 엔진 초기화"""
        self.agents = self._get_cached_agents()
        self.supervisor_llm = get_supervisor_llm()

        # 에이전트 실행 순서 (의존성 최소화)
        self.agent_config = {
            'context_expert': {'name': '🌍 시장환경', 'priority': 1},
            'sentiment_expert': {'name': '📰 뉴스분석', 'priority': 1},
            'financial_expert': {'name': '💰 재무분석', 'priority': 1},
            'advanced_technical_expert': {'name': '📈 기술분석', 'priority': 2},
            'institutional_trading_expert': {'name': '🏢 수급분석', 'priority': 2},
            'comparative_expert': {'name': '⚖️ 상대평가', 'priority': 3},
            'esg_expert': {'name': '🌱 ESG분석', 'priority': 2},
            'community_expert': {'name': '💬 커뮤니티', 'priority': 3}
        }

        logger.info("StreamlitParallelEngine 초기화 완료")

    @st.cache_resource
    def _get_cached_agents(_self):
        """에이전트 인스턴스 캐싱 (세션간 공유)"""
        try:
            agents = create_all_agents()
            logger.info(f"에이전트 캐싱 완료: {list(agents.keys())}")
            return agents
        except Exception as e:
            logger.error(f"에이전트 캐싱 실패: {str(e)}")
            return {}

    def initialize_session_state(self):
        """Session State 초기화"""
        if 'parallel_results' not in st.session_state:
            st.session_state.parallel_results = {}
        if 'parallel_progress' not in st.session_state:
            st.session_state.parallel_progress = {}
        if 'parallel_errors' not in st.session_state:
            st.session_state.parallel_errors = {}
        if 'parallel_execution_started' not in st.session_state:
            st.session_state.parallel_execution_started = False
        if 'parallel_execution_completed' not in st.session_state:
            st.session_state.parallel_execution_completed = False

        logger.info("Session State 초기화 완료")

    def execute_agents_parallel(self, stock_code: str, company_name: str) -> bool:
        """병렬 에이전트 실행 (Streamlit 최적화)"""
        try:
            logger.info(f"🔥🔥🔥 ULTRATHINK: execute_agents_parallel 메서드 진입! {stock_code} ({company_name}) 🔥🔥🔥")
            logger.info(f"📊 설정된 에이전트 수: {len(self.agent_config)}")
            logger.info(f"📊 로드된 에이전트 수: {len(self.agents)}")

            # Session State 초기화
            self.initialize_session_state()

            # 진행률 초기화
            for agent_name in self.agent_config.keys():
                st.session_state.parallel_progress[agent_name] = {
                    'status': 'waiting',
                    'progress': 0,
                    'start_time': None,
                    'end_time': None,
                    'error': None
                }

            st.session_state.parallel_execution_started = True

            # ThreadPoolExecutor 사용 (OpenAI Rate Limit 고려하여 최대 2개 동시 실행)
            max_workers = min(2, len(self.agent_config))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                logger.info(f"ThreadPoolExecutor 시작 (max_workers: {max_workers})")

                # 에이전트 실행 태스크 생성
                future_to_agent = {}

                for agent_name in self.agent_config.keys():
                    logger.info(f"🔍 에이전트 확인: {agent_name} - 존재 여부: {agent_name in self.agents}")

                    if agent_name in self.agents:
                        # 진행률 업데이트
                        st.session_state.parallel_progress[agent_name]['status'] = 'starting'
                        st.session_state.parallel_progress[agent_name]['start_time'] = datetime.now()

                        # 태스크 생성 (Streamlit 컨텍스트 처리된 함수로)
                        future = executor.submit(
                            self._execute_single_agent_with_context,
                            agent_name, stock_code, company_name
                        )

                        future_to_agent[future] = agent_name

                        logger.info(f"✅ 에이전트 {agent_name} 태스크 생성 완료")
                    else:
                        logger.warning(f"❌ 에이전트 {agent_name}이 self.agents에 없음")

                # 결과 수집 (완료되는 대로)
                completed_count = 0
                total_count = len(future_to_agent)

                logger.info(f"🔄 결과 수집 시작: {total_count}개 태스크 대기 중")

                for future in as_completed(future_to_agent):
                    agent_name = future_to_agent[future]
                    completed_count += 1

                    logger.info(f"🔄 Future 완료됨: {agent_name} ({completed_count}/{total_count})")

                    try:
                        # 결과 가져오기
                        result = future.result(timeout=300)  # 5분 타임아웃
                        logger.info(f"📝 {agent_name} 결과 수신: {type(result)}")

                        # 성공 처리
                        st.session_state.parallel_results[agent_name] = result
                        st.session_state.parallel_progress[agent_name].update({
                            'status': 'completed',
                            'progress': 100,
                            'end_time': datetime.now()
                        })

                        logger.info(f"✅ {agent_name} 완료 ({completed_count}/{total_count})")

                    except Exception as e:
                        # 에러 처리
                        error_msg = str(e)
                        logger.error(f"❌ {agent_name} Future 결과 가져오기 실패: {error_msg}")

                        st.session_state.parallel_errors[agent_name] = error_msg
                        st.session_state.parallel_progress[agent_name].update({
                            'status': 'error',
                            'progress': 0,
                            'end_time': datetime.now(),
                            'error': error_msg
                        })

                        logger.error(f"❌ {agent_name} 최종 실패: {error_msg}")

                # 실행 완료 표시
                st.session_state.parallel_execution_completed = True

                # 성공한 에이전트 수 확인
                successful_agents = len([
                    agent for agent, progress in st.session_state.parallel_progress.items()
                    if progress['status'] == 'completed'
                ])

                logger.info(f"병렬 실행 완료: {successful_agents}/{total_count} 성공")

                # 최소 5개 에이전트 성공시 성공으로 간주
                return successful_agents >= 5

        except Exception as e:
            logger.error(f"병렬 실행 시스템 오류: {str(e)}")
            st.session_state.parallel_execution_completed = True
            return False

    def _execute_single_agent_with_context(
        self,
        agent_name: str,
        stock_code: str,
        company_name: str
    ) -> Dict[str, Any]:
        """Streamlit 컨텍스트와 함께 단일 에이전트 실행 (Thread-safe 개선)"""
        try:
            logger.info(f"에이전트 실행 시작: {agent_name}")

            # 에이전트 가져오기
            agent = self.agents.get(agent_name)
            if not agent:
                raise ValueError(f"에이전트를 찾을 수 없음: {agent_name}")

            # 에이전트별 맞춤형 요청 생성
            analysis_request = self._create_agent_request(agent_name, stock_code, company_name)

            # 에이전트 실행 (Streamlit 없이 직접 실행)
            result = agent.invoke({
                "messages": [{"role": "user", "content": analysis_request}]
            })

            # 결과 처리
            if 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)

                # 완료 시그널 확인 및 추가
                completion_signal = self._get_completion_signal(agent_name)
                if completion_signal and completion_signal not in content:
                    content = content.strip() + f"\n\n{completion_signal}"

                logger.info(f"✅ {agent_name} 실행 성공 ({len(content)}자)")

                return {
                    'agent_name': agent_name,
                    'content': content,
                    'token_count': len(content.split()),
                    'execution_time': datetime.now().isoformat(),
                    'status': 'success'
                }
            else:
                raise ValueError(f"에이전트 응답이 비어있음: {agent_name}")

        except Exception as e:
            logger.error(f"❌ {agent_name} 실행 실패: {str(e)}")
            raise e

    def _execute_single_agent_thread_safe(
        self,
        agent_name: str,
        stock_code: str,
        company_name: str
    ) -> Dict[str, Any]:
        """Thread-safe 단일 에이전트 실행"""
        try:
            # 진행률 업데이트 (Thread-safe)
            self._update_progress_thread_safe(agent_name, 'running', 50)

            logger.info(f"에이전트 실행 시작: {agent_name}")

            # 에이전트 가져오기
            agent = self.agents.get(agent_name)
            if not agent:
                raise ValueError(f"에이전트를 찾을 수 없음: {agent_name}")

            # 에이전트별 맞춤형 요청 생성
            analysis_request = self._create_agent_request(agent_name, stock_code, company_name)

            # 에이전트 실행
            result = agent.invoke({
                "messages": [{"role": "user", "content": analysis_request}]
            })

            # 결과 처리
            if 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)

                # 완료 시그널 확인 및 추가
                completion_signal = self._get_completion_signal(agent_name)
                if completion_signal and completion_signal not in content:
                    content = content.strip() + f"\n\n{completion_signal}"

                logger.info(f"✅ {agent_name} 실행 성공 ({len(content)}자)")

                return {
                    'agent_name': agent_name,
                    'content': content,
                    'token_count': len(content.split()),
                    'execution_time': datetime.now().isoformat(),
                    'status': 'success'
                }
            else:
                raise ValueError(f"에이전트 응답이 비어있음: {agent_name}")

        except Exception as e:
            logger.error(f"❌ {agent_name} 실행 실패: {str(e)}")
            raise e

    def _update_progress_thread_safe(self, agent_name: str, status: str, progress: int):
        """Thread-safe 진행률 업데이트"""
        # 주의: 직접 session state 수정은 thread-safe하지 않을 수 있음
        # 하지만 Streamlit에서는 읽기 작업은 비교적 안전함
        pass

    def _create_agent_request(self, agent_name: str, stock_code: str, company_name: str) -> str:
        """에이전트별 맞춤형 요청 메시지 생성"""
        base_requests = {
            "context_expert": f"종목 {stock_code} ({company_name})에 대한 시장 환경 및 거시경제 분석을 수행해주세요.",
            "sentiment_expert": f"종목 {stock_code} ({company_name})에 대한 뉴스 및 시장 심리 분석을 수행해주세요.",
            "financial_expert": f"종목 {stock_code} ({company_name})에 대한 재무제표 및 기업 분석을 수행해주세요.",
            "advanced_technical_expert": f"종목 {stock_code} ({company_name})에 대한 고급 기술적 분석을 수행해주세요.",
            "institutional_trading_expert": f"종목 {stock_code} ({company_name})에 대한 기관 수급 분석을 수행해주세요.",
            "comparative_expert": f"종목 {stock_code} ({company_name})에 대한 동종업계 상대 평가를 수행해주세요.",
            "esg_expert": f"종목 {stock_code} ({company_name})에 대한 ESG 및 지속가능성 분석을 수행해주세요.",
            "community_expert": f"종목 {stock_code} ({company_name})에 대한 커뮤니티 여론 분석을 수행해주세요."
        }

        return base_requests.get(agent_name, f"종목 {stock_code}에 대한 분석을 수행해주세요.")

    def _get_completion_signal(self, agent_name: str) -> str:
        """에이전트별 완료 시그널"""
        completion_signals = {
            "context_expert": "MARKET_CONTEXT_ANALYSIS_COMPLETE",
            "sentiment_expert": "SENTIMENT_ANALYSIS_COMPLETE",
            "financial_expert": "FINANCIAL_ANALYSIS_COMPLETE",
            "advanced_technical_expert": "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
            "institutional_trading_expert": "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
            "comparative_expert": "COMPARATIVE_ANALYSIS_COMPLETE",
            "esg_expert": "ESG_ANALYSIS_COMPLETE",
            "community_expert": "COMMUNITY_ANALYSIS_COMPLETE"
        }

        return completion_signals.get(agent_name, "")

    def get_execution_status(self) -> Dict[str, Any]:
        """현재 실행 상태 반환"""
        if 'parallel_progress' not in st.session_state:
            return {'status': 'not_started', 'progress': 0, 'agents': {}}

        total_agents = len(self.agent_config)
        completed_agents = len([
            agent for agent, progress in st.session_state.parallel_progress.items()
            if progress['status'] == 'completed'
        ])

        overall_progress = (completed_agents / total_agents) if total_agents > 0 else 0

        return {
            'status': 'completed' if st.session_state.get('parallel_execution_completed', False) else 'running',
            'progress': overall_progress,
            'completed_agents': completed_agents,
            'total_agents': total_agents,
            'agents': st.session_state.parallel_progress,
            'results_available': len(st.session_state.get('parallel_results', {}))
        }

    def get_analysis_results(self) -> Dict[str, str]:
        """분석 결과 반환"""
        if 'parallel_results' not in st.session_state:
            return {}

        # 결과 정리
        formatted_results = {}
        for agent_name, result in st.session_state.parallel_results.items():
            if isinstance(result, dict) and 'content' in result:
                formatted_results[agent_name] = result['content']
            else:
                formatted_results[agent_name] = str(result)

        return formatted_results

# 전역 인스턴스
@st.cache_resource
def get_parallel_engine():
    """전역 병렬 엔진 인스턴스"""
    return StreamlitParallelEngine()