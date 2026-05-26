"""ProgressiveAnalysisEngine 보조 함수 단위 테스트.

엔진 자체는 LLM/에이전트 초기화 비용이 크므로 인스턴스를 만들지 않고,
완료 신호 보존 로직만 분리해서 검증한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.progressive_supervisor import ProgressiveAnalysisEngine
from core.signals import AgentSignal


@pytest.fixture
def engine_stub(monkeypatch: pytest.MonkeyPatch) -> ProgressiveAnalysisEngine:
    """LLM/에이전트 빌드 비용 없이 method-only stub.

    모든 외부 의존성(get_supervisor_llm, create_all_agents,
    get_context_manager)을 MagicMock으로 우회 — `_preserve_completion_signal`
    같은 순수 메서드만 호출하는 목적이라 init은 통과만 하면 된다.
    """
    monkeypatch.setattr("core.progressive_supervisor.get_supervisor_llm", lambda: MagicMock())
    monkeypatch.setattr("core.progressive_supervisor.create_all_agents", lambda: {})
    monkeypatch.setattr("core.progressive_supervisor.get_context_manager", lambda: MagicMock())
    return ProgressiveAnalysisEngine()


class TestPreserveCompletionSignal:
    def test_short_content_returned_as_is(self, engine_stub: ProgressiveAnalysisEngine) -> None:
        text = "짧은 분석 결과 " + AgentSignal.CONTEXT.value
        assert engine_stub._preserve_completion_signal(text, max_length=2000) == text

    def test_signal_at_end_preserved_after_truncation(self, engine_stub: ProgressiveAnalysisEngine) -> None:
        """긴 응답 끝에 완료 신호가 있어도 잘리지 않고 살아남는다."""
        long_body = "분석 내용 " * 1000  # 길이 5000+
        text = long_body + AgentSignal.CONTEXT.value
        truncated = engine_stub._preserve_completion_signal(text, max_length=2000)
        # 잘렸지만 신호는 살아 있어야 함
        assert AgentSignal.CONTEXT.value in truncated
        assert len(truncated) <= 2000 + 100  # 약간의 오차 허용 (앞부분+신호 결합)

    def test_signal_at_start_kept_via_simple_truncate(self, engine_stub: ProgressiveAnalysisEngine) -> None:
        """신호가 앞쪽이면 그냥 자르면 됨 — 신호가 잘리지 않는지."""
        text = AgentSignal.SENTIMENT.value + "분석 결과 " * 1000
        truncated = engine_stub._preserve_completion_signal(text, max_length=2000)
        assert AgentSignal.SENTIMENT.value in truncated
        assert len(truncated) <= 2000

    def test_no_signal_simple_truncate(self, engine_stub: ProgressiveAnalysisEngine) -> None:
        """완료 신호가 없는 응답은 길이 제한만 적용."""
        text = "no signal " * 1000
        truncated = engine_stub._preserve_completion_signal(text, max_length=500)
        assert len(truncated) <= 510  # `...`만 끝에 붙음
        assert truncated.endswith("...")
