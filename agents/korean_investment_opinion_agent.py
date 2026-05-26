"""
Korean Investment Opinion Agent
8개 전문 에이전트 분석 결과를 종합하여 명확한 투자 의견 생성
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from config.llm_factory import build_llm
from core.schemas import InvestmentOpinion
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


def _clamp_price(raw: Any, current_price: float, default_mult: float) -> int:
    """LLM이 반환한 가격을 current_price 대비 합리적 범위(0.5x-2.0x)로 clamp.

    - 파싱 실패/음수/0 → current_price * default_mult로 fallback.
    - 너무 멀면 (0.5x 미만 또는 2.0x 초과) 경계로 clamp (LLM 환각 방어).
    """
    if current_price <= 0:
        return int(current_price * default_mult)
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return int(current_price * default_mult)
    if price <= 0:
        return int(current_price * default_mult)
    lower = current_price * 0.5
    upper = current_price * 2.0
    return int(max(lower, min(upper, price)))


@tool
def generate_investment_opinion(
    company_name: str, stock_code: str, agent_results: dict[str, Any], current_price: float | None = None
) -> InvestmentOpinion:
    """
    🔧 P1-1: Level 3 투자 의견 생성 (목표가, 손절가, R/R 비율, 분할 매수 전략)

    8개 에이전트 분석 결과를 종합하여 고급 투자 의견 생성

    Args:
        company_name: 기업명
        stock_code: 종목코드
        agent_results: 8개 에이전트 분석 결과 딕셔너리
            {
                'context': {...},
                'sentiment': {...},
                'financial': {...},
                'technical': {...},
                'institutional': {...},
                'comparative': {...},
                'esg': {...},
                'community': {...}
            }
        current_price: 현재가 (옵션, 없으면 자동 추출 시도)

    Returns:
        {
            "company_name": str,
            "stock_code": str,
            "opinion": "BUY" | "HOLD" | "SELL",
            "confidence": int (0-100),
            "reasoning": str,
            "key_positives": List[str],
            "key_risks": List[str],
            "timeframe": "단기(1-3개월)" | "중기(3-6개월)" | "장기(6개월+)",
            # 🆕 Level 3 추가 필드
            "current_price": float,
            "target_price": float,
            "stop_loss": float,
            "risk_reward_ratio": float,
            "split_buy_strategy": List[Dict],
            "timestamp": str
        }
    """
    try:
        logger.info(f"🔧 P1-1: Generating Level 3 investment opinion for {company_name} ({stock_code})")

        # 🆕 현재가 추출 (없으면 FinanceDataReader로 가져오기)
        if current_price is None:
            current_price = _extract_current_price(stock_code, agent_results)
            logger.info(f"Current price extracted: {current_price:,}원")
        else:
            logger.info(f"Current price provided: {current_price:,}원")

        # LLM 모델 (통합 팩토리)
        llm = build_llm(temperature=0.3)

        # 8개 에이전트 결과 요약
        analysis_summary = _summarize_agent_results(agent_results)

        # 🔧 P1-1: Level 3 시스템 프롬프트 (목표가, 손절가, R/R, 분할매수 추가)
        system_prompt = f"""당신은 한국 주식 투자 전문 애널리스트입니다.

**역할**:
8개 전문 에이전트의 분석 결과를 종합하여 명확한 투자 의견을 제시합니다.

**투자 의견 기준**:
- **BUY (매수)**: 긍정 요인이 리스크를 크게 상회하고, 중장기 성장 가능성이 높을 때
- **HOLD (보유)**: 긍정 요인과 리스크가 비등하거나, 단기 불확실성이 있으나 중장기 전망은 양호할 때
- **SELL (매도)**: 리스크가 긍정 요인을 상회하거나, 펀더멘털 악화가 명확할 때

**신뢰도 산정 기준**:
- 80-100%: 8개 에이전트 대부분이 같은 방향 (매우 높음)
- 60-79%: 주요 에이전트(재무, 기술, 기관)가 일치 (높음)
- 40-59%: 에이전트 의견이 혼재 (중간)
- 20-39%: 에이전트 의견 충돌 많음 (낮음)
- 0-19%: 데이터 부족 또는 심각한 불일치 (매우 낮음)

