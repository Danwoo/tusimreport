"""실제 9개 에이전트 그래프를 세 topology로 끝까지 돌리는 통합 테스트.

LLM은 '첫 턴에 바인딩된 첫 도구를 부르고, 도구 결과를 받으면 글을 쓰는' 스크립트
모델로 바꾸고, 도구는 빈 스냅샷 디렉터리에서 replay해 네트워크를 쓰지 않는다.
도구 인자 이름, supervisor handoff 연결, 계측·기록이 실제 그래프에서 이어지는지 본다.
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

from lab import runner
from lab.tool_registry import AGENT_TOOL_LISTS

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

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedToolModel:
        return self.model_copy(update={"tools": [convert_to_openai_tool(t) for t in tools]})

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        # Supervisor workers inherit the supervisor's handoff ToolMessages, so only results
        # of this model's own tools count as "already called".
        own_tools = {tool["function"]["name"] for tool in self.tools}
        called = any(isinstance(m, ToolMessage) and m.name in own_tools for m in messages)
        if self.tools and not called:
            function = self.tools[0]["function"]
            call = {
                "name": function["name"],
                "args": _fill_args(function.get("parameters", {})),
                "id": "call-1",
            }
            message = AIMessage(content="", tool_calls=[call], usage_metadata=usage)
        else:
            message = AIMessage(content="삼성전자 분석: 데이터 없음. " * 30, usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.fixture
def scripted_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = lambda **_kw: ScriptedToolModel()  # noqa: E731
    for module_name, _ in AGENT_TOOL_LISTS.values():
        module = importlib.import_module(module_name)
        if hasattr(module, "build_llm"):
            monkeypatch.setattr(module, "build_llm", factory)
    monkeypatch.setattr("core.korean_supervisor_langgraph.build_llm", factory)
    monkeypatch.setattr("config.llm_factory.build_llm", factory)
    monkeypatch.setattr("agents.korean_financial_react_agent._financial_react_agent", None)


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


def test_supervisor_separates_uncalled_from_ungrounded_agents(scripted_llm: None, tmp_path: Path) -> None:
    record = runner.run_once("supervisor", "005930", "삼성전자", "replay", tmp_path / "empty-snapshots")

    called = record.notes["called_agents"]
    excluded = record.notes["excluded"]
    assert len(called) == 1
    assert excluded[called[0]].startswith("근거 데이터 없음")
    uncalled = set(excluded) - set(called)
    assert len(uncalled) == 8
    assert {excluded[name] for name in uncalled} == {"supervisor가 호출하지 않음"}
