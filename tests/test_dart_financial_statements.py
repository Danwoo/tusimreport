"""DART 단일회사 주요계정 파싱과 보고서 코드 검증.

fnlttSinglAcnt는 연결(CFS)과 별도(OFS) 행을 한 목록으로 돌려준다. 같은 계정명이
두 번 나오므로 한 기준만 골라야 하고, 사업보고서는 11011이다(11014는 3분기보고서).
"""

from __future__ import annotations

from typing import Any

import pytest

import data.dart_api_client as dart_module
from data.dart_api_client import ANNUAL_REPORT, REPORT_NAMES, DARTAPIClient


def _row(fs_div: str, account: str, amount: str) -> dict[str, str]:
    return {
        "rcept_no": "20260311000123",
        "reprt_code": "11011",
        "bsns_year": "2025",
        "fs_div": fs_div,
        "fs_nm": "연결재무제표" if fs_div == "CFS" else "재무제표",
        "account_nm": account,
        "thstrm_dt": "2025.01.01 ~ 2025.12.31",
        "thstrm_amount": amount,
    }


def _client_returning(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    client = DARTAPIClient.__new__(DARTAPIClient)

    def fake_request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append({"endpoint": endpoint, **params})
        return payload

    monkeypatch.setattr(client, "_make_request", fake_request)
    monkeypatch.setattr(dart_module, "dart_client", client)
    return calls


def test_annual_report_code_is_11011() -> None:
    assert ANNUAL_REPORT == "11011"
    assert REPORT_NAMES["11011"] == "사업보고서"
    assert REPORT_NAMES["11014"] == "3분기보고서"


def test_consolidated_rows_win_over_separate_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "status": "000",
        "list": [
            _row("CFS", "매출액", "300,870,903,000,000"),
            _row("CFS", "영업이익", "32,725,961,000,000"),
            _row("OFS", "매출액", "209,052,241,000,000"),
            _row("OFS", "영업이익", "12,361,014,000,000"),
        ],
    }
    _client_returning(monkeypatch, payload)

    result = dart_module.dart_client.get_financial_statements("00126380", "2025", ANNUAL_REPORT)

    assert result["fs_div"] == "CFS"
    assert result["fs_name"] == "연결재무제표"
    assert result["report_name"] == "사업보고서"
    assert result["period"] == "2025.01.01 ~ 2025.12.31"
    assert result["financial_data"] == {"매출액": 300870903000000.0, "영업이익": 32725961000000.0}


def test_separate_rows_are_used_when_there_is_no_consolidated_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client_returning(monkeypatch, {"status": "000", "list": [_row("OFS", "매출액", "1,000")]})

    result = dart_module.dart_client.get_financial_statements("00000001", "2025", ANNUAL_REPORT)

    assert result["fs_div"] == "OFS"
    assert result["financial_data"] == {"매출액": 1000.0}


def test_missing_amounts_are_dropped_not_zero_filled(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row("CFS", "매출액", "1,000"), _row("CFS", "영업이익", "-"), _row("CFS", "당기순이익", "")]
    _client_returning(monkeypatch, {"status": "000", "list": rows})

    result = dart_module.dart_client.get_financial_statements("00126380", "2025", ANNUAL_REPORT)

    assert result["financial_data"] == {"매출액": 1000.0}


def test_comprehensive_data_requests_the_last_two_annual_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _client_returning(monkeypatch, {"status": "013", "message": "조회된 데이터가 없습니다"})
    client = dart_module.dart_client
    monkeypatch.setattr(client, "get_stock_code_to_corp_code_mapping", lambda _code: "00126380")
    monkeypatch.setattr(client, "get_company_info", lambda _corp: {"corp_name": "삼성전자"})
    monkeypatch.setattr(client, "get_recent_disclosures", lambda _corp, _n: [])
    monkeypatch.setattr(dart_module, "kst_year", lambda offset=0: 2026 + offset)

    result = dart_module.get_comprehensive_company_data("005930")

    statement_calls = [c for c in calls if c["endpoint"] == "fnlttSinglAcnt.json"]
    assert [(c["bsns_year"], c["reprt_code"]) for c in statement_calls] == [
        ("2025", "11011"),
        ("2024", "11011"),
    ]
    assert set(result["financial_statements"]) == {"latest_annual", "prior_annual"}