**🆕 Level 3 추가 분석 요구사항**:
1. **목표가 (target_price)**:
   - 현재가: {current_price:,}원
   - 3-6개월 목표가를 재무/기술/기관 분석 기반으로 산출
   - BUY: 현재가 대비 15-30% 상승 목표
   - HOLD: 현재가 대비 5-15% 상승 목표
   - SELL: 현재가 대비 0-5% 또는 하락 예상

2. **손절가 (stop_loss)**:
   - 리스크 관리를 위한 손절가 제안
   - 일반적으로 현재가 대비 -5% ~ -15%
   - 기술적 지지선, 재무 악화 신호 고려

3. **Risk/Reward 비율 (risk_reward_ratio)**:
   - 계산식: (목표가 - 현재가) / (현재가 - 손절가)
   - 2.0 이상: 매우 좋음 (수익 가능성이 손실의 2배 이상)
   - 1.5-2.0: 좋음
   - 1.0-1.5: 보통
   - 1.0 미만: 위험 (리스크가 너무 높음)

4. **분할 매수 전략 (split_buy_strategy)**:
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
    "risk_reward_ratio": 2.2,  # 소수점 1자리
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
4. 숫자는 명확히 (신뢰도는 정수, 가격은 정수, R/R은 소수점 1자리)
5. 목표가와 손절가는 반드시 현재가({current_price:,}원) 기준으로 합리적 범위 내
"""

        # 사용자 프롬프트
        user_prompt = f"""**종목**: {company_name} ({stock_code})

