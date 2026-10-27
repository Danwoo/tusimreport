"""실제 9개 에이전트 그래프를 세 topology로 끝까지 돌리는 통합 테스트.

LLM은 '첫 턴에 바인딩된 첫 도구를 부르고, 도구 결과를 받으면 글을 쓰는' 스크립트
모델로 바꾸고, 도구는 스냅샷 디렉터리에서 replay해 네트워크를 쓰지 않는다.
도구 인자 이름, supervisor handoff 연결, 계측·기록이 실제 그래프에서 이어지는지 본다.
빈 디렉터리면 모든 호출이 스냅샷 누락이고, `full_snapshots`는 모든 도구에 데이터를 넣어
보고서까지 가는 경로를 연다.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from lab import runner, topologies
from lab.snapshot import SnapshotStore
from lab.tool_registry import AGENT_TOOL_LISTS, all_tools

HANDOFF_BACK_TEXT = "Transferring back to supervisor"

_TYPE_DEFAULTS: dict[str, Any] = {"integer": 5, "number": 1.0, "boolean": False, "object": {}, "array": []}


def _fill_args(parameters: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for name in parameters.get("required", []):
        spec = parameters.get("properties", {}).get(name, {})
        kind = spec.get("type", "string")
        if kind == "string":
            args[name] = "삼성전자" if ("name" in name or "company" in name) else "005930"
        else:
            args[name] = _TYPE_DEFAULTS.get(kind)
    return args


class ScriptedToolModel(BaseChatModel):
    tools: list[dict[str, Any]] = []
    # Call every bound tool once before writing (default: only the first one).
    call_every_tool: bool = False
    # The model with no tools bound is the report writer; make it fail.
    fail_unbound: bool = False
    # Fail the final writing turn of the model that owns this tool, after its tools returned.
    fail_after_tool: str | None = None

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedToolModel:
        return self.model_copy(update={"tools": [convert_to_openai_tool(t) for t in tools]})

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        if not self.tools and self.fail_unbound:
            raise RuntimeError("report LLM 500")
        # Supervisor workers inherit the supervisor's handoff ToolMessages, so only results
        # of this model's own tools count as "already called".
        own_tools = [tool["function"] for tool in self.tools]
        called = {m.name for m in messages if isinstance(m, ToolMessage)}
        pending = [f for f in own_tools if f["name"] not in called]
        if pending and (self.call_every_tool or len(pending) == len(own_tools)):
            function = pending[0]
            call = {
                "name": function["name"],
                "args": _fill_args(function.get("parameters", {})),
                "id": f"call-{len(own_tools) - len(pending)}",
            }
            message = AIMessage(content="", tool_calls=[call], usage_metadata=usage)
        elif self.fail_after_tool in {f["name"] for f in own_tools}:
            raise RuntimeError("specialist LLM 500")
        else:
            message = AIMessage(content="삼성전자 분석: 데이터 없음. " * 30, usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=message)])


def _install(monkeypatch: pytest.MonkeyPatch, **config: Any) -> None:
    factory = lambda **_kw: ScriptedToolModel(**config)  # noqa: E731
    for module_name, _ in AGENT_TOOL_LISTS.values():
        module = importlib.import_module(module_name)
        if hasattr(module, "build_llm"):
            monkeypatch.setattr(module, "build_llm", factory)
    monkeypatch.setattr("core.korean_supervisor_langgraph.build_llm", factory)
    monkeypatch.setattr("config.llm_factory.build_llm", factory)
    monkeypatch.setattr("agents.korean_financial_react_agent._financial_react_agent", None)


@pytest.fixture
def scripted_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch)


@pytest.fixture
def full_snapshots(tmp_path: Path) -> Path:
    """스크립트 모델이 부를 인자 그대로, 모든 도구에 근거 데이터가 있는 스냅샷."""
    store = SnapshotStore(tmp_path / "full-snapshots")
    for i, item in enumerate(all_tools()):
        args = _fill_args(convert_to_openai_tool(item)["function"].get("parameters", {}))
        store.save(item.name, args, {"value": 1000 * (i + 1)})
    return store.root


def _capture_outcomes(monkeypatch: pytest.MonkeyPatch, topology: str) -> list[topologies.TopologyOutcome]:
    outcomes: list[topologies.TopologyOutcome] = []
    original = runner.TOPOLOGY_RUNNERS[topology]

    def capture(*args: Any) -> topologies.TopologyOutcome:
        outcomes.append(original(*args))
        return outcomes[-1]

    monkeypatch.setitem(runner.TOPOLOGY_RUNNERS, topology, capture)
    return outcomes


@pytest.mark.parametrize("topology", ["single_agent", "progressive", "supervisor"])
def test_topology_runs_end_to_end_without_network(scripted_llm: None, tmp_path: Path, topology: str) -> None:
    record = runner.run_once(topology, "005930", "삼성전자", "replay", tmp_path / "empty-snapshots")

    assert record.error is None, record.error
    assert record.stats["llm_calls"] > 0
    assert record.tool_calls["calls"] > 0
    assert record.tool_calls["by_source"] == {"missing": record.tool_calls["calls"]}
    assert record.tool_calls["with_data"] == 0
    assert record.coverage["agents"] == []
    if topology == "single_agent":
        assert record.succeeded
    else:
        assert not record.succeeded
        assert "보고서 기준" in record.notes["incomplete"]


def test_supervisor_separates_uncalled_from_ungrounded_agents(
    scripted_llm: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes = _capture_outcomes(monkeypatch, "supervisor")

    record = runner.run_once("supervisor", "005930", "삼성전자", "replay", tmp_path / "empty-snapshots")

    called = record.notes["called_agents"]
    excluded = record.notes["excluded"]
    assert len(called) == 1
    assert excluded[called[0]].startswith("근거 데이터 없음")
    uncalled = set(excluded) - set(called)
    assert len(uncalled) == 8
    assert {excluded[name] for name in uncalled} == {"supervisor가 호출하지 않음"}
    outputs = outcomes[0].specialist_outputs
    assert set(outputs) == set(called)
    assert all(text != HANDOFF_BACK_TEXT and text.startswith("삼성전자 분석") for text in outputs.values())


def test_supervisor_reaches_a_report_from_real_specialist_analyses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, full_snapshots: Path
) -> None:
    _install(monkeypatch, call_every_tool=True)
    outcomes = _capture_outcomes(monkeypatch, "supervisor")

    record = runner.run_once("supervisor", "005930", "삼성전자", "replay", full_snapshots)

    assert record.error is None, record.error
    assert record.succeeded
    outputs = outcomes[0].specialist_outputs
    assert len(outputs) == 9
    assert all(text != HANDOFF_BACK_TEXT and len(text) > len(HANDOFF_BACK_TEXT) for text in outputs.values())
    assert record.coverage["agents"] == record.tool_coverage["agents"]
    assert len(record.coverage["agents"]) == 9
    # The callback counts data tools only; the nine handoffs are a separate counter.
    assert record.stats["handoffs"] == 9
    assert record.stats["tool_calls"] == record.tool_calls["calls"] == len(all_tools())
    assert record.stats["tool_arg_errors"] == 0


@pytest.mark.parametrize("topology", ["progressive", "supervisor"])
def test_report_llm_failure_is_the_run_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, full_snapshots: Path, topology: str
) -> None:
    _install(monkeypatch, call_every_tool=True, fail_unbound=True)

    record = runner.run_once(topology, "005930", "삼성전자", "replay", full_snapshots)

    assert not record.succeeded
    assert record.report is None
    assert "보고서 LLM 호출 실패" in record.error
    assert record.grounding["checked"] == 0
    assert len(record.coverage["agents"]) == 9


def test_progressive_coverage_leaves_out_a_specialist_that_failed_after_its_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, full_snapshots: Path
) -> None:
    _install(monkeypatch, call_every_tool=True, fail_after_tool="get_community_sentiment_analysis")

    record = runner.run_once("progressive", "005930", "삼성전자", "replay", full_snapshots)

    assert record.succeeded, record.error
    assert "community_expert" in record.tool_coverage["agents"]
    assert "community_expert" not in record.coverage["agents"]
    assert len(record.coverage["agents"]) == 8
    assert record.notes["excluded"]["community_expert"].startswith("실행 실패")
