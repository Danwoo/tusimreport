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
