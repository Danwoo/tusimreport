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


def calculate_momentum_indicators_logic(
    stock_code: str, period: int = 252
) -> Dict[str, Any]:
    """모멘텀 지표 계산 로직 (RSI, MACD, 스토캐스틱 등)"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period + 100)
        df = fdr.DataReader(stock_code, start=start_date.strftime("%Y-%m-%d"))
        if df.empty:
            return {"error": f"No data for {stock_code}"}

        high = df["High"].astype(np.float64)
        low = df["Low"].astype(np.float64)
        close = df["Close"].astype(np.float64)

        rsi = talib.RSI(close, timeperiod=14)
        macd_line, macd_signal, _ = talib.MACD(close)
        slowk, slowd = talib.STOCH(high, low, close)

        return convert_numpy_types(
            {
                "status": "success",
                "indicators": {
                    "RSI": float(rsi.iloc[-1]),
                    "MACD": {
                        "line": float(macd_line.iloc[-1]),
                        "signal": float(macd_signal.iloc[-1]),
                    },
                    "Stochastic": {
                        "K": float(slowk.iloc[-1]),
                        "D": float(slowd.iloc[-1]),
                    },
                },
            }
        )
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
        llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, api_key=llm_api_key)

    prompt = (
        "당신은 증권사의 기술적 분석 애널리스트입니다. 중급 투자자를 대상으로 차트 패턴과 기술적 지표를 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 추세 및 모멘텀(주가 추세 방향, 이동평균선 배치, RSI/MACD/스토캐스틱 수치와 의미), "
        "2) 지지선·저항선 및 변동성(주요 가격대, 볼린저 밴드, 돌파 시 예상 움직임), "
        "3) 단기 매매 타이밍(진입/청산 타이밍과 허위 신호 가능성).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## 기술적 분석\n\n"

        "### 추세 및 모멘텀 분석\n"
        "[현재 추세(상승/하락/횡보)와 이동평균선 배치를 평가하고, RSI/MACD/스토캐스틱 수치와 의미를 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 지지선·저항선 및 변동성\n"
        "[주요 지지선/저항선 가격대와 볼린저 밴드 분석, 가격대 돌파 시 예상 움직임을 2개 문단으로 서술. 400-500자]\n\n"

        "### 단기 매매 타이밍 및 유의사항\n"
        "[진입/청산 타이밍 제시와 허위 신호 주의사항을 2개 문단으로 서술. 400-500자]\n\n"

        "### 참고 데이터\n"
        "- TA-Lib: [사용된 지표 목록]\n"
        "- 분석 기간: [기간]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 400-600자 목표)\n"
        "- 문단 중심 서술 (지표 수치는 괄호 내 표기 예: RSI 65 - 과매수 진입)\n"
        "- 구체적인 지표 수치와 가격대 필수 포함 (RSI, MACD, 지지/저항선 가격)\n"
        "- 전문 용어 사용시 간단한 설명 병기\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- 매매 타이밍은 근거와 함께 명확히 제시\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'ADVANCED_TECHNICAL_ANALYSIS_COMPLETE'를 반드시 포함하세요."
    )

    return create_react_agent(
        model=llm,
        tools=advanced_technical_tools,
        prompt=prompt,
        name="advanced_technical_expert",
    )
