"""
Korean Investment Opinion Agent
8개 전문 에이전트 분석 결과를 종합하여 명확한 투자 의견 생성
"""

import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import get_llm_model

logger = logging.getLogger(__name__)


@tool
def generate_investment_opinion(
    company_name: str,
    stock_code: str,
    agent_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    8개 에이전트 분석 결과를 종합하여 투자 의견 생성

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
            "timestamp": str
        }
    """
    try:
        logger.info(f"Generating investment opinion for {company_name} ({stock_code})")

        # LLM 모델 가져오기
        provider, model, api_key = get_llm_model(raise_on_missing=True)

        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=0.3  # 일관된 의견 생성
            )
        else:  # openai
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=0.3
            )

        # 8개 에이전트 결과 요약
        analysis_summary = _summarize_agent_results(agent_results)

        # 시스템 프롬프트
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

**출력 형식 (JSON)**:
{{
    "opinion": "BUY" | "HOLD" | "SELL",
    "confidence": 75,  # 0-100 정수
    "reasoning": "3-5줄 요약 (왜 이 의견인지 핵심 근거)",
    "key_positives": ["긍정 요인 1", "긍정 요인 2", "긍정 요인 3"],  # 2-3개
    "key_risks": ["리스크 1", "리스크 2", "리스크 3"],  # 2-3개
    "timeframe": "단기(1-3개월)" | "중기(3-6개월)" | "장기(6개월+)"
}}

**주의사항**:
1. 반드시 JSON 형식으로만 출력 (다른 텍스트 없이)
2. 투자 권유가 아니라 분석 결과 기반 참고 의견임을 명시
3. 모호한 표현 금지 ("종합적으로 긍정적" 등 X)
4. 숫자는 명확히 (신뢰도는 정수만)
"""

        # 사용자 프롬프트
        user_prompt = f"""**종목**: {company_name} ({stock_code})

**8개 전문 에이전트 분석 결과**:

{analysis_summary}

위 분석 결과를 종합하여 투자 의견을 생성해주세요.
반드시 JSON 형식으로만 출력해주세요.
"""

        # LLM 호출
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = llm.invoke(messages)
        response_text = response.content.strip()

        # JSON 파싱
        import json

        # JSON 블록 추출 (```json ... ``` 형태 처리)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        opinion_data = json.loads(response_text)

        # 결과 포맷팅
        result = {
            "company_name": company_name,
            "stock_code": stock_code,
            "opinion": opinion_data.get("opinion", "HOLD"),
            "confidence": int(opinion_data.get("confidence", 50)),
            "reasoning": opinion_data.get("reasoning", "분석 결과를 종합하여 판단이 필요합니다."),
            "key_positives": opinion_data.get("key_positives", []),
            "key_risks": opinion_data.get("key_risks", []),
            "timeframe": opinion_data.get("timeframe", "중기(3-6개월)"),
        }

        # 시간 기록
        from datetime import datetime
        result["timestamp"] = datetime.now().isoformat()

        logger.info(f"Investment opinion generated: {result['opinion']} (신뢰도: {result['confidence']}%)")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        logger.error(f"Response text: {response_text}")
        return _create_fallback_opinion(company_name, stock_code, "JSON 파싱 오류")
    except Exception as e:
        logger.error(f"Error generating investment opinion: {str(e)}")
        return _create_fallback_opinion(company_name, stock_code, str(e))


