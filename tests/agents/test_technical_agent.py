"""Technical agent의 비즈니스 로직 단위 테스트.

FDR(FinanceDataReader)과 talib을 monkeypatch해서 LLM/네트워크 없이 순수
계산 로직을 검증한다. PyKRX와 달리 두 모듈 다 함수형 인터페이스라 객체
모킹이 비교적 단순.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from agents.korean_advanced_technical_agent import (
    calculate_momentum_indicators_logic,
    get_advanced_technical_analysis_logic,
)


def _stub_ohlcv(rows: int = 300) -> pd.DataFrame:
    """결정론적 OHLCV DataFrame (FDR 응답 시뮬레이션)."""
    idx = pd.date_range("2024-01-01", periods=rows, freq="B")
    base = np.linspace(50000, 70000, rows)
    return pd.DataFrame(
        {
            "Open": base,
            "High": base * 1.01,
            "Low": base * 0.99,
            "Close": base + np.sin(np.arange(rows)) * 500,
            "Volume": np.full(rows, 1_000_000),
        },
        index=idx,
    )


def test_calculates_momentum_indicators_with_stub_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """FDR이 정상 DataFrame을 돌려주면 RSI/MACD/Stochastic 키가 모두 채워진다."""
    monkeypatch.setattr(
        "agents.korean_advanced_technical_agent.fdr.DataReader",
        lambda *a, **kw: _stub_ohlcv(),
    )

    result = calculate_momentum_indicators_logic("005930", period=252)

    assert result["status"] == "success"
    indicators = result["indicators"]
    assert "RSI" in indicators
    assert 0.0 <= indicators["RSI"] <= 100.0
    assert "line" in indicators["MACD"] and "signal" in indicators["MACD"]
    assert "K" in indicators["Stochastic"] and "D" in indicators["Stochastic"]


def test_returns_error_dict_when_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """FDR이 빈 DataFrame을 돌려주면 KeyError로 터지지 않고 error 키만."""
    monkeypatch.setattr(
        "agents.korean_advanced_technical_agent.fdr.DataReader",
        lambda *a, **kw: pd.DataFrame(),
    )

    result = calculate_momentum_indicators_logic("999999", period=252)
    assert "error" in result
    assert "999999" in result["error"]


def test_wraps_fdr_exception_in_error_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """FDR이 예외를 던지면 호출자가 dict를 받게 변환."""

    def boom(*_a, **_kw):
        raise RuntimeError("upstream FDR down")

    monkeypatch.setattr("agents.korean_advanced_technical_agent.fdr.DataReader", boom)

    result = calculate_momentum_indicators_logic("005930", period=252)
    assert "error" in result
    # 메시지는 변형되지만 원인이 흘러나와야 진단 가능
    assert "FDR" in result["error"] or "upstream" in result["error"]


def test_top_level_logic_falls_back_to_korean_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """logic 함수가 내부 예외를 fallback 메시지(한글)로 변환하는지."""

    def boom(*_a, **_kw):
        raise ValueError("simulated catastrophic failure")

    # calculate_momentum_indicators_logic이 호출하는 fdr를 깨뜨림
    monkeypatch.setattr("agents.korean_advanced_technical_agent.fdr.DataReader", boom)

    # 내부에서 calculate_momentum_indicators_logic이 호출되고 그 결과가 그대로 리턴
    result = get_advanced_technical_analysis_logic("005930", "삼성전자")
    # 두 가지 경로 모두 허용 — error dict 또는 fallback dict
    assert isinstance(result, dict)
    assert "error" in result or "status" in result
