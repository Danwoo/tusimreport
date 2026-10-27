#!/usr/bin/env python3
"""
Progressive Multi-Agent Analysis System
컨텍스트 길이 제한을 해결하는 점진적 분석 시스템
"""

import logging
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.agent_status import data_status, summarize_tool_messages
from core.context_manager import get_context_manager
from core.korean_supervisor_langgraph import (
    create_all_agents,
    generate_comprehensive_report,
    get_supervisor_llm,
)
from core.run_metrics import CallStats, RunMetricsCallback
from core.signals import AGENT_TO_SIGNAL, ALL_AGENT_SIGNALS, MIN_AGENTS_FOR_REPORT
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


class ProgressiveAnalysisEngine:
    """점진적 분석 엔진 - 메모리 효율적 멀티 에이전트 실행"""

    def __init__(self):
        self.context_manager = get_context_manager()
        self.supervisor_llm = get_supervisor_llm()
        self.agents = create_all_agents()

        # 서로의 결과가 필요 없는 7개는 병렬로, 앞선 결과를 참고하는 2개는 그 뒤에 순차로 실행한다.
        self.parallel_agents = [
            "context_expert",  # 시장환경 (독립적)
            "sentiment_expert",  # 뉴스여론 (독립적)
            "advanced_technical_expert",  # 기술분석 (독립적)
            "institutional_trading_expert",  # 기관수급 (독립적)
            "esg_expert",  # ESG분석 (독립적)
            "community_expert",  # 커뮤니티 (독립적)
            "global_market_expert",  # 글로벌시장 (독립적)
        ]

        # 순차 실행 필요한 의존적 에이전트 (2개)
        self.sequential_agents = [
            "financial_expert",  # 재무분석 (DART API 의존)
            "comparative_expert",  # 상대평가 (재무 결과 참고 가능)
        ]

        # 전체 실행 순서 (레거시 호환성 유지)
        self.execution_order = self.parallel_agents + self.sequential_agents

        # Thread-safe 결과 저장소
        self.results_lock = threading.Lock()

        logger.info("Progressive Analysis Engine 초기화 완료 (병렬 7개, 순차 2개)")
        logger.info(f"  - 병렬 실행: {len(self.parallel_agents)}개 에이전트 (global_market 추가)")
        logger.info(f"  - 순차 실행: {len(self.sequential_agents)}개 에이전트")

    def execute_agent_with_context_control(
        self,
        agent_name: str,
        stock_code: str,
        company_name: str,
        previous_summaries: dict[str, str] | None = None,
        callbacks: list | None = None,
    ) -> dict[str, Any]:
        """컨텍스트 제어하에 단일 에이전트 실행.

        결과의 status는 '에이전트가 예외 없이 응답했는가'만 뜻한다. 도구가 실제 근거
        데이터를 돌려줬는지는 data_status·tool_summary로, 호출·토큰은 metrics로 따로 담는다.
        """
        metrics = RunMetricsCallback()
        started = time.monotonic()
        try:
            logger.info(f"에이전트 실행 시작: {agent_name}")

            stats = self.context_manager.get_context_stats()
            logger.info(f"컨텍스트 상태: {stats['available_tokens']:,} 토큰 사용 가능")

            agent = self.agents.get(agent_name)
            if not agent:
                raise ValueError(f"에이전트를 찾을 수 없음: {agent_name}")

            context_info = ""
            if previous_summaries:
                key_summaries = []
                for prev_agent, summary in previous_summaries.items():
                    preserved_content = self.context_manager.preserve_agent_output(prev_agent, summary)
                    key_summaries.append(f"[{prev_agent}]: {preserved_content}")

                context_info = "\n".join(key_summaries)

            analysis_request = self._create_targeted_request(
                agent_name, stock_code, company_name, context_info
            )

            result = agent.invoke(
                {"messages": [{"role": "user", "content": analysis_request}]},
                config={"callbacks": [metrics, *(callbacks or [])]},
            )

            if "messages" in result and result["messages"]:
                last_message = result["messages"][-1]
                content = last_message.content if hasattr(last_message, "content") else str(last_message)

                expected_signal = AGENT_TO_SIGNAL.get(agent_name)
                expected_signal_str = expected_signal.value if expected_signal else None
                is_complete = bool(expected_signal_str) and expected_signal_str in content

                # 신호 누락은 로깅만. 자동 추가로 실패를 성공으로 위장하지 않는다.
                if not is_complete and expected_signal_str:
                    logger.warning(
                        f"{agent_name}: completion signal '{expected_signal_str}' 누락. "
                        f"content_len={len(content)}. 결과는 보존하되 is_complete=False로 표시."
                    )

                compressed_content = self.context_manager.preserve_agent_output(agent_name, content)
                tool_summary = summarize_tool_messages(result["messages"])

                logger.info(
                    f"✅ {agent_name} 실행 완료 (완료 시그널: {is_complete}, "
                    f"데이터: {data_status(tool_summary)}, 도구 {tool_summary.to_dict()})"
                )

                return {
                    "agent_name": agent_name,
                    "status": "success",
                    "content": content,
                    "compressed_content": compressed_content,
                    "is_complete": is_complete,
                    "data_status": data_status(tool_summary),
                    "tool_summary": tool_summary.to_dict(),
                    "token_count": self.context_manager.count_tokens(content),
                    "metrics": metrics.stats.to_dict(),
                    "elapsed_s": round(time.monotonic() - started, 2),
                    "timestamp": kst_isoformat(),
                }
            else:
                raise ValueError(f"에이전트 응답이 비어있음: {agent_name}")

        except Exception as e:
            logger.error(f"❌ {agent_name} 실행 실패: {str(e)}")
            return {
                "agent_name": agent_name,
                "status": "error",
                "error": str(e),
                "metrics": metrics.stats.to_dict(),
                "elapsed_s": round(time.monotonic() - started, 2),
                "timestamp": kst_isoformat(),
            }

    def _create_targeted_request(
        self, agent_name: str, stock_code: str, company_name: str, context_info: str = ""
    ) -> str:
        """에이전트별 맞춤형 요청 메시지 생성"""

        base_requests = {
            "context_expert": f"종목 {stock_code} ({company_name})에 대한 시장 환경 및 거시경제 분석을 수행해주세요.",
            "sentiment_expert": f"종목 {stock_code} ({company_name})에 대한 뉴스 및 시장 심리 분석을 수행해주세요.",
            "financial_expert": f"종목 {stock_code} ({company_name})에 대한 재무제표 및 기업 분석을 수행해주세요.",
            "advanced_technical_expert": f"종목 {stock_code} ({company_name})에 대한 고급 기술적 분석을 수행해주세요.",
            "institutional_trading_expert": f"종목 {stock_code} ({company_name})에 대한 기관 수급 분석을 수행해주세요.",
            "comparative_expert": f"종목 {stock_code} ({company_name})에 대한 동종업계 상대 평가를 수행해주세요.",
            "esg_expert": f"종목 {stock_code} ({company_name})에 대한 ESG 및 지속가능성 분석을 수행해주세요.",
            "community_expert": f"종목 {stock_code} ({company_name})에 대한 투자자 커뮤니티 여론 분석을 수행해주세요.",
            "global_market_expert": f"종목 {stock_code} ({company_name})에 영향을 주는 글로벌 시장 환경을 분석해주세요.",
        }

        request = base_requests.get(agent_name, f"종목 {stock_code}에 대한 분석을 수행해주세요.")

        # 🎯 컨텍스트 정보 최적화 - 토큰 한계 고려
        if context_info and len(context_info) > 0:
            # 컨텍스트 토큰 수 확인
            context_tokens = self.context_manager.count_tokens(context_info)
            if context_tokens > 50000:  # 5만 토큰 초과시 앞부분만 사용
                # 앞부분 70% + 뒷부분 30% 조합으로 중요 정보 보존
                context_lines = context_info.split("\n")
                front_70 = context_lines[: int(len(context_lines) * 0.7)]
                back_30 = context_lines[-int(len(context_lines) * 0.3) :]
                context_info = "\n".join(front_70 + ["..."] + back_30)

            request += f"\n\n참고 정보:\n{context_info}"

        return request

    def _preserve_completion_signal(self, content: str, max_length: int = 2000) -> str:
        """완료 신호를 보존하면서 콘텐츠 길이를 제한합니다."""
        if len(content) <= max_length:
            return content

        # 완료 신호가 있는지 확인하고 위치 찾기 (단일 enum 소스)
        signal_info = None
        for signal in ALL_AGENT_SIGNALS:
            if signal in content:
                signal_pos = content.find(signal)
                signal_info = (signal, signal_pos)
                break

        if signal_info:
            signal, signal_pos = signal_info
            # 신호 주변 텍스트를 포함하여 자르기 (앞부분 + 신호 부분)
            if signal_pos > max_length - 100:  # 신호가 뒤쪽에 있으면
                # 앞부분 일부 + ... + 신호 부분
                front_part = content[: max_length - 200]
                signal_part = content[signal_pos - 50 : signal_pos + len(signal) + 10]
                return front_part + "...\n\n" + signal_part
            else:
                # 신호가 앞쪽에 있으면 그대로 자르기
                return content[:max_length]
        else:
            # 완료 신호가 없으면 그대로 자르기
            return content[:max_length] + "..."

    def stream_progressive_analysis(
        self, stock_code: str, company_name: str | None = None, callbacks: list | None = None
    ) -> Generator[dict[str, Any], None, None]:
        """병렬 7개 → 순차 2개 → 종합 보고서.

        보고서는 근거 데이터가 있는 에이전트가 MIN_AGENTS_FOR_REPORT개 이상일 때만 만든다.
        실행에 실패했거나 근거 데이터가 없는 에이전트는 보고서 입력에서 빼고, 그 이유를
        보고서 프롬프트와 이벤트(excluded)에 남긴다.
        """
        try:
            company_name = company_name or stock_code
            logger.info("=== 병렬 실행 모드 분석 시작 ===")
            logger.info(f"종목: {stock_code} ({company_name})")

            agent_results: dict[str, str] = {}
            agent_summaries: dict[str, str] = {}
            agent_statuses: dict[str, dict[str, Any]] = {}
            totals = CallStats()
            completed_agents = 0
            total_agents = len(self.execution_order)

            def record(result: dict[str, Any]) -> dict[str, Any]:
                if "metrics" in result:
                    totals.merge(CallStats(**result["metrics"]))
                status = {
                    "status": result.get("status", "error"),
                    "data_status": result.get("data_status", "none"),
                    "is_complete": result.get("is_complete", False),
                    "tool_summary": result.get("tool_summary", {}),
                    "error": result.get("error"),
                    "elapsed_s": result.get("elapsed_s"),
                }
                agent_statuses[result["agent_name"]] = status
                return status

            def run_events(agent_name: str, result: dict[str, Any]) -> dict[str, Any]:
                nonlocal completed_agents
                status = record(result)
                if result["status"] == "success":
                    with self.results_lock:
                        agent_results[agent_name] = result["content"]
                        agent_summaries[agent_name] = result["compressed_content"]
                        completed_agents += 1
                    return {
                        "type": "agent_complete",
                        "agent_name": agent_name,
                        "progress": completed_agents / total_agents,
                        "status": "completed",
                        "message": f"{agent_name} 분석 완료",
                        "content": self._preserve_completion_signal(result["compressed_content"], 2000),
                        "token_count": result["token_count"],
                        "agent_status": status,
                        "completed_agents": completed_agents,
                        "total_agents": total_agents,
                    }
                logger.warning(f"{agent_name} 실패: {result.get('error')}")
                return {
                    "type": "agent_error",
                    "agent_name": agent_name,
                    "progress": completed_agents / total_agents,
                    "status": "error",
                    "message": f"{agent_name} 분석 실패: {result.get('error')}",
                    "error": result.get("error"),
                    "agent_status": status,
                    "completed_agents": completed_agents,
                    "total_agents": total_agents,
                }

            def starting(agent_name: str) -> dict[str, Any]:
                return {
                    "type": "progress",
                    "agent_name": agent_name,
                    "progress": completed_agents / total_agents,
                    "status": "starting",
                    "message": f"{agent_name} 분석 시작 중...",
                    "completed_agents": completed_agents,
                    "total_agents": total_agents,
                }

            # === Phase 1: 병렬 실행 (독립적 에이전트) ===
            logger.info(f"Phase 1: {len(self.parallel_agents)}개 에이전트 병렬 실행 시작")
            with ThreadPoolExecutor(max_workers=len(self.parallel_agents)) as executor:
                future_to_agent = {}
                for agent_name in self.parallel_agents:
                    future = executor.submit(
                        self.execute_agent_with_context_control,
                        agent_name,
                        stock_code,
                        company_name,
                        {},  # 병렬 에이전트는 서로 독립적이므로 컨텍스트 없음
                        callbacks,
                    )
                    future_to_agent[future] = agent_name
                    yield starting(agent_name)

                for future in as_completed(future_to_agent):
                    agent_name = future_to_agent[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        logger.error(f"에이전트 {agent_name} 실행 중 오류: {str(e)}")
                        result = {"agent_name": agent_name, "status": "error", "error": str(e)}
                    yield run_events(agent_name, result)

            logger.info(f"Phase 1 완료: {completed_agents}/{len(self.parallel_agents)}개 성공")

            # === Phase 2: 순차 실행 (병렬 결과를 참고 정보로 받는 2개) ===
            logger.info(f"Phase 2: {len(self.sequential_agents)}개 에이전트 순차 실행 시작")
            for agent_name in self.sequential_agents:
                yield starting(agent_name)
                try:
                    result = self.execute_agent_with_context_control(
                        agent_name, stock_code, company_name, agent_summaries, callbacks
                    )
                except Exception as e:
                    logger.error(f"에이전트 {agent_name} 실행 중 오류: {str(e)}")
                    result = {"agent_name": agent_name, "status": "error", "error": str(e)}
                yield run_events(agent_name, result)

            logger.info(f"Phase 2 완료: 총 {completed_agents}/{total_agents}개 에이전트 성공")

            grounded = [
                name
                for name in self.execution_order
                if agent_statuses.get(name, {}).get("status") == "success"
                and agent_statuses[name]["data_status"] != "none"
            ]
            excluded: dict[str, str] = {}
            for name in self.execution_order:
                status = agent_statuses.get(name)
                if status is None or status["status"] != "success":
                    reason = (status or {}).get("error") or "결과 없음"
                    excluded[name] = f"실행 실패: {reason}"[:200]
                elif status["data_status"] == "none":
                    excluded[name] = "근거 데이터 없음 (도구 결과가 비었거나 모두 실패)"

            if len(grounded) < MIN_AGENTS_FOR_REPORT:
                yield {
                    "type": "incomplete",
                    "status": "incomplete",
                    "message": (
                        f"근거 데이터가 있는 분석이 {len(grounded)}/{total_agents}개로 "
                        f"보고서 기준({MIN_AGENTS_FOR_REPORT}개)에 못 미칩니다"
                    ),
                    "completed_agents": completed_agents,
                    "total_agents": total_agents,
                    "excluded": excluded,
                    "agent_statuses": agent_statuses,
                    "metrics": totals.to_dict(),
                }
                return

            try:
                yield {
                    "type": "progress",
                    "status": "generating_report",
                    "message": "종합 보고서 생성 중...",
                    "progress": 0.95,
                }
                report_metrics = RunMetricsCallback()
                final_report = generate_comprehensive_report(
                    self.supervisor_llm,
                    {name: agent_results[name] for name in grounded},
                    stock_code,
                    company_name,
                    excluded=excluded,
                    callbacks=[report_metrics, *(callbacks or [])],
                )
                totals.merge(report_metrics.stats)

                yield {
                    "type": "final_report",
                    "status": "completed",
                    "message": "종합 보고서 생성 완료",
                    "progress": 1.0,
                    "report": final_report,
                    "completed_agents": completed_agents,
                    "total_agents": total_agents,
                    "grounded_agents": grounded,
                    "excluded": excluded,
                    "agent_statuses": agent_statuses,
                    "metrics": totals.to_dict(),
                    "context_stats": self.context_manager.get_context_stats(),
                }

            except Exception as e:
                logger.error(f"최종 보고서 생성 오류: {str(e)}")
                yield {
                    "type": "report_error",
                    "status": "error",
                    "error": str(e),
                    "message": "최종 보고서 생성 실패",
                }

        except Exception as e:
            logger.error(f"점진적 분석 시스템 오류: {str(e)}")
            yield {
                "type": "system_error",
                "status": "error",
                "error": str(e),
                "message": "분석 시스템 오류 발생",
            }


# Lazy 전역 Progressive Analysis Engine (import 시점 LLM/에이전트 빌드 회피)
_progressive_engine: "ProgressiveAnalysisEngine | None" = None
_engine_init_lock = threading.Lock()


def get_progressive_engine() -> ProgressiveAnalysisEngine:
    """전역 Progressive Analysis Engine 접근 (thread-safe lazy singleton).

    동시에 첫 호출이 들어와도 에이전트/LLM이 두 번 빌드되지 않도록
    double-checked locking 패턴을 사용한다 (LLM 빌드는 비용이 크다).
    """
    global _progressive_engine
    if _progressive_engine is None:
        with _engine_init_lock:
            if _progressive_engine is None:
                _progressive_engine = ProgressiveAnalysisEngine()
    return _progressive_engine


def __getattr__(name):
    """PEP 562: `progressive_engine` 직접 접근 시 lazy 빌드."""
    if name == "progressive_engine":
        return get_progressive_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
