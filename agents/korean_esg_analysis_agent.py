#!/usr/bin/env python3
"""
Korean ESG Analysis Agent - DART API 기반
기업의 ESG(환경, 사회, 지배구조) 요소를 분석하여 지속가능성을 평가합니다.

주요 기능:
- DART API를 통한 기업 공시정보 수집
- 지배구조 분석 (이사회 구성, 감사 의견 등)
- 사회적 책임 분석 (배당 정책, 주주 환원 등)
- ESG 리스크 요인 평가
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import get_llm_model
from data.dart_api_client import get_comprehensive_company_data
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)


@tool
def get_dart_company_info_wrapper(stock_code: str, company_name: str) -> Dict[str, Any]:
    """DART API를 통해 기업 공시정보를 수집하고 ESG 관련 정보를 추출합니다."""
    try:
        logger.info(f"Fetching DART company info for {company_name} ({stock_code})")

        # DART API 클라이언트 호출
        dart_info = get_comprehensive_company_data(stock_code)

        if not dart_info or dart_info.get("error"):
            return {
                "error": f"{company_name}에 대한 DART 정보를 가져올 수 없습니다.",
                "details": dart_info.get("error", "Unknown error"),
            }

        # ESG 관련 정보 구조화
        esg_info = {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "basic_info": dart_info.get("basic_info", {}),
            "governance": {
                "ceo_info": dart_info.get("ceo_info", {}),
                "board_composition": dart_info.get("board_info", {}),
                "audit_opinion": dart_info.get("audit_opinion", "정보 없음"),
                "major_shareholders": dart_info.get("shareholders", []),
            },
            "social": {
                "dividend_policy": dart_info.get("dividend_info", {}),
                "employee_info": dart_info.get("employee_info", {}),
                "business_segments": dart_info.get("business_info", {}),
            },
            "environmental": {
                "business_nature": dart_info.get("business_nature", ""),
                "environmental_disclosures": dart_info.get("environmental_info", {}),
            },
            "data_source": "DART OpenAPI",
            "last_updated": datetime.now().isoformat(),
        }

        return convert_numpy_types(esg_info)

    except Exception as e:
        logger.error(f"Error in get_dart_company_info_wrapper: {str(e)}")
        return {"error": str(e)}


# ESG 분석 도구 목록
esg_tools = [get_dart_company_info_wrapper]


def create_esg_agent():
    """ESG Agent 생성 함수"""
    llm_provider, model_name, api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
    else:
        llm = ChatOpenAI(model=model_name, api_key=api_key)

    prompt = (
        "당신은 증권사의 ESG(환경·사회·지배구조) 분석 애널리스트입니다. 중급 투자자를 대상으로 해당 기업의 ESG 경영과 지속가능성을 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 지배구조 및 경영 투명성(경영진 구성, 이사회 독립성, 주주 권익 보호, 지배구조 리스크), "
        "2) 사회적 책임 및 환경 경영(직원 처우, 산업 안전, 환경 규제 대응, ESG 공시 수준), "
        "3) ESG 리스크 및 투자 관점(기업 가치 영향과 투자 펀드 편입 가능성).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## ESG 분석\n\n"

        "### 지배구조 및 경영 투명성\n"
        "[경영진 구성, 이사회 독립성, 주주 권익 보호 수준, 지배구조 리스크 요인을 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 사회적 책임 및 환경 경영\n"
        "[직원 처우, 산업 안전, 환경 규제 대응(탄소 배출, 친환경 기술), ESG 공시 여부와 지속가능경영 노력을 2개 문단으로 서술. 400-500자]\n\n"

        "### ESG 리스크 및 투자 관점\n"
        "[ESG 리스크가 기업 가치에 미치는 영향과 투자 펀드 편입 가능성을 2개 문단으로 서술. 400-500자]\n\n"

        "### 참고 데이터\n"
        "- DART: [공시 자료 기준일]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 400-600자 목표)\n"
        "- 문단 중심 서술 (핵심 사항은 괄호 내 표기)\n"
        "- ESG 관련 구체적 정보 필수 포함 (이사회 구성, 배당 정책, 환경 공시 등)\n"
        "- 전문 용어 사용시 간단한 설명 병기 (예: 지배구조 - 경영 투명성과 견제 체계)\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- ESG 리스크가 기업 가치에 미치는 영향을 투자 관점에서 평가\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'ESG_ANALYSIS_COMPLETE'를 반드시 포함하세요."
    )

    return create_react_agent(
        model=llm, tools=esg_tools, prompt=prompt, name="esg_expert"
    )
