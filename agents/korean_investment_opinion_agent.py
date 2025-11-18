#!/usr/bin/env python3
"""
Korean Investment Opinion Agent - Phase 1
명확한 투자 의견 제시: BUY/HOLD/SELL + 목표가 + 손절가 + 시나리오 + 리스크

Phase 1 목표: 사용자 만족도 40% → 70%
핵심 해결: "그래서 사야 하나요?" 질문에 명확한 답변
"""

import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import get_llm_model

logger = logging.getLogger(__name__)


@tool
def generate_investment_opinion(
    company_name: str,
    stock_code: str,
    all_agent_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    7개 에이전트 분석 결과를 종합하여 명확한 투자 의견 제시

    Args:
        company_name: 회사명
        stock_code: 종목코드
        all_agent_results: 7개 에이전트 분석 결과

    Returns:
        투자 의견, 목표가, 손절가, 시나리오, 리스크
    """
    try:
        logger.info(f"Investment opinion generation for {company_name} ({stock_code})")

        # 1. 각 에이전트 점수 추출
        scores = _extract_agent_scores(all_agent_results)

        # 2. 투자 의견 계산 (BUY/HOLD/SELL)
        opinion, confidence = _calculate_investment_opinion(scores)

        # 3. 현재가 가져오기 (context_expert 결과에서)
        current_price = _extract_current_price(all_agent_results)

        # 4. 목표가 계산 (1개월/3개월/6개월)
        target_prices = _calculate_target_prices(current_price, scores, opinion)

        # 5. 손절가 계산
        stop_loss = _calculate_stop_loss(current_price, scores)

        # 6. Risk/Reward 비율
        risk_reward = _calculate_risk_reward(current_price, target_prices, stop_loss)

        # 7. 투자 전략
        investment_strategy = _generate_investment_strategy(opinion, confidence)

        # 8. 시나리오 분석 (Bull/Base/Bear)
        scenarios = _generate_scenarios(company_name, current_price, all_agent_results)

        # 9. 리스크 분석
        risks = _analyze_risks(company_name, all_agent_results, scores)

        # 10. 핵심 근거 추출
        key_reasons = _extract_key_reasons(all_agent_results, opinion)

        return {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "current_price": current_price,

            # 투자 의견
            "investment_opinion": {
                "decision": opinion,           # BUY/HOLD/SELL
                "confidence": confidence,       # 0-100
                "key_reasons": key_reasons     # 핵심 근거 3가지
            },

            # 목표가
            "target_prices": target_prices,

            # 손절가
            "stop_loss": {
                "price": stop_loss,
                "percentage": round((stop_loss / current_price - 1) * 100, 1)
            },

            # Risk/Reward
            "risk_reward_ratio": risk_reward,

            # 투자 전략
            "investment_strategy": investment_strategy,

            # 시나리오 분석
            "scenarios": scenarios,

            # 리스크 분석
            "risks": risks,

            # 종합 점수
            "overall_score": scores["total"],

            # 생성 시간
            "generated_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error generating investment opinion: {str(e)}")
        return {"error": str(e)}


def _extract_agent_scores(all_agent_results: Dict[str, Any]) -> Dict[str, float]:
    """
    각 에이전트 결과에서 점수 추출 (0-100)

    가중치:
    - sentiment: 25% (뉴스 감정 분석)
    - financial: 20% (재무 상태)
    - technical: 15% (기술적 분석)
    - institutional: 15% (기관 수급)
    - comparative: 15% (상대 가치)
    - context: 5% (시장 환경)
    - esg: 5% (ESG)
    """
    weights = {
        'sentiment': 0.25,
        'financial': 0.20,
        'technical': 0.15,
        'institutional': 0.15,
        'comparative': 0.15,
        'context': 0.05,
        'esg': 0.05
    }

    scores = {}

    # 각 에이전트 점수 추출 (간단한 휴리스틱)
    # TODO: 실제로는 각 에이전트 결과를 LLM으로 분석하여 점수화

    # Sentiment (뉴스 감정)
    sentiment_data = all_agent_results.get('sentiment_expert', {})
    sentiment_score = _score_sentiment(sentiment_data)
    scores['sentiment'] = sentiment_score

    # Financial (재무)
    financial_data = all_agent_results.get('financial_expert', {})
    financial_score = _score_financial(financial_data)
    scores['financial'] = financial_score

    # Technical (기술적)
    technical_data = all_agent_results.get('advanced_technical_expert', {})
    technical_score = _score_technical(technical_data)
    scores['technical'] = technical_score

    # Institutional (기관)
    institutional_data = all_agent_results.get('institutional_trading_expert', {})
    institutional_score = _score_institutional(institutional_data)
    scores['institutional'] = institutional_score

    # Comparative (상대 가치)
    comparative_data = all_agent_results.get('comparative_expert', {})
    comparative_score = _score_comparative(comparative_data)
    scores['comparative'] = comparative_score

    # Context (시장 환경)
    context_data = all_agent_results.get('context_expert', {})
    context_score = _score_context(context_data)
    scores['context'] = context_score

    # ESG
    esg_data = all_agent_results.get('esg_expert', {})
    esg_score = _score_esg(esg_data)
    scores['esg'] = esg_score

    # 가중 평균 계산
    total_score = sum(scores[k] * weights[k] for k in weights.keys())
    scores['total'] = round(total_score, 1)

    return scores


def _score_sentiment(data: Dict[str, Any]) -> float:
    """뉴스 감정 분석 점수화 (0-100)"""
    # 간단한 휴리스틱: LLM 분석 결과에서 sentiment_score 추출
    # TODO: 실제 구현 시 더 정교한 로직

    # 기본값 50 (중립)
    score = 50.0

    # sentiment_analysis에서 점수 추출 시도
    if 'sentiment_analysis' in data:
        sentiment = data['sentiment_analysis']
        # "Overall Sentiment: 매우 긍정" 같은 텍스트 파싱
        if 'Overall Sentiment' in sentiment:
            if '매우 긍정' in sentiment.get('Overall Sentiment', ''):
                score = 85.0
            elif '긍정' in sentiment.get('Overall Sentiment', ''):
                score = 70.0
            elif '중립' in sentiment.get('Overall Sentiment', ''):
                score = 50.0
            elif '부정' in sentiment.get('Overall Sentiment', ''):
                score = 30.0
            elif '매우 부정' in sentiment.get('Overall Sentiment', ''):
                score = 15.0

    return score


def _score_financial(data: Dict[str, Any]) -> float:
    """재무 상태 점수화 (0-100)"""
    # TODO: 실제 재무 지표 기반 점수화
    return 60.0  # 임시


def _score_technical(data: Dict[str, Any]) -> float:
    """기술적 분석 점수화 (0-100)"""
    # TODO: RSI, MACD 등 기술적 지표 기반 점수화
    return 55.0  # 임시


def _score_institutional(data: Dict[str, Any]) -> float:
    """기관 수급 점수화 (0-100)"""
    # TODO: 기관 매수/매도 동향 기반 점수화
    return 65.0  # 임시


def _score_comparative(data: Dict[str, Any]) -> float:
    """상대 가치 점수화 (0-100)"""
    # TODO: PER/PBR 업종 대비 점수화
    return 70.0  # 임시


def _score_context(data: Dict[str, Any]) -> float:
    """시장 환경 점수화 (0-100)"""
    # TODO: KOSPI 동향, 금리 등 기반 점수화
    return 50.0  # 임시


def _score_esg(data: Dict[str, Any]) -> float:
    """ESG 점수화 (0-100)"""
    # TODO: ESG 등급 기반 점수화
    return 60.0  # 임시


def _calculate_investment_opinion(scores: Dict[str, float]) -> Tuple[str, int]:
    """
    투자 의견 계산

    Returns:
        (의견, 신뢰도)
        의견: BUY, HOLD, SELL
        신뢰도: 0-100
    """
    total_score = scores['total']

    if total_score >= 70:
        opinion = "BUY"
        confidence = int(total_score)
    elif total_score >= 50:
        opinion = "HOLD"
        confidence = int(total_score)
    else:
        opinion = "SELL"
        confidence = int(100 - total_score)  # SELL 신뢰도

    return opinion, confidence


def _extract_current_price(all_agent_results: Dict[str, Any]) -> int:
    """현재가 추출 (임시: 60,000원 고정)"""
    # TODO: context_expert나 technical_expert에서 실제 현재가 추출
    return 60000


def _calculate_target_prices(
    current_price: int,
    scores: Dict[str, float],
    opinion: str
) -> Dict[str, Any]:
    """
    목표가 계산 (1개월/3개월/6개월)

    로직:
    - BUY: 현재가 대비 +5%, +15%, +25%
    - HOLD: +2%, +5%, +8%
    - SELL: -5%, -10%, -15%
    """
    if opinion == "BUY":
        growth_rates = {
            '1_month': 0.05,
            '3_months': 0.15,
            '6_months': 0.25
        }
    elif opinion == "HOLD":
        growth_rates = {
            '1_month': 0.02,
            '3_months': 0.05,
            '6_months': 0.08
        }
    else:  # SELL
        growth_rates = {
            '1_month': -0.05,
            '3_months': -0.10,
            '6_months': -0.15
        }

    return {
        '1_month': {
            'price': int(current_price * (1 + growth_rates['1_month'])),
            'percentage': round(growth_rates['1_month'] * 100, 1)
        },
        '3_months': {
            'price': int(current_price * (1 + growth_rates['3_months'])),
            'percentage': round(growth_rates['3_months'] * 100, 1)
        },
        '6_months': {
            'price': int(current_price * (1 + growth_rates['6_months'])),
            'percentage': round(growth_rates['6_months'] * 100, 1)
        }
    }


def _calculate_stop_loss(current_price: int, scores: Dict[str, float]) -> int:
    """
    손절가 계산

    로직:
    - 기본: 현재가 대비 -8%
    - 변동성 고려 (TODO)
    """
    risk_tolerance = 0.08  # 8% 손실 허용
    return int(current_price * (1 - risk_tolerance))


def _calculate_risk_reward(
    current_price: int,
    target_prices: Dict[str, Any],
    stop_loss: int
) -> float:
    """
    Risk/Reward 비율 계산

    Risk: 현재가 - 손절가
    Reward: 3개월 목표가 - 현재가
    """
    risk = current_price - stop_loss
    reward = target_prices['3_months']['price'] - current_price

    if risk > 0:
        return round(reward / risk, 1)
    else:
        return 0.0


def _generate_investment_strategy(opinion: str, confidence: int) -> Dict[str, int]:
    """
    투자 전략 생성 (분할 매수 전략)

    Returns:
        각 시점별 투자 비중 (%)
    """
    if opinion == "BUY":
        return {
            "entry_now": 50,           # 현재가 50% 진입
            "add_on_dip_5pct": 30,    # -5% 시 30% 추가
            "add_on_dip_10pct": 20    # -10% 시 20% 추가
        }
    elif opinion == "HOLD":
        return {
            "entry_now": 0,
            "add_on_dip_5pct": 50,
            "add_on_dip_10pct": 50
        }
    else:  # SELL
        return {
            "exit_now": 100,
            "add_on_dip_5pct": 0,
            "add_on_dip_10pct": 0
        }


def _generate_scenarios(
    company_name: str,
    current_price: int,
    all_agent_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    시나리오 분석 (Bull/Base/Bear)

    Returns:
        각 시나리오별 확률, 조건, 목표가, 수익률
    """
    # TODO: 실제로는 각 에이전트 결과를 분석하여 시나리오 생성

    return {
        "bull_case": {
            "probability": 40,
            "condition": "HBM 수주 증가, 반도체 업황 개선",
            "target_price": int(current_price * 1.33),  # +33%
            "return_pct": 33,
            "expected_value": round(0.40 * 33, 1)  # 13.2%
        },
        "base_case": {
            "probability": 50,
            "condition": "현재 추세 유지",
            "target_price": int(current_price * 1.17),  # +17%
            "return_pct": 17,
            "expected_value": round(0.50 * 17, 1)  # 8.5%
        },
        "bear_case": {
            "probability": 10,
            "condition": "글로벌 경기 침체",
            "target_price": int(current_price * 0.83),  # -17%
            "return_pct": -17,
            "expected_value": round(0.10 * -17, 1)  # -1.7%
        },
        "expected_return": round(0.40 * 33 + 0.50 * 17 + 0.10 * -17, 1)  # 20.0%
    }


def _analyze_risks(
    company_name: str,
    all_agent_results: Dict[str, Any],
    scores: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    리스크 분석

    Returns:
        리스크 목록 (최대 3개)
    """
    # TODO: 실제로는 각 에이전트 결과에서 리스크 추출

    return [
        {
            "risk": "메모리 반도체 가격 급락",
            "probability": 15,
            "impact": -20,
            "severity": "HIGH",
            "mitigation": "손절가 설정 필수"
        },
        {
            "risk": "중국 정부 규제 강화",
            "probability": 10,
            "impact": -15,
            "severity": "MEDIUM",
            "mitigation": "포지션 50% 축소 고려"
        },
        {
            "risk": "환율 급등 (원화 약세)",
            "probability": 5,
            "impact": 5,  # 긍정적
            "severity": "LOW (Positive)",
            "mitigation": "유지"
        }
    ]


def _extract_key_reasons(all_agent_results: Dict[str, Any], opinion: str) -> List[str]:
    """
    투자 의견의 핵심 근거 3가지 추출
    """
    # TODO: 실제로는 각 에이전트 결과를 분석하여 추출

    if opinion == "BUY":
        return [
            "뉴스 감정 분석: 긍정 60%, HBM 관련 호재 집중",
            "기관 수급: 3일 연속 순매수 (1,200억원)",
            "밸류에이션: PER 12배 (업종 평균 15배 대비 저평가)"
        ]
    elif opinion == "HOLD":
        return [
            "재무 상태 양호하나 성장 모멘텀 부족",
            "기술적 지표 중립 (RSI 50)",
            "업종 평균 수준의 밸류에이션"
        ]
    else:  # SELL
        return [
            "뉴스 감정 분석: 부정 60%, 실적 악화 우려",
            "기관 수급: 5일 연속 순매도",
            "밸류에이션: PER 20배 (업종 평균 15배 대비 고평가)"
        ]


# 에이전트 생성 함수
def create_investment_opinion_agent():
    """Investment Opinion Agent 생성"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()

    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=llm_model_name,
            temperature=0.1,
            google_api_key=llm_api_key
        )
    else:
        llm = ChatOpenAI(
            model=llm_model_name,
            temperature=0.1,
            api_key=llm_api_key
        )

    prompt = """당신은 투자 의사결정 전문가입니다.

7개 AI 전문가의 분석 결과를 종합하여 명확한 투자 의견을 제시합니다.

핵심 원칙:
1. 명확성: BUY/HOLD/SELL 중 하나를 확실히 제시
2. 근거: 3가지 핵심 이유를 명확히 제시
3. 실용성: 목표가, 손절가, 투자 전략 구체적으로 제시
4. 리스크: 주요 리스크 3가지와 대응 방안 제시

투자자가 즉시 액션을 취할 수 있도록 명확하게 제시하세요.
"""

    return create_react_agent(
        model=llm,
        tools=[generate_investment_opinion],
        prompt=prompt,
        name="investment_opinion_expert"
    )


if __name__ == "__main__":
    # 테스트
    test_results = {
        'sentiment_expert': {
            'sentiment_analysis': {
                'Overall Sentiment': '긍정'
            }
        },
        'financial_expert': {},
        'advanced_technical_expert': {},
        'institutional_trading_expert': {},
        'comparative_expert': {},
        'context_expert': {},
        'esg_expert': {}
    }

    result = generate_investment_opinion(
        company_name="삼성전자",
        stock_code="005930",
        all_agent_results=test_results
    )

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
