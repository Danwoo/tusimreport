"""Financial ReAct agent의 데이터 수집 도구 단위 테스트.

@tool 데코레이터가 붙은 함수는 .invoke({"stock_code": ...}) 형태로 호출.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from agents.korean_financial_react_agent import (
    get_dart_company_data,
    get_korean_stock_data,
    get_pykrx_market_data,
    save_stock_chart,
)
from core.agent_status import classify_tool_output


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


def _stub_pykrx_fundamental(**overrides: float) -> pd.DataFrame:
    """`stock.get_market_fundamental(from, to, ticker)`의 실제 컬럼: BPS/PER/PBR/EPS/DIV/DPS (시가총액 없음)."""
    row = {"BPS": 58000, "PER": 12.5, "PBR": 1.3, "EPS": 5000, "DIV": 2.1, "DPS": 1444, **overrides}
    return pd.DataFrame(
        {column: [value] for column, value in row.items()},
        index=pd.date_range("2024-09-23", periods=1, freq="B"),
    )


def _stub_pykrx_market_cap(cap: int) -> pd.DataFrame:
    """`stock.get_market_cap(from, to, ticker)`의 실제 컬럼."""
    return pd.DataFrame(
        {
            "시가총액": [cap - 1_000_000, cap],
            "거래량": [10_000_000, 12_000_000],
            "거래대금": [700_000_000_000, 800_000_000_000],
            "상장주식수": [5_969_782_550, 5_969_782_550],
        },
        index=pd.date_range("2024-09-20", periods=2, freq="B"),
    )


class TestGetPykrxMarketData:
    @pytest.fixture(autouse=True)
    def pykrx_stubs(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        """PyKRX 호출을 모두 막는다 — 테스트가 필요한 것만 덮어쓴다."""
        calls: dict[str, Any] = {}

        def market_cap(*args: Any, **kwargs: Any) -> pd.DataFrame:
            calls["market_cap"] = (args, kwargs)
            return pd.DataFrame()

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
            lambda *a, **kw: _stub_pykrx_fundamental(),
        )
        monkeypatch.setattr("agents.korean_financial_react_agent.stock.get_market_cap", market_cap)
        return calls

    def test_parses_real_fundamental_columns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_cap",
            lambda *a, **kw: _stub_pykrx_market_cap(400_000_000_000_000),
        )

        result = get_pykrx_market_data.invoke({"stock_code": "005930"})

        assert result["company_info"]["name"] == "삼성전자"
        fd = result["fundamental_data"]
        assert fd["per"] == 12.5
        assert fd["pbr"] == 1.3
        assert fd["eps"] == 5000
        assert fd["bps"] == 58000
        # 시가총액은 get_market_cap의 마지막 거래일 값
        assert fd["market_cap"] == 400_000_000_000_000
        assert "note" not in fd

    def test_market_cap_requested_for_same_window(
        self, monkeypatch: pytest.MonkeyPatch, pykrx_stubs: dict[str, Any]
    ) -> None:
        captured: dict[str, Any] = {}

        def fundamental(*args: Any, **kwargs: Any) -> pd.DataFrame:
            captured["fundamental"] = args
            return _stub_pykrx_fundamental()

        monkeypatch.setattr("agents.korean_financial_react_agent.stock.get_market_fundamental", fundamental)
        get_pykrx_market_data.invoke({"stock_code": "005930"})

        assert pykrx_stubs["market_cap"][0] == captured["fundamental"]

    def test_pykrx_failure_is_an_error_without_placeholders(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """KRX 로그인 없이 pykrx가 KeyError를 내면 'Unknown' 같은 자리표시값 없이 오류로 집계된다."""

        def no_login(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise KeyError("PER")

        monkeypatch.setattr("agents.korean_financial_react_agent.stock.get_market_fundamental", no_login)

        result = get_pykrx_market_data.invoke({"stock_code": "005930"})

        assert classify_tool_output(result) == (True, False)
        assert "Unknown" not in str(result)
        assert result["company_info"] == {"name": "삼성전자", "market": "KOSPI"}
        assert set(result["fundamental_data"].values()) == {None}

    def test_missing_market_cap_is_none_not_zero(self) -> None:
        """get_market_fundamental에는 시가총액 컬럼이 없다 — 시가총액을 못 받으면 0이 아니라 None."""
        result = get_pykrx_market_data.invoke({"stock_code": "005930"})

        fd = result["fundamental_data"]
        assert fd["market_cap"] is None
        assert "시가총액" in fd["note"]
        assert fd["per"] == 12.5

    def test_market_cap_failure_is_none_with_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ConnectionError("KRX down")

        monkeypatch.setattr("agents.korean_financial_react_agent.stock.get_market_cap", boom)

        result = get_pykrx_market_data.invoke({"stock_code": "005930"})

        fd = result["fundamental_data"]
        assert fd["market_cap"] is None
        assert "KRX down" in fd["note"]
        # 시가총액 실패가 다른 지표까지 지우지 않는다.
        assert fd["pbr"] == 1.3

    def test_zero_values_normalized_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PyKRX는 데이터 없을 때 0을 돌려준다. 우리는 None으로 정규화."""
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_fundamental",
            lambda *a, **kw: _stub_pykrx_fundamental(PER=0, PBR=0, EPS=0, BPS=0),
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_cap",
            lambda *a, **kw: _stub_pykrx_market_cap(0),
        )

        fd = get_pykrx_market_data.invoke({"stock_code": "005930"})["fundamental_data"]

        assert fd == {
            "market_cap": None,
            "per": None,
            "pbr": None,
            "eps": None,
            "bps": None,
            "note": fd["note"],
        }

    def test_negative_eps_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """적자 기업의 음수 EPS는 실제 값이다 — 0만 'no data'다."""
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_fundamental",
            lambda *a, **kw: _stub_pykrx_fundamental(PER=0, EPS=-1234),
        )

        fd = get_pykrx_market_data.invoke({"stock_code": "005930"})["fundamental_data"]

        assert fd["eps"] == -1234
        assert fd["per"] is None

    def test_kosdaq_code_is_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_market_ticker_list()의 기본값은 KOSPI뿐 — KOSDAQ 종목도 이름·시장을 찾아야 한다."""
        listings = {"KOSPI": ["005930"], "KOSDAQ": ["247540"], "KONEX": []}
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_list",
            lambda date=None, market="KOSPI": listings[market],
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_ticker_name",
            lambda code: {"247540": "에코프로비엠"}[code],
        )
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.stock.get_market_fundamental",
            lambda *a, **kw: pd.DataFrame(),
        )

        result = get_pykrx_market_data.invoke({"stock_code": "247540"})
        assert result["company_info"] == {"name": "에코프로비엠", "market": "KOSDAQ"}
        fd = result["fundamental_data"]
        assert all(fd[key] is None for key in ("market_cap", "per", "pbr", "eps", "bps"))
        assert "비어 있음" in fd["note"]


@pytest.mark.filterwarnings("ignore:Glyph .* missing from font")
class TestSaveStockChart:
    @pytest.fixture
    def chart_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        cache_root = tmp_path / "cache"
        workdir = tmp_path / "cwd"
        workdir.mkdir()
        monkeypatch.setenv("TUSIM_CACHE_DIR", str(cache_root))
        monkeypatch.chdir(workdir)
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.fdr.DataReader",
            lambda *a, **kw: _stub_fdr_ohlcv(),
        )
        return tmp_path

    def test_chart_data_argument_does_not_crash(self, chart_env: Path) -> None:
        result = save_stock_chart.invoke({"stock_code": "005930", "chart_data": {"Close": [1, 2, 3]}})

        assert result["chart_saved"] is True, result
        assert result["data_points"] == 80

    def test_chart_written_under_cache_dir_not_cwd(self, chart_env: Path) -> None:
        result = save_stock_chart.invoke({"stock_code": "005930"})

        chart_path = Path(result["chart_path"])
        assert chart_path.is_file()
        assert chart_path.parent == chart_env / "cache" / "charts"
        assert list((chart_env / "cwd").iterdir()) == []

    def test_stock_code_cannot_escape_chart_dir(self, chart_env: Path) -> None:
        result = save_stock_chart.invoke({"stock_code": "../../005930"})

        chart_path = Path(result["chart_path"])
        assert chart_path.parent == chart_env / "cache" / "charts"
        assert chart_path.name == "stock_chart_005930.png"

    def test_empty_price_history_returns_error(
        self, chart_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "agents.korean_financial_react_agent.fdr.DataReader",
            lambda *a, **kw: pd.DataFrame(),
        )
        result = save_stock_chart.invoke({"stock_code": "005930"})
        assert result["chart_saved"] is False
        assert "error" in result


def test_dart_error_does_not_leak_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.korean_financial_react_agent.get_comprehensive_company_data",
        lambda _code: {
            "error": "list.json failed: https://opendart.fss.or.kr/api/list.json?crtfc_key=DARTKEY12345"
        },
    )
    result = get_dart_company_data.invoke({"stock_code": "005930"})
    assert "DARTKEY12345" not in result["error"]
    assert "crtfc_key=***" in result["error"]


def _statement(year: str, data: dict[str, float]) -> dict[str, Any]:
    return {
        "year": year,
        "report_name": "사업보고서",
        "fs_name": "연결재무제표",
        "period": f"{year}.01.01 ~ {year}.12.31",
        "financial_data": data,
    }


def test_dart_summary_names_fiscal_year_report_and_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.korean_financial_react_agent.get_comprehensive_company_data",
        lambda _code: {
            "company_info": {"corp_name": "삼성전자"},
            "financial_statements": {
                "latest_annual": {"error": "Financial statements not found: 조회된 데이터가 없습니다"},
                "prior_annual": _statement("2024", {"매출액": 300.0, "자본금": 7.0}),
            },
        },
    )
    result = get_dart_company_data.invoke({"stock_code": "005930"})

    assert result["financial_basis"]["fiscal_year"] == "2024"
    assert result["financial_summary"]["revenue"]["data_year"] == "FY2024 사업보고서 (연결재무제표)"
    # 자본금(paid-in capital) is not total equity.
    assert "total_equity" not in result["financial_summary"]


def test_dart_summary_prefers_latest_annual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.korean_financial_react_agent.get_comprehensive_company_data",
        lambda _code: {
            "financial_statements": {
                "latest_annual": _statement("2025", {"영업이익": 0.0}),
                "prior_annual": _statement("2024", {"영업이익": 9.0}),
            },
        },
    )
    result = get_dart_company_data.invoke({"stock_code": "005930"})

    assert result["financial_summary"]["operating_income"]["value"] == 0.0
    assert result["financial_basis"]["fiscal_year"] == "2025"


def _no_key_bok_response() -> dict[str, Any]:
    """키 없이 받은 실제 모양: 지표는 모두 실패, 통계 블록과 status 'success'가 붙는다."""
    failed = {"error": "ECOS API 키 미설정", "api_status": "failed"}
    return {
        "indicators": {"base_interest_rate": failed, "exchange_rate": failed, "export_data": failed},
        "statistics": {"successful_indicators": 1, "total_indicators": 7, "success_rate": "14.3%"},
        "status": "success",
        "data_source": "Bank of Korea ECOS API Only (No Mock Data)",
        "last_updated": "2026-10-27T12:00:00+09:00",
    }


def test_macro_tool_without_usable_indicators_is_not_data(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.korean_financial_react_agent import get_macro_economic_data

    monkeypatch.setattr(
        "agents.korean_financial_react_agent.get_macro_economic_indicators", lambda: _no_key_bok_response()
    )

    result = get_macro_economic_data.invoke({})

    assert classify_tool_output(result) == (True, False)


def test_statistics_block_alone_is_not_data() -> None:
    assert classify_tool_output({"statistics": {"successful_indicators": 1}, "status": "success"}) == (
        False,
        False,
    )
