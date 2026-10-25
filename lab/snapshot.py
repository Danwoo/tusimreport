"""도구 호출 기록과 스냅샷(기록·재생).

구조 비교 실험은 같은 입력 데이터 위에서 돌아야 한다. 외부 API는 호출할 때마다
값이 달라지고 무료 한도도 소모하므로, 한 번 실제로 받은 도구 결과를 파일로 남기고
(record) 이후 실험은 그 파일을 돌려준다(replay). off 모드에서도 호출은 기록해
평가(숫자 근거 대조, 커버리지)에 쓴다.

도구 객체는 에이전트 모듈의 전역이라 `instrument_tools`가 바꾸는 동안 같은 프로세스의
다른 실행도 영향을 받는다. 실험은 한 번에 하나씩 돌린다.
"""

from __future__ import annotations

import functools
import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool

from core.agent_status import classify_tool_output
from utils.time import kst_isoformat

SnapshotMode = Literal["off", "record", "replay"]
_STOCK_ARG_NAMES = ("stock_code", "ticker", "symbol", "code")


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    output: Any
    error: str | None
    source: str  # live | snapshot | snapshot_fuzzy | missing
    elapsed_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in sorted(args.items())}


def _stock_of(args: dict[str, Any]) -> str | None:
    for name in _STOCK_ARG_NAMES:
        value = args.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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
        path = self.path(tool_name, args)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "tool": tool_name,
            "args": _canonical_args(args),
            "output": output,
            "recorded_at": kst_isoformat(),
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return path

    def load(self, tool_name: str, args: dict[str, Any]) -> tuple[str, Any] | None:
        """(일치 방식, 결과). 정확히 같은 인자가 없으면 같은 종목의 가장 최근 기록을 쓴다.

        LLM은 같은 도구를 회사명 표기만 바꿔 부르기도 하므로, 종목코드가 같으면 같은
        데이터로 본다. 이렇게 맞춘 호출은 snapshot_fuzzy로 표시해 결과에 남긴다.
        """
        exact = self.path(tool_name, args)
        if exact.exists():
            return "exact", json.loads(exact.read_text(encoding="utf-8"))["output"]

        tool_dir = self.root / tool_name
        if not tool_dir.is_dir():
            return None
        candidates = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(tool_dir.glob("*.json"))]
        stock = _stock_of(args)
        if stock is not None:
            candidates = [c for c in candidates if _stock_of(c["args"]) == stock]
        elif len(candidates) != 1:
            return None
        if not candidates:
            return None
        latest = max(candidates, key=lambda c: c.get("recorded_at", ""))
        return "fuzzy", latest["output"]


class ToolCallRecorder:
    """도구 호출을 모두 기록하고, 모드에 따라 스냅샷을 저장하거나 돌려준다."""

    def __init__(self, mode: SnapshotMode = "off", store: SnapshotStore | None = None) -> None:
        if mode != "off" and store is None:
            raise ValueError("record/replay 모드에는 SnapshotStore가 필요합니다")
        self.mode = mode
        self.store = store
        self.calls: list[ToolCall] = []
        self._lock = threading.Lock()

    def _append(self, call: ToolCall) -> None:
        with self._lock:
            self.calls.append(call)

    def wrap(self, tool_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            call_args = dict(kwargs)
            if self.mode == "replay":
                assert self.store is not None
                found = self.store.load(tool_name, call_args)
                if found is None:
                    output = {"error": f"스냅샷 없음: {tool_name}", "args": call_args}
                    self._append(ToolCall(tool_name, call_args, output, "snapshot missing", "missing", 0.0))
                    return output
                match, output = found
                source = "snapshot" if match == "exact" else "snapshot_fuzzy"
                self._append(ToolCall(tool_name, call_args, output, None, source, time.monotonic() - started))
                return output

            try:
                output = func(*args, **kwargs)
            except Exception as e:
                self._append(ToolCall(tool_name, call_args, None, str(e), "live", time.monotonic() - started))
                raise
            if self.mode == "record":
                assert self.store is not None
                self.store.save(tool_name, call_args, output)
            self._append(ToolCall(tool_name, call_args, output, None, "live", time.monotonic() - started))
            return output

        return wrapper

    def summary(self) -> dict[str, Any]:
        by_source: dict[str, int] = {}
        for call in self.calls:
            by_source[call.source] = by_source.get(call.source, 0) + 1
        return {
            "calls": len(self.calls),
            "errors": sum(1 for c in self.calls if c.error),
            "with_data": sum(
                1 for c in self.calls if not c.error and classify_tool_output(c.output) == (False, True)
            ),
            "by_source": by_source,
        }


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
            tool.func = recorder.wrap(tool.name, func)
        yield recorder
    finally:
        for tool, func in originals:
            tool.func = func
