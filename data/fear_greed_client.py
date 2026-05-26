"""
Fear & Greed Index Client
시장 심리 지수 수집

CNN Fear & Greed Index API
API Docs: https://production.dataviz.cnn.io/index/fearandgreed/graphdata
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from data.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class FearGreedClient(BaseAPIClient):
    """Fear & Greed Index 클라이언트 - 시장 심리 지수 (인증 불필요)"""

    def __init__(self):
        super().__init__(api_key=None, cache_subdir="fear_greed_cache")
        self.api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

    def get_current_index(self) -> Dict[str, Any]:
        """
        현재 Fear & Greed Index 조회

        Returns:
            {
                "score": 45,  # 0-100
                "rating": "Fear",  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
                "previous_close": 50,
                "previous_week": 55,
                "previous_month": 60,
                "previous_year": 48,
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        cache_key = "fear_greed_index"
        cached = self.get_cached(cache_key, max_age_hours=6)  # 6시간 캐시
        if cached:
            return cached

        try:
            response = self.session.get(self.api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # 데이터 파싱
            if "fear_and_greed" in data:
                current = data["fear_and_greed"]
                result = {
                    "score": int(current.get("score", 50)),
                    "rating": current.get("rating", "Neutral"),
                    "previous_close": int(current.get("previous_close", 50)),
                    "previous_week": int(current.get("previous_1_week", 50)),
                    "previous_month": int(current.get("previous_1_month", 50)),
                    "previous_year": int(current.get("previous_1_year", 50)),
                    "timestamp": datetime.now().isoformat()
                }

                self.save_cache(cache_key, result)
                return result
            else:
                logger.warning(f"Invalid response: {data}")
                return self._create_fallback_index()

        except Exception as e:
            logger.error(f"Fear & Greed Index 조회 실패: {str(e)}")
            return self._create_fallback_index()

    def get_interpretation_korean(self, score: Optional[int] = None) -> str:
        """
        Fear & Greed Index를 한글로 해석

        Args:
            score: 지수 점수 (0-100), None이면 현재 지수 사용

        Returns:
            한글 해석 문자열
        """
        if score is None:
            index_data = self.get_current_index()
            score = index_data.get("score", 50)

        if score <= 25:
            return f"극단적 공포 ({score}/100) - 투자자들이 매우 두려워하는 상태로, 저점 매수 기회일 수 있습니다."
        elif score <= 45:
            return f"공포 ({score}/100) - 투자자들이 불안해하는 상태로, 신중한 접근이 필요합니다."
        elif score <= 55:
            return f"중립 ({score}/100) - 투자자들이 관망하는 상태로, 방향성이 불분명합니다."
        elif score <= 75:
            return f"탐욕 ({score}/100) - 투자자들이 낙관적인 상태로, 과열 조짐에 주의가 필요합니다."
        else:
            return f"극단적 탐욕 ({score}/100) - 투자자들이 매우 낙관적인 상태로, 고점 경계가 필요합니다."

    def get_trend_analysis(self) -> Dict[str, Any]:
        """
        Fear & Greed Index 추세 분석

        Returns:
            {
                "current_score": 45,
                "trend": "improving" | "stable" | "worsening",
                "change_from_week": -10,
                "change_from_month": -15,
                "interpretation_korean": "...",
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        try:
            index_data = self.get_current_index()
            current = index_data.get("score", 50)
            prev_week = index_data.get("previous_week", 50)
            prev_month = index_data.get("previous_month", 50)

            # 추세 판단
            week_change = current - prev_week
            if week_change > 5:
                trend = "improving"  # 탐욕 증가 (낙관론 증가)
            elif week_change < -5:
                trend = "worsening"  # 공포 증가 (비관론 증가)
            else:
                trend = "stable"

            return {
                "current_score": current,
                "trend": trend,
                "change_from_week": week_change,
                "change_from_month": current - prev_month,
                "interpretation_korean": self.get_interpretation_korean(current),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"추세 분석 실패: {str(e)}")
            return {
                "current_score": 50,
                "trend": "stable",
                "change_from_week": 0,
                "change_from_month": 0,
                "interpretation_korean": "데이터 없음",
                "timestamp": datetime.now().isoformat()
            }

    def _create_fallback_index(self) -> Dict[str, Any]:
        """Fallback Fear & Greed Index (API 실패 시)"""
        return {
            "score": 50,
            "rating": "Neutral",
            "previous_close": 50,
            "previous_week": 50,
            "previous_month": 50,
            "previous_year": 50,
            "timestamp": datetime.now().isoformat(),
            "note": "⚠️ Fear & Greed Index API 연결 실패. 기본값을 사용합니다."
        }


# 테스트 코드
if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)

    client = FearGreedClient()

    # 현재 지수 테스트
    print("\n=== Fear & Greed Index ===")
    index_data = client.get_current_index()
    print(json.dumps(index_data, indent=2, ensure_ascii=False))

    # 한글 해석 테스트
    print("\n=== 한글 해석 ===")
    interpretation = client.get_interpretation_korean()
    print(interpretation)

    # 추세 분석 테스트
    print("\n=== 추세 분석 ===")
    trend_data = client.get_trend_analysis()
    print(json.dumps(trend_data, indent=2, ensure_ascii=False))
