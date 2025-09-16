#!/usr/bin/env python3
"""
Tavily Search API Client
투자 전문가 & Dr. Alex Rivera (Tavily CTO) 공동 최적화
"""

import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TavilyNewsClient:
    """간소화된 Tavily Search API 클라이언트"""

    def __init__(self, api_key: Optional[str] = None):
        """Tavily API 클라이언트 초기화"""
        import os

        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com"

    def search_company_news(
        self, company_name: str, max_results: int = 10
    ) -> Dict[str, Any]:
        """
        투자 전문가 최적화: 회사 관련 금융뉴스 검색

        Args:
            company_name: 회사명
            max_results: 최대 결과 수
        """
        if not self.api_key:
            return {"error": "Tavily API 키가 설정되지 않았습니다."}

        try:
            # 투자 전문가 추천: 간결하고 효과적인 검색 쿼리
            search_query = f"{company_name} stock earnings financial"

            payload = {
                "api_key": self.api_key,
                "query": search_query,
                "search_depth": "basic",  # 투자 전문가 추천: 노이즈 최소화
                "include_answer": True,  # AI 요약 포함
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
                f"{self.base_url}/search", json=payload, timeout=15
            )
            response.raise_for_status()

            return self._format_results(response.json(), company_name)

        except Exception as e:
            logger.error(f"Tavily API 오류: {str(e)}")
            return {"error": f"API 오류: {str(e)}"}

    def _format_results(self, raw_results: Dict, company_name: str) -> Dict[str, Any]:
        """결과를 표준 형식으로 변환 (간소화)"""
        results = raw_results.get("results", [])

        # Tavily AI가 이미 필터링했으므로 추가 검증 불필요
        news_items = []
        for item in results:
            if len(item.get("title", "")) > 10:  # 최소 품질만 확인
                news_items.append(
                    {
                        "title": item.get("title", ""),
                        "content": item.get("content", "")[:400],
                        "url": item.get("url", ""),
                        "score": item.get("score", 0),
                        "source": (
                            item.get("url", "").split("//")[-1].split("/")[0]
                            if item.get("url")
                            else "unknown"
                        ),
                    }
                )

        return {
            "status": "success",
            "company_name": company_name,
            "search_query": f"{company_name} stock earnings financial",
            "news_count": len(news_items),
            "news_items": news_items,
            "ai_summary": raw_results.get("answer", ""),
            "data_source": "Tavily Search API",
            "search_timestamp": datetime.now().isoformat(),
        }


def fetch_tavily_company_news(
    company_name: str, max_results: int = 10
) -> Dict[str, Any]:
    """편의 함수: 투자 전문가 최적화 뉴스 검색"""
    client = TavilyNewsClient()
    return client.search_company_news(company_name, max_results=max_results)
