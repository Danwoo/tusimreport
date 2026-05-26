"""
CoinGecko API Client
암호화폐 시장 데이터 수집 (비트코인, 이더리움 등)

Free Tier: Generous limits (50 calls/minute)
API Docs: https://www.coingecko.com/en/api/documentation
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from data.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class CoinGeckoClient(BaseAPIClient):
    """CoinGecko API 클라이언트 - 암호화폐 데이터 (인증 불필요)"""

    def __init__(self):
        super().__init__(api_key=None, cache_subdir="coingecko_cache")
        self.base_url = "https://api.coingecko.com/api/v3"

    def _get_cached_data(self, cache_key: str, max_age_minutes: int = 5) -> Optional[Dict[str, Any]]:
        return self.get_cached(cache_key, max_age_hours=max_age_minutes / 60.0)

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        self.save_cache(cache_key, data)

    def get_market_overview(self) -> Dict[str, Any]:
        """
        암호화폐 시장 개요 조회 (주요 코인: BTC, ETH, BNB, XRP, ADA)

        Returns:
            {
                "bitcoin": {
                    "symbol": "BTC",
                    "current_price_usd": 65000.0,
                    "current_price_krw": 85800000.0,
                    "price_change_24h": 2.5,
                    "market_cap_rank": 1,
                    "total_volume": 28000000000
                },
                ...
                "total_market_cap": 2400000000000,
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        cache_key = "crypto_market_overview"
        cached = self._get_cached_data(cache_key, max_age_minutes=5)  # 5분 캐시
        if cached:
            return cached

        try:
            # 주요 암호화폐 ID
            coin_ids = ["bitcoin", "ethereum", "binancecoin", "ripple", "cardano"]

            params = {
                "ids": ",".join(coin_ids),
                "vs_currencies": "usd,krw",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true"
            }

            response = self.session.get(
                f"{self.base_url}/simple/price",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 결과 포맷팅
            result = {}
            for coin_id in coin_ids:
                if coin_id in data:
                    coin_data = data[coin_id]
                    result[coin_id] = {
                        "symbol": self._get_coin_symbol(coin_id),
                        "current_price_usd": coin_data.get("usd", 0.0),
                        "current_price_krw": coin_data.get("krw", 0.0),
                        "price_change_24h": coin_data.get("usd_24h_change", 0.0),
                        "market_cap_usd": coin_data.get("usd_market_cap", 0.0),
                        "total_volume_usd": coin_data.get("usd_24h_vol", 0.0)
                    }

            # 글로벌 시장 데이터 추가
            global_data = self._get_global_market_data()
            result["global"] = global_data
            result["timestamp"] = datetime.now().isoformat()

            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"암호화폐 시장 데이터 조회 실패: {str(e)}")
            return self._create_fallback_market_overview()

    def _get_global_market_data(self) -> Dict[str, Any]:
        """
        글로벌 암호화폐 시장 데이터 조회

        Returns:
            {
                "total_market_cap_usd": 2400000000000,
                "total_volume_24h_usd": 120000000000,
                "bitcoin_dominance": 45.2,
                "eth_dominance": 18.5
            }
        """
        try:
            response = self.session.get(f"{self.base_url}/global", timeout=10)
            response.raise_for_status()
            data = response.json()

            if "data" in data:
                market_data = data["data"]
                return {
                    "total_market_cap_usd": market_data.get("total_market_cap", {}).get("usd", 0.0),
                    "total_volume_24h_usd": market_data.get("total_volume", {}).get("usd", 0.0),
                    "bitcoin_dominance": market_data.get("market_cap_percentage", {}).get("btc", 0.0),
                    "eth_dominance": market_data.get("market_cap_percentage", {}).get("eth", 0.0),
                    "active_cryptocurrencies": market_data.get("active_cryptocurrencies", 0)
                }
            else:
                return {}

        except Exception as e:
            logger.error(f"글로벌 시장 데이터 조회 실패: {str(e)}")
            return {}

    def get_bitcoin_correlation(self, stock_symbol: str = "SPY") -> Dict[str, Any]:
        """
        비트코인과 주식시장 상관관계 분석 (간이 버전)

        Args:
            stock_symbol: 주식 심볼 (default: SPY - S&P 500 ETF)

        Returns:
            {
                "bitcoin_price": 65000.0,
                "bitcoin_change_24h": 2.5,
                "stock_symbol": "SPY",
                "correlation_interpretation": "긍정적 상관관계",
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        try:
            # 비트코인 데이터
            btc_data = self.get_market_overview().get("bitcoin", {})

            # 상관관계 해석 (간이 버전: 24시간 변화율 기준)
            btc_change = btc_data.get("price_change_24h", 0.0)

            if btc_change > 2.0:
                interpretation = "강한 상승세 - 리스크 온 (Risk-On) 환경"
            elif btc_change > 0.5:
                interpretation = "완만한 상승세 - 중립적 시장 심리"
            elif btc_change > -0.5:
                interpretation = "보합세 - 관망 분위기"
            elif btc_change > -2.0:
                interpretation = "완만한 하락세 - 조정 국면"
            else:
                interpretation = "강한 하락세 - 리스크 오프 (Risk-Off) 환경"

            return {
                "bitcoin_price": btc_data.get("current_price_usd", 0.0),
                "bitcoin_change_24h": btc_change,
                "stock_symbol": stock_symbol,
                "correlation_interpretation": interpretation,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"비트코인 상관관계 분석 실패: {str(e)}")
            return {
                "bitcoin_price": 0.0,
                "bitcoin_change_24h": 0.0,
                "stock_symbol": stock_symbol,
                "correlation_interpretation": "데이터 없음",
                "timestamp": datetime.now().isoformat()
            }

    def _get_coin_symbol(self, coin_id: str) -> str:
        """코인 ID를 심볼로 변환"""
        symbol_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "binancecoin": "BNB",
            "ripple": "XRP",
            "cardano": "ADA"
        }
        return symbol_map.get(coin_id, coin_id.upper()[:3])

    def _create_fallback_market_overview(self) -> Dict[str, Any]:
        """Fallback 암호화폐 시장 데이터 (API 실패 시)"""
        return {
            "bitcoin": {
                "symbol": "BTC",
                "current_price_usd": 0.0,
                "current_price_krw": 0.0,
                "price_change_24h": 0.0,
                "market_cap_usd": 0.0,
                "total_volume_usd": 0.0
            },
            "ethereum": {
                "symbol": "ETH",
                "current_price_usd": 0.0,
                "current_price_krw": 0.0,
                "price_change_24h": 0.0,
                "market_cap_usd": 0.0,
                "total_volume_usd": 0.0
            },
            "global": {},
            "timestamp": datetime.now().isoformat(),
            "note": "⚠️ CoinGecko API 연결 실패. 실시간 암호화폐 데이터를 사용할 수 없습니다."
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

    # 비트코인 상관관계 테스트
    print("\n=== 비트코인 상관관계 ===")
    correlation_data = client.get_bitcoin_correlation()
    print(json.dumps(correlation_data, indent=2, ensure_ascii=False))
