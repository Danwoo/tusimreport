#!/usr/bin/env python3
"""
Enhanced Korean Sentiment Analysis Agent
Naver News API + Tavily Search API 듀얼 소스 기반

Dr. Alex Rivera (Tavily CTO) 기술 지원으로 향상된 감정 분석:
- Naver News API: 한국 로컬 뉴스 (50개)
- Tavily Search API: 글로벌 뉴스 + AI 필터링 (10개)
- 듀얼 소스 통합으로 편향성 감소 및 커버리지 확장
- LLM 기반 종합 감성 분석 및 토픽 추출
"""

import logging
import requests
import os
from typing import Dict, Any, List
from datetime import datetime, timedelta

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model, settings
from data.tavily_api_client import TavilyNewsClient

logger = logging.getLogger(__name__)


@tool
def get_enhanced_news_sentiment(company_name: str, stock_code: str) -> Dict[str, Any]:
    """
    향상된 듀얼 소스 뉴스 감정 분석
    Naver News API + Tavily Search API 통합 (Dr. Rivera 기술지원)
    """
    try:
        logger.info(f"Enhanced dual-source news sentiment analysis for {company_name} ({stock_code})")

        # 1. Naver News API 데이터 수집
        naver_data = _fetch_naver_news(company_name)

        # 2. Tavily Search API 데이터 수집
        tavily_data = _fetch_tavily_news(company_name)

        # 3. 듀얼 소스 통합 및 LLM 분석
        return _analyze_dual_source_sentiment(company_name, stock_code, naver_data, tavily_data)


    except Exception as e:
        logger.error(f"Error in enhanced dual-source news sentiment analysis: {str(e)}")
        return {"error": str(e)}


def _fetch_naver_news(company_name: str) -> Dict[str, Any]:
    """네이버 뉴스 API 데이터 수집"""
    try:
        client_id = settings.naver_client_id
        client_secret = settings.naver_client_secret

        if not client_id or not client_secret:
            return {"error": "Naver API 자격 증명이 설정되지 않았습니다.", "items": []}

        # 최적화된 검색어 생성
        if company_name == "KT":
            search_query = f"{company_name} 주식"
        elif company_name in ["LG", "SK"]:
            search_query = f"{company_name} 그룹"
        elif company_name in ["현대차"]:
            search_query = f"{company_name} 자동차"
        else:
            search_query = f"{company_name} 주식"

        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {
            "query": search_query,
            "display": 10,  # 3자 전문가 추천: 10개로 통일
            "sort": "sim",
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    except Exception as e:
        logger.error(f"Naver News API 오류: {str(e)}")
        return {"error": str(e), "items": []}


def _fetch_tavily_news(company_name: str) -> Dict[str, Any]:
    """Tavily Search API 데이터 수집 (투자 전문가 최적화)"""
    try:
        tavily_client = TavilyNewsClient(settings.tavily_api_key)
        return tavily_client.search_company_news(
            company_name=company_name,
            max_results=10  # 3자 전문가 추천: 10개로 통일
        )
    except Exception as e:
        logger.error(f"Tavily Search API 오류: {str(e)}")
        return {"error": str(e), "news_items": []}


def _analyze_dual_source_sentiment(company_name: str, stock_code: str, naver_data: Dict, tavily_data: Dict) -> Dict[str, Any]:
    """듀얼 소스 통합 감정 분석 (Dr. Rivera 최적화)"""
    try:
        # LLM 초기화
        llm_provider, llm_model_name, llm_api_key = get_llm_model()
        if llm_provider == "gemini":
            sentiment_llm = ChatGoogleGenerativeAI(
                model=llm_model_name, temperature=0.0, google_api_key=llm_api_key
            )
        else:
            sentiment_llm = ChatOpenAI(
                model=llm_model_name, temperature=0.0, api_key=llm_api_key
            )

        # 3자 전문가 추천: 균형잡힌 분석 데이터 (각 10개씩)
        naver_texts = []
        if naver_data.get("items"):
            naver_texts = [
                f"[Naver] {item['title']} - {item['description']}"
                for item in naver_data["items"]  # 10개 전체
            ]

        # Tavily 뉴스 텍스트 준비
        tavily_texts = []
        if tavily_data.get("news_items"):
            tavily_texts = [
                f"[Tavily] {item['title']} - {item['content'][:200]}"
                for item in tavily_data["news_items"]  # 10개 전체
            ]

        # 통합 뉴스 텍스트
        all_news_texts = naver_texts + tavily_texts

        if not all_news_texts:
            return {"error": "수집된 뉴스 데이터가 없습니다."}

        # Dr. Rivera 추천 프롬프트 (듀얼 소스 최적화)
        analysis_prompt = f"""
다음은 {company_name} 관련 뉴스를 네이버(한국) + Tavily(글로벌) 듀얼 소스에서 수집한 데이터입니다.
각 뉴스 앞의 [Naver] 또는 [Tavily] 태그로 출처를 구분할 수 있습니다.

[뉴스 데이터]
{chr(10).join(all_news_texts)}

[분석 요구사항]
1. 전체적인 감성을 '매우 긍정', '긍정', '중립', '부정', '매우 부정' 중 하나로 평가
2. 감성 점수를 -1.0 (매우 부정) ~ 1.0 (매우 긍정) 사이 수치로 계산
3. 핵심 토픽 3가지를 키워드로 요약
4. 가장 긍정적/부정적 헤드라인 각 1개씩 선정
5. 데이터 소스별 편향성 고려 (한국 vs 글로벌 시각)

[출력 형식]
- Overall Sentiment: [평가 결과]
- Sentiment Score: [점수]
- Key Topics: [토픽1, 토픽2, 토픽3]
- Most Positive Headline: [헤드라인]
- Most Negative Headline: [헤드라인]
- Source Balance: [네이버와 Tavily 데이터 균형성 평가]
"""

        # LLM 분석 실행
        llm_response = sentiment_llm.invoke(analysis_prompt)

        # 응답 파싱
        lines = llm_response.content.strip().split("\n")
        parsed_result = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                parsed_result[key.strip()] = value.strip()

        # 3자 전문가 추천: 완전한 뉴스 소스 투명성 (총 20개)
        news_sources = []

        # 네이버 뉴스 소스 (10개 - 완전 공개)
        if naver_data.get("items"):
            for item in naver_data["items"]:
                news_sources.append({
                    "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                    "url": item.get("link", ""),
                    "source": "[Naver] 네이버 뉴스 API",
                    "pub_date": item.get("pubDate", ""),
                    "type": "naver"
                })

        # Tavily 뉴스 소스 (10개 - 완전 공개)
        if tavily_data.get("news_items"):
            for item in tavily_data["news_items"]:
                # Dr. Rivera 추천: 상세한 출처 정보
                source_domain = item.get('source', 'Unknown')
                news_sources.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": f"[Tavily] {source_domain}",
                    "score": item.get("score", 0),
                    "type": "tavily"
                })

        return {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "data_sources": {
                "naver_news_count": len(naver_data.get("items", [])),
                "tavily_news_count": len(tavily_data.get("news_items", [])),
                "total_analyzed": len(all_news_texts)
            },
            "sentiment_analysis": parsed_result,
            "news_sources": news_sources,
            "tavily_ai_summary": tavily_data.get("ai_summary", ""),
            "data_source": "Enhanced Dual-Source: Naver News API + Tavily Search API",
            "last_updated": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"듀얼 소스 감정 분석 오류: {str(e)}")
        return {"error": str(e)}


