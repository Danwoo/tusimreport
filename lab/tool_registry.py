"""9개 에이전트 모듈에 정의된 LangChain 도구를 한 곳에서 모은다.

구조 비교 실험은 모든 topology가 같은 도구 집합을 써야 공정하다. 도구 정의는
각 에이전트 모듈에 그대로 두고, 여기서는 모듈 수준 목록(`*_tools`)을 읽기만 한다.
"""

from __future__ import annotations

import importlib

from langchain_core.tools import BaseTool

# 에이전트 이름 → (모듈, 도구 목록 변수 이름)
AGENT_TOOL_LISTS: dict[str, tuple[str, str]] = {
    "context_expert": ("agents.korean_context_agent", "context_tools"),
    "sentiment_expert": ("agents.korean_sentiment_agent", "sentiment_tools"),
    "financial_expert": ("agents.korean_financial_react_agent", "financial_tools"),
    "advanced_technical_expert": ("agents.korean_advanced_technical_agent", "advanced_technical_tools"),
    "institutional_trading_expert": (
        "agents.korean_institutional_trading_agent",
        "institutional_trading_tools",
    ),
    "comparative_expert": ("agents.korean_comparative_agent", "comparative_tools"),
    "esg_expert": ("agents.korean_esg_analysis_agent", "esg_tools"),
    "community_expert": ("agents.korean_community_agent", "community_tools"),
    "global_market_expert": ("agents.korean_global_market_agent", "global_market_tools"),
}


def tools_by_agent() -> dict[str, list[BaseTool]]:
    result: dict[str, list[BaseTool]] = {}
    for agent_name, (module_name, attr) in AGENT_TOOL_LISTS.items():
        module = importlib.import_module(module_name)
        result[agent_name] = list(getattr(module, attr))
    return result


def all_tools() -> list[BaseTool]:
    """모든 에이전트의 도구를 이름 기준으로 중복 없이 모은다."""
    seen: dict[str, BaseTool] = {}
    for tools in tools_by_agent().values():
        for tool in tools:
            seen.setdefault(tool.name, tool)
    return list(seen.values())


def tool_owner() -> dict[str, str]:
    """도구 이름 → 그 도구를 가진 에이전트 이름."""
    return {tool.name: agent for agent, tools in tools_by_agent().items() for tool in tools}
