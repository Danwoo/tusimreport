#!/usr/bin/env python3
"""멀티에이전트 구조 비교 실험 실행기.

같은 종목·같은 도구 스냅샷 위에서 topology를 바꿔 돌리고, 실행마다 JSON 레코드와
전체 요약표(summary.md)를 남긴다. 방법과 지표 정의는 docs/EXPERIMENTS.md.

권장 순서 (무료 한도 절약):
    # 1) 실데이터로 세 구조를 한 번씩 돌려 도구 결과를 한 세션의 스냅샷으로 남긴다
    python scripts/run_experiment.py --snapshot-mode record --snapshot-dir snapshots/<날짜>
    # 2) 같은 스냅샷으로 세 구조를 비교한다 (외부 데이터 API 호출 없음, LLM만 호출)
    python scripts/run_experiment.py --snapshot-mode replay --snapshot-dir snapshots/<날짜> --repeats 3

스냅샷과 실행 결과에는 외부 소스의 원자료가 들어 있다. 공개 저장소에 올리지 않는다
(snapshots/, runs/는 .gitignore 대상).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.redaction import install_record_redaction  # noqa: E402
from utils.time import kst_isoformat  # noqa: E402

if TYPE_CHECKING:
    from lab.runner import RunRecord

DEFAULT_STOCKS = "005930:삼성전자"


def parse_stocks(raw: str) -> list[tuple[str, str]]:
    stocks = []
    for item in raw.split(","):
        code, _, name = item.strip().partition(":")
        if not code:
            continue
        stocks.append((code, name or code))
    return stocks


def _tokens(stats: dict[str, Any]) -> str:
    """입력/출력 토큰. usage 없이 끝난 호출이 있으면 합계가 하한이라는 것을 표시한다."""
    tokens = f"{stats['input_tokens']}/{stats['output_tokens']}"
    without_usage = stats.get("llm_calls_without_usage", 0)
    answered = stats["llm_calls"] - stats.get("llm_errors", 0)
    if without_usage and without_usage >= answered:
        return "n/a"
    if without_usage:
        return f"≥{tokens} (usage 없음 {without_usage}회)"
    return tokens


def _recorded_range(tool_calls: dict[str, Any]) -> str:
    stamps = tool_calls.get("recorded_at")
    if not stamps:
        return "-"
    first, last = stamps["min"][:16], stamps["max"][:16]
    return first if first == last else f"{first} ~ {last}"


def _coverage(record: RunRecord) -> str:
    tool_coverage = getattr(record, "tool_coverage", None) or record.coverage
    tool_level = f"도구 {len(tool_coverage['agents'])}/9"
    if record.coverage.get("basis") == "report_inputs":
        return f"보고서 {len(record.coverage['agents'])}/9 · {tool_level}"
    return tool_level


def summary_table(records: list[RunRecord]) -> str:
    """실행별 요약표.

    도구 호출은 두 계측을 나란히 둔다. `콜백`은 LangChain이 시작한 데이터 도구 호출이며
    인자 검증에서 막힌 호출을 포함하고 handoff는 뺀다. `기록`은 도구 함수까지 도달한 호출이다.
    """
    header = (
        "| topology | 종목 | 성공 | 시간(s) | LLM 호출 | 입력/출력 토큰 | 도구 호출(콜백) | 인자 오류 "
        "| handoff | 기록된 도구 호출(데이터/전체) | 스냅샷 근사/누락/손상 | 스냅샷 기록 시각 | 커버리지 "
        "| 숫자 근거 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    rows = []
    for r in records:
        grounding = r.grounding
        ratio = f"{grounding['grounded']}/{grounding['checked']}" if grounding["checked"] else "-"
        by_source = r.tool_calls.get("by_source", {})
        snapshot = f"{by_source.get('snapshot_fuzzy', 0)}/{by_source.get('missing', 0)}/{by_source.get('corrupt', 0)}"
        rows.append(
            f"| {r.topology} | {r.stock_code} | {'예' if r.succeeded else '아니오'} | {r.elapsed_s} "
            f"| {r.stats['llm_calls']} | {_tokens(r.stats)} "
            f"| {r.stats.get('tool_calls', 0)} | {r.stats.get('tool_arg_errors', 0)} | {r.stats.get('handoffs', 0)} "
            f"| {r.tool_calls['with_data']}/{r.tool_calls['calls']} | {snapshot} "
            f"| {_recorded_range(r.tool_calls)} | {_coverage(r)} | {ratio} |"
        )
    return "\n".join([header, *rows])


def main(argv: list[str] | None = None) -> int:
    # lab imports every tool and data client, some of which log at import time. Nothing configures
    # logging here, so WARNING records reach stderr through logging.lastResort: mask them first.
    install_record_redaction()
    from lab.runner import DEFAULT_TEMPERATURE, run_once, save_record
    from lab.topologies import TOPOLOGY_RUNNERS

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--stocks", default=DEFAULT_STOCKS, help="코드:이름 목록, 쉼표 구분")
    parser.add_argument("--topologies", default=",".join(TOPOLOGY_RUNNERS), help="쉼표 구분")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--snapshot-mode", choices=["off", "record", "replay"], default="off")
    parser.add_argument("--snapshot-dir", type=Path, default=Path("snapshots"))
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"실행 중 모든 LLM에 고정할 temperature (기본 {DEFAULT_TEMPERATURE})",
    )
    parser.add_argument("--out", type=Path, default=None, help="기본: runs/experiments/<시각>")
    args = parser.parse_args(argv)

    topologies = [t.strip() for t in args.topologies.split(",") if t.strip()]
    unknown = [t for t in topologies if t not in TOPOLOGY_RUNNERS]
    if unknown:
        parser.error(f"알 수 없는 topology: {', '.join(unknown)}")
    out_dir = args.out or Path("runs/experiments") / kst_isoformat().replace(":", "")[:15]

    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[RunRecord] = []
    with (out_dir / "results.jsonl").open("a", encoding="utf-8") as jsonl:
        for code, name in parse_stocks(args.stocks):
            for repeat in range(1, args.repeats + 1):
                for topology in topologies:
                    print(f"[{topology}] {code} {name} — {repeat}/{args.repeats}", flush=True)
                    record = run_once(
                        topology, code, name, args.snapshot_mode, args.snapshot_dir, args.temperature
                    )
                    save_record(record, out_dir, tag=f"r{repeat}")
                    jsonl.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")
                    jsonl.flush()
                    records.append(record)
                    status = (
                        "성공"
                        if record.succeeded
                        else f"실패: {record.error or record.notes.get('incomplete')}"
                    )
                    print(
                        f"    → {status} ({record.elapsed_s}s, LLM {record.stats['llm_calls']}회)", flush=True
                    )

    table = summary_table(records)
    (out_dir / "summary.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)
    print(f"\n결과: {out_dir}")
    return 0 if records and all(r.succeeded for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