# 도구 목록 - 향상된 듀얼 소스 버전
sentiment_tools = [get_enhanced_news_sentiment]

# 기존 함수명과의 호환성을 위한 별칭
get_naver_news_sentiment = get_enhanced_news_sentiment


def create_sentiment_agent():
    """Sentiment Analysis Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=llm_model_name, temperature=0.1, google_api_key=llm_api_key
        )
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

    prompt = (
        "당신은 뉴스와 시장 심리를 분석하는 감정 분석 전문가입니다. "
        "일반 투자자들이 쉽게 이해할 수 있도록 현재 시장의 분위기와 여론을 분석해주세요.\n\n"

        "먼저 `get_naver_news_sentiment` 도구를 사용해서 최신 뉴스 감정 분석 데이터를 수집한 후, "
        "다음과 같이 친근하고 이해하기 쉽게 설명해주세요:\n\n"

        "1. 현재 이 종목에 대한 뉴스 분위기가 어떤지 간단히 요약해주세요\n"
        "   - 전체적으로 긍정적인지, 부정적인지, 중립적인지\n"
        "   - 감정 점수를 쉬운 말로 설명해주세요\n\n"

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
        "   - 상위 5-10개 뉴스의 제목과 발행일을 간단히 나열해주세요\n"
        "   - 어떤 언론사의 뉴스가 주로 사용되었는지 알려주세요\n\n"

        "전문 용어보다는 쉬운 말로 설명해주시고, 숫자나 점수를 제시할 때는 "
        "그것이 실제로 어떤 의미인지 구체적인 예시와 함께 설명해주세요. "
        "마치 친구가 투자 조언을 해주듯이 자연스럽고 따뜻한 톤으로 작성해주세요.\n\n"

        "참고: 이 분석은 뉴스 여론 참고자료이며 투자 추천이 아닙니다. 객관적인 정보 제공을 목적으로 합니다.\n\n"
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'SENTIMENT_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=sentiment_tools, prompt=prompt, name="sentiment_expert")


# 이 파일이 직접 실행될 때 테스트용
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    company_name = "삼성전자"
    stock_code = "005930"

    print(f"--- Testing Sentiment Analysis for {company_name} ---")
    result = get_naver_news_sentiment(company_name, stock_code)

    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
