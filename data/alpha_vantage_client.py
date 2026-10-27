"""
Alpha Vantage API Client
글로벌 시장 데이터 수집 (미국 증시, 환율)

Free Tier: 25 requests/day → 캐싱 필수
API Docs: https://www.alphavantage.co/documentation/

받지 못한 값은 숫자를 지어내지 않는다: 값은 None, `available: False`,
`reason`에 한국어 사유를 담아 돌려주고 캐시에 쓰지 않는다. 실패 결과에만
붙는 `note`는 `"note" in result`로 실패를 가리는 기존 호출자(scripts/check_sources.py)용이다.
"""

import logging
from typing import Any

from core.errors import (
    AuthenticationError,
    DataQualityError,
    DataSourceUnavailableError,
    RateLimitError,
)
from data.base_client import BaseAPIClient
from data.cache_ttl import FX_RATE_HOURS, GLOBAL_QUOTE_HOURS
from utils.agent_helpers import format_error_message_korean
from utils.redaction import redact
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)

# (결과 키, 심볼, 표시 이름). 지수 자체가 아니라 지수 추종 ETF 시세다.
INDEX_ETFS = (
    ("sp500", "SPY", "S&P 500 추종 ETF(SPY)"),
    ("nasdaq", "QQQ", "NASDAQ-100 추종 ETF(QQQ)"),
    ("dow", "DIA", "다우존스 추종 ETF(DIA)"),
)

NO_KEY_REASON = "Alpha Vantage API 키(ALPHA_VANTAGE_API_KEY)가 설정되지 않았습니다."


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _raise_for_soft_error(data: Any, what: str) -> None:
    """HTTP 200으로 오는 Alpha Vantage 에러 본문을 도메인 예외로 바꾼다.

    호출 한도 초과는 `Note`(구) 또는 `Information`(현행) 키로 온다.
    """
    if not isinstance(data, dict):
        raise DataQualityError(
            f"{what}: unexpected payload type {type(data).__name__}", source="alpha_vantage"
        )
    if "Note" in data or "Information" in data:
        raise RateLimitError(f"{what}: Alpha Vantage quota reply", source="alpha_vantage", status_code=200)
    if "Error Message" in data:
        raise DataQualityError(f"{what}: {data['Error Message']}", source="alpha_vantage")


