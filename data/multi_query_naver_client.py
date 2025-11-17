#!/usr/bin/env python3
"""
Multi-Query Naver News API Client
P2-1-B: 뉴스 커버리지 확장 전략 (10개 → 50개)
"""

import logging
import requests
import time
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MultiQueryNaverClient:
    """
    멀티 쿼리 전략으로 Naver News 커버리지를 5배 확장

    전략:
    - 5개 다각화 쿼리 (기본, 실적, 주가, 전망, 발표)
    - URL 기반 중복 제거
    - Rate limiting (0.5초 대기)
    - 목표: 50개 뉴스
    """

    def __init__(self, client_id: str, client_secret: str):
        """
        Args:
            client_id: Naver API Client ID
            client_secret: Naver API Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.naver.com/v1/search/news.json"

    def _generate_queries(self, company_name: str, stock_code: str) -> List[str]:
        """
        5개 다각화 쿼리 생성

        Args:
            company_name: 회사명 (예: "삼성전자")
            stock_code: 종목코드 (예: "005930")

        Returns:
            5개 쿼리 리스트
        """
        return [
            company_name,                    # 기본 검색
            f"{company_name} 실적",          # 실적 관련
            f"{company_name} 주가",          # 주가 동향
            f"{company_name} 전망",          # 전망/분석
            f"{company_name} 발표",          # 공시/발표
        ]

    def _fetch_single_query(self, query: str, display: int = 10) -> List[Dict[str, Any]]:
        """
        단일 쿼리 실행

        Args:
            query: 검색 쿼리
            display: 결과 개수

        Returns:
            뉴스 아이템 리스트
        """
        try:
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            }
            params = {
                "query": query,
                "display": display,
                "sort": "sim",  # 정확도순
            }

            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            items = result.get("items", [])

            logger.info(f"✅ Naver 쿼리 '{query}': {len(items)}개 수집")
            return items

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Naver API 요청 실패 ('{query}'): {e}")
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

    def _format_news_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        뉴스 아이템 표준 형식 변환

        Args:
            item: Naver API 응답 아이템

        Returns:
            표준 형식 뉴스 아이템
        """
        return {
            "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
            "content": item.get("description", "").replace("<b>", "").replace("</b>", ""),
            "url": item.get("link", ""),
            "published_at": item.get("pubDate", ""),
            "source": "Naver News API",
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
            중복 제거된 뉴스 리스트
        """
        logger.info(f"🚀 멀티 쿼리 Naver 뉴스 수집 시작: {company_name} ({stock_code})")

        # 1. 5개 쿼리 생성
        queries = self._generate_queries(company_name, stock_code)
        logger.info(f"📝 생성된 쿼리: {queries}")

        # 2. 각 쿼리 실행 (Rate limiting 적용)
        all_news = []
        per_query = max(10, target_count // len(queries))

        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(0.5)  # Rate limiting: 0.5초 대기

            items = self._fetch_single_query(query, display=per_query)
            all_news.extend(items)

        logger.info(f"📰 총 수집: {len(all_news)}개 (중복 포함)")

        # 3. URL 기반 중복 제거
        unique_news = self._deduplicate_by_url(all_news)

        # 4. 표준 형식 변환
        formatted_news = [self._format_news_item(item) for item in unique_news[:target_count]]

        logger.info(f"✅ 최종 결과: {len(formatted_news)}개 (목표: {target_count}개)")

        return formatted_news


def test_multi_query_naver():
    """테스트 함수"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ Naver API 키가 설정되지 않았습니다.")
        return

    client = MultiQueryNaverClient(client_id, client_secret)

    # 삼성전자 테스트
    news = client.fetch_multi_query("삼성전자", "005930", target_count=50)

    print(f"\n📊 테스트 결과:")
    print(f"수집된 뉴스: {len(news)}개")
    print(f"\n샘플 뉴스 (최신 3개):")
    for i, item in enumerate(news[:3], 1):
        print(f"\n{i}. {item['title']}")
        print(f"   URL: {item['url']}")


if __name__ == "__main__":
    test_multi_query_naver()
