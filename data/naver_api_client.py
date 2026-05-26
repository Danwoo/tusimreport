#!/usr/bin/env python3
"""Naver News API 클라이언트."""

import logging
import requests
from typing import Any, Dict, List

from config.settings import settings

logger = logging.getLogger(__name__)


_NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _auth_headers() -> Dict[str, str] | None:
    """Naver API 인증 헤더. 자격 증명 없으면 None."""
    client_id = settings.naver_client_id
    client_secret = settings.naver_client_secret
    if not client_id or not client_secret:
        return None
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def fetch_naver_news(query: str, display: int = 50) -> Dict[str, Any]:
    """Naver News API를 호출하여 뉴스 검색 결과(raw JSON)를 반환."""
    try:
        headers = _auth_headers()
        if headers is None:
            return {"error": "Naver API 자격 증명이 .env 파일에 설정되지 않았습니다."}

        params = {"query": query, "display": display, "sort": "sim"}
        response = requests.get(_NAVER_NEWS_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Naver News API 요청 실패: {e}")
        return {"error": f"API 요청 실패: {e}"}
    except Exception as e:
        logger.error(f"Naver 뉴스 데이터 처리 중 알 수 없는 오류: {e}")
        return {"error": f"알 수 없는 오류: {e}"}


def build_display_search_query(company_name: str) -> str:
    """UI 표시용 뉴스 검색 쿼리. 종목별 키워드 보강."""
    if company_name == "KT":
        return f"{company_name} 주식"
    if company_name in {"LG", "SK"}:
        return f"{company_name} 그룹"
    if company_name == "현대차":
        return f"{company_name} 자동차"
    return f"{company_name} 주식"


def fetch_naver_news_for_display(
    company_name: str, display: int = 10
) -> List[Dict[str, str]]:
    """UI 표시용 정제된 뉴스 리스트.

    `<b>` 강조 태그를 제거하고 title/url/pub_date 필드만 노출한다.
    main.py와 UI 카드가 공통으로 호출하던 로직.
    """
    raw = fetch_naver_news(build_display_search_query(company_name), display=display)
    if raw.get("error"):
        return []
    items = []
    for item in raw.get("items", []):
        items.append(
            {
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "url": item.get("link", ""),
                "pub_date": item.get("pubDate", "")[:16],
            }
        )
    return items
