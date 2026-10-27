"""에이전트 실행 결과를 '실행 성공'과 '데이터 충분성'으로 나눠 판정한다.

에이전트는 도구가 실패해도 그 오류 메시지를 바탕으로 글을 쓰므로, 메시지가
돌아왔다는 사실(실행 성공)만으로는 분석에 근거가 있었는지 알 수 없다. 도구가
돌려준 ToolMessage를 읽어 근거 데이터가 실제로 있었는지를 따로 센다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from langchain_core.messages import ToolMessage

DataStatus = Literal["sufficient", "partial", "none"]

# 실패를 나타내는 status 값. 도구들이 제각각 쓰는 표기를 모았다.
_FAILED_STATUSES = {"error", "failed", "all_failed", "unavailable", "no_data", "missing_api_key"}
# 내용 판단에서 빼는 메타데이터 키 — 이 키만 있는 응답은 데이터가 없는 것으로 본다.
_META_KEYS = {
    "status",
    "agent",
    "stock_code",
    "company_name",
    "data_source",
    "data_sources",
    "timestamp",
    "last_updated",
    "message",
    "note",
    "suggestion",
    "reason_ko",
    "reason",
    "summary",
    "unavailable_data",
    "missing_apis",
}


@dataclass
class ToolSummary:
    calls: int = 0
    errors: int = 0
    with_data: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _parse(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            return content
    return content


def _has_payload(value: Any) -> bool:
    # Flags such as available=False describe the data; they are not data.
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        if value.get("available") is False:
            return False
        return any(_has_payload(v) for k, v in value.items() if k not in _META_KEYS)
    if isinstance(value, list | tuple):
        return any(_has_payload(v) for v in value)
    return True


def classify_tool_output(content: Any) -> tuple[bool, bool]:
    """(오류 여부, 근거 데이터 여부)."""
    parsed = _parse(content)
    if isinstance(parsed, dict):
        status = str(parsed.get("status", "")).lower()
        if parsed.get("error") or status in _FAILED_STATUSES:
            return True, False
        return False, _has_payload(parsed)
    if isinstance(parsed, str):
        lowered = parsed.lower()
        is_error = lowered.startswith(("error", "오류")) or "error:" in lowered[:200]
        return is_error, (not is_error) and bool(parsed.strip())
    return False, _has_payload(parsed)


def summarize_tool_messages(messages: list[Any]) -> ToolSummary:
    summary = ToolSummary()
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        summary.calls += 1
        is_error, has_data = classify_tool_output(message.content)
        if is_error or getattr(message, "status", "success") == "error":
            summary.errors += 1
        elif has_data:
            summary.with_data += 1
    return summary


def data_status(summary: ToolSummary) -> DataStatus:
    if summary.with_data == 0:
        return "none"
    if summary.errors > 0 or summary.with_data < summary.calls:
        return "partial"
    return "sufficient"
