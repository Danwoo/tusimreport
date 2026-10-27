"""같은 도구·같은 보고서 형식으로 오케스트레이션만 바꾼 세 가지 구조.

- single_agent: 도구 전체를 가진 ReAct 에이전트 하나가 데이터 수집부터 보고서까지 한다.
  "멀티에이전트가 정말 필요한가"를 재는 기준선.
- progressive: 코드가 실행 순서를 정한다(병렬 7개 → 순차 2개 → 보고서 작성기).
  지금 앱의 기본 경로.
- supervisor: LLM supervisor가 9개 전문가에게 handoff로 일을 넘긴다(langgraph-supervisor).
  전문가 결과를 모은 뒤 progressive와 같은 보고서 작성기를 쓴다.

세 구조 모두 `lab.tool_registry`의 같은 도구를 쓰고, 보고서는 같은 템플릿
(`REPORT_GUIDE`, `REPORT_TEMPLATE`)과 근거 규칙을 따른다.

단계 한도(LangGraph recursion_limit)는 전문가 하나에 `AGENT_RECURSION_LIMIT`를 기준으로
맞춘다. 한 그래프에서 9개 영역을 모두 다루는 single_agent와 supervisor는 그 9배를 받는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.errors import GraphRecursionError
from langgraph_supervisor.handoff import METADATA_KEY_IS_HANDOFF_BACK

from core.agent_status import STEP_LIMIT_TEXT, classify_tool_output, hit_step_limit
from core.korean_supervisor_langgraph import (
    EXPERT_LABELS,
    GROUNDING_RULE,
    REPORT_GUIDE,
    REPORT_TEMPLATE,
    create_korean_supervisor,
    generate_comprehensive_report,
    get_supervisor_llm,
)
from core.signals import AGENT_RECURSION_LIMIT, AGENT_TO_SIGNAL, MIN_AGENTS_FOR_REPORT
from lab.snapshot import ToolCallRecorder
from lab.tool_registry import all_tools, tool_owner

GRAPH_RECURSION_LIMIT = AGENT_RECURSION_LIMIT * len(AGENT_TO_SIGNAL)

# Step budget each topology runs with. A LangGraph subgraph receives the parent's config and
# counts its own steps, so each supervisor worker may also use the whole graph limit.
STEP_BUDGETS: dict[str, dict[str, int]] = {
    "single_agent": {"graph": GRAPH_RECURSION_LIMIT},
    "progressive": {"per_specialist": AGENT_RECURSION_LIMIT},
    "supervisor": {"graph": GRAPH_RECURSION_LIMIT, "per_specialist": GRAPH_RECURSION_LIMIT},
}

# Topologies whose report is written from the specialists that pass the data gate. Their
# coverage and grounding sources come from notes["grounded_agents"], not from every tool call.
REPORT_GATED_TOPOLOGIES = frozenset({"progressive", "supervisor"})


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
        agent = call.agent or owners.get(call.tool)
        if has_data and not is_error and agent is not None:
            result.add(agent)
    return [name for name in AGENT_TO_SIGNAL if name in result]


def _grounded_from_statuses(statuses: dict[str, dict[str, Any]]) -> list[str]:
    """엔진과 같은 기준: 예외 없이 끝났고 근거 데이터가 있는 전문가."""
    return [
        name
        for name in AGENT_TO_SIGNAL
        if statuses.get(name, {}).get("status") == "success"
        and statuses[name].get("data_status", "none") != "none"
    ]


def run_progressive(
    stock_code: str, company_name: str, callbacks: list, recorder: ToolCallRecorder
) -> TopologyOutcome:
    from core.progressive_supervisor import ProgressiveAnalysisEngine

    outcome = TopologyOutcome(report=None)
    statuses: dict[str, dict[str, Any]] = {}
    engine = ProgressiveAnalysisEngine()
    for event in engine.stream_progressive_analysis(stock_code, company_name, callbacks=callbacks):
        kind = event.get("type")
        if kind in ("agent_complete", "agent_error") and isinstance(event.get("agent_status"), dict):
            statuses[event["agent_name"]] = event["agent_status"]
        if kind == "agent_complete":
            outcome.specialist_outputs[event["agent_name"]] = event["content"]
        elif kind == "final_report":
            outcome.report = event["report"]
            outcome.notes.update(
                excluded=event.get("excluded", {}),
                agent_statuses=event.get("agent_statuses", statuses),
                grounded_agents=event.get("grounded_agents", []),
            )
        elif kind == "incomplete":
            outcome.notes.update(
                incomplete=event.get("message"),
                excluded=event.get("excluded", {}),
                agent_statuses=event.get("agent_statuses", statuses),
            )
        elif kind in ("system_error", "report_error"):
            outcome.error = event.get("error")
    outcome.notes.setdefault("agent_statuses", statuses)
    outcome.notes.setdefault("grounded_agents", _grounded_from_statuses(outcome.notes["agent_statuses"]))
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
    limit = STEP_BUDGETS["single_agent"]["graph"]
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request}]},
            config={"callbacks": callbacks, "recursion_limit": limit},
        )
    except GraphRecursionError as e:
        return TopologyOutcome(report=None, error=f"단계 한도({limit})를 넘어 중단됐습니다: {e}")
    messages = result["messages"]
    notes: dict[str, Any] = {"messages": len(messages)}
    if hit_step_limit(messages):
        return TopologyOutcome(
            report=None, error=f"단계 한도({limit})를 다 써서 보고서를 끝내지 못했습니다", notes=notes
        )
    final = next((m for m in reversed(messages) if isinstance(m, AIMessage) and m.content), None)
    report = final.content if final is not None and isinstance(final.content, str) else None
    return TopologyOutcome(report=report, notes=notes)


def _is_analysis(message: BaseMessage) -> bool:
    """전문가가 쓴 분석인가. handoff 복귀 문구, 도구 호출 요청, 단계 한도 문구는 아니다."""
    if not isinstance(message, AIMessage) or not isinstance(message.content, str):
        return False
    if message.response_metadata.get(METADATA_KEY_IS_HANDOFF_BACK) or message.tool_calls:
        return False
    return bool(message.content.strip()) and message.content.strip() != STEP_LIMIT_TEXT


def specialist_outputs_from_messages(messages: list[BaseMessage]) -> tuple[list[str], dict[str, str]]:
    """(supervisor가 일을 넘긴 전문가, 전문가별 마지막 분석).

    langgraph-supervisor는 전문가가 끝날 때마다 그 이름으로 'Transferring back to supervisor'
    메시지를 붙인다. 이 메시지와 도구 호출 요청은 분석이 아니므로 건너뛴다.
    """
    called: list[str] = []
    outputs: dict[str, str] = {}
    for message in messages:
        name = getattr(message, "name", None)
        if name not in AGENT_TO_SIGNAL or not isinstance(message, AIMessage):
            continue
        if name not in called:
            called.append(name)
        if _is_analysis(message):
            outputs[name] = str(message.content)
    return called, outputs


def run_supervisor(
    stock_code: str, company_name: str, callbacks: list, recorder: ToolCallRecorder
) -> TopologyOutcome:
    graph = create_korean_supervisor()
    request = (
        f"종목 {stock_code} ({company_name})의 종합 분석을 위해 각 전문가 에이전트에게 작업을 맡기세요. "
        "필요한 전문가를 모두 거친 뒤 종료하세요."
    )
    budget = STEP_BUDGETS["supervisor"]["graph"]
    # Stream so the state reached before a GraphRecursionError is kept: handoffs leave the
    # supervisor subgraph, so a looping supervisor raises instead of returning a step-limit message.
    last_state: dict[str, Any] = {"messages": []}
    graph_hit_limit = False
    try:
        for state in graph.stream(
            {"messages": [{"role": "user", "content": request}]},
            config={"callbacks": callbacks, "recursion_limit": budget},
            stream_mode="values",
        ):
            last_state = state
    except GraphRecursionError:
        graph_hit_limit = True
    messages = last_state.get("messages", [])
    called, outputs = specialist_outputs_from_messages(messages)

    grounded = [name for name in grounded_agents(recorder) if name in outputs]
    excluded: dict[str, str] = {}
    for name in AGENT_TO_SIGNAL:
        if name in grounded:
            continue
        if name not in called:
            excluded[name] = "supervisor가 호출하지 않음"
        elif name not in outputs:
            excluded[name] = "분석 없음 (단계 한도 초과 또는 빈 응답)"
        else:
            excluded[name] = "근거 데이터 없음 (도구 결과가 비었거나 모두 실패)"
    outcome = TopologyOutcome(
        report=None,
        specialist_outputs=outputs,
        notes={
            "called_agents": called,
            "grounded_agents": grounded,
            "excluded": excluded,
            "supervisor_hit_step_limit": graph_hit_limit or hit_step_limit(messages),
        },
    )
    if graph_hit_limit:
        outcome.error = f"supervisor 단계 한도({budget}) 초과: 전문가 호출을 끝내지 못해 보고서를 만들지 않음"
        return outcome
    if len(grounded) < MIN_AGENTS_FOR_REPORT:
        outcome.notes["incomplete"] = (
            f"근거 데이터가 있는 분석이 {len(grounded)}/{len(AGENT_TO_SIGNAL)}개로 "
            f"보고서 기준({MIN_AGENTS_FOR_REPORT}개)에 못 미칩니다"
        )
        return outcome
    try:
        outcome.report = generate_comprehensive_report(
            get_supervisor_llm(),
            {name: outputs[name] for name in grounded},
            stock_code,
            company_name,
            excluded=excluded,
            callbacks=callbacks,
        )
    except Exception as e:
        outcome.error = f"{type(e).__name__}: {e}"
    return outcome


TopologyRunner = Callable[[str, str, list, ToolCallRecorder], TopologyOutcome]

TOPOLOGY_RUNNERS: dict[str, TopologyRunner] = {
    "single_agent": run_single_agent,
    "progressive": run_progressive,
    "supervisor": run_supervisor,
}
