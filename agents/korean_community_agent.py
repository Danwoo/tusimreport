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
from typing import Dict, Any, List
from datetime import datetime

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model, settings
from data.paxnet_crawl_client import fetch_paxnet_discussions

logger = logging.getLogger(__name__)


@tool
def get_community_sentiment_analysis(company_name: str, stock_code: str) -> Dict[str, Any]:
    """
    한국 투자 커뮤니티 감정 분석
    Paxnet 종목토론 기반 실제 투자자 의견 분석
    """
    try:
        logger.info(f"Community sentiment analysis for {company_name} ({stock_code})")

        # 1. Paxnet 커뮤니티 데이터 수집
        paxnet_data = _fetch_paxnet_community_data(stock_code)

        # 2. 커뮤니티 데이터 감정 분석
        return _analyze_community_sentiment(company_name, stock_code, paxnet_data)

    except Exception as e:
        logger.error(f"Error in community sentiment analysis: {str(e)}")
        return {"error": str(e)}


def _fetch_paxnet_community_data(stock_code: str) -> Dict[str, Any]:
    """Paxnet 종목토론 데이터 수집"""
    try:
        logger.info(f"Fetching Paxnet community data for {stock_code}")

        # Paxnet 크롤링 클라이언트 사용 (2분 타임아웃)
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Paxnet 크롤링 2분 타임아웃")

        # Windows에서는 signal.alarm이 지원되지 않으므로 threading 사용
        import threading
        import time

        result_container = {}
        exception_container = {}

        def fetch_with_timeout():
            try:
                result_container['data'] = fetch_paxnet_discussions(stock_code, max_posts=10)
            except Exception as e:
                exception_container['error'] = e

        # 🚀 45초 타임아웃으로 크롤링 실행 (빠른 실패로 시스템 효율성 개선)
        thread = threading.Thread(target=fetch_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(timeout=45)  # 45초 타임아웃

        if thread.is_alive():
            logger.error(f"Paxnet 크롤링 45초 타임아웃 - 크롤링 실패")
            return {"error": "Paxnet 크롤링 타임아웃", "posts": []}

        if 'error' in exception_container:
            raise exception_container['error']

        result = result_container.get('data', {})

        if "error" in result:
            logger.error(f"Paxnet 데이터 수집 실패: {result['error']}")
            return {"error": result["error"], "posts": []}

        logger.info(f"Paxnet 데이터 수집 성공: {result.get('total_posts', 0)}개 게시글")
        return result

    except Exception as e:
        logger.error(f"Paxnet 커뮤니티 데이터 수집 오류: {str(e)}")
        return {"error": str(e), "posts": []}



def _analyze_community_sentiment(company_name: str, stock_code: str, paxnet_data: Dict) -> Dict[str, Any]:
    """커뮤니티 데이터 감정 분석"""
    try:
        # 크롤링 실패시 기본 분석 제공
        if "error" in paxnet_data:
            logger.warning(f"Paxnet 크롤링 실패 - 기본 커뮤니티 분석 제공: {paxnet_data['error']}")
            return {
                "community_sentiment": "중립",
                "sentiment_score": 0.0,
                "total_posts": 0,
                "positive_posts": 0,
                "negative_posts": 0,
                "key_themes": ["데이터 수집 제한으로 인한 분석 불가"],
                "analysis_summary": f"{company_name}의 온라인 커뮤니티 데이터 수집에 제한이 있어 정확한 투자자 심리 분석이 어려운 상황입니다. 다른 지표들을 통해 종합적인 투자 판단을 권장합니다.",
                "data_source": "Paxnet (제한적)",
                "last_updated": datetime.now().isoformat(),
                "status": "fallback_analysis"
            }

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

        # 커뮤니티 게시글 텍스트 준비
        community_texts = []
        if paxnet_data.get("posts"):
            community_texts = [
                f"[게시글 {i+1}] 제목: {post['title']}\n내용: {post['content'][:300]}..."
                for i, post in enumerate(paxnet_data["posts"])
            ]

        if not community_texts:
            return {"error": "수집된 커뮤니티 데이터가 없습니다."}

        # 커뮤니티 특화 분석 프롬프트
        analysis_prompt = f"""
다음은 {company_name}({stock_code}) 관련 한국 투자 커뮤니티(Paxnet 종목토론)에서 수집한 실제 투자자들의 게시글입니다.

[커뮤니티 게시글 데이터]
{chr(10).join(community_texts)}

[분석 요구사항]
투자 커뮤니티 특성을 고려하여 다음을 분석해주세요:

1. 전체적인 투자 심리를 '매우 긍정', '긍정', '중립', '부정', '매우 부정' 중 하나로 평가
2. 투자 심리 점수를 -1.0 (매우 부정) ~ 1.0 (매우 긍정) 사이 수치로 계산
3. 투자자들이 주로 관심 갖는 핵심 이슈 3가지를 키워드로 요약
4. 가장 긍정적/부정적 의견 각 1개씩 선정
5. 투자자들의 주요 관심사 (기술적 분석, 펀더멘털, 시장 이슈 등)
6. 커뮤니티 특유의 투자 정보나 루머, 추측 내용 파악

[출력 형식]
- Overall Investor Sentiment: [평가 결과]
- Sentiment Score: [점수]
- Key Investment Issues: [이슈1, 이슈2, 이슈3]
- Most Positive Opinion: [의견]
- Most Negative Opinion: [의견]
- Main Concerns: [투자자들의 주요 관심사]
- Community Insights: [커뮤니티 특유의 정보나 관점]
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

        # 커뮤니티 게시글 소스 정보
        community_sources = []
        if paxnet_data.get("posts"):
            for i, post in enumerate(paxnet_data["posts"]):
                community_sources.append({
                    "post_number": i + 1,
                    "title": post.get("title", ""),
                    "url": post.get("url", ""),
                    "source": "Paxnet 종목토론",
                    "type": "community_post"
                })

        return {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "data_source": "Paxnet 종목토론",
            "analysis_type": "Community Sentiment Analysis",
            "total_posts_analyzed": len(community_texts),
            "sentiment_analysis": parsed_result,
            "community_sources": community_sources,
            "last_updated": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"커뮤니티 감정 분석 오류: {str(e)}")
        return {"error": str(e)}


# 도구 목록
community_tools = [get_community_sentiment_analysis]


def create_community_agent():
    """Community Sentiment Analysis Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=llm_model_name, temperature=0.1, google_api_key=llm_api_key
        )
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

    prompt = (
        "당신은 한국 투자 커뮤니티의 여론과 심리를 분석하는 전문가입니다. "
        "실제 개인 투자자들의 의견과 토론을 통해 시장의 생생한 분위기를 파악하고 분석해주세요.\n\n"

        "먼저 `get_community_sentiment_analysis` 도구를 사용해서 최신 커뮤니티 감정 분석 데이터를 수집한 후, "
        "다음과 같이 투자자 친화적으로 설명해주세요:\n\n"

        "1. 현재 이 종목에 대한 투자자들의 분위기가 어떤지 요약해주세요\n"
        "   - 전체적으로 긍정적인지, 부정적인지, 관망세인지\n"
        "   - 투자 심리 점수를 쉬운 말로 설명해주세요\n\n"

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
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'COMMUNITY_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
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