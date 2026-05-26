"""ProgressiveAnalysisEngine.execute_agent_with_context_control 통합 테스트.

LangGraph agent의 .invoke()를 mock해서 ReAct loop 전체 path를 검증한다:
- 완료 신호가 응답에 있을 때 is_complete=True
- 신호 누락 시 is_complete=False (결과는 보존, raise하지 않음)
- 에이전트가 raise할 때 dict로 graceful 변환
- 이전 에이전트 요약이 context_info에 포함되는지
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from core.progressive_supervisor import ProgressiveAnalysisEngine
from core.signals import AgentSignal


def _make_engine_with_fake_agent(
    monkeypatch: pytest.MonkeyPatch,
    agent_response_content: str,
    agent_name: str = "context_expert",
) -> ProgressiveAnalysisEngine:
    """`create_all_agents`가 단일 agent dict를 돌려주도록 patch."""

    fake_agent = MagicMock()
    response_message = MagicMock()
    response_message.content = agent_response_content
    fake_agent.invoke.return_value = {"messages": [response_message]}

    monkeypatch.setattr("core.progressive_supervisor.get_supervisor_llm", lambda: MagicMock())
    monkeypatch.setattr(
        "core.progressive_supervisor.create_all_agents",
        lambda: {agent_name: fake_agent},
    )
    # context manager는 진짜 인스턴스 사용 (count_tokens 실제로 동작)
    return ProgressiveAnalysisEngine()


class TestExecuteAgentWithContextControl:
    def test_completion_signal_present_marks_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = "Market context analysis 완료. " * 50 + AgentSignal.CONTEXT.value
        engine = _make_engine_with_fake_agent(monkeypatch, body, "context_expert")

        result = engine.execute_agent_with_context_control("context_expert", "005930", "삼성전자")
        assert result["status"] == "success"
        assert result["is_complete"] is True
        # 완료 신호가 잘 살아 있는지
        assert AgentSignal.CONTEXT.value in result["content"]
        # token_count는 int
        assert isinstance(result["token_count"], int)
        # ISO timestamp +09:00 KST
        assert "+09:00" in result["timestamp"]

    def test_missing_completion_signal_still_succeeds_with_flag_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """완료 신호가 없어도 결과는 보존하되 is_complete=False.

        '자동 신호 추가로 실패를 성공으로 위장하지 않는다'는 정책의 회귀 방지.
        """
        body = "분석 결과는 있지만 끝맺음 마커가 빠졌다 " * 50
        engine = _make_engine_with_fake_agent(monkeypatch, body, "context_expert")

        result = engine.execute_agent_with_context_control("context_expert", "005930", "삼성전자")
        assert result["status"] == "success"
        assert result["is_complete"] is False
        # 컨텐츠는 보존
        assert "분석 결과" in result["content"]

    def test_unknown_agent_returns_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`create_all_agents`에 없는 에이전트 이름은 'agent_error' status."""
        engine = _make_engine_with_fake_agent(monkeypatch, "x", "context_expert")
        result = engine.execute_agent_with_context_control("nonexistent_expert", "005930", "삼성전자")
        assert result["status"] == "error"
        assert "nonexistent_expert" in result.get("error", "")

    def test_agent_invoke_raises_wraps_in_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_engine_with_fake_agent(monkeypatch, "ignored", "context_expert")
        # invoke를 raise하도록 교체
        engine.agents["context_expert"].invoke.side_effect = RuntimeError("LLM down")

        result = engine.execute_agent_with_context_control("context_expert", "005930", "삼성전자")
        # graceful: status='error', 메시지에 원인 echo
        assert result["status"] == "error"
        assert "LLM down" in result.get("error", "")

    def test_previous_summaries_flow_into_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """previous_summaries가 있으면 analysis_request에 [prev_agent]: 형식으로 포함."""
        body = "응답 본문 " * 50 + AgentSignal.SENTIMENT.value
        engine = _make_engine_with_fake_agent(monkeypatch, body, "sentiment_expert")

        prev = {"context_expert": "macro context 양호 (KOSPI 상승)"}
        engine.execute_agent_with_context_control(
            "sentiment_expert", "005930", "삼성전자", previous_summaries=prev
        )

        # 가짜 agent.invoke가 어떤 메시지를 받았는지 확인
        called_args, called_kwargs = engine.agents["sentiment_expert"].invoke.call_args
        invoked_input = called_args[0] if called_args else called_kwargs
        # input dict의 messages[0].content에 이전 요약이 포함되어 있어야
        user_msg = invoked_input["messages"][0]["content"]
        assert "[context_expert]:" in user_msg
        assert "macro context 양호" in user_msg

    def test_empty_response_messages_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """agent.invoke가 messages=[] 빈 응답을 돌려주면 error."""
        fake_agent = MagicMock()
        fake_agent.invoke.return_value = {"messages": []}

        monkeypatch.setattr("core.progressive_supervisor.get_supervisor_llm", lambda: MagicMock())
        monkeypatch.setattr(
            "core.progressive_supervisor.create_all_agents",
            lambda: {"context_expert": fake_agent},
        )
        engine = ProgressiveAnalysisEngine()

        result = engine.execute_agent_with_context_control("context_expert", "005930", "삼성전자")
        assert result["status"] == "error"
        assert "비어있음" in result.get("error", "") or "empty" in result.get("error", "").lower()


class TestProgressiveStreamMixedExecution:
    """stream_progressive_analysis 자체를 한 번 더 — 이번엔 진짜 ProgressiveAnalysisEngine을
    초기화하고 모든 9개 에이전트를 fake로 갈아 끼워서 실제 phase 1/2 로직을 통과시킨다."""

    def test_all_agents_succeed_yields_final_report(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 9개 에이전트 전부 같은 패턴으로 응답 — 각자 자기 signal 붙임
        def make_fake_agent(signal: AgentSignal) -> MagicMock:
            agent = MagicMock()
            resp = MagicMock()
            resp.content = "분석 결과 " * 50 + signal.value
            agent.invoke.return_value = {"messages": [resp]}
            return agent

        from core.signals import AGENT_TO_SIGNAL

        fakes = {name: make_fake_agent(sig) for name, sig in AGENT_TO_SIGNAL.items()}
        monkeypatch.setattr("core.progressive_supervisor.get_supervisor_llm", lambda: MagicMock())
        monkeypatch.setattr("core.progressive_supervisor.create_all_agents", lambda: fakes)

        # generate_comprehensive_report도 mock (LLM 호출 없이 결정론적 응답)
        def fake_report(*_a: Any, **_kw: Any) -> str:
            return "# 종합 보고서\n\nBUY 75% 신뢰도"

        monkeypatch.setattr("core.progressive_supervisor.generate_comprehensive_report", fake_report)

        engine = ProgressiveAnalysisEngine()
        events = list(engine.stream_progressive_analysis("005930", "삼성전자"))

        # 진행/완료/최종 이벤트가 한 번씩이라도 나왔는지
        types = [e["type"] for e in events]
        assert "progress" in types  # starting alert
        assert "agent_complete" in types  # 9개 에이전트 완료
        assert "final_report" in types

        # 9개 모두 완료됐는지
        completions = [e for e in events if e["type"] == "agent_complete"]
        assert len(completions) == 9

        # 최종 보고서가 stub 응답인지
        final = next(e for e in events if e["type"] == "final_report")
        assert "BUY 75%" in final["report"]
