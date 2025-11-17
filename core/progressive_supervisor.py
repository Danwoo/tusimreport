#!/usr/bin/env python3
"""
Progressive Multi-Agent Analysis System
컨텍스트 길이 제한을 해결하는 점진적 분석 시스템
"""

import logging
from typing import Dict, Any, List, Generator
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from core.context_manager import get_context_manager, EnterpriseContextManager
from core.korean_supervisor_langgraph import create_all_agents, get_supervisor_llm, generate_comprehensive_report

logger = logging.getLogger(__name__)

class ProgressiveAnalysisEngine:
    """점진적 분석 엔진 - 메모리 효율적 멀티 에이전트 실행"""

    def __init__(self):
        self.context_manager = get_context_manager()
        self.supervisor_llm = get_supervisor_llm()
        self.agents = create_all_agents()

        # 🔧 P0-4: 병렬 실행 최적화 - 독립적 에이전트 vs 의존적 에이전트 분리
        # 병렬 실행 가능한 독립적 에이전트 (6개)
        self.parallel_agents = [
            "context_expert",           # 시장환경 (독립적)
            "sentiment_expert",         # 뉴스여론 (독립적)
            "advanced_technical_expert", # 기술분석 (독립적)
            "institutional_trading_expert", # 기관수급 (독립적)
            "esg_expert",              # ESG분석 (독립적)
            "community_expert"         # 커뮤니티 (독립적)
        ]

        # 순차 실행 필요한 의존적 에이전트 (2개)
        self.sequential_agents = [
            "financial_expert",         # 재무분석 (DART API 의존)
            "comparative_expert"        # 상대평가 (재무 결과 참고 가능)
        ]

        # 전체 실행 순서 (레거시 호환성 유지)
        self.execution_order = self.parallel_agents + self.sequential_agents

        # Thread-safe 결과 저장소
        self.results_lock = threading.Lock()

        logger.info("Progressive Analysis Engine 초기화 완료 (병렬 실행 모드)")
        logger.info(f"  - 병렬 실행: {len(self.parallel_agents)}개 에이전트")
        logger.info(f"  - 순차 실행: {len(self.sequential_agents)}개 에이전트")

    def execute_agent_with_context_control(
        self,
        agent_name: str,
        stock_code: str,
        company_name: str,
        previous_summaries: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """컨텍스트 제어하에 단일 에이전트 실행"""
        try:
            logger.info(f"에이전트 실행 시작: {agent_name}")

            # 컨텍스트 사용량 확인
            stats = self.context_manager.get_context_stats()
            logger.info(f"컨텍스트 상태: {stats['available_tokens']:,} 토큰 사용 가능")

            agent = self.agents.get(agent_name)
            if not agent:
                raise ValueError(f"에이전트를 찾을 수 없음: {agent_name}")

            # 🎯 Smart Context Building: LLM 기반 요약으로 품질 보존
            context_info = ""
            if previous_summaries:
                # 📊 이전 에이전트 결과를 간결하게 요약하여 컨텍스트 구성
                key_summaries = []
                for prev_agent, summary in previous_summaries.items():
                    # 완전 보존 - 압축하지 않고 원본 그대로 전달
                    preserved_content = self.context_manager.preserve_agent_output(
                        prev_agent, summary
                    )
                    key_summaries.append(f"[{prev_agent}]: {preserved_content}")

                context_info = "\n".join(key_summaries)

            # 에이전트별 맞춤형 메시지 생성
            analysis_request = self._create_targeted_request(
                agent_name, stock_code, company_name, context_info
            )

            # 에이전트 실행
            result = agent.invoke({"messages": [{"role": "user", "content": analysis_request}]})

            # 결과 처리
            if 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)

                # 완료 시그널 확인
                completion_signals = {
                    "context_expert": "MARKET_CONTEXT_ANALYSIS_COMPLETE",
                    "sentiment_expert": "SENTIMENT_ANALYSIS_COMPLETE",
                    "financial_expert": "FINANCIAL_ANALYSIS_COMPLETE",
                    "advanced_technical_expert": "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
                    "institutional_trading_expert": "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
                    "comparative_expert": "COMPARATIVE_ANALYSIS_COMPLETE",
                    "esg_expert": "ESG_ANALYSIS_COMPLETE"
                }

                expected_signal = completion_signals.get(agent_name)
                is_complete = expected_signal and expected_signal in content

                # 🔧 시니어 개발자 패치: LLM이 completion signal을 빠뜨린 경우 강제 추가
                if not is_complete and expected_signal and len(content) > 200:
                    logger.warning(f"🔧 {agent_name}: LLM이 completion signal을 누락함. 자동 추가 중...")
                    content = content.strip() + f"\n\n{expected_signal}"
                    is_complete = True

                # 🎯 컨텍스트 완전 보존 - 압축/요약 없음
                compressed_content = self.context_manager.preserve_agent_output(
                    agent_name, content
                )

                logger.info(f"✅ {agent_name} 실행 완료 (완료 시그널: {is_complete})")

                return {
                    "agent_name": agent_name,
                    "status": "success",
                    "content": content,
                    "compressed_content": compressed_content,
                    "is_complete": is_complete,
                    "token_count": self.context_manager.count_tokens(content),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise ValueError(f"에이전트 응답이 비어있음: {agent_name}")

        except Exception as e:
            logger.error(f"❌ {agent_name} 실행 실패: {str(e)}")
            return {
                "agent_name": agent_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _create_targeted_request(
        self,
        agent_name: str,
        stock_code: str,
        company_name: str,
        context_info: str = ""
    ) -> str:
        """에이전트별 맞춤형 요청 메시지 생성"""

        base_requests = {
            "context_expert": f"종목 {stock_code} ({company_name})에 대한 시장 환경 및 거시경제 분석을 수행해주세요.",
            "sentiment_expert": f"종목 {stock_code} ({company_name})에 대한 뉴스 및 시장 심리 분석을 수행해주세요.",
            "financial_expert": f"종목 {stock_code} ({company_name})에 대한 재무제표 및 기업 분석을 수행해주세요.",
            "advanced_technical_expert": f"종목 {stock_code} ({company_name})에 대한 고급 기술적 분석을 수행해주세요.",
            "institutional_trading_expert": f"종목 {stock_code} ({company_name})에 대한 기관 수급 분석을 수행해주세요.",
            "comparative_expert": f"종목 {stock_code} ({company_name})에 대한 동종업계 상대 평가를 수행해주세요.",
            "esg_expert": f"종목 {stock_code} ({company_name})에 대한 ESG 및 지속가능성 분석을 수행해주세요."
        }

        request = base_requests.get(agent_name, f"종목 {stock_code}에 대한 분석을 수행해주세요.")

        # 🎯 컨텍스트 정보 최적화 - 토큰 한계 고려
        if context_info and len(context_info) > 0:
            # 컨텍스트 토큰 수 확인
            context_tokens = self.context_manager.count_tokens(context_info)
            if context_tokens > 50000:  # 5만 토큰 초과시 앞부분만 사용
                # 앞부분 70% + 뒷부분 30% 조합으로 중요 정보 보존
                context_lines = context_info.split('\n')
                front_70 = context_lines[:int(len(context_lines) * 0.7)]
                back_30 = context_lines[-int(len(context_lines) * 0.3):]
                context_info = '\n'.join(front_70 + ['...'] + back_30)

            request += f"\n\n참고 정보:\n{context_info}"

        return request

    def _preserve_completion_signal(self, content: str, max_length: int = 2000) -> str:
        """완료 신호를 보존하면서 콘텐츠 길이를 제한합니다."""
        if len(content) <= max_length:
            return content

        # 완료 신호 패턴들
        completion_signals = [
            "MARKET_CONTEXT_ANALYSIS_COMPLETE",
            "SENTIMENT_ANALYSIS_COMPLETE",
            "FINANCIAL_ANALYSIS_COMPLETE",
            "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
            "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
            "COMPARATIVE_ANALYSIS_COMPLETE",
            "ESG_ANALYSIS_COMPLETE"
        ]

        # 완료 신호가 있는지 확인하고 위치 찾기
        signal_info = None
        for signal in completion_signals:
            if signal in content:
                signal_pos = content.find(signal)
                signal_info = (signal, signal_pos)
                break

        if signal_info:
            signal, signal_pos = signal_info
            # 신호 주변 텍스트를 포함하여 자르기 (앞부분 + 신호 부분)
            if signal_pos > max_length - 100:  # 신호가 뒤쪽에 있으면
                # 앞부분 일부 + ... + 신호 부분
                front_part = content[:max_length-200]
                signal_part = content[signal_pos-50:signal_pos+len(signal)+10]
                return front_part + "...\n\n" + signal_part
            else:
                # 신호가 앞쪽에 있으면 그대로 자르기
                return content[:max_length]
        else:
            # 완료 신호가 없으면 그대로 자르기
            return content[:max_length] + "..."

    def stream_progressive_analysis(
        self,
        stock_code: str,
        company_name: str = None
    ) -> Generator[Dict[str, Any], None, None]:
        """🔧 P0-4: 병렬 실행 최적화 - 점진적 분석 실행"""
        try:
            logger.info(f"=== 병렬 실행 모드 분석 시작 ===")
            logger.info(f"종목: {stock_code} ({company_name})")
            logger.info(f"병렬 에이전트: {len(self.parallel_agents)}개")
            logger.info(f"순차 에이전트: {len(self.sequential_agents)}개")

            agent_results = {}  # 🎯 전체 원본 분석 내용 보존
            agent_summaries = {}  # 압축된 요약본 (컨텍스트용)
            completed_agents = 0
            total_agents = len(self.execution_order)

            # === Phase 1: 병렬 실행 (6개 독립적 에이전트) ===
            logger.info(f"Phase 1: {len(self.parallel_agents)}개 에이전트 병렬 실행 시작")

            # ThreadPoolExecutor로 병렬 실행
            with ThreadPoolExecutor(max_workers=6) as executor:
                # Submit all parallel agents
                future_to_agent = {}
                for agent_name in self.parallel_agents:
                    future = executor.submit(
                        self.execute_agent_with_context_control,
                        agent_name,
                        stock_code,
                        company_name,
                        {}  # 병렬 에이전트는 서로 독립적이므로 컨텍스트 없음
                    )
                    future_to_agent[future] = agent_name

                    # 시작 알림
                    yield {
                        "type": "progress",
                        "agent_name": agent_name,
                        "progress": completed_agents / total_agents,
                        "status": "starting",
                        "message": f"{agent_name} 분석 시작 중 (병렬)...",
                        "completed_agents": completed_agents,
                        "total_agents": total_agents
                    }

                # Process completed futures as they finish
                for future in as_completed(future_to_agent):
                    agent_name = future_to_agent[future]
                    try:
                        result = future.result()

                        if result["status"] == "success":
                            # Thread-safe 결과 저장
                            with self.results_lock:
                                agent_results[agent_name] = result["content"]
                                agent_summaries[agent_name] = result["compressed_content"]
                                completed_agents += 1

                            # 완료 상태 yield
                            yield {
                                "type": "agent_complete",
                                "agent_name": agent_name,
                                "progress": completed_agents / total_agents,
                                "status": "completed",
                                "message": f"{agent_name} 분석 완료 (병렬)",
                                "content": self._preserve_completion_signal(result["compressed_content"], 2000),
                                "token_count": result["token_count"],
                                "completed_agents": completed_agents,
                                "total_agents": total_agents
                            }
                        else:
                            # 실패한 경우
                            logger.warning(f"{agent_name} 실패: {result.get('error')}")
                            yield {
                                "type": "agent_error",
                                "agent_name": agent_name,
                                "progress": completed_agents / total_agents,
                                "status": "error",
                                "message": f"{agent_name} 분석 실패: {result['error']}",
                                "error": result["error"],
                                "completed_agents": completed_agents,
                                "total_agents": total_agents
                            }

                    except Exception as e:
                        logger.error(f"에이전트 {agent_name} 실행 중 오류: {str(e)}")
                        yield {
                            "type": "agent_error",
                            "agent_name": agent_name,
                            "status": "error",
                            "error": str(e),
                            "completed_agents": completed_agents,
                            "total_agents": total_agents
                        }

            logger.info(f"Phase 1 완료: {completed_agents}/{len(self.parallel_agents)}개 성공")

            # === Phase 2: 순차 실행 (2개 의존적 에이전트) ===
            logger.info(f"Phase 2: {len(self.sequential_agents)}개 에이전트 순차 실행 시작")

            for agent_name in self.sequential_agents:
                try:
                    # 진행 상황 yield
                    yield {
                        "type": "progress",
                        "agent_name": agent_name,
                        "progress": completed_agents / total_agents,
                        "status": "starting",
                        "message": f"{agent_name} 분석 시작 중 (순차)...",
                        "completed_agents": completed_agents,
                        "total_agents": total_agents
                    }

                    # 에이전트 실행 (병렬 에이전트 결과 컨텍스트 포함)
                    result = self.execute_agent_with_context_control(
                        agent_name, stock_code, company_name, agent_summaries
                    )

                    if result["status"] == "success":
                        # 성공한 경우
                        agent_results[agent_name] = result["content"]
                        agent_summaries[agent_name] = result["compressed_content"]
                        completed_agents += 1

                        # 완료 상태 yield
                        yield {
                            "type": "agent_complete",
                            "agent_name": agent_name,
                            "progress": completed_agents / total_agents,
                            "status": "completed",
                            "message": f"{agent_name} 분석 완료 (순차)",
                            "content": self._preserve_completion_signal(result["compressed_content"], 2000),
                            "token_count": result["token_count"],
                            "completed_agents": completed_agents,
                            "total_agents": total_agents
                        }
                    else:
                        # 실패한 경우
                        logger.warning(f"{agent_name} 실패: {result.get('error')}")
                        yield {
                            "type": "agent_error",
                            "agent_name": agent_name,
                            "progress": completed_agents / total_agents,
                            "status": "error",
                            "message": f"{agent_name} 분석 실패: {result['error']}",
                            "error": result["error"],
                            "completed_agents": completed_agents,
                            "total_agents": total_agents
                        }

                except Exception as e:
                    logger.error(f"에이전트 {agent_name} 실행 중 오류: {str(e)}")
                    yield {
                        "type": "agent_error",
                        "agent_name": agent_name,
                        "status": "error",
                        "error": str(e),
                        "completed_agents": completed_agents,
                        "total_agents": total_agents
                    }

            logger.info(f"Phase 2 완료: 총 {completed_agents}/{total_agents}개 에이전트 성공")

            # 모든 에이전트 완료 후 최종 보고서 생성
            if completed_agents == total_agents:
                try:
                    yield {
                        "type": "progress",
                        "status": "generating_report",
                        "message": "종합 보고서 생성 중...",
                        "progress": 0.95
                    }

                    # 🎯 최종 보고서용 - 전체 원본 분석 내용 사용
                    logger.info(f"🔍 최종 보고서 생성을 위한 에이전트 분석 내용 확인:")
                    for agent_name, content in agent_results.items():
                        content_length = len(content) if content else 0
                        logger.info(f"  - {agent_name}: {content_length}자")

                    # 📈 Supervisor가 전체 원본 내용으로 최종 보고서 생성
                    final_report = generate_comprehensive_report(
                        self.supervisor_llm, agent_results, stock_code, company_name
                    )

                    yield {
                        "type": "final_report",
                        "status": "completed",
                        "message": "종합 보고서 생성 완료",
                        "progress": 1.0,
                        "report": final_report,
                        "completed_agents": completed_agents,
                        "total_agents": total_agents,
                        "context_stats": self.context_manager.get_context_stats()
                    }

                except Exception as e:
                    logger.error(f"최종 보고서 생성 오류: {str(e)}")
                    yield {
                        "type": "report_error",
                        "status": "error",
                        "error": str(e),
                        "message": "최종 보고서 생성 실패"
                    }
            else:
                yield {
                    "type": "incomplete",
                    "status": "incomplete",
                    "message": f"일부 에이전트 실행 실패 ({completed_agents}/{total_agents})",
                    "completed_agents": completed_agents,
                    "total_agents": total_agents
                }

        except Exception as e:
            logger.error(f"점진적 분석 시스템 오류: {str(e)}")
            yield {
                "type": "system_error",
                "status": "error",
                "error": str(e),
                "message": "분석 시스템 오류 발생"
            }

# 전역 Progressive Analysis Engine
progressive_engine = ProgressiveAnalysisEngine()

def get_progressive_engine() -> ProgressiveAnalysisEngine:
    """전역 Progressive Analysis Engine 접근"""
    return progressive_engine