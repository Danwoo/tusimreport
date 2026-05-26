"""Supervisor stream end-to-end 통합 테스트.

ProgressiveAnalysisEngine을 stub로 갈아 끼우고 stream_korean_stock_analysis를
끝까지 돌려, supervisor → UI로 흐르는 payload(running_agent 키 포함)와
final_report 처리가 정확한지 검증.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from core import korean_supervisor_langgraph as supervisor_mod
from core.korean_supervisor_langgraph import (
    AGENT_STAGES,
    generate_comprehensive_report,
    stream_korean_stock_analysis,
)


class FakeProgressiveEngine:
    """ProgressiveAnalysisEngine 대용. 정해진 이벤트 시퀀스를 그대로 yield."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    def stream_progressive_analysis(self, *_a: Any, **_kw: Any) -> Iterator[dict[str, Any]]:
        yield from self._events


def _install_fake_engine(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
    """`get_progressive_engine`가 FakeProgressiveEngine을 돌려주도록 patch.

    progressive_supervisor 자체를 import하지 않고도 supervisor 스트림을
    end-to-end로 실행할 수 있게 한다.
    """
    fake = FakeProgressiveEngine(events)

    def _get_engine() -> Any:
        return fake

    # stream_korean_stock_analysis는 `from core.progressive_supervisor import
    # get_progressive_engine`를 함수 안에서 import한다 → 그 모듈 자체에 patch.
    import core.progressive_supervisor as progressive_mod

    monkeypatch.setattr(progressive_mod, "get_progressive_engine", _get_engine)


class TestStreamKoreanStockAnalysis:
    def test_agent_complete_yields_supervisor_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """agent_complete 이벤트 → current_stage(한글)와 progress가 들어간 supervisor dict."""
        events = [
            {
                "type": "agent_complete",
                "agent_name": "context_expert",
                "progress": 0.11,
                "content": "macro 분석 결과 (1000자)" * 50,
                "completed_agents": 1,
                "total_agents": 9,
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        assert len(chunks) == 1
        sup = chunks[0]["supervisor"]

        assert sup["stock_code"] == "005930"
        assert sup["company_name"] == "삼성전자"
        # AGENT_STAGES 매핑이 한글 라벨로 들어가는지
        expected_label, _ = AGENT_STAGES["context_expert"]
        assert sup["current_stage"] == expected_label
        assert sup["progressive_mode"] is True

    def test_progress_status_starting_carries_running_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """status='starting' progress 이벤트는 running_agent 키를 가져야
        main.py:_handle_running_signal이 카드를 running으로 바꿀 수 있다."""
        events = [
            {
                "type": "progress",
                "agent_name": "sentiment_expert",
                "progress": 0.0,
                "status": "starting",
                "message": "sentiment_expert 분석 시작 중...",
                "completed_agents": 0,
                "total_agents": 9,
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        sup = chunks[0]["supervisor"]
        # 명시적 running_agent 키 — 한글 stage_name substring 매칭의 dead-code
        # 회귀 방지.
        assert sup["running_agent"] == "sentiment_expert"

    def test_progress_status_other_leaves_running_agent_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """status가 'starting'이 아니면 running_agent는 빈 문자열."""
        events = [
            {
                "type": "progress",
                "agent_name": "context_expert",
                "progress": 0.5,
                "status": "in_progress",
                "message": "...",
                "completed_agents": 0,
                "total_agents": 9,
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        assert chunks[0]["supervisor"]["running_agent"] == ""

    def test_final_report_yields_report_chunk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """final_report 이벤트 → final_report_generated 플래그 + 보고서 메시지."""
        events = [
            {
                "type": "final_report",
                "report": "## 투자 의견\n\nBUY 70% 신뢰도 ...",
                "completed_agents": 9,
                "total_agents": 9,
                "context_stats": {"max_tokens": 300_000, "available_tokens": 200_000},
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        sup = chunks[0]["supervisor"]
        assert sup["final_report_generated"] is True
        # 보고서 내용이 messages에 들어가야 main.py가 _extract_final_report로
        # 꺼낼 수 있음
        assert any("BUY" in m["content"] for m in sup["messages"])

    def test_error_event_yields_error_chunk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """agent_error / system_error / report_error 이벤트는 error 키로 전달."""
        events = [
            {
                "type": "system_error",
                "error": "전체 분석 시스템 오류",
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        # main.py가 'error' 키로 분기
        assert "error" in chunks[0]
        assert chunks[0]["error"]["error"] == "전체 분석 시스템 오류"
        assert chunks[0]["error"]["progressive_mode"] is True

    def test_full_event_sequence_streams_in_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """실제 한 종목 분석에 가까운 mixed 시퀀스 — 진행 + 완료 + 최종 보고서."""
        events = [
            {
                "type": "progress",
                "agent_name": "context_expert",
                "progress": 0.0,
                "status": "starting",
                "message": "start",
                "completed_agents": 0,
                "total_agents": 9,
            },
            {
                "type": "agent_complete",
                "agent_name": "context_expert",
                "progress": 0.11,
                "content": "x" * 1000,
                "completed_agents": 1,
                "total_agents": 9,
            },
            {
                "type": "final_report",
                "report": "최종 보고서 본문 " * 100,
                "completed_agents": 9,
                "total_agents": 9,
            },
        ]
        _install_fake_engine(monkeypatch, events)

        chunks = list(stream_korean_stock_analysis("005930", "삼성전자"))
        assert len(chunks) == 3
        # 첫 chunk: running_agent='context_expert'
        assert chunks[0]["supervisor"]["running_agent"] == "context_expert"
        # 두 번째: agent_complete, current_stage 한글 라벨
        assert chunks[1]["supervisor"]["current_stage"] == AGENT_STAGES["context_expert"][0]
        # 마지막: final_report
        assert chunks[2]["supervisor"]["final_report_generated"] is True


class TestGenerateComprehensiveReport:
    def test_assembles_korean_expert_sections(self) -> None:
        """모든 9개 전문가 분석을 받아 LLM 프롬프트에 한글 라벨로 묶는다."""
        # 충분히 긴 분석 입력 — 길이 가드(< 1000자) 통과용
        analyses = {
            "context_expert": "macro context " * 50,
            "sentiment_expert": "뉴스 여론 " * 50,
            "financial_expert": "재무 분석 " * 50,
            "advanced_technical_expert": "기술 " * 50,
            "institutional_trading_expert": "수급 " * 50,
            "comparative_expert": "상대평가 " * 50,
            "esg_expert": "ESG " * 50,
            "community_expert": "커뮤니티 " * 50,
            "global_market_expert": "글로벌 " * 50,
        }
        stub_llm = MagicMock()
        response = MagicMock()
        response.content = "# 종합 보고서\n\n" + ("이 종목은... " * 300)  # 약 3000자
        stub_llm.invoke.return_value = response

        report = generate_comprehensive_report(stub_llm, analyses, "005930", "삼성전자")

        # LLM에 전달된 프롬프트에 9개 한글 전문가 라벨이 모두 들어 있어야
        call_args, _ = stub_llm.invoke.call_args
        prompt = call_args[0]
        for label in [
            "시장·경제 전문가",
            "뉴스·여론 전문가",
            "재무·공시 전문가",
            "기술적 분석 전문가",
            "수급 분석 전문가",
            "상대 가치 전문가",
            "ESG 분석 전문가",
            "커뮤니티 여론 전문가",
            "글로벌 시장 전문가",
        ]:
            assert label in prompt, f"missing 한글 라벨: {label}"

        # 응답이 그대로 돌아오는지
        assert "종합 보고서" in report

    def test_too_few_agents_returns_early(self) -> None:
        """4개 미만의 전문가 분석은 LLM 호출 없이 즉시 '분석 데이터 부족'."""
        stub_llm = MagicMock()
        report = generate_comprehensive_report(
            stub_llm,
            {"context_expert": "x" * 200, "sentiment_expert": "y" * 200},
            "005930",
            "삼성전자",
        )
        assert "분석 데이터 부족" in report
        stub_llm.invoke.assert_not_called()

    def test_too_short_analysis_returns_early(self) -> None:
        """전체 분석 길이가 1000자 미만이면 LLM 호출 전에 'analysis 내용 부족'."""
        stub_llm = MagicMock()
        report = generate_comprehensive_report(
            stub_llm,
            {f"agent_{i}": "x" * 50 for i in range(5)},  # 5개 × 50 = 250자
            "005930",
            "삼성전자",
        )
        assert "분석 내용 부족" in report
        stub_llm.invoke.assert_not_called()

    def test_llm_exception_returns_error_report(self) -> None:
        """LLM이 raise하면 호출자에게 '## 종합 보고서 생성 오류' 마크다운으로."""
        stub_llm = MagicMock()
        stub_llm.invoke.side_effect = RuntimeError("LLM provider rate limit")

        analyses = {f"agent_{i}": "x" * 300 for i in range(9)}
        report = generate_comprehensive_report(stub_llm, analyses, "005930", "삼성전자")
        assert "종합 보고서 생성 오류" in report
        assert "rate limit" in report
