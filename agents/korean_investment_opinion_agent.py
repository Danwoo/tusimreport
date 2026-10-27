"""
Korean Investment Opinion Agent
근거 데이터가 있는 전문 에이전트 분석 결과를 종합하여 명확한 투자 의견 생성
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from config.llm_factory import build_llm
from core.korean_supervisor_langgraph import EXPERT_LABELS
from core.schemas import InvestmentOpinion
from core.signals import AGENT_TO_SIGNAL
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


# 현재가 대비 이 범위를 벗어난 LLM 가격은 환각으로 보고 버린다 (경계값으로 바꿔 넣지 않는다).
PRICE_RANGE = (0.5, 2.0)


def _parse_price(raw: Any, current_price: float | None) -> int | None:
    """LLM이 준 가격. 현재가가 없거나, 숫자가 아니거나, 현재가 대비 범위를 벗어나면 None."""
    if current_price is None or current_price <= 0:
        return None
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return None
    low, high = PRICE_RANGE
    if not current_price * low <= price <= current_price * high:
        logger.warning(f"범위를 벗어난 가격을 버림: {raw!r} (현재가 {current_price:,.0f}원)")
        return None
    return int(price)


def _risk_reward(
    current_price: float | None, target_price: int | None, stop_loss: int | None
) -> float | None:
    """(목표가 - 현재가) / (현재가 - 손절가). LLM이 계산한 값 대신 가격에서 직접 구한다."""
    if current_price is None or target_price is None or stop_loss is None:
        return None
    if not stop_loss < current_price < target_price:
        return None
    return round((target_price - current_price) / (current_price - stop_loss), 1)


_OPINION_ALIASES = {
    "BUY": "BUY",
    "HOLD": "HOLD",
    "SELL": "SELL",
    "매수": "BUY",
    "강력매수": "BUY",
    "보유": "HOLD",
    "중립": "HOLD",
    "매도": "SELL",
    "강력매도": "SELL",
}


def _parse_opinion(raw: Any) -> str:
    """같은 뜻의 표기만 BUY/HOLD/SELL로 맞춘다. 알 수 없는 값을 HOLD로 바꿔 넣지 않는다."""
    label = _OPINION_ALIASES.get(str(raw).strip().upper()) or _OPINION_ALIASES.get(str(raw).strip())
    if label is None:
        raise ValueError(f"알 수 없는 투자 의견: {raw!r}")
    return label


def _parse_confidence(raw: Any) -> int | None:
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return None


def _parse_split_plan(raw: Any) -> list[dict[str, str]]:
    """LLM이 준 분할 매수 계획 중 형식이 맞는 항목만. 없으면 빈 목록 (가격대를 지어내지 않는다)."""
    if not isinstance(raw, list):
        return []
    keys = ("order", "price_range", "weight", "timing")
    return [{k: str(item.get(k, "")) for k in keys} for item in raw if isinstance(item, dict)]


@tool
def generate_investment_opinion(
    company_name: str, stock_code: str, agent_results: dict[str, Any], current_price: float | None = None
) -> InvestmentOpinion:
    """
    투자 의견 생성 (목표가, 손절가, R/R 비율, 분할 매수 전략 포함)

    근거 데이터가 있는 전문 에이전트 분석 결과를 종합하여 고급 투자 의견 생성

    Args:
        company_name: 기업명
        stock_code: 종목코드
        agent_results: 에이전트명 → 분석 텍스트. 근거 데이터가 있는 분석만 넘긴다.
            예: {'context_expert': '...', 'financial_expert': '...'}
            빠진 영역은 프롬프트에 '데이터 없음'으로 적힌다.
        current_price: 현재가 (옵션, 없으면 자동 추출 시도)

    Returns:
        {
            "company_name": str,
            "stock_code": str,
            "opinion": "BUY" | "HOLD" | "SELL",
            "confidence": int (0-100) | None,
            "reasoning": str,
            "key_positives": List[str],
            "key_risks": List[str],
            "timeframe": "단기(1-3개월)" | "중기(3-6개월)" | "장기(6개월+)",
            "current_price": float | None,  # 받지 못하면 None
            "target_price": int | None,
            "stop_loss": int | None,
            "risk_reward_ratio": float | None,  # 가격에서 계산
            "split_buy_strategy": List[Dict],
            "timestamp": str
        }
    """
    try:
        logger.info(f"Generating investment opinion for {company_name} ({stock_code})")

        # 현재가 추출 (없으면 FinanceDataReader로 가져오기)
        if current_price is None:
            current_price = _extract_current_price(stock_code, agent_results)
        logger.info(f"Current price: {current_price if current_price is not None else '없음'}")
        price_line = f"{current_price:,.0f}원" if current_price is not None else "데이터 없음"

        # LLM 모델 (통합 팩토리)
        llm = build_llm(temperature=0.3)

        analysis_summary = _summarize_agent_results(agent_results)
        section_count = f"{len(opinion_sections(agent_results))}/{len(AGENT_TO_SIGNAL)}"

        system_prompt = f"""당신은 한국 주식 투자 전문 애널리스트입니다.

