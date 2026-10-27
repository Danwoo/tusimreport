"""구조 비교 실험의 1회 실행과 그 결과 레코드.

`run_once`는 topology 하나를 같은 도구·같은 스냅샷 위에서 돌리고, 보고서와 함께
비용(LLM·도구 호출 수, 토큰, 시간)과 품질 지표(숫자 근거 일치율, 영역 커버리지)를
한 레코드로 돌려준다. Streamlit 없이 실행된다.

보고서를 근거 있는 전문가 분석으로만 쓰는 progressive·supervisor는 커버리지와 숫자 근거의
출처를 보고서 작성기에 들어간 전문가로 한정한다. single_agent에는 그런 단위가 없어
도구 호출 전체를 쓴다. 도구 단위 커버리지는 세 구조 모두 `tool_coverage`에 따로 남긴다.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import agents.korean_financial_react_agent as financial_agent
from config.llm_factory import temperature_override
from config.settings import resolve_llm_config, settings
from core.run_metrics import RunMetricsCallback
from core.signals import AGENT_TO_SIGNAL
from lab.grounding import numeric_grounding
from lab.snapshot import SnapshotMode, SnapshotStore, ToolCallRecorder, instrument_tools
from lab.tool_registry import all_tools, tool_owner
from lab.topologies import REPORT_GATED_TOPOLOGIES, STEP_BUDGETS, TOPOLOGY_RUNNERS, grounded_agents
from utils.time import kst_isoformat

DEFAULT_TEMPERATURE = 0.0


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
    tool_coverage: dict[str, Any]
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return bool(self.report) and self.error is None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["succeeded"] = self.succeeded
        data["report_chars"] = len(self.report or "")
        return data


def _llm_info(temperature: float) -> dict[str, Any]:
    config, problem = resolve_llm_config()
    if config is None:
        return {"configured": False, "problem": (problem or "").splitlines()[0], "temperature": temperature}
    host = urlparse(config.base_url).hostname if config.base_url else None
    return {
        "configured": True,
        "provider": config.provider,
        "model": config.model_name,
        "endpoint_host": host,
        "max_requests_per_minute": settings.llm_max_requests_per_minute,
        "temperature": temperature,
    }


def _coverage(agents: list[str], basis: str) -> dict[str, Any]:
    return {"agents": agents, "ratio": len(agents) / len(AGENT_TO_SIGNAL), "basis": basis}


def run_once(
    topology: str,
    stock_code: str,
    company_name: str,
    snapshot_mode: SnapshotMode = "off",
    snapshot_dir: Path = Path("snapshots"),
    temperature: float = DEFAULT_TEMPERATURE,
) -> RunRecord:
    """topology 하나를 1회 실행한다. 실행 중에는 모든 LLM의 temperature를 `temperature`로 고정한다."""
    if topology not in TOPOLOGY_RUNNERS:
        raise ValueError(f"알 수 없는 topology: {topology} (가능: {', '.join(TOPOLOGY_RUNNERS)})")

    store = SnapshotStore(snapshot_dir) if snapshot_mode != "off" else None
    recorder = ToolCallRecorder(snapshot_mode, store, owners=tool_owner())
    metrics = RunMetricsCallback()
    started_at = kst_isoformat()
    started = time.monotonic()
    error: str | None = None
    report: str | None = None
    notes: dict[str, Any] = {}

    with temperature_override(temperature), instrument_tools(all_tools(), recorder):
        # The financial agent caches its compiled graph with the LLM it was built with; rebuild it
        # under this run's temperature override.
        financial_agent.reset_financial_react_agent()
        try:
            outcome = TOPOLOGY_RUNNERS[topology](stock_code, company_name, [metrics], recorder)
            report, error, notes = outcome.report, outcome.error, outcome.notes
            notes["specialists"] = sorted(outcome.specialist_outputs)
            notes["specialist_chars"] = {name: len(text) for name, text in outcome.specialist_outputs.items()}
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    notes["step_budget"] = STEP_BUDGETS[topology]

    tool_covered = grounded_agents(recorder)
    if topology in REPORT_GATED_TOPOLOGIES:
        reached_report = set(notes.get("grounded_agents", []))
        report_inputs = [name for name in AGENT_TO_SIGNAL if name in reached_report]
        coverage = _coverage(report_inputs, "report_inputs")
        scope: set[str] | None = set(report_inputs)
    else:
        coverage = _coverage(tool_covered, "tool_calls")
        scope = None
    sources = [
        call.output
        for call in recorder.calls
        if call.error is None and (scope is None or call.agent in scope)
    ]
    return RunRecord(
        topology=topology,
        stock_code=stock_code,
        company_name=company_name,
        started_at=started_at,
        elapsed_s=round(time.monotonic() - started, 2),
        llm=_llm_info(temperature),
        snapshot_mode=snapshot_mode,
        report=report,
        error=error,
        stats=metrics.stats.to_dict(),
        tool_calls=recorder.summary(),
        grounding=numeric_grounding(report or "", sources, stock_code).to_dict(),
        coverage=coverage,
        tool_coverage=_coverage(tool_covered, "tool_calls"),
        notes=notes,
    )


def save_record(record: RunRecord, out_dir: Path, tag: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = record.started_at.replace(":", "").replace("-", "")[:15]
    suffix = f"_{tag}" if tag else ""
    path = out_dir / f"{stamp}_{record.topology}_{record.stock_code}{suffix}.json"
    path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path
