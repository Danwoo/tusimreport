"""
Multi-Query Tavily Search Client
다각화된 검색 전략으로 글로벌 뉴스 커버리지 5배 확장

🎯 P2-1-B: Tavily API 최적화 (Option B)
- 단일 쿼리 10개 → 멀티 쿼리 50개
- 시간대별/카테고리별 다각화 검색
- 글로벌 + 한국 매체 균형잡힌 커버리지
"""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class MultiQueryTavilyClient:
    """멀티 쿼리 기반 Tavily Search 클라이언트"""

    def __init__(self, api_key: str):
        """
        클라이언트 초기화

        Args:
            api_key: Tavily API Key
        """
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    def generate_queries(self, company_name: str, stock_code: str) -> list[dict[str, Any]]:
        """
        기업명 기반 다각화 검색 쿼리 생성

        Args:
            company_name: 기업명 (예: "삼성전자")
            stock_code: 종목코드 (예: "005930")

        Returns:
            쿼리 설정 리스트 (5개)
        """
        queries = [
            {"query": f"{company_name} stock earnings financial", "category": "재무/실적", "max_results": 10},
            {"query": f"{company_name} stock price analysis", "category": "주가 분석", "max_results": 10},
            {"query": f"{company_name} latest news", "category": "최신 뉴스", "max_results": 10},
            {"query": f"{company_name} market outlook forecast", "category": "시장 전망", "max_results": 10},
            {"query": f"{company_name} stock investment", "category": "투자 의견", "max_results": 10},
        ]

        return queries

    def search_single_query(self, query_config: dict[str, Any]) -> dict[str, Any]:
        """
        단일 쿼리로 뉴스 검색

        Args:
            query_config: 쿼리 설정 (query, category, max_results)

        Returns:
            Tavily API 응답 데이터
        """
        try:
            payload = {
                "api_key": self.api_key,
                "query": query_config["query"],
                "search_depth": "basic",
                "include_answer": True,
                "include_raw_content": False,
                "max_results": query_config["max_results"],
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

            response = requests.post(f"{self.base_url}/search", json=payload, timeout=15)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Tavily API 요청 실패 (쿼리: {query_config['query']}): {str(e)}")
            return {"error": str(e), "results": []}

    def fetch_multi_query(
        self, company_name: str, stock_code: str, target_count: int = 50
    ) -> list[dict[str, Any]]:
        """
        멀티 쿼리 전략으로 글로벌 뉴스 수집

        Args:
            company_name: 기업명
            stock_code: 종목코드
            target_count: 목표 뉴스 개수 (기본 50개)

        Returns:
            중복 제거된 뉴스 리스트
        """
        try:
            logger.info(f"🌍 Tavily 멀티 쿼리 뉴스 수집 시작: {company_name} (목표: {target_count}개)")

            # 1. 검색 쿼리 생성
            query_configs = self.generate_queries(company_name, stock_code)
            logger.info(f"   생성된 검색 쿼리: {len(query_configs)}개")

            # 2. 각 쿼리로 뉴스 수집
            all_news = []
            seen_urls = set()

            for i, query_config in enumerate(query_configs, 1):
                logger.info(f"   [{i}/{len(query_configs)}] 카테고리: {query_config['category']}")
                logger.info(f'      쿼리: "{query_config["query"]}"')

                # API 호출
                data = self.search_single_query(query_config)
                results = data.get("results", [])

                # 중복 제거하면서 추가
                new_count = 0
                for item in results:
                    url = item.get("url", "")
                    if url and url not in seen_urls and len(item.get("title", "")) > 10:
                        seen_urls.add(url)
                        all_news.append(
                            {
                                "title": item.get("title", ""),
                                "content": item.get("content", "")[:400],
                                "url": url,
                                "score": item.get("score", 0),
                                "source": item.get("url", "").split("//")[-1].split("/")[0]
                                if url
                                else "unknown",
                                "category": query_config["category"],
                                "query": query_config["query"],
                            }
                        )
                        new_count += 1

                logger.info(f"      → 수집: {len(results)}개, 신규: {new_count}개")

                # API Rate Limiting 고려 (1초 대기)
                if i < len(query_configs):
                    time.sleep(1)

            # 3. Relevance Score 기준 정렬 (Tavily 자체 스코어)
            all_news.sort(key=lambda x: x.get("score", 0), reverse=True)

            logger.info(f"✅ Tavily 멀티 쿼리 뉴스 수집 완료: {len(all_news)}개 (중복 제거 후)")

            return all_news[:target_count]  # 목표 개수만큼만 반환

        except Exception as e:
            logger.error(f"Tavily 멀티 쿼리 뉴스 수집 실패: {str(e)}")
            return []


# 테스트 코드
if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # API 키 로드
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        print("❌ Tavily API 키가 설정되지 않았습니다.")
        print("💡 .env 파일에 다음을 추가하세요:")
        print("   TAVILY_API_KEY=your_api_key")
        exit(1)

    # 클라이언트 생성
    client = MultiQueryTavilyClient(api_key)

    # 테스트: 삼성전자
    print("\n" + "=" * 80)
    print("🌍 멀티 쿼리 Tavily Search 테스트 (삼성전자)")
    print("=" * 80)

    news_list = client.fetch_multi_query(company_name="삼성전자", stock_code="005930", target_count=50)

    print(f"\n✅ 총 {len(news_list)}개 뉴스 수집 완료")
    print("\n🔍 상위 10개 뉴스 샘플:")
    for i, news in enumerate(news_list[:10], 1):
        print(f"\n[{i}] [{news['category']}] (Score: {news['score']:.2f})")
        print(f"    제목: {news['title'][:60]}...")
        print(f"    출처: {news['source']}")
        print(f"    URL: {news['url']}")
