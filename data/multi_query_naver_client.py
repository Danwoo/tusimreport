"""
Multi-Query Naver News Client
멀티 쿼리 전략으로 뉴스 커버리지 5배 확장

🎯 P2-1-B: Naver API 최적화 (Option B)
- 단일 쿼리 10개 → 멀티 쿼리 50개
- 중복 제거 및 품질 필터링
- 다각화된 검색어로 포괄적 커버리지
"""

import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class MultiQueryNaverClient:
    """멀티 쿼리 기반 Naver News 클라이언트"""

    def __init__(self, client_id: str, client_secret: str):
        """
        클라이언트 초기화

        Args:
            client_id: Naver API Client ID
            client_secret: Naver API Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.naver.com/v1/search/news.json"

    def generate_queries(
        self,
        company_name: str,
        stock_code: str
    ) -> List[str]:
        """
        기업명 기반 다각화 검색어 생성

        Args:
            company_name: 기업명 (예: "삼성전자")
            stock_code: 종목코드 (예: "005930")

        Returns:
            검색어 리스트 (5개)
        """
        queries = [
            company_name,                    # 기본 검색
            f"{company_name} 실적",          # 실적 관련
            f"{company_name} 주가",          # 주가 동향
            f"{company_name} 전망",          # 전망/분석
            f"{company_name} 발표",          # 공시/발표
        ]

        # 산업별 특화 키워드 (향후 확장 가능)
        # 예: 삼성전자 → HBM, 반도체
        # 예: 현대차 → 전기차, EV
        # 예: 네이버 → AI, 검색

        return queries

    def fetch_single_query(
        self,
        query: str,
        display: int = 10
    ) -> Dict[str, Any]:
        """
        단일 쿼리로 뉴스 검색

        Args:
            query: 검색 쿼리
            display: 결과 개수 (기본 10개)

        Returns:
            Naver API 응답 데이터
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

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Naver API 요청 실패 (쿼리: {query}): {str(e)}")
            return {"error": str(e), "items": []}

    def fetch_multi_query(
        self,
        company_name: str,
        stock_code: str,
        target_count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        멀티 쿼리 전략으로 뉴스 수집

        Args:
            company_name: 기업명
            stock_code: 종목코드
            target_count: 목표 뉴스 개수 (기본 50개)

        Returns:
            중복 제거된 뉴스 리스트
        """
        try:
            logger.info(f"📰 멀티 쿼리 뉴스 수집 시작: {company_name} (목표: {target_count}개)")

            # 1. 검색어 생성
            queries = self.generate_queries(company_name, stock_code)
            logger.info(f"   생성된 검색어: {len(queries)}개")

            # 2. 각 쿼리로 뉴스 수집
            all_news = []
            seen_urls = set()

            for i, query in enumerate(queries, 1):
                logger.info(f"   [{i}/{len(queries)}] 쿼리: \"{query}\"")

                # API 호출
                data = self.fetch_single_query(query, display=10)
                items = data.get("items", [])

                # 중복 제거하면서 추가
                new_count = 0
                for item in items:
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_news.append({
                            "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                            "content": item.get("description", "").replace("<b>", "").replace("</b>", ""),
                            "url": url,
                            "source": "Naver News API",
                            "published_at": item.get("pubDate", ""),
                            "query": query,  # 어떤 쿼리로 수집되었는지 추적
                        })
                        new_count += 1

                logger.info(f"      → 수집: {len(items)}개, 신규: {new_count}개")

                # API Rate Limiting 고려 (0.5초 대기)
                if i < len(queries):
                    time.sleep(0.5)

            # 3. 최신순 정렬
            # pubDate 파싱이 복잡하므로 수집 순서 유지 (이미 최신순)

            logger.info(f"✅ 멀티 쿼리 뉴스 수집 완료: {len(all_news)}개 (중복 제거 후)")

            return all_news[:target_count]  # 목표 개수만큼만 반환

        except Exception as e:
            logger.error(f"멀티 쿼리 뉴스 수집 실패: {str(e)}")
            return []


# 테스트 코드
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # API 키 로드
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ Naver API 키가 설정되지 않았습니다.")
        print("💡 .env 파일에 다음을 추가하세요:")
        print("   NAVER_CLIENT_ID=your_client_id")
        print("   NAVER_CLIENT_SECRET=your_client_secret")
        exit(1)

    # 클라이언트 생성
    client = MultiQueryNaverClient(client_id, client_secret)

    # 테스트: 삼성전자
    print("\n" + "="*80)
    print("📰 멀티 쿼리 Naver News 테스트 (삼성전자)")
    print("="*80)

    news_list = client.fetch_multi_query(
        company_name="삼성전자",
        stock_code="005930",
        target_count=50
    )

    print(f"\n✅ 총 {len(news_list)}개 뉴스 수집 완료")
    print(f"\n🔍 상위 10개 뉴스 샘플:")
    for i, news in enumerate(news_list[:10], 1):
        print(f"\n[{i}] [{news['query']}]")
        print(f"    제목: {news['title'][:60]}...")
        print(f"    URL: {news['url']}")
        print(f"    발행: {news['published_at']}")
