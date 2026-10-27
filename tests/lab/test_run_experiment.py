"""scripts/run_experiment.py: 요약표의 두 도구 호출 계측, 토큰 누락 표시, 스냅샷 조건, temperature 옵션."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from lab.runner import RunRecord

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_experiment.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_experiment_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(**overrides: Any) -> RunRecord:
    values: dict[str, Any] = {
        "topology": "supervisor",
        "stock_code": "005930",
        "company_name": "삼성전자",
        "started_at": "2026-10-27T10:00:00+09:00",
        "elapsed_s": 12.5,
        "llm": {"configured": True, "temperature": 0.0},
        "snapshot_mode": "replay",
        "report": "# 보고서",
        "error": None,
        "stats": {
            "llm_calls": 20,
            "llm_errors": 0,
            "llm_calls_without_usage": 0,
            "input_tokens": 1000,
            "output_tokens": 200,
            "tool_calls": 15,
            "tool_errors": 2,
            "tool_arg_errors": 1,
            "handoffs": 9,
        },
        "tool_calls": {
            "calls": 14,
            "errors": 1,
            "with_data": 12,
            "by_source": {"snapshot": 12, "snapshot_fuzzy": 1, "missing": 1},
            "fuzzy": 1,
            "recorded_at": {"min": "2026-10-20T09:01:02+09:00", "max": "2026-10-20T09:07:45+09:00"},
        },
        "grounding": {"checked": 10, "grounded": 7, "ratio": 0.7, "ungrounded": []},
        "coverage": {"agents": ["a"] * 6, "ratio": 6 / 9, "basis": "report_inputs"},
        "tool_coverage": {"agents": ["a"] * 8, "ratio": 8 / 9, "basis": "tool_calls"},
    }
    values.update(overrides)
    return RunRecord(**values)


def _row(table: str) -> list[str]:
    return [cell.strip() for cell in table.splitlines()[2].strip("|").split("|")]


def test_summary_shows_both_tool_counters_and_snapshot_conditions() -> None:
    table = _load_script().summary_table([_record()])
    header = [cell.strip() for cell in table.splitlines()[0].strip("|").split("|")]
    row = dict(zip(header, _row(table), strict=True))

    assert row["도구 호출(콜백)"] == "15"
    assert row["인자 오류"] == "1"
    assert row["handoff"] == "9"
    assert row["기록된 도구 호출(데이터/전체)"] == "12/14"
    assert row["스냅샷 근사/누락/손상"] == "1/1/0"
    assert row["스냅샷 기록 시각"] == "2026-10-20T09:01 ~ 2026-10-20T09:07"
    assert row["커버리지"] == "보고서 6/9 · 도구 8/9"
    assert row["입력/출력 토큰"] == "1000/200"


@pytest.mark.parametrize(
    ("without_usage", "expected"),
    [(0, "1000/200"), (3, "≥1000/200 (usage 없음 3회)"), (20, "n/a")],
)
def test_token_totals_are_marked_when_usage_is_missing(without_usage: int, expected: str) -> None:
    record = _record()
    record.stats["llm_calls_without_usage"] = without_usage

    table = _load_script().summary_table([record])

    assert expected in _row(table)


def test_single_agent_coverage_is_tool_level() -> None:
    record = _record(
        topology="single_agent",
        coverage={"agents": ["a"] * 8, "ratio": 8 / 9, "basis": "tool_calls"},
    )

    assert "도구 8/9" in _row(_load_script().summary_table([record]))


def test_cli_passes_temperature_to_every_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import lab.runner

    script = _load_script()
    seen: list[float] = []

    def fake_run_once(
        topology: str, code: str, name: str, mode: str, directory: Path, temperature: float
    ) -> Any:
        seen.append(temperature)
        return _record(topology=topology, llm={"temperature": temperature})

    monkeypatch.setattr(lab.runner, "run_once", fake_run_once)
    monkeypatch.setattr(lab.runner, "save_record", lambda *_a, **_kw: None)

    code = script.main(
        ["--topologies", "progressive,supervisor", "--temperature", "0.4", "--out", str(tmp_path / "run")]
    )

    assert code == 0
    assert seen == [0.4, 0.4]
    assert "도구 호출(콜백)" in (tmp_path / "run" / "summary.md").read_text(encoding="utf-8")
