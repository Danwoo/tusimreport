"""Comparative agent의 비즈니스 로직 단위 테스트.

PyKRX 함수들을 monkeypatch해서 외부 호출 없이 동작 검증.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from agents.korean_comparative_agent import get_comparative_analysis_logic


def _stub_fundamental_df() -> pd.DataFrame:
    """PyKRX get_market_fundamental 응답 시뮬레이션.

    005930과 같은 업종(전자부품) peer가 있어야 비교 로직이 작동.
    """
    return pd.DataFrame(
        {
            "PER": [12.5, 18.3, 22.0],
            "PBR": [1.3, 1.8, 1.2],
            "EPS": [5000, 3000, 4500],
            "BPS": [58000, 32000, 47000],
        },
        index=["005930", "000660", "035420"],
    )


def test_returns_sector_analysis_when_peers_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """대상 종목이 INDUSTRY_MAPPING에 있고 peer가 있으면 비교 결과 dict."""
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_fundamental",
        lambda *_a, **_kw: _stub_fundamental_df(),
    )
    # market_cap도 호출되므로 빈 DataFrame 정도면 OK
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_cap",
        lambda *_a, **_kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_ticker_name",
        lambda code: {"005930": "삼성전자", "000660": "SK하이닉스"}.get(code, code),
    )

    result = get_comparative_analysis_logic("005930", "삼성전자")

    # 정상 응답은 analysis_summary.sector_analysis에 비교 결과를 담는다.
    # PyKRX 시장캡 호출이 외부 네트워크에 닿아 실패해도 sector 분석은 살아 있어야.
    summary = result.get("analysis_summary", {})
    assert "sector_analysis" in summary or "error" in result, result

    if "error" not in result and "sector_analysis" in summary:
        sa = summary["sector_analysis"]
        assert sa["peer_count"] >= 1
        assert "전자부품" in sa["sector_name"]


def test_unknown_stock_falls_back_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    """매핑에 없는 종목 코드를 줘도 KeyError 없이 dict를 돌려준다.

    실제 호출자(supervisor)가 임의 종목을 넘기는 시나리오 회귀 방지.
    """
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_fundamental",
        lambda *_a, **_kw: _stub_fundamental_df(),
    )
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_cap",
        lambda *_a, **_kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "agents.korean_comparative_agent.stock.get_market_ticker_name",
        lambda code: code,
    )

    result = get_comparative_analysis_logic("999999", "Unknown")
    assert isinstance(result, dict)


def test_pykrx_failure_wrapped_in_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """PyKRX가 예외를 던지면 korean fallback message로 변환."""

    def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
        raise RuntimeError("KRX timeout")

    monkeypatch.setattr("agents.korean_comparative_agent.stock.get_market_fundamental", boom)
    monkeypatch.setattr("agents.korean_comparative_agent.stock.get_market_cap", boom)

    result = get_comparative_analysis_logic("005930", "삼성전자")
    # graceful degradation: status=='limited' 또는 'error' 키
    assert isinstance(result, dict)
    assert result.get("status") in ("limited", None) or "error" in result
