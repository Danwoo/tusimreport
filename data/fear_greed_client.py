"""
Fear & Greed Index Client
시장 심리 지수 수집

CNN Fear & Greed Index API
API Docs: https://production.dataviz.cnn.io/index/fearandgreed/graphdata

받지 못한 지수는 중립(50)으로 채우지 않는다: 값은 None, `available: False`,
`reason`에 한국어 사유를 담고 캐시에 쓰지 않는다. 실패 결과에만 붙는 `note`는
`"note" in result`로 실패를 가리는 기존 호출자(scripts/check_sources.py)용이다.
"""

import logging
from typing import Any

from core.errors import DataQualityError
from data.base_client import BaseAPIClient
from data.cache_ttl import FEAR_GREED_HOURS
from utils.agent_helpers import format_error_message_korean
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)

UNAVAILABLE_INTERPRETATION = "데이터 없음 — Fear & Greed Index를 가져오지 못했습니다."


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class FearGreedClient(BaseAPIClient):
    """Fear & Greed Index 클라이언트 - 시장 심리 지수 (인증 불필요)"""

    def __init__(self):
        super().__init__(api_key=None, cache_subdir="fear_greed_cache")
        self.api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

    def get_current_index(self) -> dict[str, Any]:
        """
        현재 Fear & Greed Index 조회

        Returns:
            {
                "score": 45,  # 0-100
                "rating": "Fear",  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
                "previous_close": 50,  # 없으면 None
                "previous_week": 55,
                "previous_month": 60,
                "previous_year": 48,
                "available": True,
                "timestamp": "2025-11-17T10:30:00+09:00"
            }
            실패 시 모든 값 None, available=False, reason=str
        """
        cache_key = "fear_greed_index"
        cached = self.get_cached(cache_key, max_age_hours=FEAR_GREED_HOURS)
        if isinstance(cached, dict) and cached.get("available") is True and cached.get("score") is not None:
            return cached

        try:
            result = self._fetch_index()
        except Exception as e:
            logger.warning(f"Fear & Greed Index 조회 실패: {e}")
            return self._unavailable_index(format_error_message_korean(e, "Fear & Greed Index 조회"))

        self.save_cache(cache_key, result)
        return result

    def _fetch_index(self) -> dict[str, Any]:
        data = self.request_json("GET", self.api_url)
        current = data.get("fear_and_greed") if isinstance(data, dict) else None
        if not isinstance(current, dict):
            raise DataQualityError("CNN payload has no 'fear_and_greed' object", source="cnn_fear_greed")

        score = _optional_int(current.get("score"))
        if score is None or not 0 <= score <= 100:
            raise DataQualityError("CNN payload has no usable score", source="cnn_fear_greed")

        return {
            "score": score,
            "rating": current.get("rating") or None,
            "previous_close": _optional_int(current.get("previous_close")),
            "previous_week": _optional_int(current.get("previous_1_week")),
            "previous_month": _optional_int(current.get("previous_1_month")),
            "previous_year": _optional_int(current.get("previous_1_year")),
            "available": True,
            "timestamp": kst_isoformat(),
        }

    def get_interpretation_korean(self, score: int | None = None) -> str:
        """
        Fear & Greed Index를 한글로 해석

        Args:
            score: 지수 점수 (0-100), None이면 현재 지수 사용

        Returns:
            한글 해석 문자열. 지수를 받지 못했으면 수치 없는 '데이터 없음' 문구.
        """
        if score is None:
            score = self.get_current_index().get("score")
        if score is None:
            return UNAVAILABLE_INTERPRETATION

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

    def get_trend_analysis(self, index_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Fear & Greed Index 추세 분석

        Args:
            index_data: 이미 받은 `get_current_index()` 결과. None이면 새로 조회.

        Returns:
            {
                "current_score": 45,
                "trend": "improving" | "stable" | "worsening" | None,
                "change_from_week": -10,  # 비교 값이 없으면 None
                "change_from_month": -15,
                "interpretation_korean": "...",
                "available": True,
                "timestamp": "2025-11-17T10:30:00+09:00"
            }
        """
        if index_data is None:
            index_data = self.get_current_index()

        current = index_data.get("score")
        if not index_data.get("available") or current is None:
            return {
                "current_score": None,
                "trend": None,
                "change_from_week": None,
                "change_from_month": None,
                "interpretation_korean": UNAVAILABLE_INTERPRETATION,
                "available": False,
                "reason": index_data.get("reason", "Fear & Greed Index 없음"),
                "timestamp": kst_isoformat(),
            }

        prev_week = index_data.get("previous_week")
        prev_month = index_data.get("previous_month")
        week_change = current - prev_week if prev_week is not None else None

        if week_change is None:
            trend = None
        elif week_change > 5:
            trend = "improving"  # 탐욕 증가 (낙관론 증가)
        elif week_change < -5:
            trend = "worsening"  # 공포 증가 (비관론 증가)
        else:
            trend = "stable"

        return {
            "current_score": current,
            "trend": trend,
            "change_from_week": week_change,
            "change_from_month": current - prev_month if prev_month is not None else None,
            "interpretation_korean": self.get_interpretation_korean(current),
            "available": True,
            "timestamp": kst_isoformat(),
        }

    @staticmethod
    def _unavailable_index(reason: str) -> dict[str, Any]:
        return {
            "score": None,
            "rating": None,
            "previous_close": None,
            "previous_week": None,
            "previous_month": None,
            "previous_year": None,
            "available": False,
            "reason": reason,
            "note": f"⚠️ {reason}",
            "timestamp": kst_isoformat(),
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
    trend_data = client.get_trend_analysis(index_data)
    print(json.dumps(trend_data, indent=2, ensure_ascii=False))