**8개 전문 에이전트 분석 결과**:

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

        # 생성지점에서 화이트리스트 검증 — UI가 막더라도 TypedDict 계약을 진실로 만든다.
        # LLM이 "매수"/"강력매수"/임의 문자열 반환해도 BUY/HOLD/SELL로 정규화.
        raw_opinion = opinion_data.get("opinion", "HOLD")
        if raw_opinion not in ("BUY", "HOLD", "SELL"):
            logger.warning(f"LLM이 비표준 opinion 반환: {raw_opinion!r} → HOLD로 정규화")
            raw_opinion = "HOLD"

        # confidence도 0-100 clamp
        try:
            confidence = int(opinion_data.get("confidence", 50))
        except (TypeError, ValueError):
            confidence = 50
        confidence = max(0, min(100, confidence))

        # 가격/비율도 생성지점에서 합리적 범위로 clamp.
        # LLM이 target=-5000이나 999999999를 뱉으면 UI에서 % 계산이 깨지므로 막아야 함.
        target_price = _clamp_price(opinion_data.get("target_price"), current_price, default_mult=1.1)
        stop_loss = _clamp_price(opinion_data.get("stop_loss"), current_price, default_mult=0.9)
        try:
            rr_ratio = round(float(opinion_data.get("risk_reward_ratio", 1.5)), 1)
        except (TypeError, ValueError):
            rr_ratio = 1.5
        # R/R는 음수/0 차단 + 합리적 상한(10배 이상은 비현실)
        rr_ratio = max(0.1, min(10.0, rr_ratio))

        # 🔧 P1-1: Level 3 결과 포맷팅 (목표가, 손절가, R/R, 분할매수 추가)
        result = {
            "company_name": company_name,
            "stock_code": stock_code,
            "opinion": raw_opinion,
            "confidence": confidence,
            "reasoning": opinion_data.get("reasoning", "분석 결과를 종합하여 판단이 필요합니다."),
            "key_positives": opinion_data.get("key_positives", []),
            "key_risks": opinion_data.get("key_risks", []),
            "timeframe": opinion_data.get("timeframe", "중기(3-6개월)"),
            # 🆕 Level 3 추가 필드
            "current_price": current_price,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "risk_reward_ratio": rr_ratio,
            "split_buy_strategy": opinion_data.get(
                "split_buy_strategy",
                [
                    {
                        "order": "1차",
                        "price_range": f"{int(current_price * 0.98):,}-{int(current_price * 1.02):,}",
                        "weight": "30%",
                        "timing": "현재가 근처",
                    },
                    {
                        "order": "2차",
                        "price_range": f"{int(current_price * 0.94):,}-{int(current_price * 0.97):,}",
                        "weight": "40%",
                        "timing": "조정 시",
                    },
                    {
                        "order": "3차",
                        "price_range": f"{int(current_price * 0.89):,}-{int(current_price * 0.92):,}",
                        "weight": "30%",
                        "timing": "추가 하락 시",
                    },
                ],
            ),
        }

        result["timestamp"] = kst_isoformat()

        logger.info(f"✅ Level 3 투자 의견 생성: {result['opinion']} (신뢰도: {result['confidence']}%)")
        logger.info(
            f"   목표가: {result['target_price']:,}원, 손절가: {result['stop_loss']:,}원, R/R: {result['risk_reward_ratio']}"
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


def _summarize_agent_results(agent_results: dict[str, Any]) -> str:
    """
    8개 에이전트 결과를 텍스트로 요약

    agent_results 형식:
    - Dict[str, str]: 각 키가 에이전트명, 값이 분석 텍스트 (agent_states의 content)
    - 예: {'context_expert': '...text...', 'sentiment_expert': '...text...'}
    """

    summary_parts = []

    # 에이전트명 매핑
    agent_labels = {
        "context_expert": "🌍 **시장 환경 분석**",
        "sentiment_expert": "📰 **뉴스 여론 분석**",
        "financial_expert": "💰 **재무 상태 분석**",
        "advanced_technical_expert": "📈 **기술적 분석**",
        "institutional_trading_expert": "🏦 **기관 수급 분석**",
        "comparative_expert": "⚖️ **상대 가치 분석**",
        "esg_expert": "🌱 **ESG 분석**",
        "community_expert": "💬 **커뮤니티 투자 심리**",
    }

    # 각 에이전트 결과를 순서대로 추가
    for agent_name in [
        "context_expert",
        "sentiment_expert",
        "financial_expert",
        "advanced_technical_expert",
        "institutional_trading_expert",
        "comparative_expert",
        "esg_expert",
        "community_expert",
    ]:
        if agent_name in agent_results and agent_results[agent_name]:
            content = agent_results[agent_name]
            # 텍스트가 너무 길면 앞부분만 (LLM 컨텍스트 제한)
            if len(content) > 1500:
                content = content[:1500] + "...(생략)"

            summary_parts.append(f"{agent_labels.get(agent_name, agent_name)}:\n{content}\n")

    return "\n".join(summary_parts)


def _extract_current_price(stock_code: str, agent_results: dict[str, Any]) -> float:
    """
    🆕 P1-1: 현재가 추출

    우선순위:
    1. agent_results에서 추출 시도
    2. FinanceDataReader로 직접 조회

    Returns:
        현재가 (float)
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

        # 3. 모두 실패 시 기본값 (100,000원)
        logger.warning("현재가 조회 실패. 기본값 100,000원 사용")
        return 100000.0

    except Exception as e:
        logger.error(f"현재가 추출 오류: {str(e)}")
        return 100000.0  # 기본값


def _create_fallback_opinion(
    company_name: str, stock_code: str, error_msg: str, current_price: float = 100000.0
) -> dict[str, Any]:
    """🔧 P1-1: Level 3 fallback 투자 의견 (에러 발생 시)"""
    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "opinion": "HOLD",
        "confidence": 30,
        "reasoning": f"분석 중 오류가 발생하여 정확한 투자 의견을 생성할 수 없습니다. ({error_msg[:50]}...)",
        "key_positives": ["데이터 부족으로 판단 어려움"],
        "key_risks": ["분석 오류로 리스크 평가 불가"],
        "timeframe": "중기(3-6개월)",
        # 🆕 Level 3 필드
        "current_price": current_price,
        "target_price": int(current_price * 1.05),
        "stop_loss": int(current_price * 0.95),
        "risk_reward_ratio": 1.0,
        "split_buy_strategy": [
            {"order": "1차", "price_range": "데이터 부족", "weight": "30%", "timing": "분석 불가"},
            {"order": "2차", "price_range": "데이터 부족", "weight": "40%", "timing": "분석 불가"},
            {"order": "3차", "price_range": "데이터 부족", "weight": "30%", "timing": "분석 불가"},
        ],
        "timestamp": kst_isoformat(),
        "error": error_msg,
    }


# 테스트용 함수
def test_investment_opinion():
    """투자 의견 에이전트 테스트"""

    # 샘플 에이전트 결과 (실제로는 8개 에이전트에서 받음)
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
