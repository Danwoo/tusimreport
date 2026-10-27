"""LLM·도구 호출 계측 콜백이 실제 LangChain 실행에서 호출 수와 토큰을 세는지 검증."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from core.run_metrics import CallStats, RunMetricsCallback


def test_counts_llm_calls_and_usage_tokens() -> None:
    reply = AIMessage(
        content="ok", usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15}
    )
    llm = GenericFakeChatModel(messages=iter([reply, reply]))
    callback = RunMetricsCallback()

    llm.invoke("hi", config={"callbacks": [callback]})
    llm.invoke("hi again", config={"callbacks": [callback]})

    assert callback.stats.llm_calls == 2
    assert callback.stats.input_tokens == 24
    assert callback.stats.output_tokens == 6


def test_counts_tool_calls_and_errors() -> None:
    @tool
    def lookup(code: str) -> str:
        """종목 조회."""
        if code == "bad":
            raise ValueError("no data")
        return "ok"

    callback = RunMetricsCallback()
    lookup.invoke({"code": "005930"}, config={"callbacks": [callback]})
    with pytest.raises(ValueError):
        lookup.invoke({"code": "bad"}, config={"callbacks": [callback]})

    assert callback.stats.tool_calls == 2
    assert callback.stats.tool_errors == 1
    assert callback.stats.tools_used == {"lookup": 2}


def test_merge_adds_counts() -> None:
    total = CallStats(llm_calls=1, input_tokens=10, tools_used={"a": 1})
    total.merge(CallStats(llm_calls=2, input_tokens=5, tools_used={"a": 2, "b": 1}))

    assert total.llm_calls == 3
    assert total.input_tokens == 15
    assert total.tools_used == {"a": 3, "b": 1}


def test_response_without_usage_is_counted_not_silently_zero() -> None:
    with_usage = AIMessage(
        content="ok", usage_metadata={"input_tokens": 7, "output_tokens": 2, "total_tokens": 9}
    )
    llm = GenericFakeChatModel(messages=iter([with_usage, AIMessage(content="no usage")]))
    callback = RunMetricsCallback()

    llm.invoke("a", config={"callbacks": [callback]})
    llm.invoke("b", config={"callbacks": [callback]})

    assert callback.stats.llm_calls == 2
    assert callback.stats.llm_calls_without_usage == 1
    assert (callback.stats.input_tokens, callback.stats.output_tokens) == (7, 2)


def test_handoff_tools_are_counted_apart_from_data_tools() -> None:
    @tool
    def transfer_to_financial_expert() -> str:
        """supervisor handoff."""
        return "ok"

    @tool
    def lookup(code: str) -> str:
        """종목 조회."""
        return "ok"

    callback = RunMetricsCallback()
    transfer_to_financial_expert.invoke({}, config={"callbacks": [callback]})
    lookup.invoke({"code": "005930"}, config={"callbacks": [callback]})

    assert callback.stats.handoffs == 1
    assert callback.stats.tool_calls == 1
    assert callback.stats.tools_used == {"lookup": 1}


def test_handoff_is_recognised_by_library_metadata() -> None:
    from langgraph_supervisor.handoff import METADATA_KEY_HANDOFF_DESTINATION

    @tool
    def hand_over() -> str:
        """custom-named handoff."""
        return "ok"

    hand_over.metadata = {METADATA_KEY_HANDOFF_DESTINATION: "esg_expert"}
    callback = RunMetricsCallback()
    hand_over.invoke({}, config={"callbacks": [callback]})

    assert (callback.stats.handoffs, callback.stats.tool_calls) == (1, 0)


def test_argument_validation_failure_is_counted_separately() -> None:
    """ReAct 루프에서 인자 검증에 걸린 호출: 콜백은 시작을 보지만 도구 함수는 실행되지 않는다."""
    from langgraph.prebuilt import create_react_agent

    ran: list[str] = []

    @tool
    def lookup(code: str, period_days: int = 20) -> str:
        """종목 조회."""
        ran.append(code)
        return "ok"

    class ToolModel(GenericFakeChatModel):
        def bind_tools(self, tools: object, **kwargs: object) -> ToolModel:
            return self

    model = ToolModel(
        messages=iter(
            [
                AIMessage(
                    content="", tool_calls=[{"name": "lookup", "args": {"period_days": "x"}, "id": "1"}]
                ),
                AIMessage(content="done"),
            ]
        )
    )
    callback = RunMetricsCallback()
    create_react_agent(model=model, tools=[lookup]).invoke(
        {"messages": [{"role": "user", "content": "go"}]}, config={"callbacks": [callback]}
    )

    assert ran == []
    assert callback.stats.tool_calls == 1
    assert callback.stats.tool_errors == 1
    assert callback.stats.tool_arg_errors == 1


def test_merge_adds_new_counters() -> None:
    total = CallStats(llm_calls_without_usage=1, handoffs=2, tool_arg_errors=1)
    total.merge(CallStats(llm_calls_without_usage=2, handoffs=1, tool_arg_errors=3))

    assert (total.llm_calls_without_usage, total.handoffs, total.tool_arg_errors) == (3, 3, 4)
