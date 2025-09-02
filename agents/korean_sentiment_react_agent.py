import logging
from typing import Dict, Any
from datetime import datetime
import asyncio
import json

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from agents.korean_news_aggregator import korean_news_aggregator

logger = logging.getLogger(__name__)


@tool
def collect_korean_news_official_sources(
    keyword: str, company_name: str = None
) -> Dict[str, Any]:
    """공식 소스에서만 한국 뉴스 수집 (네이버 API + HashScraper API)

    Args:
        keyword: 검색 키워드 (종목코드 또는 회사명)
        company_name: 회사명 (선택적)
    """
    try:
        logger.info(f"Collecting Korean news from official sources for {keyword}")

        # Async 함수를 sync로 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                korean_news_aggregator.aggregate_all_sources(keyword, company_name)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error collecting Korean news: {str(e)}")
        return {
            "keyword": keyword,
            "error": str(e),
            "news_count": 0,
            "collection_stats": {"error": True},
        }


@tool
def analyze_sentiment_korean_text(
    text_data: str, context: str = "stock_analysis"
) -> Dict[str, Any]:
    """한국어 텍스트 감정 분석 (GPT-4 기반)

    Args:
        text_data: 분석할 한국어 텍스트
        context: 분석 컨텍스트 (기본: stock_analysis)
    """
    try:
        logger.info(f"Analyzing Korean sentiment for context: {context}")

        # LLM 초기화 (Gemini 또는 OpenAI)
        provider, model_name, api_key = get_llm_model()

        if provider == "gemini":
            sentiment_llm = ChatGoogleGenerativeAI(
                model=model_name, temperature=0.1, google_api_key=api_key
            )
        else:
            sentiment_llm = ChatOpenAI(
                model=model_name, temperature=0.1, api_key=api_key
            )

        sentiment_prompt = f"""
        당신은 한국 주식 시장 전문 감정 분석가입니다.
        
        다음 한국어 뉴스 텍스트를 분석하고 투자 관점에서 감정을 평가해주세요:
        
        텍스트: {text_data[:2000]}  # 토큰 제한
        
        분석 기준:
        - 긍정적: 주가 상승 요인, 좋은 뉴스, 성장 전망
        - 부정적: 주가 하락 요인, 나쁜 뉴스, 리스크 요인  
        - 중립적: 단순 사실 보도, 영향 불분명
        
        응답 형식 (JSON):
        {{
            "sentiment_score": 1-10 점수 (1=매우부정, 5=중립, 10=매우긍정),
            "sentiment_label": "긍정적" | "부정적" | "중립적",
            "confidence": 0.0-1.0 신뢰도,
            "key_factors": ["주요 감정 요인들"],
            "investment_impact": "투자 영향 요약"
        }}
        """

        response = sentiment_llm.invoke([HumanMessage(content=sentiment_prompt)])

        # JSON 파싱 시도 (개선된 버전)
        try:
            response_content = response.content
            
            # 마크다운 코드 블록 제거 (```json ... ``` 형태)
            if "```json" in response_content:
                start_idx = response_content.find("```json") + 7
                end_idx = response_content.find("```", start_idx)
                if end_idx != -1:
                    response_content = response_content[start_idx:end_idx].strip()
            
            # 백틱 제거 (` ... ` 형태)
            elif response_content.startswith("`") and response_content.endswith("`"):
                response_content = response_content.strip("`").strip()
            
            sentiment_result = json.loads(response_content)
            
        except (json.JSONDecodeError, AttributeError, ValueError) as e:
            logger.warning(f"JSON parsing failed, using fallback: {str(e)}")
            # JSON 파싱 실패시 기본값
            sentiment_result = {
                "sentiment_score": 5,
                "sentiment_label": "중립적",
                "confidence": 0.7,
                "key_factors": ["분석 완료"],
                "investment_impact": (
                    response.content[:200]
                    if hasattr(response, "content")
                    else "분석 결과 파싱 실패"
                ),
            }

        sentiment_result["analysis_timestamp"] = datetime.now().isoformat()
        sentiment_result["text_length"] = len(text_data)
        sentiment_result["context"] = context

        return sentiment_result

    except Exception as e:
        logger.error(f"Error in Korean sentiment analysis: {str(e)}")
        return {
            "sentiment_score": 5,
            "sentiment_label": "분석실패",
            "confidence": 0.0,
            "error": str(e),
            "analysis_timestamp": datetime.now().isoformat(),
        }


