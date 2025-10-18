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


def get_investor_trading_analysis_logic(
    stock_code: str, period_days: int = 20
) -> Dict[str, Any]:
    """투자자별 매매 동향 분석 로직"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days + 10)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        trading_value = stock.get_market_trading_value_by_investor(
            start_str, end_str, stock_code
        )
        if trading_value.empty:
            return {"error": f"No trading value data for {stock_code}"}

        analysis_data = {}
        if "순매수" in trading_value.columns:
            latest_net = trading_value["순매수"]
            key_investors = ["외국인", "기관합계", "개인"]
            key_analysis = {}
            for investor in key_investors:
                if investor in latest_net.index:
                    net_amount = float(latest_net[investor])
                    key_analysis[investor] = {
                        "net_purchase_billion": net_amount / 100000000,
                    }
            analysis_data["key_investors"] = key_analysis

        return convert_numpy_types(
            {
                "status": "success",
                "analysis_data": analysis_data,
                "data_source": "PyKRX",
            }
        )
    except Exception as e:
        return {"error": str(e)}


@tool
def get_investor_trading_analysis(
    stock_code: str, period_days: int = 20
) -> Dict[str, Any]:
    """투자자별 매매 동향 분석 (기관/개인/외국인)"""
    return get_investor_trading_analysis_logic(stock_code, period_days)


# 도구 목록
institutional_trading_tools = [get_investor_trading_analysis]


def create_institutional_trading_agent():
    """Institutional Trading Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, api_key=llm_api_key)

    prompt = (
        "당신은 증권사의 수급 분석 애널리스트입니다. 중급 투자자를 대상으로 기관/외국인/개인 투자자의 매매 동향을 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 투자자별 매매 동향(외국인/기관/개인의 순매수/순매도 현황과 트렌드), "
        "2) 수급 패턴 해석(주가에 미치는 영향과 수급 전환 신호 가능성), "
        "3) 투자 유의사항(수급 쏠림 리스크와 급격한 변화 가능성).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## 수급 분석\n\n"

        "### 투자자별 매매 동향\n"
        "[외국인, 기관, 개인의 순매수/순매도 현황과 트렌드, 주도 세력 평가를 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 수급 패턴 해석 및 주가 영향\n"
        "[현재 수급 패턴이 주가에 미치는 영향(상승/하락 압력)과 수급 전환 신호 가능성을 2개 문단으로 서술. 400-500자]\n\n"

        "### 투자자 유의사항\n"
        "[수급 쏠림 리스크와 급격한 매매 변화 가능성을 1-2개 문단으로 서술. 300-400자]\n\n"

        "### 참고 데이터\n"
        "- PyKRX: [투자자별 매매 데이터 기간]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 400-600자 목표)\n"
        "- 문단 중심 서술 (순매수 금액은 괄호 내 표기 예: 순매수 1,200억원 - 외국인 지속 매수)\n"
        "- 구체적인 순매수 금액과 기간 필수 포함\n"
        "- 전문 용어 사용시 간단한 설명 병기\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- 수급 패턴이 주가에 미치는 영향을 구체적으로 평가\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE'를 반드시 포함하세요."
    )

    return create_react_agent(
        model=llm,
        tools=institutional_trading_tools,
        prompt=prompt,
        name="institutional_trading_expert",
    )
