"""프로젝트 전반에서 공유하는 구조화 타입.

이 모듈을 추가하기 전엔 같은 dict 시그니처가 `Dict[str, Any]`로 흩어져 있어서
- 어떤 필드가 필수인지 IDE/타입체커가 알 수 없고
- 생성지점과 소비지점이 분리돼 키 오타를 런타임에야 알았다.

여기 모인 TypedDict들은 LLM 출력/에이전트 응답/UI 카드의 계약(contract)을
한 곳에서 선언한다. 새 키를 추가할 땐 여기서 시작한다.

NOTE: TypedDict는 runtime cost가 0이다 (단순 dict). 점진 도입 가능.
"""

from __future__ import annotations

from typing import Literal, TypedDict

OpinionLabel = Literal["BUY", "HOLD", "SELL"]


class SplitBuyOrder(TypedDict, total=False):
    """투자 의견의 분할 매수 전략 한 행."""

    order: str
    price_range: str
    weight: str
    timing: str


class InvestmentOpinion(TypedDict, total=False):
    """`korean_investment_opinion_agent.generate_investment_opinion` 반환 형식.

    UI(ui/cards.create_investment_opinion_card)가 이 키들을 그대로 읽는다.
    필수 키: opinion, confidence, reasoning.
    나머지는 fallback이 가능하므로 total=False.
    """

    company_name: str
    stock_code: str
    opinion: OpinionLabel
    confidence: int  # 0-100
    reasoning: str
    key_positives: list[str]
    key_risks: list[str]
    timeframe: str
    current_price: float
    target_price: float
    stop_loss: float
    risk_reward_ratio: float
    split_buy_strategy: list[SplitBuyOrder]
    timestamp: str


# 실제 코드베이스에서 쓰는 모든 status 값. 새 값 추가 시 여기서 시작.
AgentStatus = Literal["success", "limited", "demo", "error", "partial"]


class AgentResponse(TypedDict, total=False):
    """에이전트 헬퍼(`utils/agent_helpers.py`) 메시지 표준 스키마.

    total=False인 이유: status에 따라 채워지는 필드가 다르다
    (`success`는 analysis/data_sources, `limited`는 missing_apis/suggestion 등).
    각 status별 키 집합은 helper 함수의 반환문에서 확인할 수 있다.
    """

    status: AgentStatus
    agent: str
    company_name: str
    stock_code: str
    message: str
    error: str

    # success 전용
    analysis: object
    data_sources: list[str]  # create_success_message가 쓰는 복수형
    data_source: str  # 7개 에이전트(esg/institutional/community/financial 등)가 쓰는 단수형
    # NOTE: data_source vs data_sources는 historical하게 둘 다 코드베이스에 박혀있다.
    # 둘 다 선언해서 TypedDict가 "거짓말"하지 않게 한다. 새 코드는 data_sources 권장.

    # limited/partial 전용
    available_data: object
    missing_apis: list[str]
    suggestion: str
    reason_ko: str
