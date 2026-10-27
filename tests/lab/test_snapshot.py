"""도구 호출 기록과 스냅샷 기록·재생 검증."""

from __future__ import annotations

import json
import os
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


@tool
def trading_tool(stock_code: str, period_days: int = 20) -> dict:
    """기간별 수급."""
    return {"stock_code": stock_code, "period_days": period_days, "net": 1_000_000}


def _replay(store: SnapshotStore, calls: list[dict]) -> tuple[list[dict], ToolCallRecorder]:
    recorder = ToolCallRecorder("replay", store)
    with instrument_tools([trading_tool], recorder):
        outputs = [trading_tool.invoke(args) for args in calls]
    return outputs, recorder


def test_fuzzy_replay_never_substitutes_a_different_period(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    store.save("trading_tool", {"stock_code": "005930", "period_days": 20}, {"net": 1, "period_days": 20})

    outputs, recorder = _replay(
        store,
        [{"stock_code": "005930", "period_days": 120}, {"stock_code": "005930"}],
    )

    assert "스냅샷 없음" in outputs[0]["error"]
    assert outputs[1]["period_days"] == 20
    assert [c.source for c in recorder.calls] == ["missing", "snapshot"]


def test_snapshot_calls_carry_recorded_at_and_summary_shows_fuzzy_and_range(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    recorder = ToolCallRecorder("record", store, owners={"price_tool": "financial_expert"})
    with instrument_tools([price_tool], recorder):
        price_tool.invoke({"stock_code": "005930", "company_name": "삼성전자"})
    recorded_at = json.loads(next((tmp_path / "price_tool").glob("*.json")).read_text("utf-8"))["recorded_at"]

    replay = ToolCallRecorder("replay", store)
    with instrument_tools([price_tool], replay):
        price_tool.invoke({"stock_code": "005930", "company_name": "삼성전자"})
        price_tool.invoke({"stock_code": "005930", "company_name": "Samsung"})

    assert recorder.calls[0].agent == "financial_expert"
    assert recorder.calls[0].recorded_at is not None
    assert [c.recorded_at for c in replay.calls] == [recorded_at, recorded_at]
    summary = replay.summary()
    assert summary["fuzzy"] == 1
    assert summary["recorded_at"] == {"min": recorded_at, "max": recorded_at}


def test_save_is_atomic_when_the_write_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SnapshotStore(tmp_path)
    args = {"stock_code": "005930", "company_name": "삼성전자"}
    path = store.save("price_tool", args, {"price": 70000})
    before = path.read_text("utf-8")

    def interrupted(*_a: object, **_kw: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError, match="disk full"):
        store.save("price_tool", args, {"price": 71000})

    assert path.read_text("utf-8") == before
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


def test_corrupt_snapshot_is_recorded_instead_of_raising(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    args = {"stock_code": "005930", "company_name": "삼성전자"}
    store.path("price_tool", args).parent.mkdir(parents=True)
    store.path("price_tool", args).write_text('{"tool": "price_tool", "args": {', encoding="utf-8")

    recorder = ToolCallRecorder("replay", store)
    with instrument_tools([price_tool], recorder):
        output = price_tool.invoke(args)

    assert "error" in output
    assert [c.source for c in recorder.calls] == ["corrupt"]
    assert recorder.calls[0].error.startswith("스냅샷 손상")
    assert recorder.summary()["errors"] == 1


def test_ignored_argument_does_not_make_a_replay_fuzzy(tmp_path: Path) -> None:
    """save_stock_chart는 chart_data를 읽지 않는다. 그 값만 다르면 같은 데이터이므로 정확한 일치다."""
    store = SnapshotStore(tmp_path)
    store.save(
        "save_stock_chart", {"stock_code": "005930", "chart_data": {"close": [1, 2, 3]}}, {"path": "x.png"}
    )

    for args in ({"stock_code": "005930", "chart_data": {"close": [1, 2, 4]}}, {"stock_code": "005930"}):
        hit = store.load("save_stock_chart", args)
        assert hit is not None
        assert hit.match == "exact"


def test_record_mode_keeps_the_call_when_saving_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SnapshotStore(tmp_path)
    monkeypatch.setattr(store, "save", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("disk full")))
    recorder = ToolCallRecorder("record", store)

    with instrument_tools([price_tool], recorder):
        assert price_tool.invoke({"stock_code": "005930", "company_name": "삼성전자"})["price"] == 70000

    summary = recorder.summary()
    assert summary["calls"] == 1
    assert summary["save_failures"] == 1
