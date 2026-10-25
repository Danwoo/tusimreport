#!/usr/bin/env python3
"""
Korean ESG Analysis Agent - DART API 기반
기업의 ESG(환경, 사회, 지배구조) 요소를 분석하여 지속가능성을 평가합니다.

주요 기능:
- DART 기업개황(대표자·업종코드)과 최근 90일 공시 제목 수집
- 공시 제목으로 지배구조·사회·환경 관련 공시 분류
- 근거가 없는 축은 available=False로 표시 (ESG 점수·등급은 만들지 않음)
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
from utils.redaction import redact
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


# 공시 제목 키워드로 E/S/G 관련 공시를 고른다. 한 공시가 여러 축에 걸릴 수 있다.
GOVERNANCE_KEYWORDS = (
    "지배구조",
    "주주총회",
    "최대주주",
    "임원",
    "이사",
    "감사",
    "배당",
    "자기주식",
    "소유상황",
)
SOCIAL_KEYWORDS = ("지속가능", "사회", "안전", "재해", "인권", "고용", "노사", "공정거래")
# "에너지"는 넣지 않는다: 자회사명(…에너지솔루션)이 든 공시 제목에 걸린다.
ENVIRONMENTAL_KEYWORDS = ("환경", "탄소", "온실가스", "배출", "기후", "지속가능")
MAX_DISCLOSURES_PER_PILLAR = 10


def _matching_disclosures(
    disclosures: list[dict[str, Any]], keywords: tuple[str, ...]
) -> list[dict[str, Any]]:
    matched = []
    for item in disclosures:
        title = item.get("report_nm") or ""
        if any(keyword in title for keyword in keywords):
            matched.append(
                {"title": title.strip(), "date": item.get("rcept_dt"), "rcept_no": item.get("rcept_no")}
            )
    return matched[:MAX_DISCLOSURES_PER_PILLAR]


def _pillar(related: list[dict[str, Any]], missing_reason: str, **facts: Any) -> dict[str, Any]:
    """한 축의 결과. 근거가 하나도 없으면 available=False와 사유만 둔다 (점수·등급을 만들지 않는다)."""
    present = {key: value for key, value in facts.items() if value}
    pillar: dict[str, Any] = {
        "available": bool(related or present),
        **present,
        "related_disclosures": related,
    }
    if not pillar["available"]:
        pillar["reason"] = missing_reason
    return pillar


def get_esg_analysis_logic(stock_code: str, company_name: str) -> dict[str, Any]:
    """ESG 분석 로직.

    입력은 get_comprehensive_company_data()가 실제로 돌려주는 것만 쓴다:
    company_info(대표자·업종코드 등)와 최근 90일 recent_disclosures 제목.
    DART에 근거가 없는 축은 available=False로 표시한다.
    """
    try:
        logger.info(f"Fetching DART company info for {company_name} ({stock_code})")

        # DART API 클라이언트 호출
        dart_info = get_comprehensive_company_data(stock_code)

        if not dart_info or dart_info.get("error"):
            return {
                "error": f"{company_name}에 대한 DART 정보를 가져올 수 없습니다.",
                "details": redact(str((dart_info or {}).get("error", "Unknown error"))),
            }

        company_info = dart_info.get("company_info") or {}
        disclosures = [d for d in dart_info.get("recent_disclosures") or [] if isinstance(d, dict)]
        no_disclosure = f"최근 90일 DART 공시 {len(disclosures)}건 중 관련 공시 없음"

        esg_info: dict[str, Any] = {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "basic_info": {
                key: company_info.get(key)
                for key in (
                    "corp_name",
                    "stock_name",
                    "ceo_nm",
                    "corp_cls",
                    "induty_code",
                    "est_dt",
                    "hm_url",
                )
                if company_info.get(key)
            },
            "governance": _pillar(
                _matching_disclosures(disclosures, GOVERNANCE_KEYWORDS),
                f"대표자 정보 없음, {no_disclosure}",
                ceo_name=company_info.get("ceo_nm"),
            ),
            "social": _pillar(
                _matching_disclosures(disclosures, SOCIAL_KEYWORDS),
                f"{no_disclosure} (직원·안전·사회공헌 항목은 이 도구가 받지 않음)",
            ),
            "environmental": _pillar(
                _matching_disclosures(disclosures, ENVIRONMENTAL_KEYWORDS),
                f"{no_disclosure} (배출량 등 환경 수치는 DART 공시 API로 받지 않음)",
            ),
            "disclosures_reviewed": len(disclosures),
            "esg_rating": None,
            "esg_rating_note": "외부 ESG 등급·점수는 사용하지 않습니다 (DART 공시 원문만 근거).",
            "data_source": "DART OpenAPI",
            "last_updated": kst_isoformat(),
        }

        # 세 축 모두 근거가 없으면 기업개황만으로 ESG를 논할 수 없다.
        if not any(esg_info[pillar]["available"] for pillar in ("governance", "social", "environmental")):
            esg_info["status"] = "no_data"

        return convert_numpy_types(esg_info)

    except Exception as e:
        error_msg = redact(format_error_message_korean(e, "ESG 분석"))
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
        "데이터 사용 원칙:\n"
        "- 도구 결과(DART 기업개황과 최근 90일 공시 제목)에 있는 사실만 근거로 쓰세요\n"
        "- governance/social/environmental 중 available이 false인 축은 "
        "'DART 공시 근거 부족으로 평가할 수 없음'이라고 밝히고 사유(reason)를 전하세요\n"
        "- ESG 점수·등급·배출량·직원 수 같은 수치를 추정하거나 만들어내지 마세요\n\n"
        "전문 용어를 사용할 때는 쉬운 설명을 함께 해주시고, "
        "ESG 점수나 등급보다는 실제 경영 활동과 그 의미를 중심으로 설명해주세요. "
        "ESG 컨설턴트가 투자자에게 친근하게 설명해주는 느낌으로 작성해주세요.\n\n"
        "참고: 이 분석은 ESG 평가 참고자료이며 투자 추천이 아닙니다. 투자 시에는 신중히 판단하세요.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.ESG.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=esg_tools, prompt=prompt, name="esg_expert")
