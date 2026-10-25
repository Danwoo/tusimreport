"""Comparative agent의 비즈니스 로직 단위 테스트.

PyKRX·FinanceDataReader 함수들을 monkeypatch해서 외부 호출 없이 동작 검증.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

import agents.korean_comparative_agent as comp
from agents.korean_comparative_agent import INDUSTRY_MAPPING, get_comparative_analysis_logic

BUSINESS_DAY = "20251024"


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


def _stub_listing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Code": ["005930", "000660", "068270", "999999"],
            "Marcap": [400_000_000_000_000, 150_000_000_000_000, 40_000_000_000_000, 50_000_000_000],
        }
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """PyKRX 영업일 조회·FDR 상장 목록은 기본으로 막는다. 테스트가 필요하면 덮어쓴다."""
    calls: dict[str, Any] = {}

    def fundamental(*args: Any, **kwargs: Any) -> pd.DataFrame:
        calls["fundamental"] = (args, kwargs)
        return _stub_fundamental_df()

    monkeypatch.setattr(comp.stock, "get_nearest_business_day_in_a_week", lambda *_a, **_kw: BUSINESS_DAY)
    monkeypatch.setattr(comp.stock, "get_market_fundamental", fundamental)
    monkeypatch.setattr(comp.stock, "get_market_cap", lambda *_a, **_kw: pd.DataFrame())
    monkeypatch.setattr(
        comp.stock,
        "get_market_ticker_name",
        lambda code: {"005930": "삼성전자", "000660": "SK하이닉스"}.get(code, code),
    )
    monkeypatch.setattr("FinanceDataReader.StockListing", lambda *_a, **_kw: _stub_listing())
    return calls


def test_industry_mapping_sectors() -> None:
    assert INDUSTRY_MAPPING["068270"] == "의료용 물질 및 의약품"  # 셀트리온
    assert INDUSTRY_MAPPING["373220"] == "전기장비"  # LG에너지솔루션
    assert INDUSTRY_MAPPING["000270"] == "자동차 및 트레일러"  # 기아
    assert INDUSTRY_MAPPING["024110"] == "금융업"  # 기업은행


def test_returns_sector_analysis_when_peers_present(no_network: dict[str, Any]) -> None:
    result = get_comparative_analysis_logic("005930", "삼성전자")

    assert result["status"] == "success", result
    sa = result["analysis_summary"]["sector_analysis"]
    assert sa["available"] is True
    assert sa["peer_count"] == 2
    assert "전자부품" in sa["sector_name"]
    assert sa["target_metrics"]["PER"] == 12.5
    assert sa["peer_averages"]["PER"] == pytest.approx((12.5 + 18.3) / 2)
    assert result["analysis_summary"]["key_competitors"]["000660"]["name"] == "SK하이닉스"


def test_fundamentals_requested_for_all_markets_on_latest_business_day(no_network: dict[str, Any]) -> None:
    result = get_comparative_analysis_logic("005930", "삼성전자")

    args, kwargs = no_network["fundamental"]
    assert args == (BUSINESS_DAY,)
    assert kwargs == {"market": "ALL"}
    assert result["analysis_date"] == BUSINESS_DAY


def test_latest_business_day_falls_back_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> str:
        raise IndexError("KRX index data empty")

    monkeypatch.setattr(comp.stock, "get_nearest_business_day_in_a_week", boom)
    monkeypatch.setattr(comp, "kst_today_compact", lambda: "20251025")
    assert comp._latest_business_day() == "20251025"


def test_code_missing_from_fundamentals_has_no_unbound_local(no_network: dict[str, Any]) -> None:
    """get_market_fundamental 결과에 없는 종목(매핑에도 없음)도 크래시 없이 처리된다."""
    result = get_comparative_analysis_logic("999999", "Unknown")

    assert result["status"] == "success", result
    summary = result["analysis_summary"]
    assert summary["sector_analysis"]["available"] is False
    assert "999999" in summary["sector_analysis"]["reason"]
    assert summary["market_position"]["available"] is True
    assert summary["market_position"]["rank"] == 4
    assert any("업종 미분류" in line for line in result["key_insights"])


def test_mapped_code_missing_from_fundamentals_keeps_peers(no_network: dict[str, Any]) -> None:
    """매핑에는 있지만 그날 지표에 없는 종목(예: KOSDAQ만 빠진 응답)."""
    result = get_comparative_analysis_logic("068270", "셀트리온")

    assert result["status"] == "success", result
    assert result["analysis_summary"]["sector_analysis"]["available"] is False
    assert any("의료용 물질 및 의약품" in line for line in result["key_insights"])


def test_zero_per_is_missing_not_averaged(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _stub_fundamental_df()
    df.loc["000660", "PER"] = 0.0
    monkeypatch.setattr(comp.stock, "get_market_fundamental", lambda *_a, **_kw: df)

    sa = get_comparative_analysis_logic("005930", "삼성전자")["analysis_summary"]["sector_analysis"]
    assert sa["peer_averages"]["PER"] == 12.5
    assert sa["peer_averages"]["PBR"] == pytest.approx((1.3 + 1.8) / 2)


def test_missing_market_cap_is_unavailable_not_rank_999(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
        raise ConnectionError("KRX listing down")

    monkeypatch.setattr("FinanceDataReader.StockListing", boom)

    result = get_comparative_analysis_logic("005930", "삼성전자")
    position = result["analysis_summary"]["market_position"]
    assert position["available"] is False
    assert "999" not in str(result)
    assert any("데이터 없음" in line for line in result["key_insights"])


def test_pykrx_failure_wrapped_in_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """PyKRX·FDR 모두 실패하면 korean fallback message로 변환."""

    def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
        raise RuntimeError("KRX timeout")

    monkeypatch.setattr(comp.stock, "get_market_fundamental", boom)
    monkeypatch.setattr(comp.stock, "get_market_cap", boom)
    monkeypatch.setattr("FinanceDataReader.StockListing", boom)

    result = get_comparative_analysis_logic("005930", "삼성전자")
    assert result["status"] == "limited"
    assert "KRX timeout" in result["error"]
