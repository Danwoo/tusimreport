"""single_agent topology를 실제 LangGraph ReAct 루프로 돌려 run_once 레코드를 검증."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from lab import runner, topologies


class FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeToolCallingModel:
        return self


@tool
def fake_price(stock_code: str) -> dict:
    """현재가 조회."""
    return {"stock_code": stock_code, "price": 70000, "per": 12.34}


def _model() -> FakeToolCallingModel:
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    return FakeToolCallingModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "fake_price", "args": {"stock_code": "005930"}, "id": "c1"}],
                    usage_metadata=usage,
                ),
                AIMessage(content="현재가 70,000원, PER 12.3배. 목표가 99,000원.", usage_metadata=usage),
            ]
        )
    )


@pytest.fixture
def fake_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "all_tools", lambda: [fake_price])
    monkeypatch.setattr(topologies, "all_tools", lambda: [fake_price])
    monkeypatch.setattr(topologies, "tool_owner", lambda: {"fake_price": "financial_expert"})
    monkeypatch.setattr("config.llm_factory.build_llm", lambda **_kw: _model())


def test_single_agent_run_record(fake_lab: None, tmp_path: Path) -> None:
    record = runner.run_once("single_agent", "005930", "삼성전자", "record", tmp_path / "snap")

    assert record.succeeded
    assert record.stats["llm_calls"] == 2
    assert record.stats["input_tokens"] == 200
    assert record.stats["tools_used"] == {"fake_price": 1}
    assert record.tool_calls == {"calls": 1, "errors": 0, "with_data": 1, "by_source": {"live": 1}}
    assert record.coverage["agents"] == ["financial_expert"]
    assert record.grounding["checked"] == 3
    assert record.grounding["grounded"] == 2
    assert record.grounding["ungrounded"][0]["number"].startswith("99,000")
    assert (tmp_path / "snap" / "fake_price").is_dir()

    path = runner.save_record(record, tmp_path / "runs", tag="r1")
    assert path.name.endswith("_single_agent_005930_r1.json")


def test_unknown_topology_is_rejected() -> None:
    with pytest.raises(ValueError, match="topology"):
        runner.run_once("swarm", "005930", "삼성전자")


def test_failure_inside_topology_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any) -> Any:
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(runner, "all_tools", lambda: [])
    monkeypatch.setitem(runner.TOPOLOGY_RUNNERS, "progressive", boom)

    record = runner.run_once("progressive", "005930", "삼성전자")

    assert not record.succeeded
    assert record.error == "RuntimeError: 429 rate limit"


def test_supervisor_reports_only_from_grounded_called_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.snapshot import ToolCall, ToolCallRecorder

    called = ["context_expert", "financial_expert", "advanced_technical_expert", "comparative_expert"]
    grounded = called + ["institutional_trading_expert"]

    class FakeGraph:
        def invoke(self, *_a: Any, **_kw: Any) -> dict:
            messages = [
                AIMessage(content=f"{n} 분석", name=n) for n in called + ["institutional_trading_expert"]
            ]
            return {"messages": [AIMessage(content="supervisor 지시"), *messages]}

    owners = {f"tool_{n}": n for n in grounded}
    recorder = ToolCallRecorder("off")
    recorder.calls = [ToolCall(f"tool_{n}", {}, {"value": 1}, None, "live", 0.0) for n in grounded]
    reports: list[dict] = []

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: FakeGraph())
    monkeypatch.setattr(topologies, "tool_owner", lambda: owners)
    monkeypatch.setattr(topologies, "get_supervisor_llm", lambda: None)
    monkeypatch.setattr(
        topologies,
        "generate_comprehensive_report",
        lambda _llm, analyses, *_a, **kw: reports.append({"analyses": analyses, **kw}) or "# 보고서",
    )

    outcome = topologies.run_supervisor("005930", "삼성전자", [], recorder)

    assert outcome.report == "# 보고서"
    assert set(reports[0]["analyses"]) == set(grounded)
    assert "esg_expert" in reports[0]["excluded"]


def test_supervisor_without_enough_grounded_agents_is_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.snapshot import ToolCallRecorder

    class FakeGraph:
        def invoke(self, *_a: Any, **_kw: Any) -> dict:
            return {"messages": [AIMessage(content="재무 분석", name="financial_expert")]}

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: FakeGraph())
    monkeypatch.setattr(topologies, "tool_owner", lambda: {})

    outcome = topologies.run_supervisor("005930", "삼성전자", [], ToolCallRecorder("off"))

    assert outcome.report is None
    assert "0/9" in outcome.notes["incomplete"]
