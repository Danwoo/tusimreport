"""도구 호출 기록과 스냅샷(기록·재생).

구조 비교 실험은 같은 입력 데이터 위에서 돌아야 한다. 외부 API는 호출할 때마다
값이 달라지고 무료 한도도 소모하므로, 한 번 실제로 받은 도구 결과를 파일로 남기고
(record) 이후 실험은 그 파일을 돌려준다(replay). off 모드에서도 호출은 기록해
평가(숫자 근거 대조, 커버리지)에 쓴다.

도구 객체는 에이전트 모듈의 전역이라 `instrument_tools`가 바꾸는 동안 같은 프로세스의
다른 실행도 영향을 받는다. 실험은 한 번에 하나씩 돌린다.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool

from core.agent_status import classify_tool_output
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)

SnapshotMode = Literal["off", "record", "replay"]

# Arguments a tool accepts but does not read (save_stock_chart's chart_data). They are dropped
# before keying, so they never turn an identical replay into a fuzzy one.
_IGNORED_ARG_NAMES = frozenset({"chart_data"})
# Arguments replay may ignore when no exact snapshot exists: spellings of the company name. Any
# other argument (stock_code, period_days, ...) changes the data, so a mismatch there is missing.
_LOOSE_ARG_NAMES = frozenset({"company_name", "company", "corp_name", "stock_name", "name"})


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    output: Any
    error: str | None
    source: str  # live | snapshot | snapshot_fuzzy | missing | corrupt
    elapsed_s: float
    agent: str | None = None
    recorded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SnapshotHit:
    match: Literal["exact", "fuzzy"]
    output: Any
    recorded_at: str | None


def _canonical_args(args: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in sorted(args.items())
        if k not in _IGNORED_ARG_NAMES
    }


def _effective_args(args: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    """생략한 인자를 도구의 기본값으로 채운 인자. `{"period_days": 20}` 생략과 명시를 같게 본다."""
    return _canonical_args({**defaults, **args})


def _strict_part(args: Mapping[str, Any]) -> str:
    strict = {k: v for k, v in args.items() if k not in _LOOSE_ARG_NAMES}
    return json.dumps(strict, sort_keys=True, ensure_ascii=False, default=str)


class SnapshotStore:
    """`<root>/<tool>/<key>.json`에 도구 결과를 저장하고 읽는다."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @staticmethod
    def key(tool_name: str, args: dict[str, Any]) -> str:
        payload = json.dumps(
            {"tool": tool_name, "args": _canonical_args(args)}, sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def path(self, tool_name: str, args: dict[str, Any]) -> Path:
        return self.root / tool_name / f"{self.key(tool_name, args)}.json"

    def save(self, tool_name: str, args: dict[str, Any], output: Any) -> Path:
        """임시 파일에 쓴 뒤 바꿔 끼운다. 중간에 끊겨도 반쯤 쓴 스냅샷이 남지 않는다."""
        path = self.path(tool_name, args)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "tool": tool_name,
            "args": _canonical_args(args),
            "output": output,
            "recorded_at": kst_isoformat(),
        }
        text = json.dumps(record, ensure_ascii=False, indent=1, default=str)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return path

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or "output" not in record or not isinstance(record.get("args"), dict):
            raise ValueError(f"스냅샷 형식이 아닙니다: {path.name}")
        return record

    def load(
        self, tool_name: str, args: dict[str, Any], defaults: Mapping[str, Any] | None = None
    ) -> SnapshotHit | None:
        """같은 인자로 기록한 결과. 없으면 이름 표기만 다른 기록 중 가장 최근 것(fuzzy).

        도구 기본값으로 채웠을 때 인자가 같으면 정확히 일치한 것으로 본다. 회사명 표기 같은
        이름 인자(`_LOOSE_ARG_NAMES`)만 다르면 fuzzy로 돌려준다. 그 밖의 인자가 하나라도 다르면
        None이다. 손상된 파일을 만나면 예외를 그대로 올린다.
        """
        exact = self.path(tool_name, args)
        if exact.exists():
            record = self._read(exact)
            return SnapshotHit("exact", record["output"], record.get("recorded_at"))

        tool_dir = self.root / tool_name
        if not tool_dir.is_dir():
            return None
        defaults = defaults or {}
        wanted = _effective_args(args, defaults)
        wanted_strict = _strict_part(wanted)
        best: tuple[tuple[bool, str], SnapshotHit] | None = None
        for path in sorted(tool_dir.glob("*.json")):
            record = self._read(path)
            have = _effective_args(record["args"], defaults)
            if _strict_part(have) != wanted_strict:
                continue
            recorded_at = record.get("recorded_at")
            hit = SnapshotHit("exact" if have == wanted else "fuzzy", record["output"], recorded_at)
            rank = (hit.match == "exact", recorded_at or "")
            if best is None or rank > best[0]:
                best = (rank, hit)
        return best[1] if best else None


