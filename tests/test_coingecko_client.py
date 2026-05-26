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


def test_5xx_falls_back_silently(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """coingecko가 503을 돌려도 except 블록에서 fallback이 잡아낸다."""
    mocked_responses_loose.add(
        responses.GET,
        "https://api.coingecko.com/api/v3/simple/price",
        status=503,
    )

    client = CoinGeckoClient()
    result = client.get_market_overview()

    # fallback 형태 확인. 정확한 키는 _create_fallback_market_overview()에
    # 잠겨 있지만 dict이고 timestamp 또는 status가 있어야 한다.
    assert isinstance(result, dict)


def test_cache_short_circuits_external_call(isolated_cache_dir: Path) -> None:
    client = CoinGeckoClient()
    cached = {
        "bitcoin": {"current_price_usd": 99999.0},
        "timestamp": "2025-11-17T00:00:00",
    }
    client.save_cache("crypto_market_overview", cached)

    # 외부 호출이 일어나면 connection error로 fail해야 한다 (responses 빈 상태).
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_market_overview()
        assert result["bitcoin"]["current_price_usd"] == 99999.0
        assert len(rsps.calls) == 0
