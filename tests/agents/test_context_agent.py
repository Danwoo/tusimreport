"""Context agent: 주가 + 지수 + 거시지표 종합 단위 테스트."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.korean_context_agent import get_market_and_economic_context_logic


def _stub_stock_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [70000.0],
            "High": [71000.0],
            "Low": [69500.0],
            "Close": [70500.0],
            "Volume": [1_000_000],
            "Change": [0.01],
        },
        index=pd.date_range("2024-09-23", periods=1, freq="B"),
    )


def _stub_kospi_ohlcv() -> pd.DataFrame:
    # PyKRX index 응답은 한국어 컬럼명 ("종가")
    return pd.DataFrame(
        {"시가": [2500.0], "고가": [2520.0], "저가": [2480.0], "종가": [2510.5], "거래량": [1e9]},
        index=pd.date_range("2024-09-23", periods=1, freq="B"),
    )


def test_assembles_all_three_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.korean_context_agent.fdr.DataReader",
        lambda *a, **kw: _stub_stock_ohlcv(),
    )
    monkeypatch.setattr(
        "agents.korean_context_agent.stock.get_index_ohlcv_by_date",
        lambda *a, **kw: _stub_kospi_ohlcv(),
    )
    monkeypatch.setattr(
        "agents.korean_context_agent.get_macro_economic_indicators",
        lambda: {
            "indicators": {
                "base_interest_rate": {"current_rate": "3.5"},
                "usd_exchange_rate": {"current_rate": "1320"},
            }
        },
    )

    result = get_market_and_economic_context_logic("005930", "삼성전자")

    assert result["status"] == "success"
    cs = result["context_summary"]
    assert cs["stock_price"]["current"] == 70500.0
    assert cs["kospi"]["current"] == 2510.5
    assert cs["macro_economics"]["base_interest_rate"]["current_rate"] == "3.5"
    # 모든 데이터 소스 라벨이 들어 있어야 함
    assert set(result["data_sources"]) == {"FinanceDataReader", "PyKRX", "BOK ECOS API"}


def test_partial_data_still_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """FDR/PyKRX 둘 중 하나만 실패해도 나머지로 status='success' 유지."""
    monkeypatch.setattr(
        "agents.korean_context_agent.fdr.DataReader",
        lambda *a, **kw: pd.DataFrame(),  # 빈 응답
    )
    monkeypatch.setattr(
        "agents.korean_context_agent.stock.get_index_ohlcv_by_date",
        lambda *a, **kw: _stub_kospi_ohlcv(),
    )
    monkeypatch.setattr(
        "agents.korean_context_agent.get_macro_economic_indicators",
        lambda: {"error": "ECOS not configured"},
    )

    result = get_market_and_economic_context_logic("005930", "삼성전자")
    # 빈 FDR이어도 raise하지 않고 진행
    assert result["status"] == "success"
    # macro_economics는 ECOS 실패라 누락
    assert "macro_economics" not in result["context_summary"]
    # KOSPI는 살아 있어야
    assert "kospi" in result["context_summary"]


def test_full_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """try의 가장 바깥 블록이 raise하는 catastrophic 케이스 → korean fallback."""

    # context_data dict 자체를 못 만드는 상황 시뮬레이션
    def boom(*_a, **_kw):
        raise RuntimeError("catastrophic")

    # convert_numpy_types에 넣을 dict 만들기 전부터 실패하도록
    monkeypatch.setattr("agents.korean_context_agent.fdr.DataReader", boom)
    monkeypatch.setattr("agents.korean_context_agent.stock.get_index_ohlcv_by_date", boom)
    monkeypatch.setattr("agents.korean_context_agent.get_macro_economic_indicators", boom)

    result = get_market_and_economic_context_logic("005930", "삼성전자")
    # 모든 inner try가 잡혀서 결국 status='success' + 빈 context_summary로 끝남.
    # graceful degradation 가드 — raise되지 않는 게 핵심.
    assert isinstance(result, dict)
    assert result.get("status") in ("success", "limited", "error")
