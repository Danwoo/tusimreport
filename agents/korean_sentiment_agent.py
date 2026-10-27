#!/usr/bin/env python3
"""
Korean Sentiment Analysis Agent

Tavily 검색으로 받은 기사 제목과 본문 일부를 도구가 그대로 돌려주고, 여론 판단은
에이전트 LLM이 한다. Naver 검색 API는 2026-09-07 시행 약관이 검색 결과의 AI 입력을
금지하므로 이 분석 경로에서 쓰지 않는다 (docs/API_KEYS.md 4.4).
"""

import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from config.settings import settings
from core.signals import AgentSignal
from data.tavily_api_client import TavilyNewsClient
from utils.agent_helpers import create_fallback_message, format_error_message_korean
from utils.redaction import redact
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)

MAX_ARTICLES = 10
MAX_CONTENT_CHARS = 300


def get_enhanced_news_sentiment_logic(company_name: str, stock_code: str) -> dict[str, Any]:
    """종목 관련 최근 기사를 모아 돌려준다. 감성 판단은 하지 않는다."""
    try:
        logger.info(f"News collection for {company_name} ({stock_code})")
        return _summarize_articles(company_name, stock_code, _fetch_tavily_news(company_name))

    except Exception as e:
        error_msg = format_error_message_korean(e, "뉴스 수집")
        logger.error(error_msg)
        return create_fallback_message(
            agent_name="Korean Sentiment Agent",
            company_name=company_name,
            stock_code=stock_code,
            reason=error_msg,
            data_source="Tavily Search",
        )


@tool
def get_enhanced_news_sentiment(company_name: str, stock_code: str) -> dict[str, Any]:
    """종목 관련 최근 기사(제목, 본문 일부, 출처, URL)를 Tavily 검색으로 수집합니다."""
    return get_enhanced_news_sentiment_logic(company_name, stock_code)


def _fetch_tavily_news(company_name: str) -> dict[str, Any]:
    try:
        tavily_client = TavilyNewsClient(settings.tavily_api_key)
        return tavily_client.search_company_news(company_name=company_name, max_results=MAX_ARTICLES)
    except Exception as e:
        reason = redact(str(e))
        logger.error(f"Tavily Search API 오류: {reason}")
        return {"error": reason, "news_items": []}


def _summarize_articles(company_name: str, stock_code: str, tavily_data: dict) -> dict[str, Any]:
    """기사를 잘라 그대로 돌려준다.

    Tavily의 `ai_summary`는 검색 서비스가 생성한 문장이라 원천 데이터로 넘기지 않는다.
    """
    items = tavily_data.get("news_items") or []
    if not items:
        return {"error": tavily_data.get("error") or "수집된 뉴스 데이터가 없습니다."}

    articles = [
        {
            "article_number": i + 1,
            "title": item.get("title", ""),
            "content": (item.get("content") or "")[:MAX_CONTENT_CHARS],
            "source": item.get("source", ""),
            "url": item.get("url", ""),
        }
        for i, item in enumerate(items[:MAX_ARTICLES])
    ]
    return {
        "status": "success",
        "company_name": company_name,
        "stock_code": stock_code,
        "data_source": "Tavily Search API",
        "search_query": tavily_data.get("search_query", ""),
        "total_articles": len(articles),
        "articles": articles,
        "last_updated": kst_isoformat(),
    }


sentiment_tools = [get_enhanced_news_sentiment]


def create_sentiment_agent():
    """Sentiment Analysis Agent 생성 함수"""
    llm = build_llm(temperature=0.1)

    prompt = (
        "당신은 뉴스와 시장 심리를 분석하는 감정 분석 전문가입니다. "
        "일반 투자자들이 쉽게 이해할 수 있도록 현재 시장의 분위기와 여론을 분석해주세요.\n\n"
        "먼저 `get_enhanced_news_sentiment` 도구로 최근 기사(제목, 본문 일부, 출처)를 받은 뒤, "
        "기사 내용만 근거로 다음과 같이 친근하고 이해하기 쉽게 설명해주세요:\n\n"
        "1. 현재 이 종목에 대한 뉴스 분위기가 어떤지 간단히 요약해주세요\n"
        "   - 전체적으로 긍정적인지, 부정적인지, 중립적인지\n"
        "   - 그렇게 판단한 근거가 된 기사 번호를 함께 적어주세요\n\n"
        "2. 어떤 종류의 뉴스가 많은지 알려주세요\n"
        "   - 가장 긍정적인 뉴스는 어떤 내용인지\n"
        "   - 가장 우려되는 뉴스는 어떤 내용인지\n"
        "   - 주요 키워드들을 알기 쉽게 설명해주세요\n\n"
        "3. 투자자 입장에서 이런 뉴스들이 어떤 의미인지 설명해주세요\n"
        "   - 시장 참여자들이 어떤 마음가짐을 가지고 있을 것 같은지\n"
        "   - 단기적으로 주가에 어떤 영향을 줄 수 있는지\n"
        "   - 이런 분위기가 언제까지 이어질 것 같은지\n\n"
        "4. 투자자들이 주의해서 봐야 할 점들을 조언해주세요\n"
        "   - 뉴스의 신뢰성은 어떤지\n"
        "   - 감정적으로 과도하게 반응하지 않으려면 어떻게 해야 하는지\n\n"
        "5. 📰 분석에 사용된 뉴스 출처를 투명하게 공개해주세요\n"
        "   - 상위 5-10개 뉴스의 제목과 출처를 간단히 나열해주세요\n"
        "   - 어떤 언론사의 뉴스가 주로 사용되었는지 알려주세요\n\n"
        "전문 용어보다는 쉬운 말로 설명해주시고, 숫자나 점수를 제시할 때는 "
        "그것이 실제로 어떤 의미인지 구체적인 예시와 함께 설명해주세요. "
        "마치 친구가 투자 조언을 해주듯이 자연스럽고 따뜻한 톤으로 작성해주세요.\n\n"
        "참고: 이 분석은 뉴스 여론 참고자료이며 투자 추천이 아닙니다. 객관적인 정보 제공을 목적으로 합니다.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.SENTIMENT.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=sentiment_tools, prompt=prompt, name="sentiment_expert")


# 이 파일이 직접 실행될 때 테스트용
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    company_name = "삼성전자"
    stock_code = "005930"

    print(f"--- Testing news collection for {company_name} ---")
    result = get_enhanced_news_sentiment_logic(company_name, stock_code)

    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
