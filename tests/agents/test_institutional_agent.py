"""Institutional trading agent: PyKRX 투자자별 매매 동향 단위 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from agents.korean_institutional_trading_agent import get_investor_trading_analysis_logic


def _stub_trading_value() -> pd.DataFrame:
    """PyKRX get_market_trading_value_by_investor 응답 모양.

    index가 투자자 구분 (외국인/기관합계/개인 등), 컬럼은 매수/매도/순매수.
    """
    return pd.DataFrame(
        {
            "매도": [1_000_000_000_000, 2_000_000_000_000, 3_000_000_000_000],
            "매수": [1_500_000_000_000, 1_800_000_000_000, 3_200_000_000_000],
            "순매수": [500_000_000_000, -200_000_000_000, 200_000_000_000],
        },
        index=["외국인", "기관합계", "개인"],
    )


def test_aggregates_investor_net_purchase_in_billions(monkeypatch: pytest.MonkeyPatch) -> None:
    """3개 투자자 모두 billion 단위로 정규화."""
    monkeypatch.setattr(
        "agents.korean_institutional_trading_agent.stock.get_market_trading_value_by_investor",
        lambda *_a, **_kw: _stub_trading_value(),
    )

    result = get_investor_trading_analysis_logic("005930", "삼성전자", period_days=20)

    assert result["status"] == "success"
    key = result["analysis_data"]["key_investors"]
    # 5000억 = 500_000_000_000원 → 5000 billion (×1e-8)
    assert key["외국인"]["net_purchase_billion"] == 5000.0
    assert key["기관합계"]["net_purchase_billion"] == -2000.0
    assert key["개인"]["net_purchase_billion"] == 2000.0


def test_empty_pykrx_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.korean_institutional_trading_agent.stock.get_market_trading_value_by_investor",
        lambda *_a, **_kw: pd.DataFrame(),
    )

    result = get_investor_trading_analysis_logic("005930", "삼성전자")
    assert "error" in result
    assert "005930" in result["error"]


def test_pykrx_exception_wrapped_in_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_kw):
        raise RuntimeError("KRX login failed")

    monkeypatch.setattr(
        "agents.korean_institutional_trading_agent.stock.get_market_trading_value_by_investor",
        boom,
    )

    result = get_investor_trading_analysis_logic("005930", "삼성전자")
    assert isinstance(result, dict)
    # graceful — error 키 또는 status='limited'
    assert "error" in result or result.get("status") == "limited"
