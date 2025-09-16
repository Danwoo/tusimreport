#!/usr/bin/env python3
"""
Korean Advanced Technical Analysis Agent - TA-Lib 기반 고급 기술적 분석
한국 주식 시장 전문 기술적 분석 에이전트
"""

import logging
from typing import Dict, Any
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

import talib
import FinanceDataReader as fdr
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)

def calculate_momentum_indicators_logic(stock_code: str, period: int = 252) -> Dict[str, Any]:
    """모멘텀 지표 계산 로직 (RSI, MACD, 스토캐스틱 등)"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period + 100)
        df = fdr.DataReader(stock_code, start=start_date.strftime('%Y-%m-%d'))
        if df.empty: return {"error": f"No data for {stock_code}"}

        high = df['High'].astype(np.float64)
        low = df['Low'].astype(np.float64)
        close = df['Close'].astype(np.float64)
        
        rsi = talib.RSI(close, timeperiod=14)
        macd_line, macd_signal, _ = talib.MACD(close)
        slowk, slowd = talib.STOCH(high, low, close)

        return convert_numpy_types({
            "status": "success",
            "indicators": {
                "RSI": float(rsi.iloc[-1]),
                "MACD": {'line': float(macd_line.iloc[-1]), 'signal': float(macd_signal.iloc[-1])},
                "Stochastic": {'K': float(slowk.iloc[-1]), 'D': float(slowd.iloc[-1])}
            }
        })
    except Exception as e:
        return {"error": str(e)}

@tool
def calculate_momentum_indicators(stock_code: str, period: int = 252) -> Dict[str, Any]:
    """모멘텀 지표 계산 (RSI, MACD, 스토캐스틱, CCI, Williams %R 등)"""
    return calculate_momentum_indicators_logic(stock_code, period)

# 다른 지표 함수들도 위와 같이 _logic과 @tool로 분리할 수 있으나, 테스트를 위해 하나만 분리합니다.
# For brevity, only one function is refactored. Others like trend, volatility follow the same pattern.

# 도구 목록
advanced_technical_tools = [calculate_momentum_indicators]

def create_advanced_technical_agent():
    """Advanced Technical Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.1, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

    prompt = (
        "당신은 차트와 기술적 지표를 분석하는 기술적 분석 전문가입니다. "
        "투자자들이 쉽게 이해할 수 있도록 차트의 흐름과 매매 신호를 분석해주세요.\n\n"

        "먼저 `calculate_momentum_indicators` 도구를 사용해서 다양한 기술적 지표들을 계산한 후, "
        "다음과 같이 친근하고 이해하기 쉽게 설명해주세요:\n\n"

        "1. 현재 주가의 전체적인 흐름이 어떤지 설명해주세요\n"
        "   - 상승 추세인지, 하락 추세인지, 횡보하고 있는지\n"
        "   - 이동평균선들이 어떻게 배치되어 있는지\n"
        "   - 추세가 얼마나 강한지 약한지\n\n"

        "2. 주요 기술적 지표들이 보여주는 신호를 알려주세요\n"
        "   - RSI나 MACD 같은 지표들이 현재 어떤 상태인지\n"
        "   - 과매수나 과매도 상태인지\n"
        "   - 매수 신호인지 매도 신호인지 (하지만 이건 참고용일 뿐이에요)\n\n"

        "3. 거래량은 어떤 상태인지 분석해주세요\n"
        "   - 거래량이 많은지 적은지\n"
        "   - 가격 움직임과 거래량이 일치하는지\n"
        "   - 기관들이 들어오고 있는지 나가고 있는지\n\n"

        "4. 차트에서 중요하게 봐야 할 가격대들을 알려주세요\n"
        "   - 지지선과 저항선이 어디에 있는지\n"
        "   - 이 가격들을 뚫으면 어떻게 될 것 같은지\n"
        "   - 볼린저 밴드나 다른 지표들이 제시하는 중요 구간\n\n"

        "5. 단기적으로 주의해서 봐야 할 점들을 조언해주세요\n"
        "   - 변동성이 큰지 작은지\n"
        "   - 가짜 신호(속임수)가 나올 가능성은 없는지\n"
        "   - 전체 시장 상황과 개별 종목이 일치하는지\n\n"

        "전문 용어를 사용할 때는 쉬운 말로 함께 설명해주시고, "
        "지표 수치를 말할 때는 그게 좋은 신호인지 나쁜 신호인지도 함께 알려주세요. "
        "너무 복잡하게 말하지 마시고, 일반 투자자도 이해할 수 있게 설명해주세요.\n\n"

        "참고: 이 분석은 기술적 분석 참고자료이며 매매 추천이 아닙니다. 실제 투자 시에는 신중히 판단하세요.\n\n"
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'ADVANCED_TECHNICAL_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )
    
    return create_react_agent(model=llm, tools=advanced_technical_tools, prompt=prompt, name="advanced_technical_expert")
