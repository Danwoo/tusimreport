"""도구 결과로 에이전트의 근거 데이터 유무를 판정하는 규칙 검증."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from core.agent_status import classify_tool_output, data_status, summarize_tool_messages


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"price": 70000, "status": "success"}', (False, True)),
        ('{"error": "ECOS API 키 미설정"}', (True, False)),
        ('{"status": "all_failed", "indicators": {}}', (True, False)),
        ('{"status": "success", "items": [], "stock_code": "005930"}', (False, False)),
        ('{"usd_krw": null, "available": false, "note": "unavailable"}', (False, True)),
        ("오류: 데이터를 가져올 수 없습니다", (True, False)),
        ("삼성전자 최근 뉴스 3건", (False, True)),
    ],
)
def test_classify_tool_output(content: str, expected: tuple[bool, bool]) -> None:
    assert classify_tool_output(content) == expected


def test_summary_counts_only_tool_messages() -> None:
    messages = [
        AIMessage(content="도구를 부른다"),
        ToolMessage(content='{"price": 1}', tool_call_id="a"),
        ToolMessage(content='{"error": "timeout"}', tool_call_id="b"),
        ToolMessage(content='{"items": []}', tool_call_id="c"),
        AIMessage(content="분석 결과"),
    ]

    summary = summarize_tool_messages(messages)

    assert summary.to_dict() == {"calls": 3, "errors": 1, "with_data": 1}
    assert data_status(summary) == "partial"


def test_data_status_levels() -> None:
    assert data_status(summarize_tool_messages([])) == "none"
    assert (
        data_status(summarize_tool_messages([ToolMessage(content='{"error": "x"}', tool_call_id="a")]))
        == "none"
    )
    assert (
        data_status(summarize_tool_messages([ToolMessage(content='{"v": 2}', tool_call_id="a")]))
        == "sufficient"
    )