def _unavailable_reason(error: Exception) -> str:
    """도구 출력·LLM 프롬프트에 실리는 사유. 예외 문자열은 URL(키 포함)을 담을 수 있어 가린다."""
    if isinstance(error, RateLimitError):
        return "Alpha Vantage 호출 한도 초과(무료 25회/일) 또는 이용 제한 응답 — 잠시 후 다시 시도하세요."
    if isinstance(error, AuthenticationError):
        return "Alpha Vantage가 API 키를 거부했습니다."
    if isinstance(error, DataSourceUnavailableError):
        return "Alpha Vantage 서버에 연결하지 못했습니다."
    if isinstance(error, DataQualityError):
        return redact(f"Alpha Vantage 응답에 사용할 값이 없습니다: {error}")
    return redact(format_error_message_korean(error, "Alpha Vantage 조회"))


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
        글로벌 주요 지수 추종 ETF 현황 조회 (SPY, QQQ, DIA)

        시세는 종목별 키로 캐시한다. 한 종목이 실패해도 받은 종목은 다음 실행에서
        캐시로 재사용하고 실패한 종목만 다시 요청한다(무료 한도 25회/일). 실패는
        캐시하지 않는다. 한도 초과 응답을 받으면 남은 종목은 요청하지 않는다.

        Returns:
            {
                "sp500": {"symbol": "SPY", "price": 450.12, "change_percent": 0.5, "available": True, ...},
                "nasdaq": {"symbol": "QQQ", "price": None, "change_percent": None,
                           "available": False, "reason": "..."},
                "dow": {...},
                "available": True,  # 하나라도 받았으면 True
                "timestamp": "2025-11-17T10:30:00+09:00"  # 받은 시세 중 가장 오래된 조회 시각
            }
        """
        result: dict[str, Any] = {}
        skip_reason = None if self.api_key else NO_KEY_REASON
        for key, symbol, _label in INDEX_ETFS:
            cached = self._cached_quote(symbol)
            if cached is not None:
                result[key] = cached
            elif skip_reason is not None:
                result[key] = self._unavailable_quote(symbol, skip_reason)
            else:
                result[key], error = self._request_quote(symbol)
                if isinstance(error, RateLimitError):
                    skip_reason = (
                        f"{_unavailable_reason(error)} (앞선 요청이 한도 초과 응답을 받아 요청하지 않음)"
                    )

        result["available"] = any(result[key]["available"] for key, _s, _l in INDEX_ETFS)
        # Quotes may come from cache; report when the oldest one was actually fetched.
        fetched = [result[key].get("fetched_at") for key, _s, _l in INDEX_ETFS if result[key]["available"]]
        result["timestamp"] = min((f for f in fetched if f), default=kst_isoformat())
        if not result["available"]:
            result["reason"] = result[INDEX_ETFS[0][0]].get("reason", "")
            result["note"] = f"⚠️ {result['reason']}"
        return result

    def _get_quote(self, symbol: str) -> dict[str, Any]:
        """
        개별 종목 시세 조회. 실패해도 raise하지 않고 unavailable 항목을 돌려준다.

        Returns:
            {"symbol": "SPY", "price": 450.12, "change_percent": 0.5, "available": True, ...}
            또는 {"symbol": "SPY", "price": None, "change_percent": None, "available": False, "reason": str}
        """
        quote, _error = self._request_quote(symbol)
        return quote

    def _request_quote(self, symbol: str) -> tuple[dict[str, Any], Exception | None]:
        """GLOBAL_QUOTE 한 건을 요청해 성공하면 종목별 캐시에 쓴다. 실패는 (unavailable 항목, 예외)."""
        try:
            quote = self._fetch_quote(symbol)
        except Exception as e:
            logger.warning(f"Quote 조회 실패 ({symbol}): {redact(str(e))}")
            return self._unavailable_quote(symbol, _unavailable_reason(e)), e
        self.save_cache(self._quote_cache_key(symbol), quote)
        return quote, None

    def _cached_quote(self, symbol: str) -> dict[str, Any] | None:
        cached = self.get_cached(self._quote_cache_key(symbol), max_age_hours=GLOBAL_QUOTE_HOURS)
        return cached if self._is_usable_quote(cached) else None

    @staticmethod
    def _quote_cache_key(symbol: str) -> str:
        return f"global_quote_{symbol}"

    def _fetch_quote(self, symbol: str) -> dict[str, Any]:
        """GLOBAL_QUOTE 한 건. 한도 초과·스키마 불일치·HTTP 실패는 TusimError로 raise."""
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.api_key}
        data = self.request_json("GET", self.base_url, params=params)
        _raise_for_soft_error(data, f"GLOBAL_QUOTE {symbol}")

        quote = data.get("Global Quote")
        if not isinstance(quote, dict) or not quote:
            raise DataQualityError(
                f"GLOBAL_QUOTE {symbol}: 'Global Quote' missing or empty", source="alpha_vantage"
            )

        price = _to_float(quote.get("05. price"))
        if price is None or price <= 0:
            raise DataQualityError(f"GLOBAL_QUOTE {symbol}: no usable price", source="alpha_vantage")

        return {
            "symbol": symbol,
            "price": price,
            "change_percent": _to_float(quote.get("10. change percent")),
            "volume": _to_int(quote.get("06. volume")),
            "latest_trading_day": quote.get("07. latest trading day") or None,
            "available": True,
            "fetched_at": kst_isoformat(),
        }

    def get_exchange_rate(self, from_currency: str = "USD", to_currency: str = "KRW") -> dict[str, Any]:
        """
        환율 조회

        Args:
            from_currency: 기준 통화 (default: USD)
            to_currency: 대상 통화 (default: KRW)

        Returns:
            {"from": "USD", "to": "KRW", "rate": 1320.50, "bid": ..., "ask": ...,
             "available": True, "timestamp": "..."}
            실패 시 rate=None, available=False, reason=str
        """
        cache_key = f"exchange_rate_{from_currency}_{to_currency}"
        cached = self.get_cached(cache_key, max_age_hours=FX_RATE_HOURS)
        if isinstance(cached, dict) and cached.get("available") is True and cached.get("rate"):
            return cached

        if not self.api_key:
            return self._unavailable_exchange_rate(from_currency, to_currency, NO_KEY_REASON)

        try:
            result = self._fetch_exchange_rate(from_currency, to_currency)
        except Exception as e:
            logger.warning(f"환율 조회 실패 ({from_currency}/{to_currency}): {redact(str(e))}")
            return self._unavailable_exchange_rate(from_currency, to_currency, _unavailable_reason(e))

        self.save_cache(cache_key, result)
        return result

    def _fetch_exchange_rate(self, from_currency: str, to_currency: str) -> dict[str, Any]:
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "apikey": self.api_key,
        }
        what = f"CURRENCY_EXCHANGE_RATE {from_currency}/{to_currency}"
        data = self.request_json("GET", self.base_url, params=params)
        _raise_for_soft_error(data, what)

        rate_data = data.get("Realtime Currency Exchange Rate")
        if not isinstance(rate_data, dict) or not rate_data:
            raise DataQualityError(f"{what}: payload missing", source="alpha_vantage")

        rate = _to_float(rate_data.get("5. Exchange Rate"))
        if rate is None or rate <= 0:
            raise DataQualityError(f"{what}: no usable rate", source="alpha_vantage")

        return {
            "from": from_currency,
            "to": to_currency,
            "rate": rate,
            "timestamp": rate_data.get("6. Last Refreshed") or kst_isoformat(),
            "bid": _to_float(rate_data.get("8. Bid Price")),
            "ask": _to_float(rate_data.get("9. Ask Price")),
            "available": True,
        }

    @staticmethod
    def _is_usable_quote(data: Any) -> bool:
        """실제 가격을 가진 성공 시세인지. 형식이 다르거나 가격이 0인 캐시는 거른다."""
        if not isinstance(data, dict) or data.get("available") is not True:
            return False
        price = data.get("price")
        return isinstance(price, int | float) and not isinstance(price, bool) and price > 0

    @staticmethod
    def _unavailable_quote(symbol: str, reason: str) -> dict[str, Any]:
        return {"symbol": symbol, "price": None, "change_percent": None, "available": False, "reason": reason}

    @staticmethod
    def _unavailable_exchange_rate(from_currency: str, to_currency: str, reason: str) -> dict[str, Any]:
        return {
            "from": from_currency,
            "to": to_currency,
            "rate": None,
            "bid": None,
            "ask": None,
            "available": False,
            "reason": reason,
            "note": f"⚠️ {reason}",
            "timestamp": kst_isoformat(),
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
