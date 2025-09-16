#!/usr/bin/env python3
"""
Korean Institutional Trading Agent - PyKRX 투자자별 매매 동향 전문 분석
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

import pykrx.stock as stock
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)

def get_investor_trading_analysis_logic(stock_code: str, period_days: int = 20) -> Dict[str, Any]:
    """투자자별 매매 동향 분석 로직"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days + 10)
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        trading_value = stock.get_market_trading_value_by_investor(start_str, end_str, stock_code)
        if trading_value.empty:
            return {"error": f"No trading value data for {stock_code}"}
        
        analysis_data = {}
        if '순매수' in trading_value.columns:
            latest_net = trading_value['순매수']
            key_investors = ['외국인', '기관합계', '개인']
            key_analysis = {}
            for investor in key_investors:
                if investor in latest_net.index:
                    net_amount = float(latest_net[investor])
                    key_analysis[investor] = {
                        'net_purchase_billion': net_amount / 100000000,
                    }
            analysis_data['key_investors'] = key_analysis

        return convert_numpy_types({
            "status": "success",
            "analysis_data": analysis_data,
            "data_source": "PyKRX"
        })
    except Exception as e:
        return {"error": str(e)}

@tool
def get_investor_trading_analysis(stock_code: str, period_days: int = 20) -> Dict[str, Any]:
    """투자자별 매매 동향 분석 (기관/개인/외국인)"""
    return get_investor_trading_analysis_logic(stock_code, period_days)

# 도구 목록
institutional_trading_tools = [get_investor_trading_analysis]

def create_institutional_trading_agent():
    """Institutional Trading Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.1, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

    prompt = (
        "당신은 기관투자자들의 매매 패턴을 분석하는 수급 분석 전문가입니다. "
        "투자자들이 쉽게 이해할 수 있도록 누가 사고 있고 누가 팔고 있는지, 그리고 이것이 주가에 어떤 영향을 주는지 분석해주세요.\n\n"

        "먼저 `get_investor_trading_analysis` 도구를 사용해서 최신 매매 동향 데이터를 수집한 후, "
        "다음과 같이 이해하기 쉽게 설명해주세요:\n\n"

        "1. 누가 이 주식을 사고 팔고 있는지 알려주세요\n"
        "   - 외국인투자자, 기관투자자, 개인투자자 중에서 누가 많이 사고 있는지\n"
        "   - 최근 몇 주간의 매매 패턴이 어떤지\n"
        "   - 이런 패턴이 평소와 비교해서 어떻게 다른지\n\n"

        "2. 외국인 투자자들의 움직임을 분석해주세요\n"
        "   - 지속적으로 사고 있는지, 팔고 있는지\n"
        "   - 글로벌 시장 상황과 어떤 관련이 있는지\n"
        "   - 환율이나 해외 증시가 영향을 주고 있는지\n\n"

        "3. 국내 기관투자자들은 어떻게 하고 있는지 알려주세요\n"
        "   - 연기금, 보험회사, 자산운용사들의 움직임\n"
        "   - 장기 투자 목적인지 단기 수익 목적인지\n"
        "   - 기관들끼리 의견이 일치하는지 엇갈리는지\n\n"

        "4. 개인투자자들의 매매 패턴을 설명해주세요\n"
        "   - 개인들이 주로 언제 사고 파는지\n"
        "   - 기관이나 외국인과 반대로 움직이고 있는지\n"
        "   - 감정적인 매매를 하고 있는지, 냉정한 판단인지\n\n"

        "5. 이런 수급 상황이 주가에 어떤 영향을 줄 것 같은지 분석해주세요\n"
        "   - 단기적으로 상승 압력인지 하락 압력인지\n"
        "   - 언제까지 이런 패턴이 이어질 것 같은지\n"
        "   - 수급 상황이 바뀔 수 있는 신호가 있는지\n\n"

        "6. 투자자들이 주의해서 봐야 할 점들을 알려주세요\n"
        "   - 특정 투자자 그룹에 너무 의존하고 있지는 않은지\n"
        "   - 급격한 매매 변화가 일어날 위험은 없는지\n"
        "   - 공매도나 대량 거래 같은 특별한 상황은 없는지\n\n"

        "전문 용어를 쓸 때는 쉬운 설명을 함께 해주시고, "
        "수치를 말할 때는 그것이 많은 건지 적은 건지, 좋은 신호인지 나쁜 신호인지 함께 설명해주세요. "
        "마치 증권사 직원이 고객에게 친근하게 설명해주는 것처럼 작성해주세요.\n\n"

        "참고: 이 분석은 수급 분석 참고자료이며 매매 추천이 아닙니다. 투자 시에는 신중히 판단하세요.\n\n"
        "🚨 매우 중요 🚨: 분석을 완전히 마친 후 새로운 줄에서 반드시 'INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이 신호가 없으면 시스템이 분석을 완료된 것으로 인식하지 못합니다. 절대 잊지 마세요!"
    )
    
    return create_react_agent(model=llm, tools=institutional_trading_tools, prompt=prompt, name="institutional_trading_expert")