**역할**:
전문 에이전트 분석 결과({section_count}개 영역)를 종합하여 명확한 투자 의견을 제시합니다.
'데이터 없음'으로 표시된 영역은 근거로 쓰지 않고 내용을 짐작하지 않습니다.

**투자 의견 기준**:
- **BUY (매수)**: 긍정 요인이 리스크를 크게 상회하고, 중장기 성장 가능성이 높을 때
- **HOLD (보유)**: 긍정 요인과 리스크가 비등하거나, 단기 불확실성이 있으나 중장기 전망은 양호할 때
- **SELL (매도)**: 리스크가 긍정 요인을 상회하거나, 펀더멘털 악화가 명확할 때

**신뢰도 산정 기준**:
- 80-100%: 분석된 영역 대부분이 같은 방향 (매우 높음)
- 60-79%: 주요 에이전트(재무, 기술, 기관)가 일치 (높음)
- 40-59%: 에이전트 의견이 혼재 (중간)
- 20-39%: 에이전트 의견 충돌 많음 (낮음)
- 0-19%: 데이터 부족 또는 심각한 불일치 (매우 낮음)

**추가 분석 요구사항**:
현재가가 '데이터 없음'이면 target_price, stop_loss는 null, split_buy_strategy는 빈 목록으로 둔다.

1. **목표가 (target_price)**:
   - 현재가: {price_line}
   - 3-6개월 목표가를 재무/기술/기관 분석 기반으로 산출
   - BUY: 현재가 대비 15-30% 상승 목표
   - HOLD: 현재가 대비 5-15% 상승 목표
   - SELL: 현재가 대비 0-5% 또는 하락 예상

2. **손절가 (stop_loss)**:
   - 리스크 관리를 위한 손절가 제안
   - 일반적으로 현재가 대비 -5% ~ -15%
   - 기술적 지지선, 재무 악화 신호 고려

3. **분할 매수 전략 (split_buy_strategy)**:
   - 3회 분할 매수 추천 (리스크 분산)
   - 각 매수 시점: 가격대, 비중(%), 타이밍
   - 예시:
     [
       {{"order": "1차", "price": 64000-66000원 범위, "weight": "30%", "timing": "현재가 근처"}},
       {{"order": "2차", "price": 61000-63000원 범위, "weight": "40%", "timing": "조정 시"}},
       {{"order": "3차", "price": 58000-60000원 범위, "weight": "30%", "timing": "추가 하락 시"}}
     ]

**출력 형식 (JSON)**:
{{
    "opinion": "BUY" | "HOLD" | "SELL",
    "confidence": 75,  # 0-100 정수
    "reasoning": "3-5줄 요약 (왜 이 의견인지 핵심 근거)",
    "key_positives": ["긍정 요인 1", "긍정 요인 2", "긍정 요인 3"],  # 2-3개
    "key_risks": ["리스크 1", "리스크 2", "리스크 3"],  # 2-3개
    "timeframe": "단기(1-3개월)" | "중기(3-6개월)" | "장기(6개월+)",
    "target_price": 78000,  # 정수 (원)
    "stop_loss": 59000,  # 정수 (원)
    "split_buy_strategy": [
        {{"order": "1차", "price_range": "64,000-66,000", "weight": "30%", "timing": "현재가 근처"}},
        {{"order": "2차", "price_range": "61,000-63,000", "weight": "40%", "timing": "조정 시"}},
        {{"order": "3차", "price_range": "58,000-60,000", "weight": "30%", "timing": "추가 하락 시"}}
    ]
}}

