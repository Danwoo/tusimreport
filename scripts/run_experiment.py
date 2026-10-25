#!/usr/bin/env python3
"""멀티에이전트 구조 비교 실험 실행기.

같은 종목·같은 도구 스냅샷 위에서 topology를 바꿔 돌리고, 실행마다 JSON 레코드와
전체 요약표(summary.md)를 남긴다. 방법과 지표 정의는 docs/EXPERIMENTS.md.

권장 순서 (무료 한도 절약):
    # 1) 실데이터로 한 번 돌려 도구 결과를 스냅샷으로 남긴다
    python scripts/run_experiment.py --topologies progressive --snapshot-mode record
    # 2) 같은 스냅샷으로 세 구조를 비교한다 (외부 데이터 API 호출 없음, LLM만 호출)
    python scripts/run_experiment.py --snapshot-mode replay --repeats 3

스냅샷과 실행 결과에는 외부 소스의 원자료가 들어 있다. 공개 저장소에 올리지 않는다
(snapshots/, runs/는 .gitignore 대상).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab.runner import RunRecord, run_once, save_record  # noqa: E402
from lab.topologies import TOPOLOGY_RUNNERS  # noqa: E402
from utils.time import kst_isoformat  # noqa: E402

DEFAULT_STOCKS = "005930:삼성전자"


def parse_stocks(raw: str) -> list[tuple[str, str]]:
    stocks = []
    for item in raw.split(","):
        code, _, name = item.strip().partition(":")
        if not code:
            continue
        stocks.append((code, name or code))
    return stocks


def summary_table(records: list[RunRecord]) -> str:
    header = (
        "| topology | 종목 | 성공 | 시간(s) | LLM 호출 | 입력/출력 토큰 | 데이터 있는 도구 호출 | 스냅샷 누락 "
        "| 커버리지 | 숫자 근거 |\n|---|---|---|---|---|---|---|---|---|---|"
    )
    rows = []
    for r in records:
        grounding = r.grounding
        ratio = f"{grounding['grounded']}/{grounding['checked']}" if grounding["checked"] else "-"
        missing = r.tool_calls["by_source"].get("missing", 0)
        rows.append(
            f"| {r.topology} | {r.stock_code} | {'예' if r.succeeded else '아니오'} | {r.elapsed_s} "
            f"| {r.stats['llm_calls']} | {r.stats['input_tokens']}/{r.stats['output_tokens']} "
            f"| {r.tool_calls['with_data']}/{r.tool_calls['calls']} | {missing} | {len(r.coverage['agents'])}/9 | {ratio} |"
        )
    return "\n".join([header, *rows])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--stocks", default=DEFAULT_STOCKS, help="코드:이름 목록, 쉼표 구분")
    parser.add_argument("--topologies", default=",".join(TOPOLOGY_RUNNERS), help="쉼표 구분")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--snapshot-mode", choices=["off", "record", "replay"], default="off")
    parser.add_argument("--snapshot-dir", type=Path, default=Path("snapshots"))
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
                    record = run_once(topology, code, name, args.snapshot_mode, args.snapshot_dir)
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
