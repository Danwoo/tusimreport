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
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from core.signals import AgentSignal
from data.dart_api_client import get_comprehensive_company_data
from utils.agent_helpers import create_fallback_message, format_error_message_korean
from utils.helpers import convert_numpy_types
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


def get_esg_analysis_logic(stock_code: str, company_name: str) -> dict[str, Any]:
    """ESG 분석 로직"""
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
            "last_updated": kst_isoformat(),
        }

        return convert_numpy_types(esg_info)

    except Exception as e:
        error_msg = format_error_message_korean(e, "ESG 분석")
        logger.error(error_msg)
        return create_fallback_message(
            agent_name="Korean ESG Analysis Agent",
            company_name=company_name,
            stock_code=stock_code,
            reason=error_msg,
            data_source="DART API",
        )


@tool
def get_dart_company_info_wrapper(stock_code: str, company_name: str) -> dict[str, Any]:
    """DART API를 통해 기업 공시정보를 수집하고 ESG 관련 정보를 추출합니다."""
    return get_esg_analysis_logic(stock_code, company_name)


# ESG 분석 도구 목록
esg_tools = [get_dart_company_info_wrapper]


def create_esg_agent():
    """ESG Agent 생성 함수"""
    llm = build_llm(temperature=0.1)

    prompt = (
        "당신은 ESG(환경·사회·지배구조) 분석 전문가입니다. "
        "투자자들이 쉽게 이해할 수 있도록 이 회사의 ESG 경영 상태와 지속가능성을 분석해주세요.\n\n"
        "먼저 `get_dart_company_info_wrapper` 도구를 사용해서 기업 공시 정보를 수집한 후, "
        "다음과 같이 친근하고 이해하기 쉽게 설명해주세요:\n\n"
        "1. 이 회사의 지배구조(경영 투명성)는 어떤지 알려주세요\n"
        "   - 경영진의 전문성과 안정성은 어떤지\n"
        "   - 이사회가 제대로 견제 역할을 하고 있는지\n"
        "   - 주주들의 권익은 잘 보호받고 있는지\n\n"
        "2. 사회적 책임은 어떻게 수행하고 있는지 설명해주세요\n"
        "   - 직원들을 어떻게 대우하고 있는지\n"
        "   - 지역사회나 사회 전체에 어떤 기여를 하고 있는지\n"
        "   - 고객이나 협력업체와의 관계는 어떤지\n\n"
        "3. 환경 경영은 어떤 수준인지 평가해주세요\n"
        "   - 환경 오염이나 기후변화에 대한 대응은 어떤지\n"
        "   - 친환경 제품이나 기술 개발 노력은 있는지\n"
        "   - 에너지 효율화나 탄소 배출 감소 노력은 어떤지\n\n"
        "4. 장기적인 지속가능성은 어떻게 보이는지 분석해주세요\n"
        "   - ESG 리스크가 사업에 어떤 영향을 줄 수 있는지\n"
        "   - 미래 규제나 사회적 변화에 잘 대응할 수 있을지\n"
        "   - ESG 경영이 기업 가치에 도움이 될지\n\n"
        "5. 투자자 관점에서 ESG 투자 매력도를 알려주세요\n"
        "   - 다른 회사들과 비교해서 ESG 수준이 어떤지\n"
        "   - ESG 투자 펀드들이 관심을 가질 만한지\n"
        "   - 앞으로 ESG 개선 여지는 어느 정도인지\n\n"
        "전문 용어를 사용할 때는 쉬운 설명을 함께 해주시고, "
        "ESG 점수나 등급보다는 실제 경영 활동과 그 의미를 중심으로 설명해주세요. "
        "ESG 컨설턴트가 투자자에게 친근하게 설명해주는 느낌으로 작성해주세요.\n\n"
        "참고: 이 분석은 ESG 평가 참고자료이며 투자 추천이 아닙니다. 투자 시에는 신중히 판단하세요.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.ESG.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=esg_tools, prompt=prompt, name="esg_expert")
