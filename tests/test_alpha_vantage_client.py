"""AlphaVantageClient: 응답 매핑/캐시/unavailable 단위 테스트.

테스트되는 시나리오:
1. API 키 미설정 → 외부 호출 없이 unavailable (가격 None, 환율 None — 지어낸 값 없음)
2. Global Quote 정상 응답 → 가격/변화율 정확 파싱 + 캐시 저장
3. HTTP 200 한도 초과 응답('Note'/'Information') → unavailable, 캐시에 쓰지 않음
4. 부분 실패 → 받은 것만 available, 캐시에 쓰지 않음
5. 캐시 hit 시 외부 호출 0건, 구버전(0.0 가격) 캐시는 무시
6. base_client 통합 — 429는 RateLimitError로 변환
7. 실패 사유(reason)·로그에 API 키가 실리지 않음
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import requests
import responses

from core.errors import RateLimitError
from data.alpha_vantage_client import AlphaVantageClient

BASE_URL = "https://www.alphavantage.co/query"


def _quote_payload(symbol: str, price: float, change_pct: float) -> dict:
    return {
        "Global Quote": {
            "01. symbol": symbol,
            "05. price": str(price),
            "06. volume": "12345",
            "07. latest trading day": "2025-11-17",
            "10. change percent": f"{change_pct}%",
        }
    }


def _quote_matcher(symbol: str) -> list:
    return [
        responses.matchers.query_param_matcher(
            {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": "FAKEKEY"}
        )
    ]


@pytest.fixture
def no_settings_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """.env에 키가 있어도 '키 없음' 경로를 강제한다."""
    from config.settings import settings

    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)


def test_returns_unavailable_when_api_key_missing(isolated_cache_dir: Path, no_settings_key: None) -> None:
    client = AlphaVantageClient(api_key=None)
    assert not client.api_key

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_global_market_overview()
        assert len(rsps.calls) == 0

    assert result["available"] is False
    assert "ALPHA_VANTAGE_API_KEY" in result["reason"]
    for key in ("sp500", "nasdaq", "dow"):
        assert result[key]["available"] is False
        assert result[key]["price"] is None
        assert result[key]["change_percent"] is None


def test_exchange_rate_unavailable_without_key_has_no_default_rate(
    isolated_cache_dir: Path, no_settings_key: None
) -> None:
    client = AlphaVantageClient(api_key=None)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_exchange_rate("USD", "KRW")
        assert len(rsps.calls) == 0

    assert result["rate"] is None
    assert result["available"] is False
    assert result["reason"]
    assert client.get_cached("exchange_rate_USD_KRW", max_age_hours=1) is None


def test_parses_global_quote_response(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """모든 3개 인덱스 ETF 호출에 정상 응답을 등록하고 파싱 결과를 검증."""
    for sym, price, chg in [("SPY", 450.12, 0.5), ("QQQ", 380.45, 0.8), ("DIA", 350.23, 0.3)]:
        mocked_responses.add(
            responses.GET,
            BASE_URL,
            json=_quote_payload(sym, price, chg),
            status=200,
            match=_quote_matcher(sym),
        )

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_global_market_overview()

    assert result["available"] is True
    assert result["sp500"]["price"] == 450.12
    assert result["sp500"]["change_percent"] == 0.5
    assert result["sp500"]["available"] is True
    assert result["nasdaq"]["price"] == 380.45
    assert result["dow"]["change_percent"] == 0.3
    assert "timestamp" in result
    # 세 건 모두 받은 결과만 캐시된다.
    assert client.get_cached("global_market_overview", max_age_hours=1)["sp500"]["price"] == 450.12


@pytest.mark.parametrize(
    "payload",
    [
        {
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 25 requests per day."
        },
        {
            "Information": "We have detected your API key as FAKEKEY and our standard API rate limit is 25/day."
        },
    ],
    ids=["note", "information"],
)
def test_rate_limit_reply_is_unavailable_and_not_cached(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path, payload: dict
) -> None:
    """HTTP 200 한도 초과 응답은 0.0 가격이 아니라 unavailable이고, 캐시에 남지 않는다."""
    mocked_responses_loose.add(responses.GET, BASE_URL, json=payload, status=200)

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_global_market_overview()

    assert result["available"] is False
    for key in ("sp500", "nasdaq", "dow"):
        assert result[key]["available"] is False
        assert result[key]["price"] is None
        assert "한도" in result[key]["reason"]
    assert client.get_cached("global_market_overview", max_age_hours=1) is None


def test_empty_global_quote_is_unavailable(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses_loose.add(responses.GET, BASE_URL, json={"Global Quote": {}}, status=200)

    quote = AlphaVantageClient(api_key="FAKEKEY")._get_quote("SPY")
    assert quote == {
        "symbol": "SPY",
        "price": None,
        "change_percent": None,
        "available": False,
        "reason": quote["reason"],
    }
    assert quote["reason"]


def test_partial_failure_returns_what_arrived_without_caching(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses.add(
        responses.GET, BASE_URL, json=_quote_payload("SPY", 450.12, 0.5), match=_quote_matcher("SPY")
    )
    mocked_responses.add(responses.GET, BASE_URL, json={"Note": "quota"}, match=_quote_matcher("QQQ"))
    mocked_responses.add(
        responses.GET, BASE_URL, json=_quote_payload("DIA", 350.23, 0.3), match=_quote_matcher("DIA")
    )

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_global_market_overview()

    assert result["available"] is True
    assert result["sp500"]["price"] == 450.12
    assert result["nasdaq"]["available"] is False
    assert result["nasdaq"]["price"] is None
    assert client.get_cached("global_market_overview", max_age_hours=1) is None


def test_cache_prevents_second_call(isolated_cache_dir: Path) -> None:
    """완전한 캐시가 있으면 외부 호출 없이 그대로 돌려준다."""
    client = AlphaVantageClient(api_key="FAKEKEY")

    assert client.cache_dir is not None
    assert client.cache_dir.startswith(str(isolated_cache_dir))

    cached = {
        key: {"symbol": sym, "price": 999.99, "change_percent": 1.0, "available": True}
        for key, sym in (("sp500", "SPY"), ("nasdaq", "QQQ"), ("dow", "DIA"))
    }
    cached["available"] = True
    client.save_cache("global_market_overview", cached)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_global_market_overview()
        assert result["sp500"]["price"] == 999.99
        assert len(rsps.calls) == 0


def test_legacy_zero_price_cache_is_ignored(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """구버전이 한도 초과 응답을 0.0 가격으로 캐시했어도 다시 받아 온다."""
    client = AlphaVantageClient(api_key="FAKEKEY")
    client.save_cache(
        "global_market_overview",
        {
            "sp500": {"symbol": "SPY", "price": 0.0, "change_percent": 0.0},
            "nasdaq": {"symbol": "QQQ", "price": 0.0, "change_percent": 0.0},
            "dow": {"symbol": "DIA", "price": 0.0, "change_percent": 0.0},
        },
    )
    for sym, price in [("SPY", 450.12), ("QQQ", 380.45), ("DIA", 350.23)]:
        mocked_responses.add(
            responses.GET, BASE_URL, json=_quote_payload(sym, price, 0.1), match=_quote_matcher(sym)
        )

    result = client.get_global_market_overview()
    assert result["sp500"]["price"] == 450.12


def test_exchange_rate_parses_and_caches(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses.add(
        responses.GET,
        BASE_URL,
        json={
            "Realtime Currency Exchange Rate": {
                "5. Exchange Rate": "1385.25000000",
                "6. Last Refreshed": "2025-11-17 01:00:00",
                "8. Bid Price": "1385.20",
                "9. Ask Price": "-",
            }
        },
    )

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_exchange_rate("USD", "KRW")

    assert result["rate"] == 1385.25
    assert result["bid"] == 1385.20
    assert result["ask"] is None
    assert result["available"] is True
    assert client.get_cached("exchange_rate_USD_KRW", max_age_hours=1)["rate"] == 1385.25


def test_exchange_rate_quota_reply_is_unavailable_and_not_cached(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses.add(responses.GET, BASE_URL, json={"Information": "rate limit"})

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_exchange_rate("USD", "KRW")

    assert result["rate"] is None
    assert result["available"] is False
    assert client.get_cached("exchange_rate_USD_KRW", max_age_hours=1) is None


def test_connection_error_reason_and_logs_do_not_leak_key(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """requests 예외는 URL(키 포함)을 담는다. 도구 출력과 로그 어디에도 키가 남지 않아야 한다."""
    secret = "SECRETKEY123"
    mocked_responses.add(
        responses.GET,
        BASE_URL,
        body=requests.ConnectionError(
            f"Max retries exceeded with url: /query?function=GLOBAL_QUOTE&symbol=SPY&apikey={secret}"
        ),
    )

    client = AlphaVantageClient(api_key=secret)
    with caplog.at_level(logging.WARNING, logger="data.alpha_vantage_client"):
        quote = client._get_quote("SPY")

    assert quote["available"] is False
    assert secret not in str(quote)
    assert secret not in caplog.text
    assert "apikey=***" in caplog.text


def test_429_propagates_as_rate_limit_error(isolated_cache_dir: Path) -> None:
    """BaseAPIClient.request_json 경로에서 429가 정확히 매핑되는지."""
    client = AlphaVantageClient(api_key="FAKEKEY")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, BASE_URL, json={"Note": "quota"}, status=429)
        with pytest.raises(RateLimitError) as exc_info:
            client.request_json("GET", BASE_URL)
        assert exc_info.value.status_code == 429
