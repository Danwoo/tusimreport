"""같은 도구·같은 보고서 형식으로 오케스트레이션만 바꾼 세 가지 구조.

- single_agent: 도구 전체를 가진 ReAct 에이전트 하나가 데이터 수집부터 보고서까지 한다.
  "멀티에이전트가 정말 필요한가"를 재는 기준선.
- progressive: 코드가 실행 순서를 정한다(병렬 7개 → 순차 2개 → 보고서 작성기).
  지금 앱의 기본 경로.
- supervisor: LLM supervisor가 9개 전문가에게 handoff로 일을 넘긴다(langgraph-supervisor).
  전문가 결과를 모은 뒤 progressive와 같은 보고서 작성기를 쓴다.

세 구조 모두 `lab.tool_registry`의 같은 도구를 쓰고, 보고서는 같은 템플릿
(`REPORT_GUIDE`, `REPORT_TEMPLATE`)과 근거 규칙을 따른다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage

from core.agent_status import classify_tool_output
from core.korean_supervisor_langgraph import (
    EXPERT_LABELS,
    GROUNDING_RULE,
    REPORT_GUIDE,
    REPORT_TEMPLATE,
    create_korean_supervisor,
    generate_comprehensive_report,
    get_supervisor_llm,
)
from core.signals import AGENT_TO_SIGNAL, MIN_AGENTS_FOR_REPORT
from lab.snapshot import ToolCallRecorder
from lab.tool_registry import all_tools, tool_owner


@dataclass
class TopologyOutcome:
    report: str | None
    specialist_outputs: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)


def grounded_agents(recorder: ToolCallRecorder) -> list[str]:
    """도구 호출 기록에서 근거 데이터를 하나라도 받은 에이전트."""
    owners = tool_owner()
    result: set[str] = set()
    for call in recorder.calls:
        if call.error:
            continue
        is_error, has_data = classify_tool_output(call.output)
        if has_data and not is_error and call.tool in owners:
            result.add(owners[call.tool])
    return [name for name in AGENT_TO_SIGNAL if name in result]


def run_progressive(
    stock_code: str, company_name: str, callbacks: list, recorder: ToolCallRecorder
) -> TopologyOutcome:
    from core.progressive_supervisor import ProgressiveAnalysisEngine

    outcome = TopologyOutcome(report=None)
    engine = ProgressiveAnalysisEngine()
    for event in engine.stream_progressive_analysis(stock_code, company_name, callbacks=callbacks):
        kind = event.get("type")
        if kind == "agent_complete":
            outcome.specialist_outputs[event["agent_name"]] = event["content"]
        elif kind == "final_report":
            outcome.report = event["report"]
            outcome.notes.update(
                excluded=event.get("excluded", {}),
                agent_statuses=event.get("agent_statuses", {}),
                grounded_agents=event.get("grounded_agents", []),
            )
        elif kind == "incomplete":
            outcome.notes.update(
                incomplete=event.get("message"),
                excluded=event.get("excluded", {}),
                agent_statuses=event.get("agent_statuses", {}),
            )
        elif kind in ("system_error", "report_error"):
            outcome.error = event.get("error")
    return outcome


def _single_agent_prompt() -> str:
    owners = tool_owner()
    lines = "\n".join(f"- `{name}`: {EXPERT_LABELS.get(agent, agent)}" for name, agent in owners.items())
    return f"""당신은 한국 주식 리서치 애널리스트입니다. 아래 도구를 직접 호출해 데이터를 모은 뒤
종합 투자 리서치 보고서를 한국어로 작성합니다.

사용할 수 있는 도구와 담당 영역:
{lines}

진행 방법:
1. 영역마다 해당 도구를 호출해 데이터를 모은다. 같은 도구를 불필요하게 반복 호출하지 않는다.
2. 도구가 오류를 돌려준 영역은 '데이터 없음'으로 처리한다.
3. 모든 도구를 확인한 뒤 아래 형식으로 보고서를 쓴다.

{GROUNDING_RULE}

{REPORT_GUIDE}

{REPORT_TEMPLATE}
"""


def run_single_agent(
    stock_code: str, company_name: str, callbacks: list, recorder: ToolCallRecorder
) -> TopologyOutcome:
    from langgraph.prebuilt import create_react_agent

    from config.llm_factory import build_llm

    llm = build_llm(temperature=0.1)
    if llm is None:
        raise ValueError("LLM 설정이 없습니다 (docs/API_KEYS.md)")
    agent = create_react_agent(model=llm, tools=all_tools(), prompt=_single_agent_prompt())
    request = f"종목 {stock_code} ({company_name})에 대한 종합 투자 리서치 보고서를 작성해주세요."
    result = agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"callbacks": callbacks, "recursion_limit": 60},
    )
    final = next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage) and m.content), None)
    report = final.content if final is not None and isinstance(final.content, str) else None
    return TopologyOutcome(report=report, notes={"messages": len(result["messages"])})


def run_supervisor(
    stock_code: str, company_name: str, callbacks: list, recorder: ToolCallRecorder
) -> TopologyOutcome:
    graph = create_korean_supervisor()
    request = (
        f"종목 {stock_code} ({company_name})의 종합 분석을 위해 각 전문가 에이전트에게 작업을 맡기세요. "
        "필요한 전문가를 모두 거친 뒤 종료하세요."
    )
    result = graph.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"callbacks": callbacks, "recursion_limit": 100},
    )

    outputs: dict[str, str] = {}
    for message in result["messages"]:
        name = getattr(message, "name", None)
        if isinstance(message, AIMessage) and name in AGENT_TO_SIGNAL and isinstance(message.content, str):
            outputs[name] = message.content

    grounded = [name for name in grounded_agents(recorder) if name in outputs]
    excluded = {
        name: "근거 데이터 없음 (도구 결과가 비었거나 모두 실패)"
        if name in outputs
        else "supervisor가 호출하지 않음"
        for name in AGENT_TO_SIGNAL
        if name not in grounded
    }
    outcome = TopologyOutcome(
        report=None,
        specialist_outputs=outputs,
        notes={"called_agents": list(outputs), "grounded_agents": grounded, "excluded": excluded},
    )
    if len(grounded) < MIN_AGENTS_FOR_REPORT:
        outcome.notes["incomplete"] = (
            f"근거 데이터가 있는 분석이 {len(grounded)}/{len(AGENT_TO_SIGNAL)}개로 "
            f"보고서 기준({MIN_AGENTS_FOR_REPORT}개)에 못 미칩니다"
        )
        return outcome
    outcome.report = generate_comprehensive_report(
        get_supervisor_llm(),
        {name: outputs[name] for name in grounded},
        stock_code,
        company_name,
        excluded=excluded,
        callbacks=callbacks,
    )
    return outcome


TopologyRunner = Callable[[str, str, list, ToolCallRecorder], TopologyOutcome]

TOPOLOGY_RUNNERS: dict[str, TopologyRunner] = {
    "single_agent": run_single_agent,
    "progressive": run_progressive,
    "supervisor": run_supervisor,
}
