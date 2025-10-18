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


def get_market_and_economic_context_logic(
    stock_code: str, company_name: str
) -> Dict[str, Any]:
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
                context_data["stock_price"] = {
                    "current": float(latest["Close"]),
                    "change": float(latest["Change"]),
                    "volume": int(latest["Volume"]),
                }
                insights.append(f"{company_name} 현재가: {latest['Close']:,.0f}원")
        except Exception as e:
            logger.warning(f"FDR stock data error for {stock_code}: {e}")

        # 2. 시장 지수 (PyKRX) - 최근 30일만
        try:
            today_str = datetime.now().strftime("%Y%m%d")
            start_str = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            kospi_ohlcv = stock.get_index_ohlcv_by_date(start_str, today_str, "1001")
            kosdaq_ohlcv = stock.get_index_ohlcv_by_date(start_str, today_str, "2001")
            if not kospi_ohlcv.empty:
                context_data["kospi"] = {"current": float(kospi_ohlcv.iloc[-1]["종가"])}
                insights.append(f"KOSPI 지수: {kospi_ohlcv.iloc[-1]['종가']:,.2f}")
            if not kosdaq_ohlcv.empty:
                context_data["kosdaq"] = {
                    "current": float(kosdaq_ohlcv.iloc[-1]["종가"])
                }
                insights.append(f"KOSDAQ 지수: {kosdaq_ohlcv.iloc[-1]['종가']:,.2f}")
        except Exception as e:
            logger.warning(f"PyKRX index data error: {e}")

        # 3. 거시 경제 지표 (BOK API Wrapper) - 최신 값만 추출
        try:
            macro_indicators = get_macro_economic_indicators()
            if not macro_indicators.get("error"):
                # 🔧 LLM에게는 최신 값만 전달 (전체 배열 대신)
                indicators = macro_indicators.get("indicators", {})
                context_data["macro_economics"] = {
                    "base_rate": indicators.get("base_interest_rate", {}).get("current_rate", "N/A"),
                    "usd_rate": indicators.get("usd_exchange_rate", {}).get("current_rate", "N/A"),
                    "gdp": indicators.get("gdp", {}).get("current_value", "N/A"),
                    "cpi": indicators.get("cpi", {}).get("current_value", "N/A"),
                }
                rate = context_data["macro_economics"]["base_rate"]
                fx = context_data["macro_economics"]["usd_rate"]
                insights.append(f"기준금리: {rate}% | 원/달러 환율: {fx}원")
        except Exception as e:
            logger.warning(f"BOK API data error: {e}")

        return convert_numpy_types(
            {
                "status": "success",
                "context_summary": context_data,
                "key_insights": insights,
                "data_sources": ["FinanceDataReader", "PyKRX", "BOK ECOS API"],
                "last_updated": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error in get_market_and_economic_context_logic: {str(e)}")
        return {"error": str(e)}


@tool
def get_market_and_economic_context(
    stock_code: str, company_name: str
) -> Dict[str, Any]:
    """주식 시세, 시장 지수, 주요 거시 경제 지표를 종합적으로 수집하고 분석합니다."""
    return get_market_and_economic_context_logic(stock_code, company_name)


# 도구 목록
context_tools = [get_market_and_economic_context]


def create_context_agent():
    """Market & Economic Context Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, api_key=llm_api_key)

    prompt = (
        "당신은 증권사의 시장·경제 환경 분석 애널리스트입니다. 중급 투자자를 대상으로 거시경제 지표와 시장 환경을 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 시장 지수 및 종목 현황(KOSPI/KOSDAQ 동향과 종목의 상대적 강세/약세), "
        "2) 거시경제 환경(금리, 환율, GDP, 인플레이션 현황과 업종 영향), "
        "3) 투자 유의사항(시장 분위기와 모니터링할 경제 이벤트 및 리스크).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## 시장 환경 및 경제 분석\n\n"

        "### 시장 지수 및 종목 현황\n"
        "[KOSPI/KOSDAQ 지수 동향과 해당 종목의 주가·거래량 변화, 시장 대비 상대적 강세/약세를 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 거시경제 환경 및 영향 분석\n"
        "[금리, 환율, GDP, 인플레이션 현황과 변화 방향, 해당 업종 및 종목에 미치는 영향을 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 투자자 유의사항\n"
        "[현재 시장 분위기와 모니터링할 경제 이벤트 및 리스크 요인을 2개 문단으로 서술. 400-500자]\n\n"

        "### 참고 데이터\n"
        "- 한국은행 경제통계: [기준일]\n"
        "- PyKRX/FinanceDataReader: [시장 데이터 기준일]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 400-600자 목표)\n"
        "- 문단 중심 서술 (지표 수치는 괄호 내 표기 예: 기준금리 3.5% - 중립금리 수준)\n"
        "- 구체적인 지표 수치와 변화율 필수 포함 (KOSPI, 금리, 환율, GDP 등)\n"
        "- 전문 용어 사용시 간단한 설명 병기\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- 거시경제가 종목에 미치는 영향을 투자 관점에서 평가\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'MARKET_CONTEXT_ANALYSIS_COMPLETE'를 반드시 포함하세요."
    )

    return create_react_agent(
        model=llm, tools=context_tools, prompt=prompt, name="context_expert"
    )
