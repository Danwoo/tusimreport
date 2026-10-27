"""LLM·도구 호출 계측 콜백.

한 번의 분석이 LLM을 몇 번 부르고 토큰을 얼마나 쓰는지, 도구를 몇 번 부르고
몇 번 실패하는지를 에이전트 단위로 센다. 무료 등급의 분당·일간 한도를 계획하고
멀티에이전트 구조끼리 비용을 비교하는 근거가 된다.

`RunnableConfig(callbacks=[...])`로 넘긴 콜백은 LangChain이 contextvar로 하위
실행에 전파하므로, 도구 안에서 다시 부르는 LLM 호출도 같은 콜백에 잡힌다.

도구 호출 수(`tool_calls`)는 데이터 도구만 센다. supervisor가 전문가에게 일을 넘기는
handoff 도구(`transfer_to_*`)는 `handoffs`로 따로 센다. 인자 검증에서 막힌 호출은
도구 함수가 실행되지 않았어도 `tool_calls`·`tool_errors`에 들어가고 `tool_arg_errors`로
따로 보인다.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langgraph_supervisor.handoff import METADATA_KEY_HANDOFF_DESTINATION
from pydantic import ValidationError
from pydantic.v1 import ValidationError as ValidationErrorV1

_HANDOFF_PREFIXES = ("transfer_to_", "transfer_back_to_")


@dataclass
class CallStats:
    """한 실행 범위(에이전트 1개 또는 분석 1회)의 호출 집계."""

    llm_calls: int = 0
    llm_errors: int = 0
    # Responses that carried no usage block; the token totals leave them out.
    llm_calls_without_usage: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    tool_arg_errors: int = 0
    handoffs: int = 0
    tools_used: dict[str, int] = field(default_factory=dict)

    def merge(self, other: CallStats) -> None:
        self.llm_calls += other.llm_calls
        self.llm_errors += other.llm_errors
        self.llm_calls_without_usage += other.llm_calls_without_usage
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.tool_calls += other.tool_calls
        self.tool_errors += other.tool_errors
        self.tool_arg_errors += other.tool_arg_errors
        self.handoffs += other.handoffs
        for name, count in other.tools_used.items():
            self.tools_used[name] = self.tools_used.get(name, 0) + count

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _usage_from_result(response: LLMResult) -> tuple[int, int] | None:
    """응답의 (입력 토큰, 출력 토큰). 제공자가 usage를 주지 않으면 None."""
    input_tokens = output_tokens = 0
    found = False
    for generations in response.generations:
        for generation in generations:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if usage:
                input_tokens += int(usage.get("input_tokens", 0) or 0)
                output_tokens += int(usage.get("output_tokens", 0) or 0)
                found = True
    if not found and response.llm_output:
        usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
        if usage:
            input_tokens = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)
            found = True
    return (input_tokens, output_tokens) if found else None


def _is_handoff(name: str, metadata: dict[str, Any] | None) -> bool:
    return METADATA_KEY_HANDOFF_DESTINATION in (metadata or {}) or name.startswith(_HANDOFF_PREFIXES)


class RunMetricsCallback(BaseCallbackHandler):
    """LLM·도구 호출 수와 토큰을 `self.stats`에 누적한다.

    병렬 에이전트마다 인스턴스를 따로 두는 것이 기본이지만, 도구가 내부 스레드에서
    LLM을 다시 부를 수 있어 누적은 잠금 안에서 한다.
    """

    raise_error = False

    def __init__(self) -> None:
        self.stats = CallStats()
        self._lock = threading.Lock()
        self._handoff_runs: set[UUID] = set()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _usage_from_result(response)
        with self._lock:
            self.stats.llm_calls += 1
            if usage is None:
                self.stats.llm_calls_without_usage += 1
            else:
                self.stats.input_tokens += usage[0]
                self.stats.output_tokens += usage[1]

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        with self._lock:
            self.stats.llm_calls += 1
            self.stats.llm_errors += 1

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        with self._lock:
            if _is_handoff(name, kwargs.get("metadata")):
                self.stats.handoffs += 1
                run_id = kwargs.get("run_id")
                if run_id is not None:
                    self._handoff_runs.add(run_id)
                return
            self.stats.tool_calls += 1
            self.stats.tools_used[name] = self.stats.tools_used.get(name, 0) + 1

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        with self._lock:
            self._handoff_runs.discard(kwargs.get("run_id"))

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        with self._lock:
            run_id = kwargs.get("run_id")
            if run_id in self._handoff_runs:
                self._handoff_runs.discard(run_id)
                return
            self.stats.tool_errors += 1
            # BaseTool.run raises these while parsing the arguments, before the tool function runs.
            if isinstance(error, ValidationError | ValidationErrorV1):
                self.stats.tool_arg_errors += 1
