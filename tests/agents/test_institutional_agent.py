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


def test_net_purchase_is_returned_in_won(monkeypatch: pytest.MonkeyPatch) -> None:
    """PyKRX 순매수(원)를 나누지 않고 그대로 돌려준다."""
    monkeypatch.setattr(
        "agents.korean_institutional_trading_agent.stock.get_market_trading_value_by_investor",
        lambda *_a, **_kw: _stub_trading_value(),
    )

    result = get_investor_trading_analysis_logic("005930", "삼성전자", period_days=20)

    assert result["status"] == "success"
    key = result["analysis_data"]["key_investors"]
    assert key["외국인"] == {"net_purchase_won": 500_000_000_000.0}
    assert key["기관합계"] == {"net_purchase_won": -200_000_000_000.0}
    assert key["개인"] == {"net_purchase_won": 200_000_000_000.0}


def test_report_amounts_in_eok_won_match_the_tool_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """보고서의 '5,000억원 순매수', '2,000억원 순매도'가 도구 결과로 확인된다."""
    from lab.grounding import numeric_grounding

    monkeypatch.setattr(
        "agents.korean_institutional_trading_agent.stock.get_market_trading_value_by_investor",
        lambda *_a, **_kw: _stub_trading_value(),
    )
    output = get_investor_trading_analysis_logic("005930", "삼성전자")

    result = numeric_grounding("외국인은 5,000억원 순매수, 기관은 2,000억원 순매도했다.", [output])

    assert (result.checked, result.grounded) == (2, 2)


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