def _summarize_agent_results(agent_results: Dict[str, Any]) -> str:
    """8개 에이전트 결과를 텍스트로 요약"""

    summary_parts = []

    # 1. 시장 환경 (Context)
    if 'context' in agent_results and agent_results['context']:
        context = agent_results['context']
        summary_parts.append(f"""
🌍 **시장 환경 분석**:
- KOSPI 지수: {context.get('kospi_index', 'N/A')}
- 기준금리: {context.get('base_rate', 'N/A')}
- 시장 전망: {context.get('market_outlook', 'N/A')}
""")

    # 2. 뉴스 여론 (Sentiment)
    if 'sentiment' in agent_results and agent_results['sentiment']:
        sentiment = agent_results['sentiment']
        summary_parts.append(f"""
📰 **뉴스 여론 분석**:
- 전체 감정: {sentiment.get('overall_sentiment', 'N/A')}
- 긍정 뉴스: {sentiment.get('positive_count', 0)}개
- 부정 뉴스: {sentiment.get('negative_count', 0)}개
- 주요 이슈: {', '.join(sentiment.get('key_topics', [])[:3])}
""")

    # 3. 재무 상태 (Financial)
    if 'financial' in agent_results and agent_results['financial']:
        financial = agent_results['financial']
        summary_parts.append(f"""
💰 **재무 상태 분석**:
- 부채비율: {financial.get('debt_ratio', 'N/A')}
- ROE: {financial.get('roe', 'N/A')}
- 영업이익률: {financial.get('operating_margin', 'N/A')}
- 재무 건전성: {financial.get('financial_health', 'N/A')}
""")

    # 4. 기술적 분석 (Technical)
    if 'technical' in agent_results and agent_results['technical']:
        technical = agent_results['technical']
        summary_parts.append(f"""
📈 **기술적 분석**:
- RSI: {technical.get('rsi', 'N/A')}
- MACD 시그널: {technical.get('macd_signal', 'N/A')}
- 볼린저밴드: {technical.get('bollinger_signal', 'N/A')}
- 추세: {technical.get('trend', 'N/A')}
""")

    # 5. 기관 수급 (Institutional)
    if 'institutional' in agent_results and agent_results['institutional']:
        institutional = agent_results['institutional']
        summary_parts.append(f"""
🏦 **기관 수급 분석**:
- 최근 3일 기관 매매: {institutional.get('recent_trend', 'N/A')}
- 순매수 금액: {institutional.get('net_buying', 'N/A')}
- 수급 전망: {institutional.get('supply_outlook', 'N/A')}
""")

    # 6. 상대 가치 (Comparative)
    if 'comparative' in agent_results and agent_results['comparative']:
        comparative = agent_results['comparative']
        summary_parts.append(f"""
⚖️ **상대 가치 분석**:
- PER: {comparative.get('per', 'N/A')} (업계 평균: {comparative.get('sector_avg_per', 'N/A')})
- PBR: {comparative.get('pbr', 'N/A')} (업계 평균: {comparative.get('sector_avg_pbr', 'N/A')})
- 밸류에이션: {comparative.get('valuation', 'N/A')}
""")

    # 7. ESG 분석
    if 'esg' in agent_results and agent_results['esg']:
        esg = agent_results['esg']
        summary_parts.append(f"""
🌱 **ESG 분석**:
- ESG 등급: {esg.get('esg_grade', 'N/A')}
- 지배구조: {esg.get('governance', 'N/A')}
- 지속가능성: {esg.get('sustainability', 'N/A')}
""")

    # 8. 커뮤니티 심리 (Community)
    if 'community' in agent_results and agent_results['community']:
        community = agent_results['community']
        summary_parts.append(f"""
💬 **커뮤니티 투자 심리**:
- 전체 감정: {community.get('overall_sentiment', 'N/A')}
- 긍정 게시글: {community.get('positive_count', 0)}개
- 부정 게시글: {community.get('negative_count', 0)}개
- 주요 관심사: {', '.join(community.get('key_topics', [])[:3])}
""")

    return "\n".join(summary_parts)


def _create_fallback_opinion(
    company_name: str,
    stock_code: str,
    error_msg: str
) -> Dict[str, Any]:
    """에러 발생 시 fallback 투자 의견"""
    from datetime import datetime

    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "opinion": "HOLD",
        "confidence": 30,
        "reasoning": f"분석 중 오류가 발생하여 정확한 투자 의견을 생성할 수 없습니다. ({error_msg[:50]}...)",
        "key_positives": ["데이터 부족으로 판단 어려움"],
        "key_risks": ["분석 오류로 리스크 평가 불가"],
        "timeframe": "중기(3-6개월)",
        "timestamp": datetime.now().isoformat(),
        "error": error_msg
    }


# 테스트용 함수
def test_investment_opinion():
    """투자 의견 에이전트 테스트"""

    # 샘플 에이전트 결과 (실제로는 8개 에이전트에서 받음)
    sample_results = {
        'context': {
            'kospi_index': '2,500',
            'base_rate': '3.50%',
            'market_outlook': '안정적'
        },
        'sentiment': {
            'overall_sentiment': 'positive',
            'positive_count': 15,
            'negative_count': 5,
            'key_topics': ['신제품 출시', '실적 개선', '시장 점유율 증가']
        },
        'financial': {
            'debt_ratio': '45%',
            'roe': '12.5%',
            'operating_margin': '15.3%',
            'financial_health': '우수'
        },
        'technical': {
            'rsi': '65',
            'macd_signal': '매수',
            'bollinger_signal': '중립',
            'trend': '상승'
        },
        'institutional': {
            'recent_trend': '순매수',
            'net_buying': '+50억원',
            'supply_outlook': '긍정적'
        },
        'comparative': {
            'per': '12.5',
            'sector_avg_per': '15.2',
            'pbr': '1.8',
            'sector_avg_pbr': '2.1',
            'valuation': '저평가'
        },
        'esg': {
            'esg_grade': 'A',
            'governance': '우수',
            'sustainability': '양호'
        },
        'community': {
            'overall_sentiment': 'positive',
            'positive_count': 25,
            'negative_count': 10,
            'key_topics': ['매수 추천', '기술력 우수', '성장 기대']
        }
    }

    result = generate_investment_opinion.invoke({
        'company_name': '삼성전자',
        'stock_code': '005930',
        'agent_results': sample_results
    })

    print("=== 투자 의견 생성 결과 ===")
    print(f"종목: {result['company_name']} ({result['stock_code']})")
    print(f"투자 의견: {result['opinion']}")
    print(f"신뢰도: {result['confidence']}%")
    print(f"투자 기간: {result['timeframe']}")
    print(f"\n근거:\n{result['reasoning']}")
    print(f"\n긍정 요인:")
    for pos in result['key_positives']:
        print(f"  - {pos}")
    print(f"\n주요 리스크:")
    for risk in result['key_risks']:
        print(f"  - {risk}")


if __name__ == "__main__":
    # 테스트 실행
    test_investment_opinion()
