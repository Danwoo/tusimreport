"""Financial ReAct agent의 데이터 수집 도구 단위 테스트.

@tool 데코레이터가 붙은 함수는 .invoke({"stock_code": ...}) 형태로 호출.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from agents.korean_financial_react_agent import (
    get_korean_stock_data,
    get_pykrx_market_data,
)


def _stub_fdr_ohlcv(rows: int = 80) -> pd.DataFrame:
    idx = pd.date_range("2024-09-01", periods=rows, freq="B")
    base = np.linspace(60000, 65000, rows)
    return pd.DataFrame(
        {
            "Open": base,
            "High": base * 1.01,
            "Low": base * 0.99,
            "Close": base + 100,
            "Volume": np.full(rows, 2_000_000),
        },
        index=idx,
    )


class TestGetKoreanStockData:
    def test_parses_fdr_dataframe_into_summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.fdr.DataReader",
            lambda *a, **kw: _stub_fdr_ohlcv(),
        )

        result = get_korean_stock_data.invoke({"stock_code": "005930"})

        assert "stock_info" in result
        info = result["stock_info"]
        assert info["code"] == "005930"
        assert info["current_price"] > 0
        # change/change_percent는 stub에서 monotonic이라 양수
        assert info["change_percent"] != 0 or info["change"] != 0
        assert "technical_indicators" in result
        ti = result["technical_indicators"]
        assert ti["sma_20"] > 0 and ti["sma_60"] > 0
        # ISO 타임스탬프 (+09:00 KST offset)
        assert "+09:00" in result["last_updated"]

    def test_empty_fdr_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.fdr.DataReader",
            lambda *a, **kw: pd.DataFrame(),
        )
        result = get_korean_stock_data.invoke({"stock_code": "999999"})
        assert "error" in result

    def test_fdr_exception_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise RuntimeError("FDR offline")

        monkeypatch.setattr("agents.korean_financial_react_agent.fdr.DataReader", boom)
        result = get_korean_stock_data.invoke({"stock_code": "005930"})
        assert "error" in result


class TestGetPykrxMarketData:
    def test_parses_fundamental_dataframe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # PyKRX는 한국어 컬럼명. 회귀 검증을 위해 의도적으로 한국어 사용.
        fundamental = pd.DataFrame(
            {
                "시가총액": [400_000_000_000_000],
                "PER": [12.5],
                "PBR": [1.3],
                "EPS": [5000],
                "BPS": [58000],
            },
            index=pd.date_range("2024-09-23", periods=1, freq="B"),
        )

        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_list",
            lambda *a, **kw: ["005930"],
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_name",
            lambda code: "삼성전자",
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_fundamental",
            lambda *a, **kw: fundamental,
        )

        result = get_pykrx_market_data.invoke({"stock_code": "005930"})

        assert result["company_info"]["name"] == "삼성전자"
        fd = result["fundamental_data"]
        assert fd["per"] == 12.5
        assert fd["pbr"] == 1.3
        assert fd["market_cap"] == 400_000_000_000_000

    def test_zero_per_pbr_normalized_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PyKRX는 데이터 없을 때 0을 돌려준다. 우리는 None으로 정규화."""
        fundamental = pd.DataFrame(
            {
                "시가총액": [1_000_000_000_000],
                "PER": [0],  # 0은 None으로 변환돼야
                "PBR": [0],
                "EPS": [100],
                "BPS": [1000],
            },
            index=pd.date_range("2024-09-23", periods=1, freq="B"),
        )

        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_list",
            lambda *a, **kw: ["005930"],
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_name",
            lambda code: "삼성전자",
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_fundamental",
            lambda *a, **kw: fundamental,
        )

        result = get_pykrx_market_data.invoke({"stock_code": "005930"})
        assert result["fundamental_data"]["per"] is None
        assert result["fundamental_data"]["pbr"] is None
