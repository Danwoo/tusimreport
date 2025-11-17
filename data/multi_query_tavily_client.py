#!/usr/bin/env python3
"""
Multi-Query Tavily Search API Client
P2-1-B: 뉴스 커버리지 확장 전략 (10개 → 50개)
"""

import logging
import requests
import time
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MultiQueryTavilyClient:
    """
    멀티 쿼리 전략으로 Tavily Search 커버리지를 5배 확장

    전략:
    - 5개 카테고리별 쿼리 (재무, 주가, 뉴스, 전망, 투자)
    - Relevance Score 기반 정렬
    - Rate limiting (1초 대기)
    - 목표: 50개 뉴스
    """

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Tavily API Key
        """
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    def _generate_queries(self, company_name: str, stock_code: str) -> List[Dict[str, str]]:
        """
        5개 카테고리별 쿼리 생성

        Args:
            company_name: 회사명 (예: "삼성전자")
            stock_code: 종목코드 (예: "005930")

        Returns:
            카테고리별 쿼리 리스트
        """
        return [
            {
                "category": "재무/실적",
                "query": f"{company_name} stock earnings financial"
            },
            {
                "category": "주가 분석",
                "query": f"{company_name} stock price analysis"
            },
            {
                "category": "최신 뉴스",
                "query": f"{company_name} latest news"
            },
            {
                "category": "시장 전망",
                "query": f"{company_name} market outlook forecast"
            },
            {
                "category": "투자 의견",
                "query": f"{company_name} stock investment"
            },
        ]

    def _fetch_single_query(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        단일 쿼리 실행

        Args:
            query: 검색 쿼리
            max_results: 최대 결과 수

        Returns:
            뉴스 아이템 리스트
        """
        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
                "max_results": max_results,
                "include_domains": [
                    # 글로벌 금융 매체
                    "reuters.com",
                    "bloomberg.com",
                    "marketwatch.com",
                    "cnbc.com",
                    "finance.yahoo.com",
                    "investing.com",
                    # 한국 주요 매체
                    "chosun.com",
                    "joongang.co.kr",
                    "donga.com",
                    "hankyung.com",
                    "mk.co.kr",
                    "moneytoday.co.kr",
                    "yonhapnews.co.kr",
                    "news1.kr",
                ],
            }

            response = requests.post(
                f"{self.base_url}/search",
                json=payload,
                timeout=15
            )
            response.raise_for_status()

            result = response.json()
            items = result.get("results", [])

            logger.info(f"✅ Tavily 쿼리 '{query}': {len(items)}개 수집")
            return items

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Tavily API 요청 실패 ('{query}'): {e}")
            return []
        except Exception as e:
            logger.error(f"❌ 알 수 없는 오류 ('{query}'): {e}")
            return []

    def _deduplicate_by_url(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        URL 기반 중복 제거

        Args:
            news_list: 뉴스 아이템 리스트

        Returns:
            중복 제거된 리스트
        """
        seen_urls = set()
        unique_news = []

        for news in news_list:
            url = news.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_news.append(news)

        logger.info(f"🔗 중복 제거: {len(news_list)}개 → {len(unique_news)}개")
        return unique_news

    def _format_news_item(self, item: Dict[str, Any], category: str = "") -> Dict[str, Any]:
        """
        뉴스 아이템 표준 형식 변환

        Args:
            item: Tavily API 응답 아이템
            category: 카테고리명

        Returns:
            표준 형식 뉴스 아이템
        """
        return {
            "title": item.get("title", ""),
            "content": item.get("content", "")[:400],
            "url": item.get("url", ""),
            "score": item.get("score", 0),
            "source": (
                item.get("url", "").split("//")[-1].split("/")[0]
                if item.get("url")
                else "unknown"
            ),
            "category": category,
        }

    def fetch_multi_query(
        self,
        company_name: str,
        stock_code: str,
        target_count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        멀티 쿼리 전략으로 뉴스 수집

        Args:
            company_name: 회사명 (예: "삼성전자")
            stock_code: 종목코드 (예: "005930")
            target_count: 목표 뉴스 개수 (기본: 50)

        Returns:
            중복 제거 및 정렬된 뉴스 리스트
        """
        logger.info(f"🚀 멀티 쿼리 Tavily 뉴스 수집 시작: {company_name} ({stock_code})")

        # 1. 5개 카테고리별 쿼리 생성
        queries = self._generate_queries(company_name, stock_code)
        logger.info(f"📝 생성된 쿼리: {[q['category'] for q in queries]}")

        # 2. 각 쿼리 실행 (Rate limiting 적용)
        all_news = []
        per_query = max(10, target_count // len(queries))

        for i, query_info in enumerate(queries):
            if i > 0:
                time.sleep(1.0)  # Rate limiting: 1초 대기

            category = query_info["category"]
            query = query_info["query"]

            items = self._fetch_single_query(query, max_results=per_query)

            # 카테고리 정보 추가
            for item in items:
                item["_category"] = category

            all_news.extend(items)

        logger.info(f"🌍 총 수집: {len(all_news)}개 (중복 포함)")

        # 3. URL 기반 중복 제거
        unique_news = self._deduplicate_by_url(all_news)

        # 4. Relevance Score 기반 정렬
        unique_news.sort(key=lambda x: x.get("score", 0), reverse=True)

        # 5. 표준 형식 변환
        formatted_news = [
            self._format_news_item(item, item.get("_category", ""))
            for item in unique_news[:target_count]
        ]

        logger.info(f"✅ 최종 결과: {len(formatted_news)}개 (목표: {target_count}개)")

        return formatted_news


def test_multi_query_tavily():
    """테스트 함수"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        print("❌ Tavily API 키가 설정되지 않았습니다.")
        return

    client = MultiQueryTavilyClient(api_key)

    # 삼성전자 테스트
    news = client.fetch_multi_query("삼성전자", "005930", target_count=50)

    print(f"\n📊 테스트 결과:")
    print(f"수집된 뉴스: {len(news)}개")
    print(f"\n샘플 뉴스 (최고 점수 3개):")
    for i, item in enumerate(news[:3], 1):
        print(f"\n{i}. [{item['category']}] {item['title']}")
        print(f"   Score: {item['score']:.2f}")
        print(f"   Source: {item['source']}")
        print(f"   URL: {item['url']}")


if __name__ == "__main__":
    test_multi_query_tavily()
