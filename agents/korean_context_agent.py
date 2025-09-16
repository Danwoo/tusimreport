#!/usr/bin/env python3
"""
Korean Market & Economic Context Agent
시장 데이터와 거시 경제 지표를 통합하여 분석의 기본 컨텍스트를 제공합니다.

역할 통합:
- Market Data Agent (시세, 거래량)
- Macro Economic Agent (거시경제 지표)
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

import FinanceDataReader as fdr
import pykrx.stock as stock
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from data.bok_api_client import get_macro_economic_indicators
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)

def get_market_and_economic_context_logic(stock_code: str, company_name: str) -> Dict[str, Any]:
    """주식 시세, 시장 지수, 주요 거시 경제 지표를 종합적으로 수집하고 분석하는 핵심 로직"""
    try:
        logger.info(f"Fetching market and economic context for {stock_code}")
        
        context_data = {}
        insights = []

        # 1. 주식 현재 시세 (FinanceDataReader)
        try:
            df = fdr.DataReader(stock_code, start=datetime.now() - timedelta(days=30))
            if not df.empty:
                latest = df.iloc[-1]
                context_data['stock_price'] = {
                    'current': float(latest['Close']),
                    'change': float(latest['Change']),
                    'volume': int(latest['Volume'])
                }
                insights.append(f"{company_name} 현재가: {latest['Close']:,.0f}원")
        except Exception as e:
            logger.warning(f"FDR stock data error for {stock_code}: {e}")

        # 2. 시장 지수 (PyKRX)
        try:
            today_str = datetime.now().strftime('%Y%m%d')
            kospi_ohlcv = stock.get_index_ohlcv_by_date("20240101", today_str, "1001")
            kosdaq_ohlcv = stock.get_index_ohlcv_by_date("20240101", today_str, "2001")
            if not kospi_ohlcv.empty:
                context_data['kospi'] = {'current': float(kospi_ohlcv.iloc[-1]['종가'])}
                insights.append(f"KOSPI 지수: {kospi_ohlcv.iloc[-1]['종가']:,.2f}")
            if not kosdaq_ohlcv.empty:
                context_data['kosdaq'] = {'current': float(kosdaq_ohlcv.iloc[-1]['종가'])}
                insights.append(f"KOSDAQ 지수: {kosdaq_ohlcv.iloc[-1]['종가']:,.2f}")
        except Exception as e:
            logger.warning(f"PyKRX index data error: {e}")

        # 3. 거시 경제 지표 (BOK API Wrapper)
        try:
            macro_indicators = get_macro_economic_indicators()
            if not macro_indicators.get("error"):
                context_data['macro_economics'] = macro_indicators['indicators']
                rate = macro_indicators.get('indicators', {}).get('base_interest_rate', {}).get('current_rate', 'N/A')
                fx = macro_indicators.get('indicators', {}).get('usd_exchange_rate', {}).get('current_rate', 'N/A')
                insights.append(f"기준금리: {rate}% | 원/달러 환율: {fx}원")
        except Exception as e:
            logger.warning(f"BOK API data error: {e}")

        return convert_numpy_types({
            "status": "success",
            "context_summary": context_data,
            "key_insights": insights,
            "data_sources": ["FinanceDataReader", "PyKRX", "BOK ECOS API"],
            "last_updated": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in get_market_and_economic_context_logic: {str(e)}")
        return {"error": str(e)}

@tool
def get_market_and_economic_context(stock_code: str, company_name: str) -> Dict[str, Any]:
    """주식 시세, 시장 지수, 주요 거시 경제 지표를 종합적으로 수집하고 분석합니다."""
    return get_market_and_economic_context_logic(stock_code, company_name)

# 도구 목록
context_tools = [get_market_and_economic_context]

def create_context_agent():
    """Market & Economic Context Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.1, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

    prompt = (
        "당신은 한국 주식시장을 전문적으로 분석하는 시장 환경 분석가입니다. "
        "투자 초보자부터 경험자까지 모두가 이해하기 쉽게 현재 시장 상황을 설명해주세요.\n\n"

        "먼저 `get_market_and_economic_context` 도구를 사용해서 최신 데이터를 확인한 후, "
        "다음과 같은 자연스러운 방식으로 분석해주세요:\n\n"

        "1. 현재 시장 상황을 간단히 요약해주세요 (주가, 거래량, 시장 지수 등)\n"
        "2. 금리, 환율 같은 경제지표가 실제로 우리 투자에 어떤 의미인지 설명해주세요\n"
        "3. 지금 시장 분위기는 어떤지, 투자자들이 어떤 마음가짐을 가져야 할지 조언해주세요\n"
        "4. 앞으로 주의 깊게 봐야 할 요소들을 알기 쉽게 알려주세요\n\n"

        "마치 경험 많은 투자 상담사가 고객에게 친근하게 설명하듯이 작성해주세요. "
        "전문 용어를 사용할 때는 간단한 설명을 함께 해주시고, "
        "숫자나 데이터를 제시할 때는 그것이 투자자에게 어떤 의미인지 함께 설명해주세요.\n\n"

        "참고: 이 분석은 투자 참고자료이며 투자 추천이 아닙니다. 객관적인 정보 제공을 목적으로 합니다.\n\n"
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'MARKET_CONTEXT_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )
    
    return create_react_agent(model=llm, tools=context_tools, prompt=prompt, name="context_expert")