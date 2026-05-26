"""에이전트 완료 신호 enum.

LLM 출력 종료를 문자열 매칭으로 판정하는 약한 결합을 한 곳에 모은다.
프롬프트, supervisor, progressive engine이 같은 상수를 참조하도록 한다.
"""

from __future__ import annotations

from enum import StrEnum


class AgentSignal(StrEnum):
    """에이전트 → supervisor 완료 신호.

    StrEnum이라 f-string과 비교에 그대로 사용 가능 (Python 3.11+).
    """

    CONTEXT = "MARKET_CONTEXT_ANALYSIS_COMPLETE"
    SENTIMENT = "SENTIMENT_ANALYSIS_COMPLETE"
    FINANCIAL = "FINANCIAL_ANALYSIS_COMPLETE"
    TECHNICAL = "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE"
    INSTITUTIONAL = "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE"
    COMPARATIVE = "COMPARATIVE_ANALYSIS_COMPLETE"
    ESG = "ESG_ANALYSIS_COMPLETE"
    COMMUNITY = "COMMUNITY_ANALYSIS_COMPLETE"
    GLOBAL_MARKET = "GLOBAL_MARKET_ANALYSIS_COMPLETE"
    SUPERVISOR = "SUPERVISOR_REPORT_GENERATION_COMPLETE"


AGENT_TO_SIGNAL: dict[str, AgentSignal] = {
    "context_expert": AgentSignal.CONTEXT,
    "sentiment_expert": AgentSignal.SENTIMENT,
    "financial_expert": AgentSignal.FINANCIAL,
    "advanced_technical_expert": AgentSignal.TECHNICAL,
    "institutional_trading_expert": AgentSignal.INSTITUTIONAL,
    "comparative_expert": AgentSignal.COMPARATIVE,
    "esg_expert": AgentSignal.ESG,
    "community_expert": AgentSignal.COMMUNITY,
    "global_market_expert": AgentSignal.GLOBAL_MARKET,
}

ALL_AGENT_SIGNALS: list[str] = [s.value for s in AgentSignal if s != AgentSignal.SUPERVISOR]
