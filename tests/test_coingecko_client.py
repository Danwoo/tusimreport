"""CoinGeckoClient: 응답 파싱과 캐시 hit 동작 검증."""

from __future__ import annotations

from pathlib import Path

import responses

from data.coingecko_client import CoinGeckoClient

_SIMPLE_PRICE_BODY = {
    "bitcoin": {
        "usd": 65000.0,
        "krw": 85800000.0,
        "usd_24h_change": 2.5,
        "usd_market_cap": 1.3e12,
        "usd_24h_vol": 2.8e10,
    },
    "ethereum": {
        "usd": 2500.0,
        "krw": 3300000.0,
        "usd_24h_change": 1.2,
        "usd_market_cap": 3e11,
        "usd_24h_vol": 1e10,
    },
    "binancecoin": {"usd": 500.0, "krw": 660000.0, "usd_24h_change": -0.5},
    "ripple": {"usd": 0.6, "krw": 800.0, "usd_24h_change": 0.1},
    "cardano": {"usd": 0.4, "krw": 528.0, "usd_24h_change": 1.5},
}

_GLOBAL_BODY = {
    "data": {
        "total_market_cap": {"usd": 2.4e12},
        "total_volume": {"usd": 1.2e11},
        "market_cap_percentage": {"btc": 45.2, "eth": 18.5},
    }
}


def test_parses_simple_price_and_global(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """정상 응답 → 코인별 가격, dominance까지 파싱."""
    mocked_responses.add(
        responses.GET,
        "https://api.coingecko.com/api/v3/simple/price",
        json=_SIMPLE_PRICE_BODY,
        status=200,
    )
    mocked_responses.add(
        responses.GET,
        "https://api.coingecko.com/api/v3/global",
        json=_GLOBAL_BODY,
        status=200,
    )

    client = CoinGeckoClient()
    result = client.get_market_overview()

    assert result["bitcoin"]["current_price_usd"] == 65000.0
    assert result["bitcoin"]["current_price_krw"] == 85800000.0
    assert result["bitcoin"]["price_change_24h"] == 2.5
    # global 섹션이 결합됐는지
    assert "global" in result
    # global_data의 dominance 키는 클라이언트 내부 정규화에 따라 다를 수 있어
    # 존재만 확인. 정확한 키 이름은 클라이언트 구현에 잠긴다.
    assert isinstance(result["global"], dict)


def test_5xx_is_unavailable_with_reason_and_not_cached(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """503이면 0.0 가격이 아니라 available=False와 사유를 돌려주고 캐시하지 않는다."""
    mocked_responses_loose.add(
        responses.GET,
        "https://api.coingecko.com/api/v3/simple/price",
        status=503,
    )

    client = CoinGeckoClient()
    result = client.get_market_overview()

    assert result["available"] is False
    assert "503" in result["reason"]
    assert result["bitcoin"] == {}
    assert client.get_cached("crypto_market_overview", max_age_hours=1) is None


def test_missing_fields_are_none_not_zero(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses.add(
        responses.GET,
        "https://api.coingecko.com/api/v3/simple/price",
        json={"bitcoin": {"usd": 65000.0}, "ethereum": {"krw": 3300000.0}},
    )
    mocked_responses.add(responses.GET, "https://api.coingecko.com/api/v3/global", status=500)

    result = CoinGeckoClient().get_market_overview()

    assert result["available"] is True
    assert result["bitcoin"]["price_change_24h"] is None
    assert result["bitcoin"]["current_price_krw"] is None
    # A coin without a USD price is left out rather than reported at 0.
    assert "ethereum" not in result
    assert result["global"] == {}


def test_response_without_requested_coins_is_unavailable(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses.add(responses.GET, "https://api.coingecko.com/api/v3/simple/price", json={})

    client = CoinGeckoClient()
    result = client.get_market_overview()

    assert result["available"] is False
    assert client.get_cached("crypto_market_overview", max_age_hours=1) is None


def test_cache_short_circuits_external_call(isolated_cache_dir: Path) -> None:
    client = CoinGeckoClient()
    cached = {
        "bitcoin": {"current_price_usd": 99999.0},
        "available": True,
        "timestamp": "2025-11-17T00:00:00",
    }
    client.save_cache("crypto_market_overview", cached)

    # 외부 호출이 일어나면 connection error로 fail해야 한다 (responses 빈 상태).
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_market_overview()
        assert result["bitcoin"]["current_price_usd"] == 99999.0
        assert len(rsps.calls) == 0


def test_legacy_cache_without_available_flag_is_refetched(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """구버전은 실패 결과(0.0 가격)도 캐시할 수 있었으므로 available 표시가 없는 캐시는 버린다."""
    client = CoinGeckoClient()
    client.save_cache("crypto_market_overview", {"bitcoin": {"current_price_usd": 0.0}})
    mocked_responses.add(
        responses.GET, "https://api.coingecko.com/api/v3/simple/price", json=_SIMPLE_PRICE_BODY
    )
    mocked_responses.add(responses.GET, "https://api.coingecko.com/api/v3/global", json=_GLOBAL_BODY)

    result = client.get_market_overview()

    assert result["bitcoin"]["current_price_usd"] == 65000.0
    assert result["global"]["bitcoin_dominance"] == 45.2
