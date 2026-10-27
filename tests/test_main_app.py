"""main.py가 분석 스트림을 소비하는 경로를 Streamlit AppTest로 끝까지 돌린다.

진행형 엔진만 가짜로 바꾸고 core.korean_supervisor_langgraph.stream_korean_stock_analysis의
실제 변환을 거치므로, 화면이 받는 chunk 모양은 운영 경로와 같다. LLM·네트워크는 쓰지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from core.signals import AGENT_TO_SIGNAL, MIN_AGENTS_FOR_REPORT
from ui.cards import get_agent_config

MAIN = str(Path(__file__).resolve().parents[1] / "main.py")
TOTAL = len(AGENT_TO_SIGNAL)
STATE_KEYS = ("final_report", "investment_opinion", "chat_session", "analysis_completed", "analysis_agents")


class _FakeEngine:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    def stream_progressive_analysis(self, *_a: Any, **_kw: Any) -> Iterator[dict[str, Any]]:
        yield from self._events


def _agent_events(grounded: list[str], no_data: list[str], empty: tuple[str, ...] = ()) -> list[dict]:
    """grounded·no_data는 응답한 에이전트, 나머지는 실행 실패. empty는 완료 신호만 낸 에이전트."""
    events: list[dict] = []
    done = 0
    for name in AGENT_TO_SIGNAL:
        events.append({"type": "progress", "agent_name": name, "status": "starting", "progress": 0.0})
        if name in grounded or name in no_data:
            done += 1
            body = "" if name in empty else f"{name} 분석 본문 " * 20
            events.append(
                {
                    "type": "agent_complete",
                    "agent_name": name,
                    "progress": done / TOTAL,
                    "content": body + AGENT_TO_SIGNAL[name].value,
                    "agent_status": {
                        "status": "success",
                        "data_status": "sufficient" if name in grounded else "none",
                    },
                    "completed_agents": done,
                    "total_agents": TOTAL,
                }
            )
        else:
            events.append(
                {
                    "type": "agent_error",
                    "agent_name": name,
                    "error": "429 Too Many Requests",
                    "message": f"{name} 분석 실패",
                    "completed_agents": done,
                    "total_agents": TOTAL,
                }
            )
    return events


def _excluded(grounded: list[str]) -> dict[str, str]:
    return {name: "실행 실패: 429 Too Many Requests" for name in AGENT_TO_SIGNAL if name not in grounded}


def _final_report(grounded: list[str]) -> dict:
    return {
        "type": "final_report",
        "report": "# 종합 보고서\n\n" + "근거 있는 분석을 종합한 본문. " * 20,
        "completed_agents": len(grounded),
        "total_agents": TOTAL,
        "excluded": _excluded(grounded),
        "agent_statuses": {name: {"status": "success"} for name in grounded},
    }


def _unset(at: AppTest, key: str) -> bool:
    return key not in at.session_state or not at.session_state[key]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import agents.korean_investment_opinion_agent as opinion_mod
    import core.chat_session as chat_mod
    import core.progressive_supervisor as progressive_mod
    import data.chart_generator as chart_mod
    import data.naver_api_client as naver_mod
    import utils.helpers as helpers_mod
    import utils.logging_context as logging_context_mod

    monkeypatch.setattr(helpers_mod, "setup_logging", lambda *_a, **_kw: logging.getLogger("main-apptest"))
    monkeypatch.setattr(logging_context_mod, "configure_logging", lambda *_a, **_kw: None)
    monkeypatch.setattr(naver_mod, "fetch_naver_news_for_display", lambda *_a, **_kw: [])
    monkeypatch.setattr(chart_mod, "create_stock_chart", lambda *_a, **_kw: None)

    opinion = MagicMock()
    opinion.invoke.return_value = {
        "company_name": "삼성전자",
        "stock_code": "005930",
        "opinion": "HOLD",
        "confidence": 55,
        "reasoning": "근거 있는 분석 종합",
        "key_positives": ["실적"],
        "key_risks": ["환율"],
        "timeframe": "중기(3-6개월)",
        "current_price": 70000,
        "target_price": 75000,
        "stop_loss": 65000,
        "risk_reward_ratio": 1.0,
        "split_buy_strategy": [],
        "timestamp": "2026-10-27T10:00:00+09:00",
    }
    monkeypatch.setattr(opinion_mod, "generate_investment_opinion", opinion)
    chat = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(chat_mod, "create_chat_session", chat)

    def run(events: list[dict], seed: dict[str, Any] | None = None) -> AppTest:
        monkeypatch.setattr(progressive_mod, "get_progressive_engine", lambda: _FakeEngine(events))
        at = AppTest.from_file(MAIN, default_timeout=60)
        at.run()
        for key, value in (seed or {}).items():
            at.session_state[key] = value
        at.button(key="popular_005930").click().run()
        assert not at.exception
        return at

    return {"run": run, "opinion": opinion, "chat": chat}


def test_report_error_stores_nothing_and_skips_opinion_and_chat(app: dict[str, Any]) -> None:
    grounded = list(AGENT_TO_SIGNAL)[:6]
    events = _agent_events(grounded, no_data=[]) + [
        {"type": "report_error", "status": "error", "error": "보고서 LLM 호출 실패: 429", "message": "실패"}
    ]

    at = app["run"](events, seed={"final_report": "## 이전 분석의 보고서"})

    errors = [e.value for e in at.error]
    assert any("종합 보고서를 만들지 못했습니다" in e and "보고서 LLM 호출 실패: 429" in e for e in errors)
    app["opinion"].invoke.assert_not_called()
    app["chat"].assert_not_called()
    for key in STATE_KEYS:
        assert _unset(at, key), key
    texts = [str(at.session_state[k]) for k in STATE_KEYS if k in at.session_state]
    assert not any("보고서 생성 오류" in text for text in texts)


def test_success_passes_only_grounded_agents_and_keeps_exclusions_after_rerun(app: dict[str, Any]) -> None:
    grounded = [
        "context_expert",
        "sentiment_expert",
        "financial_expert",
        "advanced_technical_expert",
        "institutional_trading_expert",
        "global_market_expert",
    ]
    no_data = ["community_expert"]
    events = _agent_events(grounded, no_data) + [_final_report(grounded)]

    at = app["run"](events)

    # After _finalize_analysis reruns the script, the results tab is what remains on screen.
    assert len(at.tabs) == 2
    assert at.session_state["final_report"].startswith("# 종합 보고서")
    excluded = set(AGENT_TO_SIGNAL) - set(grounded)
    assert set(at.session_state["analysis_excluded"]) == excluded
    assert "analysis_agent_statuses" in at.session_state
    warnings = "\n".join(w.value for w in at.warning)
    assert "종합 보고서에 반영되지 않았습니다" in warnings
    for name in excluded:
        assert get_agent_config(name)["name"] in warnings
    cards = "\n".join(m.value for m in at.markdown)
    assert get_agent_config("global_market_expert")["name"] in cards

    agent_results = app["opinion"].invoke.call_args.args[0]["agent_results"]
    assert set(agent_results) == set(grounded)
    chat_args, chat_kwargs = app["chat"].call_args
    assert set(chat_args[2]) == set(grounded)
    assert set(chat_kwargs["excluded"]) == excluded


def test_opinion_gate_counts_sections_actually_passed(app: dict[str, Any]) -> None:
    grounded = list(AGENT_TO_SIGNAL)[:MIN_AGENTS_FOR_REPORT]
    events = _agent_events(grounded, no_data=[], empty=(grounded[0],)) + [_final_report(grounded)]

    at = app["run"](events)

    app["opinion"].invoke.assert_not_called()
    app["chat"].assert_not_called()
    assert _unset(at, "analysis_completed")
    assert _unset(at, "final_report")
    assert any(f"{MIN_AGENTS_FOR_REPORT - 1}개" in w.value for w in at.warning)
