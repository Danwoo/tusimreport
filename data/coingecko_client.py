"""
CoinGecko API Client
암호화폐 시장 데이터 수집 (비트코인, 이더리움 등)

Free Tier: Generous limits (50 calls/minute)
API Docs: https://www.coingecko.com/en/api/documentation
"""

import logging
from typing import Any

from data.base_client import BaseAPIClient
from data.cache_ttl import CRYPTO_PRICE_MINUTES
from utils.redaction import redact
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


class CoinGeckoClient(BaseAPIClient):
    """CoinGecko API 클라이언트 - 암호화폐 데이터 (인증 불필요)"""

    def __init__(self):
        super().__init__(api_key=None, cache_subdir="coingecko_cache")
        self.base_url = "https://api.coingecko.com/api/v3"

    def _get_cached_data(self, cache_key: str, max_age_minutes: int = 5) -> dict[str, Any] | None:
        return self.get_cached(cache_key, max_age_hours=max_age_minutes / 60.0)

    def _save_to_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        self.save_cache(cache_key, data)

    def get_market_overview(self) -> dict[str, Any]:
        """
        암호화폐 시장 개요 조회 (주요 코인: BTC, ETH, BNB, XRP, ADA)

        응답에 없는 값은 0.0이 아니라 None이다. 실패하면 available=False와 사유를
        돌려주고 캐시에 쓰지 않는다.

        Returns:
            {
                "bitcoin": {
                    "symbol": "BTC",
                    "current_price_usd": 65000.0,
                    "current_price_krw": 85800000.0,
                    "price_change_24h": 2.5,
                    "market_cap_usd": 1.3e12,
                    "total_volume_usd": 2.8e10
                },
                ...
                "global": {...},  # /global 실패 시 {}
                "available": bool,
                "reason": str,  # available이 False일 때만
                "timestamp": "2025-11-17T10:30:00+09:00"
            }
        """
        cache_key = "crypto_market_overview"
        cached = self._get_cached_data(cache_key, max_age_minutes=CRYPTO_PRICE_MINUTES)
        if cached and cached.get("available") is True:
            return cached

        try:
            coin_ids = ["bitcoin", "ethereum", "binancecoin", "ripple", "cardano"]

            params = {
                "ids": ",".join(coin_ids),
                "vs_currencies": "usd,krw",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
            }

            response = self.session.get(f"{self.base_url}/simple/price", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            result: dict[str, Any] = {}
            for coin_id in coin_ids:
                coin_data = data.get(coin_id) if isinstance(data, dict) else None
                if isinstance(coin_data, dict) and coin_data.get("usd") is not None:
                    result[coin_id] = {
                        "symbol": self._get_coin_symbol(coin_id),
                        "current_price_usd": coin_data.get("usd"),
                        "current_price_krw": coin_data.get("krw"),
                        "price_change_24h": coin_data.get("usd_24h_change"),
                        "market_cap_usd": coin_data.get("usd_market_cap"),
                        "total_volume_usd": coin_data.get("usd_24h_vol"),
                    }

            if not result:
                return self._unavailable("CoinGecko 응답에 요청한 코인 가격이 없습니다")

            result["global"] = self._get_global_market_data()
            result["available"] = True
            result["timestamp"] = kst_isoformat()

            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            reason = redact(f"CoinGecko 연결 실패: {type(e).__name__}: {e}")
            logger.error(f"암호화폐 시장 데이터 조회 실패: {reason}")
            return self._unavailable(reason)

    def _get_global_market_data(self) -> dict[str, Any]:
        """
        글로벌 암호화폐 시장 데이터 조회. 실패하면 {}.

        Returns:
            {
                "total_market_cap_usd": 2400000000000,
                "total_volume_24h_usd": 120000000000,
                "bitcoin_dominance": 45.2,
                "eth_dominance": 18.5,
                "active_cryptocurrencies": 12000
            }
        """
        try:
            response = self.session.get(f"{self.base_url}/global", timeout=10)
            response.raise_for_status()
            data = response.json()

            market_data = data.get("data") if isinstance(data, dict) else None
            if not isinstance(market_data, dict):
                return {}
            return {
                "total_market_cap_usd": (market_data.get("total_market_cap") or {}).get("usd"),
                "total_volume_24h_usd": (market_data.get("total_volume") or {}).get("usd"),
                "bitcoin_dominance": (market_data.get("market_cap_percentage") or {}).get("btc"),
                "eth_dominance": (market_data.get("market_cap_percentage") or {}).get("eth"),
                "active_cryptocurrencies": market_data.get("active_cryptocurrencies"),
            }

        except Exception as e:
            logger.error(f"글로벌 시장 데이터 조회 실패: {redact(str(e))}")
            return {}

    def _get_coin_symbol(self, coin_id: str) -> str:
        """코인 ID를 심볼로 변환"""
        symbol_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "binancecoin": "BNB",
            "ripple": "XRP",
            "cardano": "ADA",
        }
        return symbol_map.get(coin_id, coin_id.upper()[:3])

    def _unavailable(self, reason: str) -> dict[str, Any]:
        """받지 못한 결과. 'note'는 옛 호출자(note 유무로 실패를 판단)와의 호환용이다."""
        return {
            "bitcoin": {},
            "ethereum": {},
            "global": {},
            "available": False,
            "reason": reason,
            "note": reason,
            "timestamp": kst_isoformat(),
        }


# 테스트 코드
if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)

    client = CoinGeckoClient()

    # 암호화폐 시장 현황 테스트
    print("\n=== 암호화폐 시장 현황 ===")
    market_data = client.get_market_overview()
    print(json.dumps(market_data, indent=2, ensure_ascii=False))
