"""Global market agent: 받지 못한 데이터가 숫자로 둔갑하지 않는지 검증.

Alpha Vantage / CoinGecko 클라이언트 메서드를 monkeypatch하거나 responses로 막아
외부 호출 없이 돈다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import responses

import agents.korean_global_market_agent as gm
from data.alpha_vantage_client import AlphaVantageClient
from data.coingecko_client import CoinGeckoClient


def _coingecko_down(self: CoinGeckoClient) -> dict[str, Any]:
    return self._unavailable("CoinGecko 연결 실패: ConnectionError: boom")


def _coingecko_up(_self: CoinGeckoClient) -> dict[str, Any]:
    return {
        "bitcoin": {
            "symbol": "BTC",
            "current_price_usd": 65000.0,
            "current_price_krw": 85800000.0,
            "price_change_24h": 2.5,
            "market_cap_usd": 1.3e12,
            "total_volume_usd": 2.8e10,
        },
        "ethereum": {
            "symbol": "ETH",
            "current_price_usd": 2500.0,
            "current_price_krw": None,
            "price_change_24h": None,
            "market_cap_usd": None,
            "total_volume_usd": None,
        },
        "global": {"bitcoin_dominance": 45.2, "eth_dominance": 18.5},
        "available": True,
        "timestamp": "2025-11-17T10:30:00+09:00",
    }


@pytest.fixture
def everything_unavailable(
    monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path, mocked_responses_loose: responses.RequestsMock
) -> None:
    """키 없음(Alpha Vantage) + CoinGecko 실패."""
    from config.settings import settings

    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(CoinGeckoClient, "get_market_overview", _coingecko_down)


@pytest.fixture
def everything_available(monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path) -> None:
    monkeypatch.setattr(
        AlphaVantageClient,
        "get_global_market_overview",
        lambda _self: {
            "sp500": {"symbol": "SPY", "price": 450.12, "change_percent": 0.5, "available": True},
            "nasdaq": {
                "symbol": "QQQ",
                "price": None,
                "change_percent": None,
                "available": False,
                "reason": "한도 초과",
            },
            "dow": {"symbol": "DIA", "price": 350.23, "change_percent": -0.3, "available": True},
            "available": True,
            "timestamp": "2025-11-17T10:30:00+09:00",
        },
    )
    monkeypatch.setattr(
        AlphaVantageClient,
        "get_exchange_rate",
        lambda _self, *_a: {"rate": 1385.25, "bid": None, "ask": None, "available": True, "timestamp": "t"},
    )
    monkeypatch.setattr(CoinGeckoClient, "get_market_overview", _coingecko_up)


def test_tool_argument_schema_is_unchanged() -> None:
    assert set(gm.analyze_global_market_context.args) == {"company_name", "stock_code"}


def test_unavailable_sources_carry_none_not_defaults(everything_unavailable: None) -> None:
    markets = gm._fetch_global_markets()
    crypto = gm._fetch_crypto_markets()
    forex = gm._fetch_forex_data()

    assert markets["available"] is False
    assert markets["sp500"]["price"] is None
    assert markets["reason"]

    assert crypto["available"] is False
    assert crypto["bitcoin"] == {}
    assert crypto["ethereum"] == {}
    assert crypto["global"] == {}
    assert "CoinGecko 연결 실패" in crypto["reason"]

    assert forex["available"] is False
    assert forex["usd_krw"]["rate"] is None
    assert forex["reason"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "bitcoin": {"current_price_usd": 0.0, "price_change_24h": 0.0},
            "ethereum": {"current_price_usd": 0.0},
            "global": {"bitcoin_dominance": 0.0},
            "available": False,
            "reason": "CoinGecko 응답에 요청한 코인 가격이 없습니다",
        },
        {
            "bitcoin": {"current_price_usd": 65000.0},
            "ethereum": {},
            "global": {"bitcoin_dominance": 45.2},
        },
    ],
    ids=["available_false_without_note", "legacy_shape_without_available"],
)
def test_crypto_availability_comes_from_available_flag_not_note(
    monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path, payload: dict[str, Any]
) -> None:
    """'note'가 없어도 available이 True가 아니면 받지 못한 것이고, 클라이언트가 남긴 값은 버린다."""
    monkeypatch.setattr(CoinGeckoClient, "get_market_overview", lambda _self: payload)

    crypto = gm._fetch_crypto_markets()

    assert crypto["available"] is False
    assert crypto["bitcoin"] == {}
    assert crypto["ethereum"] == {}
    assert crypto["global"] == {}
    assert crypto["reason"]
    text = gm._format_crypto_markets(crypto)
    assert gm.NO_DATA in text
    assert "65" not in text
    assert "0.0" not in text


def test_summary_says_unavailable_instead_of_inventing_numbers(everything_unavailable: None) -> None:
    summary = gm._build_summary(
        gm._fetch_global_markets(), gm._fetch_crypto_markets(), gm._fetch_forex_data()
    )

    assert summary.count(gm.NO_DATA) >= 3
    assert "ALPHA_VANTAGE_API_KEY" in summary
    assert "CoinGecko 연결 실패" in summary
    for invented in ("1,320", "1320", "0.00", "$", "None"):
        assert invented not in summary, invented


def test_tool_returns_data_only_without_calling_an_llm(
    everything_unavailable: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(gm, "build_llm", lambda **kw: llm_calls.append(kw))

    result = gm.analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})

    assert llm_calls == []
    assert "analysis" not in result
    assert "market_sentiment" not in result
    assert result["status"] == "unavailable"
    assert len(result["unavailable_data"]) == 3
    assert any(
        "Alpha Vantage" in line and "ALPHA_VANTAGE_API_KEY" in line for line in result["unavailable_data"]
    )
    assert any("CoinGecko" in line for line in result["unavailable_data"])
    assert result["forex"]["usd_krw"]["rate"] is None
    assert result["crypto_markets"]["bitcoin"] == {}
    assert gm.NO_DATA in result["summary"]


def test_available_data_is_formatted_with_real_values(everything_available: None) -> None:
    markets_text = gm._format_global_markets(gm._fetch_global_markets())
    assert "S&P 500 추종 ETF(SPY): $450.12 (+0.50%)" in markets_text
    assert "NASDAQ-100 추종 ETF(QQQ): 데이터 없음 (한도 초과)" in markets_text
    assert "(-0.30%)" in markets_text

    assert "USD/KRW: 1,385.25원" in gm._format_forex(gm._fetch_forex_data())

    crypto_text = gm._format_crypto_markets(gm._fetch_crypto_markets())
    assert "- Bitcoin: $65,000.00 (24시간 +2.50%)" in crypto_text
    assert "- BTC 도미넌스: 45.2%" in crypto_text


def test_crypto_change_is_shown_only_when_it_is_a_number(everything_available: None) -> None:
    """가격은 있는데 24시간 변동률이 None이면 가격만 쓰고, 변동률 자리를 지어내지 않는다."""
    lines = gm._format_crypto_markets(gm._fetch_crypto_markets()).splitlines()

    ethereum = next(line for line in lines if line.startswith("- Ethereum"))
    assert ethereum == "- Ethereum: $2,500.00"


def test_crypto_coin_without_price_is_no_data() -> None:
    text = gm._format_crypto_markets(
        {
            "bitcoin": {"current_price_usd": None, "price_change_24h": 2.5},
            "ethereum": {"current_price_usd": 2500.0, "price_change_24h": "n/a"},
            "global": {"bitcoin_dominance": None},
            "available": True,
        }
    )

    assert f"- Bitcoin: {gm.NO_DATA}" in text
    assert "2.50" not in text
    assert "- Ethereum: $2,500.00\n" in text
    assert f"- BTC 도미넌스: {gm.NO_DATA}" in text
    assert "None" not in text


def test_tool_summary_carries_the_collected_numbers(everything_available: None) -> None:
    result = gm.analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})

    assert result["status"] == "success"
    assert result["unavailable_data"] == []
    summary = result["summary"]
    assert "S&P 500 추종 ETF(SPY): $450.12 (+0.50%)" in summary
    assert "NASDAQ-100 추종 ETF(QQQ): 데이터 없음 (한도 초과)" in summary
    assert "- Bitcoin: $65,000.00 (24시간 +2.50%)" in summary
    assert "USD/KRW: 1,385.25원" in summary


def test_fallback_analysis_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict[str, Any]:
        raise RuntimeError("failed calling https://example.test/query?apikey=TOPSECRET99")

    monkeypatch.setattr(gm, "_fetch_global_markets", boom)

    result = gm.analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})
    assert "TOPSECRET99" not in str(result)
    assert result["global_markets"] == {"available": False}
    assert "analysis" not in result
    assert gm.NO_DATA in result["summary"]
    assert len(result["unavailable_data"]) == 3
