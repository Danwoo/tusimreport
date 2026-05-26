"""
Alpha Vantage API Client
글로벌 시장 데이터 수집 (미국 증시, 환율)

Free Tier: 25 requests/day → 캐싱 필수
API Docs: https://www.alphavantage.co/documentation/
"""

import logging
from datetime import datetime
from typing import Any

from data.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class AlphaVantageClient(BaseAPIClient):
    """Alpha Vantage API 클라이언트 - 글로벌 시장 데이터"""

    def __init__(self, api_key: str | None = None):
        from config.settings import settings

        resolved_key = api_key or getattr(settings, "alpha_vantage_api_key", None)
        super().__init__(api_key=resolved_key, cache_subdir="alpha_vantage_cache")
        self.base_url = "https://www.alphavantage.co/query"
        if not self.api_key:
            logger.warning("⚠️ Alpha Vantage API key not configured")

    def get_global_market_overview(self) -> dict[str, Any]:
        """
        글로벌 주요 지수 현황 조회 (S&P 500, NASDAQ, 다우존스)

        Returns:
            {
                "sp500": {"symbol": "SPY", "price": 450.12, "change_percent": 0.5},
                "nasdaq": {"symbol": "QQQ", "price": 380.45, "change_percent": 0.8},
                "dow": {"symbol": "DIA", "price": 350.23, "change_percent": 0.3},
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        cache_key = "global_market_overview"
        cached = self.get_cached(cache_key, max_age_hours=1)  # 1시간 캐시
        if cached:
            return cached

        if not self.api_key:
            return self._create_fallback_market_overview()

        try:
            # SPY (S&P 500 ETF) 조회
            result = {
                "sp500": self._get_quote("SPY"),
                "nasdaq": self._get_quote("QQQ"),
                "dow": self._get_quote("DIA"),
                "timestamp": datetime.now().isoformat(),
            }

            self.save_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"글로벌 시장 데이터 조회 실패: {str(e)}")
            return self._create_fallback_market_overview()

    def _get_quote(self, symbol: str) -> dict[str, Any]:
        """
        개별 종목 시세 조회

        Args:
            symbol: 종목 심볼 (예: "SPY", "AAPL")

        Returns:
            {"symbol": "SPY", "price": 450.12, "change_percent": 0.5}
        """
        try:
            params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.api_key}

            response = self.session.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "Global Quote" not in data:
                logger.warning(f"Invalid response for {symbol}: {data}")
                return {"symbol": symbol, "price": 0.0, "change_percent": 0.0}

            quote = data["Global Quote"]
            return {
                "symbol": symbol,
                "price": float(quote.get("05. price", 0)),
                "change_percent": float(quote.get("10. change percent", "0").replace("%", "")),
                "volume": int(quote.get("06. volume", 0)),
                "latest_trading_day": quote.get("07. latest trading day", ""),
            }

        except Exception as e:
            logger.error(f"Quote 조회 실패 ({symbol}): {str(e)}")
            return {"symbol": symbol, "price": 0.0, "change_percent": 0.0}

    def get_exchange_rate(self, from_currency: str = "USD", to_currency: str = "KRW") -> dict[str, Any]:
        """
        환율 조회

        Args:
            from_currency: 기준 통화 (default: USD)
            to_currency: 대상 통화 (default: KRW)

        Returns:
            {
                "from": "USD",
                "to": "KRW",
                "rate": 1320.50,
                "timestamp": "2025-11-17T10:30:00"
            }
        """
        cache_key = f"exchange_rate_{from_currency}_{to_currency}"
        cached = self.get_cached(cache_key, max_age_hours=1)  # 1시간 캐시
        if cached:
            return cached

        if not self.api_key:
            return self._create_fallback_exchange_rate(from_currency, to_currency)

        try:
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency,
                "to_currency": to_currency,
                "apikey": self.api_key,
            }

            response = self.session.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "Realtime Currency Exchange Rate" not in data:
                logger.warning(f"Invalid response for {from_currency}/{to_currency}: {data}")
                return self._create_fallback_exchange_rate(from_currency, to_currency)

            rate_data = data["Realtime Currency Exchange Rate"]
            result = {
                "from": from_currency,
                "to": to_currency,
                "rate": float(rate_data.get("5. Exchange Rate", 0)),
                "timestamp": rate_data.get("6. Last Refreshed", datetime.now().isoformat()),
                "bid": float(rate_data.get("8. Bid Price", 0)),
                "ask": float(rate_data.get("9. Ask Price", 0)),
            }

            self.save_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"환율 조회 실패: {str(e)}")
            return self._create_fallback_exchange_rate(from_currency, to_currency)

    def _create_fallback_market_overview(self) -> dict[str, Any]:
        """Fallback 글로벌 시장 데이터 (API 키 없을 때)"""
        return {
            "sp500": {"symbol": "SPY", "price": 0.0, "change_percent": 0.0},
            "nasdaq": {"symbol": "QQQ", "price": 0.0, "change_percent": 0.0},
            "dow": {"symbol": "DIA", "price": 0.0, "change_percent": 0.0},
            "timestamp": datetime.now().isoformat(),
            "note": "⚠️ Alpha Vantage API 키가 설정되지 않았습니다. 실시간 데이터를 사용할 수 없습니다.",
        }

    def _create_fallback_exchange_rate(self, from_currency: str, to_currency: str) -> dict[str, Any]:
        """Fallback 환율 데이터 (API 키 없을 때)"""
        # 기본값: 1 USD = 1,320 KRW (대략적인 값)
        default_rate = 1320.0 if from_currency == "USD" and to_currency == "KRW" else 0.0

        return {
            "from": from_currency,
            "to": to_currency,
            "rate": default_rate,
            "timestamp": datetime.now().isoformat(),
            "note": "⚠️ Alpha Vantage API 키가 설정되지 않았습니다. 실시간 환율을 사용할 수 없습니다.",
        }


# 테스트 코드
if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)

    client = AlphaVantageClient()

    # 글로벌 시장 현황 테스트
    print("\n=== 글로벌 시장 현황 ===")
    market_data = client.get_global_market_overview()
    print(json.dumps(market_data, indent=2, ensure_ascii=False))

    # 환율 테스트
    print("\n=== USD/KRW 환율 ===")
    exchange_data = client.get_exchange_rate("USD", "KRW")
    print(json.dumps(exchange_data, indent=2, ensure_ascii=False))