class ToolCallRecorder:
    """도구 호출을 모두 기록하고, 모드에 따라 스냅샷을 저장하거나 돌려준다.

    `owners`(도구 이름 → 에이전트)를 주면 호출마다 그 도구를 가진 에이전트를 남긴다.
    """

    def __init__(
        self,
        mode: SnapshotMode = "off",
        store: SnapshotStore | None = None,
        owners: Mapping[str, str] | None = None,
    ) -> None:
        if mode != "off" and store is None:
            raise ValueError("record/replay 모드에는 SnapshotStore가 필요합니다")
        self.mode = mode
        self.store = store
        self.owners = dict(owners or {})
        self.calls: list[ToolCall] = []
        self.save_failures = 0
        self._lock = threading.Lock()

    def _append(self, call: ToolCall) -> None:
        call.agent = self.owners.get(call.tool)
        with self._lock:
            self.calls.append(call)

    def _replay(self, tool_name: str, call_args: dict[str, Any], defaults: Mapping[str, Any]) -> Any:
        assert self.store is not None
        started = time.monotonic()
        try:
            found = self.store.load(tool_name, call_args, defaults)
        except (OSError, ValueError, KeyError, TypeError) as e:
            reason = f"스냅샷 손상: {type(e).__name__}: {e}"
            self._append(ToolCall(tool_name, call_args, None, reason, "corrupt", time.monotonic() - started))
            return {"error": f"스냅샷을 읽을 수 없음: {tool_name}", "args": call_args}
        if found is None:
            output = {"error": f"스냅샷 없음: {tool_name}", "args": call_args}
            self._append(ToolCall(tool_name, call_args, output, "snapshot missing", "missing", 0.0))
            return output
        source = "snapshot" if found.match == "exact" else "snapshot_fuzzy"
        self._append(
            ToolCall(
                tool_name,
                call_args,
                found.output,
                None,
                source,
                time.monotonic() - started,
                recorded_at=found.recorded_at,
            )
        )
        return found.output

    def wrap(
        self, tool_name: str, func: Callable[..., Any], defaults: Mapping[str, Any] | None = None
    ) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            call_args = dict(kwargs)
            if self.mode == "replay":
                return self._replay(tool_name, call_args, defaults or {})

            started = time.monotonic()
            fetched_at = kst_isoformat()
            try:
                output = func(*args, **kwargs)
            except Exception as e:
                self._append(ToolCall(tool_name, call_args, None, str(e), "live", time.monotonic() - started))
                raise
            if self.mode == "record":
                assert self.store is not None
                try:
                    self.store.save(tool_name, call_args, output)
                except OSError as e:
                    # The live result still reaches the agent; the run just cannot be replayed later.
                    logger.warning(f"스냅샷 저장 실패 ({tool_name}): {e}")
                    self.save_failures += 1
            self._append(
                ToolCall(
                    tool_name,
                    call_args,
                    output,
                    None,
                    "live",
                    time.monotonic() - started,
                    recorded_at=fetched_at,
                )
            )
            return output

        return wrapper

    def summary(self) -> dict[str, Any]:
        by_source: dict[str, int] = {}
        for call in self.calls:
            by_source[call.source] = by_source.get(call.source, 0) + 1
        stamps = sorted(c.recorded_at for c in self.calls if c.recorded_at)
        result = {
            "calls": len(self.calls),
            "errors": sum(1 for c in self.calls if c.error),
            "with_data": sum(
                1 for c in self.calls if not c.error and classify_tool_output(c.output) == (False, True)
            ),
            "by_source": by_source,
            "fuzzy": by_source.get("snapshot_fuzzy", 0),
            "recorded_at": {"min": stamps[0], "max": stamps[-1]} if stamps else None,
        }
        if self.save_failures:
            result["save_failures"] = self.save_failures
        return result


def _tool_defaults(tool: BaseTool) -> dict[str, Any]:
    return {name: spec["default"] for name, spec in tool.args.items() if "default" in spec}


@contextmanager
def instrument_tools(tools: Iterable[BaseTool], recorder: ToolCallRecorder) -> Iterator[ToolCallRecorder]:
    """도구의 `func`를 recorder로 감싸고, 블록이 끝나면 원래 함수로 되돌린다."""
    originals: list[tuple[BaseTool, Callable[..., Any]]] = []
    try:
        for tool in tools:
            func = getattr(tool, "func", None)
            if func is None:
                continue
            originals.append((tool, func))
            tool.func = recorder.wrap(tool.name, func, _tool_defaults(tool))
        yield recorder
    finally:
        for tool, func in originals:
            tool.func = func
