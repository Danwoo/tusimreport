"""Global market agent: 받지 못한 데이터가 숫자로 둔갑하지 않는지 검증.

Alpha Vantage / CoinGecko / Fear&Greed 클라이언트 메서드를 monkeypatch하거나
responses로 막아 외부 호출 없이 돈다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import responses

import agents.korean_global_market_agent as gm
from data.alpha_vantage_client import AlphaVantageClient
from data.coingecko_client import CoinGeckoClient
from data.fear_greed_client import FearGreedClient

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _coingecko_down(_self: Any) -> dict[str, Any]:
    return {"bitcoin": {}, "ethereum": {}, "global": {}, "note": "⚠️ CoinGecko API 연결 실패."}


@pytest.fixture
def everything_unavailable(
    monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path, mocked_responses_loose: responses.RequestsMock
) -> None:
    """키 없음(Alpha Vantage) + CNN 503 + CoinGecko 실패."""
    from config.settings import settings

    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(CoinGeckoClient, "get_market_overview", _coingecko_down)
    mocked_responses_loose.add(responses.GET, CNN_URL, json={}, status=503)


def test_unavailable_sources_carry_none_not_defaults(everything_unavailable: None) -> None:
    markets = gm._fetch_global_markets()
    sentiment = gm._fetch_market_sentiment()
    forex = gm._fetch_forex_data()

    assert markets["available"] is False
    assert markets["sp500"]["price"] is None
    assert markets["reason"]

    assert sentiment["available"] is False
    assert sentiment["score"] is None
    assert sentiment["rating"] is None
    assert sentiment["trend"] is None
    assert sentiment["reason"]

    assert forex["available"] is False
    assert forex["usd_krw"]["rate"] is None
    assert forex["reason"]


def test_prompt_says_unavailable_instead_of_inventing_numbers(everything_unavailable: None) -> None:
    prompt = gm._build_analysis_prompt(
        "삼성전자",
        "005930",
        gm._fetch_global_markets(),
        gm._fetch_crypto_markets(),
        gm._fetch_market_sentiment(),
        gm._fetch_forex_data(),
    )

    assert gm.NO_DATA in prompt
    for invented in ("50/100", "중립", "Neutral", "1,320", "1320", "0.00"):
        assert invented not in prompt, invented


def test_tool_output_lists_unavailable_sources(
    everything_unavailable: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gm, "build_llm", lambda **_kw: None)

    result = gm.analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})

    assert result["status"] == "unavailable"
    assert len(result["unavailable_data"]) == 4
    assert any(
        "Alpha Vantage" in line and "ALPHA_VANTAGE_API_KEY" in line for line in result["unavailable_data"]
    )
    assert result["market_sentiment"]["score"] is None
    assert result["forex"]["usd_krw"]["rate"] is None


def test_available_data_is_formatted_with_real_values(
    monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path
) -> None:
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
    monkeypatch.setattr(
        FearGreedClient,
        "get_current_index",
        lambda _self: {
            "score": 32,
            "rating": "Fear",
            "previous_week": 40,
            "previous_month": 55,
            "available": True,
        },
    )

    markets_text = gm._format_global_markets(gm._fetch_global_markets())
    assert "S&P 500 추종 ETF(SPY): $450.12 (+0.50%)" in markets_text
    assert "NASDAQ-100 추종 ETF(QQQ): 데이터 없음 (한도 초과)" in markets_text
    assert "(-0.30%)" in markets_text

    assert "USD/KRW: 1,385.25원" in gm._format_forex(gm._fetch_forex_data())

    sentiment_text = gm._format_market_sentiment(gm._fetch_market_sentiment())
    assert "32/100 (Fear)" in sentiment_text
    assert "worsening" in sentiment_text


def test_fallback_analysis_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict[str, Any]:
        raise RuntimeError("failed calling https://example.test/query?apikey=TOPSECRET99")

    monkeypatch.setattr(gm, "_fetch_global_markets", boom)

    result = gm.analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})
    assert "TOPSECRET99" not in str(result)
    assert result["global_markets"] == {"available": False}
