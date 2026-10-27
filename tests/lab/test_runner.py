"""single_agent topology를 실제 LangGraph ReAct 루프로 돌려 run_once 레코드를 검증."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, tool

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
    monkeypatch.setattr(runner, "tool_owner", lambda: {"fake_price": "financial_expert"})
    monkeypatch.setattr(topologies, "tool_owner", lambda: {"fake_price": "financial_expert"})
    monkeypatch.setattr("config.llm_factory.build_llm", lambda **_kw: _model())


def test_single_agent_run_record(fake_lab: None, tmp_path: Path) -> None:
    record = runner.run_once("single_agent", "005930", "삼성전자", "record", tmp_path / "snap")

    assert record.succeeded
    assert record.stats["llm_calls"] == 2
    assert record.stats["input_tokens"] == 200
    assert record.stats["tools_used"] == {"fake_price": 1}
    assert {k: record.tool_calls[k] for k in ("calls", "errors", "with_data", "by_source", "fuzzy")} == {
        "calls": 1,
        "errors": 0,
        "with_data": 1,
        "by_source": {"live": 1},
        "fuzzy": 0,
    }
    assert record.tool_calls["recorded_at"]["min"] == record.tool_calls["recorded_at"]["max"]
    assert record.coverage == {"agents": ["financial_expert"], "ratio": 1 / 9, "basis": "tool_calls"}
    assert record.tool_coverage == record.coverage
    assert record.llm["temperature"] == 0.0
    assert record.notes["step_budget"] == {"graph": 225}
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
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            yield self.invoke(*args, **kwargs)

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
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            yield self.invoke(*args, **kwargs)

        def invoke(self, *_a: Any, **_kw: Any) -> dict:
            return {"messages": [AIMessage(content="재무 분석", name="financial_expert")]}

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: FakeGraph())
    monkeypatch.setattr(topologies, "tool_owner", lambda: {})

    outcome = topologies.run_supervisor("005930", "삼성전자", [], ToolCallRecorder("off"))

    assert outcome.report is None
    assert "0/9" in outcome.notes["incomplete"]


def _always_calls_tool() -> Iterator[AIMessage]:
    for i in itertools.count():
        yield AIMessage(
            content="", tool_calls=[{"name": "fake_price", "args": {"stock_code": "005930"}, "id": f"c{i}"}]
        )


def test_single_agent_out_of_steps_is_an_error_not_a_report(
    fake_lab: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.agent_status import STEP_LIMIT_TEXT

    monkeypatch.setattr(
        "config.llm_factory.build_llm", lambda **_kw: FakeToolCallingModel(messages=_always_calls_tool())
    )
    monkeypatch.setitem(topologies.STEP_BUDGETS, "single_agent", {"graph": 12})

    record = runner.run_once("single_agent", "005930", "삼성전자")

    assert not record.succeeded
    assert record.report is None
    assert "단계 한도(12)" in record.error
    assert STEP_LIMIT_TEXT not in record.error
    assert record.grounding["checked"] == 0
    assert record.tool_calls["calls"] >= 5


def test_single_agent_graph_recursion_error_is_an_error(
    fake_lab: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langgraph.errors import GraphRecursionError

    configs: list[dict] = []

    class Exhausted:
        def stream(self, state: dict, config: dict, **_kw: Any) -> Any:
            yield self.invoke(state, config)

        def invoke(self, _state: dict, config: dict) -> dict:
            configs.append(config)
            raise GraphRecursionError("Recursion limit of 225 reached")

    monkeypatch.setattr("langgraph.prebuilt.create_react_agent", lambda **_kw: Exhausted())

    record = runner.run_once("single_agent", "005930", "삼성전자")

    assert configs[0]["recursion_limit"] == 225
    assert not record.succeeded
    assert record.error.startswith("단계 한도(225)를 넘어 중단됐습니다")


def test_supervisor_uses_the_scaled_step_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.snapshot import ToolCallRecorder

    configs: list[dict] = []

    class FakeGraph:
        def stream(self, state: dict, config: dict, **_kw: Any) -> Any:
            yield self.invoke(state, config)

        def invoke(self, _state: dict, config: dict) -> dict:
            configs.append(config)
            return {"messages": []}

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: FakeGraph())

    topologies.run_supervisor("005930", "삼성전자", [], ToolCallRecorder("off"))

    assert configs[0]["recursion_limit"] == 225


def test_temperature_is_pinned_during_the_run_and_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import llm_factory

    seen: list[float] = []

    def probe(*_a: Any) -> topologies.TopologyOutcome:
        seen.append(llm_factory.effective_temperature(0.3))
        return topologies.TopologyOutcome(report=None)

    monkeypatch.setattr(runner, "all_tools", lambda: [])
    monkeypatch.setitem(runner.TOPOLOGY_RUNNERS, "progressive", probe)

    record = runner.run_once("progressive", "005930", "삼성전자", temperature=0.2)

    assert seen == [0.2]
    assert record.llm["temperature"] == 0.2
    assert llm_factory.effective_temperature(0.3) == 0.3


_GROUNDED = [
    "context_expert",
    "financial_expert",
    "advanced_technical_expert",
    "comparative_expert",
    "esg_expert",
]


def _expert_tools() -> tuple[list[Any], dict[str, str]]:
    """전문가마다 도구 하나. 도구 결과 숫자는 전문가마다 다르다."""
    tools, owners = [], {}
    for i, agent in enumerate([*_GROUNDED, "community_expert"]):

        def fetch(stock_code: str, _value: int = 1000 * (i + 1)) -> dict:
            return {"value": _value}

        made = StructuredTool.from_function(fetch, name=f"tool_{agent}", description="데이터 조회")
        tools.append(made)
        owners[made.name] = agent
    return tools, owners


def _call_every_tool(tools: list[Any]) -> None:
    for item in tools:
        item.invoke({"stock_code": "005930"})


@pytest.fixture
def expert_tools(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    tools, owners = _expert_tools()
    monkeypatch.setattr(runner, "all_tools", lambda: tools)
    monkeypatch.setattr(runner, "tool_owner", lambda: owners)
    monkeypatch.setattr(topologies, "tool_owner", lambda: owners)
    return tools


def test_report_failure_in_supervisor_is_the_run_error(
    expert_tools: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.errors import ReportGenerationError

    class FakeGraph:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            yield self.invoke(*args, **kwargs)

        def invoke(self, *_a: Any, **_kw: Any) -> dict:
            _call_every_tool(expert_tools)
            return {"messages": [AIMessage(content=f"{n} 분석", name=n) for n in _GROUNDED]}

    def failing_report(*_a: Any, **_kw: Any) -> str:
        raise ReportGenerationError("보고서 LLM 호출 실패: 500 Server Error (1000, 2000)")

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: FakeGraph())
    monkeypatch.setattr(topologies, "get_supervisor_llm", lambda: None)
    monkeypatch.setattr(topologies, "generate_comprehensive_report", failing_report)

    record = runner.run_once("supervisor", "005930", "삼성전자")

    assert not record.succeeded
    assert record.error.startswith("ReportGenerationError: 보고서 LLM 호출 실패")
    assert record.report is None
    assert record.grounding == {"checked": 0, "grounded": 0, "ratio": None, "ungrounded": []}
    assert record.coverage["agents"] == _GROUNDED


def test_report_error_event_in_progressive_is_the_run_error(
    expert_tools: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeEngine:
        def stream_progressive_analysis(self, *_a: Any, **_kw: Any) -> Iterator[dict]:
            _call_every_tool(expert_tools)
            for name in _GROUNDED:
                status = {"status": "success", "data_status": "sufficient"}
                yield {
                    "type": "agent_complete",
                    "agent_name": name,
                    "content": "분석",
                    "agent_status": status,
                }
            yield {"type": "report_error", "error": "보고서 LLM 호출 실패: 500 (1000, 2000)"}

    monkeypatch.setattr("core.progressive_supervisor.ProgressiveAnalysisEngine", FakeEngine)

    record = runner.run_once("progressive", "005930", "삼성전자")

    assert not record.succeeded
    assert record.error == "보고서 LLM 호출 실패: 500 (1000, 2000)"
    assert record.grounding["checked"] == 0
    assert record.coverage["agents"] == _GROUNDED


def test_coverage_and_grounding_use_only_experts_that_reached_the_report(
    expert_tools: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """community는 도구 데이터를 받았지만 마지막 LLM 호출이 실패해 보고서에서 빠졌다."""

    class FakeEngine:
        def stream_progressive_analysis(self, *_a: Any, **_kw: Any) -> Iterator[dict]:
            _call_every_tool(expert_tools)
            yield {
                "type": "agent_error",
                "agent_name": "community_expert",
                "error": "LLM 500",
                "agent_status": {"status": "error", "data_status": "none"},
            }
            yield {
                "type": "final_report",
                "report": "근거 있는 값 1,000원, 빠진 전문가의 값 6,000원.",
                "grounded_agents": _GROUNDED,
                "excluded": {"community_expert": "실행 실패: LLM 500"},
            }

    monkeypatch.setattr("core.progressive_supervisor.ProgressiveAnalysisEngine", FakeEngine)

    record = runner.run_once("progressive", "005930", "삼성전자")

    assert record.succeeded
    assert record.coverage == {"agents": _GROUNDED, "ratio": 5 / 9, "basis": "report_inputs"}
    assert record.tool_coverage["agents"] == [*_GROUNDED[:4], "esg_expert", "community_expert"]
    assert record.grounding["checked"] == 2
    assert record.grounding["grounded"] == 1
    assert record.grounding["ungrounded"][0]["number"].startswith("6,000")


def test_supervisor_step_limit_is_an_error_that_keeps_its_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import AIMessage
    from langgraph.errors import GraphRecursionError

    from lab import topologies

    class LoopingGraph:
        def stream(self, *_a: Any, **_kw: Any) -> Any:
            yield {"messages": [AIMessage(content="시장 분석 " * 50, name="context_expert")]}
            raise GraphRecursionError("limit")

    monkeypatch.setattr(topologies, "create_korean_supervisor", lambda: LoopingGraph())
    recorder = topologies.ToolCallRecorder("off")

    outcome = topologies.run_supervisor("005930", "삼성전자", [], recorder)

    assert outcome.report is None
    assert "단계 한도" in (outcome.error or "")
    assert outcome.notes["supervisor_hit_step_limit"] is True
    assert outcome.notes["called_agents"] == ["context_expert"]
