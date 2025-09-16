#!/usr/bin/env python3
"""
Naver News API 클라이언트
"""

import logging
import requests
from typing import Dict, Any, List

from config.settings import settings

logger = logging.getLogger(__name__)

def fetch_naver_news(query: str, display: int = 50) -> Dict[str, Any]:
    """Naver News API를 호출하여 뉴스 검색 결과를 반환합니다."""
    try:
        client_id = settings.naver_client_id
        client_secret = settings.naver_client_secret

        if not client_id or not client_secret:
            return {"error": "Naver API 자격 증명이 .env 파일에 설정되지 않았습니다."}

        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {
            "query": query,
            "display": display,
            "sort": "sim",  # 정확도순
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Naver News API 요청 실패: {e}")
        return {"error": f"API 요청 실패: {e}"}
    except Exception as e:
        logger.error(f"Naver 뉴스 데이터 처리 중 알 수 없는 오류: {e}")
        return {"error": f"알 수 없는 오류: {e}"}
