#!/usr/bin/env python3
"""
Korean Community Sentiment Analysis Agent
Paxnet 종목토론 기반 투자 커뮤니티 감정 분석

한국 투자자들의 실제 의견과 토론을 통한 시장 심리 분석:
- Paxnet 종목토론: 실제 투자자 게시글 (10개)
- 커뮤니티 특화 감정 분석 및 토픽 추출
- 실제 투자자 심리와 여론 동향 파악
- 기관/언론과 다른 개인 투자자 시각 제공
"""

import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from core.signals import AgentSignal
from data.paxnet_crawl_client import fetch_paxnet_discussions
from utils.agent_helpers import create_fallback_message, format_error_message_korean
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


def get_community_sentiment_analysis_logic(company_name: str, stock_code: str) -> dict[str, Any]:
    """
    한국 투자 커뮤니티 감정 분석 로직
    Paxnet 종목토론 기반 실제 투자자 의견 분석
    """
    try:
        logger.info(f"Community sentiment analysis for {company_name} ({stock_code})")

        # 1. Paxnet 커뮤니티 데이터 수집
        paxnet_data = _fetch_paxnet_community_data(stock_code)

        # 2. 에이전트 LLM이 읽을 게시글 원문 정리
        return _summarize_posts(company_name, stock_code, paxnet_data)

    except Exception as e:
        error_msg = format_error_message_korean(e, "커뮤니티 분석")
        logger.error(error_msg)
        return create_fallback_message(
            agent_name="Korean Community Agent",
            company_name=company_name,
            stock_code=stock_code,
            reason=error_msg,
            data_source="Paxnet 크롤링",
        )


@tool
def get_community_sentiment_analysis(company_name: str, stock_code: str) -> dict[str, Any]:
    """
    한국 투자 커뮤니티 감정 분석
    Paxnet 종목토론 기반 실제 투자자 의견 분석
    """
    return get_community_sentiment_analysis_logic(company_name, stock_code)


def _fetch_paxnet_community_data(stock_code: str) -> dict[str, Any]:
    """Paxnet 종목토론 데이터 수집"""
    try:
        logger.info(f"Fetching Paxnet community data for {stock_code}")

        # Paxnet 크롤링 클라이언트 사용
        result = fetch_paxnet_discussions(stock_code, max_posts=10)

        if "error" in result:
            logger.error(f"Paxnet 데이터 수집 실패: {result['error']}")
            return {"error": result["error"], "posts": []}

        logger.info(f"Paxnet 데이터 수집 성공: {result.get('total_posts', 0)}개 게시글")
        return result

    except Exception as e:
        logger.error(f"Paxnet 커뮤니티 데이터 수집 오류: {str(e)}")
        return {"error": str(e), "posts": []}


MAX_POST_CHARS = 300


def _summarize_posts(company_name: str, stock_code: str, paxnet_data: dict) -> dict[str, Any]:
    """게시글을 잘라 그대로 돌려준다. 심리 판단은 에이전트 LLM이 원문을 보고 한다.

    도구 안에서 LLM을 다시 부르면 그 결과(심리 점수 등)가 '도구 데이터'처럼 보여
    근거 대조가 불가능해지고, 호출 수도 에이전트 밖에서 늘어난다.
    """
    posts = paxnet_data.get("posts") or []
    if not posts:
        return {"error": paxnet_data.get("error") or "수집된 커뮤니티 데이터가 없습니다."}

    return {
        "status": "success",
        "company_name": company_name,
        "stock_code": stock_code,
        "data_source": "Paxnet 종목토론",
        "total_posts": len(posts),
        "posts": [
            {
                "post_number": i + 1,
                "title": post.get("title", ""),
                "content": (post.get("content") or "")[:MAX_POST_CHARS],
                "url": post.get("url", ""),
            }
            for i, post in enumerate(posts)
        ],
        "last_updated": kst_isoformat(),
    }


# 도구 목록
community_tools = [get_community_sentiment_analysis]


def create_community_agent():
    """Community Sentiment Analysis Agent 생성 함수"""
    llm = build_llm(temperature=0.1)

    prompt = (
        "당신은 한국 투자 커뮤니티의 여론과 심리를 분석하는 전문가입니다. "
        "실제 개인 투자자들의 의견과 토론을 통해 시장의 생생한 분위기를 파악하고 분석해주세요.\n\n"
        "먼저 `get_community_sentiment_analysis` 도구로 최근 종목토론 게시글(제목·본문 일부)을 받은 뒤, "
        "게시글 내용만 근거로 다음과 같이 투자자 친화적으로 설명해주세요:\n\n"
        "1. 현재 이 종목에 대한 투자자들의 분위기가 어떤지 요약해주세요\n"
        "   - 전체적으로 긍정적인지, 부정적인지, 관망세인지\n"
        "   - 그렇게 판단한 근거가 된 게시글 번호를 함께 적어주세요\n\n"
        "2. 투자자들이 가장 관심 갖는 이슈들을 알려주세요\n"
        "   - 어떤 종류의 정보나 이슈에 집중하고 있는지\n"
        "   - 기술적 분석, 기업 실적, 시장 이슈 등 어떤 관점이 많은지\n"
        "   - 투자자들 사이에서 화제가 되는 특별한 정보나 루머가 있는지\n\n"
        "3. 개인 투자자들의 실제 투자 심리를 분석해주세요\n"
        "   - 매수세인지 매도세인지, 관망세인지\n"
        "   - 단기적 관점인지 장기적 관점인지\n"
        "   - 투자자들이 우려하는 리스크는 무엇인지\n\n"
        "4. 기관/언론과 다른 개인 투자자만의 시각이 있는지 분석해주세요\n"
        "   - 커뮤니티에서만 나오는 독특한 관점이나 정보\n"
        "   - 일반 뉴스와 다른 해석이나 의견\n"
        "   - 투자자들 간의 의견 대립이 있는지\n\n"
        "5. 📋 분석에 사용된 커뮤니티 게시글 출처를 투명하게 공개해주세요\n"
        "   - 상위 5-10개 게시글의 제목을 간단히 나열해주세요\n"
        "   - 어떤 커뮤니티에서 수집된 데이터인지 명시해주세요\n\n"
        "개인 투자자들의 생생한 목소리를 전달하되, 객관적이고 균형잡힌 시각으로 분석해주세요. "
        "커뮤니티 특유의 감정적 반응이나 편향성도 있을 수 있음을 고려하여 해석해주세요.\n\n"
        "참고: 이 분석은 투자자 여론 참고자료이며 투자 추천이 아닙니다. 커뮤니티 의견의 객관적 분석을 목적으로 합니다.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.COMMUNITY.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=community_tools, prompt=prompt, name="community_expert")


# 이 파일이 직접 실행될 때 테스트용
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    company_name = "삼성전자"
    stock_code = "005930"

    print(f"--- Testing Community Analysis for {company_name} ---")
    result = get_community_sentiment_analysis(company_name, stock_code)

    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
