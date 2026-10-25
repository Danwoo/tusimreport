"""구조 비교 실험의 1회 실행과 그 결과 레코드.

`run_once`는 topology 하나를 같은 도구·같은 스냅샷 위에서 돌리고, 보고서와 함께
비용(LLM·도구 호출 수, 토큰, 시간)과 품질 지표(숫자 근거 일치율, 영역 커버리지)를
한 레코드로 돌려준다. Streamlit 없이 실행된다.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config.settings import resolve_llm_config, settings
from core.run_metrics import RunMetricsCallback
from core.signals import AGENT_TO_SIGNAL
from lab.grounding import numeric_grounding
from lab.snapshot import SnapshotMode, SnapshotStore, ToolCallRecorder, instrument_tools
from lab.tool_registry import all_tools
from lab.topologies import TOPOLOGY_RUNNERS, grounded_agents
from utils.time import kst_isoformat


@dataclass
class RunRecord:
    topology: str
    stock_code: str
    company_name: str
    started_at: str
    elapsed_s: float
    llm: dict[str, Any]
    snapshot_mode: str
    report: str | None
    error: str | None
    stats: dict[str, Any]
    tool_calls: dict[str, Any]
    grounding: dict[str, Any]
    coverage: dict[str, Any]
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return bool(self.report) and self.error is None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["succeeded"] = self.succeeded
        data["report_chars"] = len(self.report or "")
        return data


def _llm_info() -> dict[str, Any]:
    config, problem = resolve_llm_config()
    if config is None:
        return {"configured": False, "problem": (problem or "").splitlines()[0]}
    host = urlparse(config.base_url).hostname if config.base_url else None
    return {
        "configured": True,
        "provider": config.provider,
        "model": config.model_name,
        "endpoint_host": host,
        "max_requests_per_minute": settings.llm_max_requests_per_minute,
    }


def run_once(
    topology: str,
    stock_code: str,
    company_name: str,
    snapshot_mode: SnapshotMode = "off",
    snapshot_dir: Path = Path("snapshots"),
) -> RunRecord:
    if topology not in TOPOLOGY_RUNNERS:
        raise ValueError(f"알 수 없는 topology: {topology} (가능: {', '.join(TOPOLOGY_RUNNERS)})")

    store = SnapshotStore(snapshot_dir) if snapshot_mode != "off" else None
    recorder = ToolCallRecorder(snapshot_mode, store)
    metrics = RunMetricsCallback()
    started_at = kst_isoformat()
    started = time.monotonic()
    error: str | None = None
    report: str | None = None
    notes: dict[str, Any] = {}

    with instrument_tools(all_tools(), recorder):
        try:
            outcome = TOPOLOGY_RUNNERS[topology](stock_code, company_name, [metrics], recorder)
            report, error, notes = outcome.report, outcome.error, outcome.notes
            notes["specialists"] = sorted(outcome.specialist_outputs)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

    outputs = [call.output for call in recorder.calls if call.error is None]
    covered = grounded_agents(recorder)
    return RunRecord(
        topology=topology,
        stock_code=stock_code,
        company_name=company_name,
        started_at=started_at,
        elapsed_s=round(time.monotonic() - started, 2),
        llm=_llm_info(),
        snapshot_mode=snapshot_mode,
        report=report,
        error=error,
        stats=metrics.stats.to_dict(),
        tool_calls=recorder.summary(),
        grounding=numeric_grounding(report or "", outputs, stock_code).to_dict(),
        coverage={"agents": covered, "ratio": len(covered) / len(AGENT_TO_SIGNAL)},
        notes=notes,
    )


def save_record(record: RunRecord, out_dir: Path, tag: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = record.started_at.replace(":", "").replace("-", "")[:15]
    suffix = f"_{tag}" if tag else ""
    path = out_dir / f"{stamp}_{record.topology}_{record.stock_code}{suffix}.json"
    path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path
