"""도구 호출 기록과 스냅샷 기록·재생 검증."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import tool

from lab.snapshot import SnapshotStore, ToolCallRecorder, instrument_tools


@tool
def price_tool(stock_code: str, company_name: str) -> dict:
    """현재가 조회."""
    return {"stock_code": stock_code, "price": 70000}


def test_record_then_replay_without_calling_the_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SnapshotStore(tmp_path)
    recorder = ToolCallRecorder("record", store)
    with instrument_tools([price_tool], recorder):
        assert price_tool.invoke({"stock_code": "005930", "company_name": "삼성전자"})["price"] == 70000

    original = price_tool.func
    monkeypatch.setattr(price_tool, "func", lambda **_kw: pytest.fail("replay must not call the tool"))
    replay = ToolCallRecorder("replay", store)
    with instrument_tools([price_tool], replay):
        exact = price_tool.invoke({"stock_code": "005930", "company_name": "삼성전자"})
        fuzzy = price_tool.invoke({"stock_code": "005930", "company_name": "Samsung"})
        missing = price_tool.invoke({"stock_code": "000660", "company_name": "SK하이닉스"})
    monkeypatch.setattr(price_tool, "func", original)

    assert exact["price"] == 70000
    assert fuzzy["price"] == 70000
    assert "스냅샷 없음" in missing["error"]
    assert [c.source for c in replay.calls] == ["snapshot", "snapshot_fuzzy", "missing"]
    summary = replay.summary()
    assert summary["by_source"] == {"snapshot": 1, "snapshot_fuzzy": 1, "missing": 1}
    assert summary["errors"] == 1
    assert summary["with_data"] == 2


def test_instrument_restores_original_func_and_records_errors(tmp_path: Path) -> None:
    @tool
    def flaky(stock_code: str) -> str:
        """항상 실패."""
        raise RuntimeError("upstream 503")

    original = flaky.func
    recorder = ToolCallRecorder("off")
    with instrument_tools([flaky], recorder), pytest.raises(RuntimeError):
        flaky.func(stock_code="005930")

    assert flaky.func is original
    assert recorder.calls[0].error == "upstream 503"


def test_replay_requires_store() -> None:
    with pytest.raises(ValueError):
        ToolCallRecorder("replay")
