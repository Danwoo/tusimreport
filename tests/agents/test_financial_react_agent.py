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