@tool
def generate_sentiment_summary(
    news_data: dict, sentiment_results: dict
) -> Dict[str, Any]:
    """뉴스 데이터와 감정 분석 결과를 종합하여 최종 요약 생성

    Args:
        news_data: 수집된 뉴스 데이터
        sentiment_results: 감정 분석 결과
    """
    try:
        logger.info("Generating sentiment summary")

        # 뉴스 통계
        news_count = news_data.get("news_count", 0)
        collection_stats = news_data.get("collection_stats", {})

        # 감정 분석 요약
        sentiment_score = sentiment_results.get("sentiment_score", 5)
        sentiment_label = sentiment_results.get("sentiment_label", "중립적")
        confidence = sentiment_results.get("confidence", 0.7)

        # 종합 평가
        if sentiment_score >= 7:
            overall_sentiment = "긍정적"
            investment_recommendation = "관심"
        elif sentiment_score <= 3:
            overall_sentiment = "부정적"
            investment_recommendation = "주의"
        else:
            overall_sentiment = "중립적"
            investment_recommendation = "관망"

        summary = {
            "overall_sentiment": overall_sentiment,
            "sentiment_score": sentiment_score,
            "confidence_level": confidence,
            "investment_recommendation": investment_recommendation,
            "news_analysis": {
                "total_articles": news_count,
                "sources_used": list(collection_stats.keys()),
                "data_quality": (
                    "높음" if news_count > 10 else "보통" if news_count > 5 else "낮음"
                ),
            },
            "key_insights": sentiment_results.get("key_factors", []),
            "analysis_timestamp": datetime.now().isoformat(),
            "multi_source_analysis": True,
        }

        return summary

    except Exception as e:
        logger.error(f"Error generating sentiment summary: {str(e)}")
        return {
            "overall_sentiment": "분석실패",
            "error": str(e),
            "analysis_timestamp": datetime.now().isoformat(),
        }


# ====================
# REACT AGENT SETUP
# ====================

# 감정 분석 도구 목록
sentiment_tools = [
    collect_korean_news_official_sources,
    analyze_sentiment_korean_text,
    generate_sentiment_summary,
]

# LLM 설정 (Gemini 또는 OpenAI)
provider, model_name, api_key = get_llm_model()

if provider == "gemini":
    llm = ChatGoogleGenerativeAI(
        model=model_name, temperature=0.2, google_api_key=api_key
    )
else:
    llm = ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key)

# 한국 감정 분석 ReAct Agent 생성
korean_sentiment_react_agent = create_react_agent(
    model=llm,
    tools=sentiment_tools,
    prompt=(
        "You are a Korean Sentiment Analysis Agent specializing in Korean stock market sentiment.\n\n"
        "CAPABILITIES:\n"
        "- Collect Korean news from official sources only (Naver API, HashScraper API)\n"
        "- Analyze Korean text sentiment using advanced LLM\n"
        "- Generate comprehensive sentiment summaries for investment decisions\n\n"
        "INSTRUCTIONS:\n"
        "- Always use the provided tools to gather and analyze data\n"
        "- Focus on investment-relevant sentiment analysis\n"
        "- Use only reliable official APIs (no dummy data)\n"
        "- Provide clear sentiment scoring (1-10 scale)\n"
        "- Consider Korean market context and language nuances\n\n"
        "WORKFLOW:\n"
        "1. Collect Korean news with collect_korean_news_official_sources\n"
        "2. Analyze sentiment of collected text with analyze_sentiment_korean_text\n"
        "3. Generate final summary with generate_sentiment_summary\n"
        "4. Provide investment insights based on sentiment analysis\n\n"
        "Always conclude with 'SENTIMENT_ANALYSIS_COMPLETE' when done."
    ),
)


def analyze_korean_stock_sentiment(stock_code: str, company_name: str = None) -> dict:
    """Korean Sentiment Agent 실행 함수"""
    try:
        search_keyword = company_name if company_name else stock_code

        messages = [
            HumanMessage(
                content=f"Perform comprehensive sentiment analysis for Korean stock {stock_code} "
                f"({company_name or 'Unknown Company'}). "
                f"Collect news from multiple sources and analyze market sentiment. "
                f"Search using keyword: {search_keyword}"
            )
        ]

        result = korean_sentiment_react_agent.invoke({"messages": messages})
        
        # 뉴스 데이터를 별도로 수집하여 결과에 포함
        try:
            news_result = collect_korean_news_official_sources.invoke({
                'keyword': search_keyword,
                'company_name': company_name
            })
            collected_news = news_result.get('news_data', [])[:10]  # 상위 10개만
        except Exception as news_error:
            logger.warning(f"News collection for UI failed: {str(news_error)}")
            collected_news = []
        
        return {
            "agent": "korean_sentiment_agent",
            "messages": result["messages"],
            "analysis_complete": True,
            "timestamp": datetime.now().isoformat(),
            "news_data": collected_news,  # UI 표시용 뉴스 데이터 추가
        }

    except Exception as e:
        logger.error(f"Error in Korean Sentiment Agent: {str(e)}")
        return {
            "agent": "korean_sentiment_agent",
            "error": str(e),
            "analysis_complete": False,
            "timestamp": datetime.now().isoformat(),
        }