**주의사항**:
1. 반드시 JSON 형식으로만 출력 (다른 텍스트 없이)
2. 투자 권유가 아니라 분석 결과 기반 참고 의견임을 명시
3. 모호한 표현 금지 ("종합적으로 긍정적" 등 X)
4. 숫자는 명확히 (신뢰도는 정수, 가격은 정수)
5. 목표가와 손절가는 현재가({price_line}) 기준으로 합리적 범위 내. 범위를 크게 벗어난 가격은 버려진다
"""

        # 사용자 프롬프트
        user_prompt = f"""**종목**: {company_name} ({stock_code})

**전문 에이전트 분석 결과 ({section_count}개 영역)**:

{analysis_summary}

위 분석 결과를 종합하여 투자 의견을 생성해주세요.
반드시 JSON 형식으로만 출력해주세요.
"""

        # LLM 호출
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = llm.invoke(messages)
        response_text = response.content.strip()

        # JSON 블록 추출 (```json ... ``` 형태 처리)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        opinion_data = json.loads(response_text)

        raw_opinion = _parse_opinion(opinion_data.get("opinion"))

        target_price = _parse_price(opinion_data.get("target_price"), current_price)
        stop_loss = _parse_price(opinion_data.get("stop_loss"), current_price)

        result = {
            "company_name": company_name,
            "stock_code": stock_code,
            "opinion": raw_opinion,
            "confidence": _parse_confidence(opinion_data.get("confidence")),
            "reasoning": opinion_data.get("reasoning", ""),
            "key_positives": opinion_data.get("key_positives", []),
            "key_risks": opinion_data.get("key_risks", []),
            "timeframe": opinion_data.get("timeframe", ""),
            "current_price": current_price,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "risk_reward_ratio": _risk_reward(current_price, target_price, stop_loss),
            "split_buy_strategy": _parse_split_plan(opinion_data.get("split_buy_strategy"))
            if current_price is not None
            else [],
        }

        result["timestamp"] = kst_isoformat()

        logger.info(
            f"투자 의견 생성: {result['opinion']} (신뢰도 {result['confidence']}, 목표가 {result['target_price']}, "
            f"손절가 {result['stop_loss']}, R/R {result['risk_reward_ratio']})"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        logger.error(f"Response text: {response_text}")
        return _create_fallback_opinion(company_name, stock_code, "JSON 파싱 오류", current_price)
    except Exception as e:
        logger.error(f"Error generating investment opinion: {str(e)}")
        # current_price는 함수 파라미터(또는 _extract_current_price)로 항상 bound되어 있다.
        return _create_fallback_opinion(company_name, stock_code, str(e), current_price)


def opinion_sections(agent_results: dict[str, Any]) -> dict[str, str]:
    """투자 의견에 들어가는 분석: AGENT_TO_SIGNAL 순서, 내용이 있는 텍스트만.

    호출자는 이 수로 투자 의견을 만들지 정한다. 프롬프트에 실제로 들어가는 영역 수와 같다.
    """
    sections = {}
    for name in AGENT_TO_SIGNAL:
        content = agent_results.get(name)
        if isinstance(content, str) and content.strip():
            sections[name] = content.strip()
    return sections


def _summarize_agent_results(agent_results: dict[str, Any]) -> str:
    """분석 결과를 영역별 텍스트로 옮기고, 빠진 영역을 '데이터 없음'으로 적는다.

    agent_results: 에이전트명 → 분석 텍스트 (예: {'context_expert': '...'})
    """
    sections = opinion_sections(agent_results)
    summary_parts = []
    for name, content in sections.items():
        # 텍스트가 너무 길면 앞부분만 (LLM 컨텍스트 제한)
        if len(content) > 1500:
            content = content[:1500] + "...(생략)"
        summary_parts.append(f"**{EXPERT_LABELS.get(name, name)}**:\n{content}\n")

    missing = [name for name in AGENT_TO_SIGNAL if name not in sections]
    if missing:
        lines = "\n".join(f"- {EXPERT_LABELS.get(name, name)}" for name in missing)
        summary_parts.append(f"**데이터 없음** (근거 데이터가 없어 빠진 영역):\n{lines}\n")

    return "\n".join(summary_parts)


def _extract_current_price(stock_code: str, agent_results: dict[str, Any]) -> float | None:
    """
    현재가 추출

    우선순위:
    1. agent_results에서 추출 시도
    2. FinanceDataReader로 직접 조회

    Returns:
        현재가. 어디서도 받지 못하면 None.
    """
    try:
        # 1. agent_results에서 추출 시도 (예: technical expert 결과에 있을 수 있음)
        for agent_name, content in agent_results.items():
            if isinstance(content, str):
                # "현재가: 65,000원" 같은 패턴 찾기
                price_patterns = [
                    r"현재가[:\s]+([0-9,]+)원?",
                    r"종가[:\s]+([0-9,]+)원?",
                    r"Close[:\s]+([0-9,]+)",
                ]
                for pattern in price_patterns:
                    match = re.search(pattern, content)
                    if match:
                        price_str = match.group(1).replace(",", "")
                        price = float(price_str)
                        logger.info(f"현재가 추출 성공 ({agent_name}에서): {price:,}원")
                        return price

        # 2. FinanceDataReader로 직접 조회
        logger.info("agent_results에서 현재가 없음. FinanceDataReader로 조회 중...")
        import FinanceDataReader as fdr

        df = fdr.DataReader(stock_code, end=None)  # 최근 데이터
        if df is not None and not df.empty:
            current_price = float(df["Close"].iloc[-1])
            logger.info(f"FinanceDataReader로 현재가 조회 성공: {current_price:,}원")
            return current_price

        logger.warning("현재가를 받지 못함")
        return None

    except Exception as e:
        logger.error(f"현재가 추출 오류: {str(e)}")
        return None


def _create_fallback_opinion(
    company_name: str, stock_code: str, error_msg: str, current_price: float | None = None
) -> dict[str, Any]:
    """오류 시 돌려주는 결과. 'error'가 있어 화면에 투자 의견으로 표시되지 않는다."""
    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "opinion": "HOLD",
        "confidence": None,
        "reasoning": f"분석 중 오류가 발생해 투자 의견을 만들지 못했습니다. ({error_msg[:50]})",
        "key_positives": [],
        "key_risks": [],
        "timeframe": "",
        "current_price": current_price,
        "target_price": None,
        "stop_loss": None,
        "risk_reward_ratio": None,
        "split_buy_strategy": [],
        "timestamp": kst_isoformat(),
        "error": error_msg,
    }


# 테스트용 함수
def test_investment_opinion():
    """투자 의견 에이전트 테스트"""

    # 샘플 에이전트 결과
    sample_results = {
        "context": {"kospi_index": "2,500", "base_rate": "3.50%", "market_outlook": "안정적"},
        "sentiment": {
            "overall_sentiment": "positive",
            "positive_count": 15,
            "negative_count": 5,
            "key_topics": ["신제품 출시", "실적 개선", "시장 점유율 증가"],
        },
        "financial": {
            "debt_ratio": "45%",
            "roe": "12.5%",
            "operating_margin": "15.3%",
            "financial_health": "우수",
        },
        "technical": {"rsi": "65", "macd_signal": "매수", "bollinger_signal": "중립", "trend": "상승"},
        "institutional": {"recent_trend": "순매수", "net_buying": "+50억원", "supply_outlook": "긍정적"},
        "comparative": {
            "per": "12.5",
            "sector_avg_per": "15.2",
            "pbr": "1.8",
            "sector_avg_pbr": "2.1",
            "valuation": "저평가",
        },
        "esg": {"esg_grade": "A", "governance": "우수", "sustainability": "양호"},
        "community": {
            "overall_sentiment": "positive",
            "positive_count": 25,
            "negative_count": 10,
            "key_topics": ["매수 추천", "기술력 우수", "성장 기대"],
        },
    }

    result = generate_investment_opinion.invoke(
        {"company_name": "삼성전자", "stock_code": "005930", "agent_results": sample_results}
    )

    print("=== 투자 의견 생성 결과 ===")
    print(f"종목: {result['company_name']} ({result['stock_code']})")
    print(f"투자 의견: {result['opinion']}")
    print(f"신뢰도: {result['confidence']}%")
    print(f"투자 기간: {result['timeframe']}")
    print(f"\n근거:\n{result['reasoning']}")
    print("\n긍정 요인:")
    for pos in result["key_positives"]:
        print(f"  - {pos}")
    print("\n주요 리스크:")
    for risk in result["key_risks"]:
        print(f"  - {risk}")


if __name__ == "__main__":
    # 테스트 실행
    test_investment_opinion()
