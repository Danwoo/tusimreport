"""scripts/check_sources.py: per-source key / request / data / as-of states and exit code.

No network: HTTP goes through `responses` (unregistered URLs raise), FinanceDataReader
and pykrx are monkeypatched. Keys are set on `config.settings.settings` per test so a
key in the session environment or `.env` cannot change the outcome.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import responses
from responses import matchers

from config.settings import settings
from utils.time import KST, kst_year

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_sources.py"
_spec = importlib.util.spec_from_file_location("check_sources", _SCRIPT)
assert _spec is not None and _spec.loader is not None
cs = importlib.util.module_from_spec(_spec)
sys.modules["check_sources"] = cs
_spec.loader.exec_module(cs)

DART = "https://opendart.fss.or.kr/api"
ECOS_RE = re.compile(r"https://ecos\.bok\.or\.kr/api/StatisticSearch/.+")
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
COINGECKO = "https://api.coingecko.com/api/v3"

DART_SECRET = "DART-TEST-SECRET-VALUE"
ECOS_SECRET = "ECOS-TEST-SECRET-VALUE"
KEY_ATTRS = (
    "dart_api_key",
    "ecos_api_key",
    "tavily_api_key",
    "alpha_vantage_api_key",
    "naver_client_id",
    "naver_client_secret",
)


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch: pytest.MonkeyPatch, isolated_cache_dir: Path) -> None:
    for attr in KEY_ATTRS:
        monkeypatch.setattr(settings, attr, None)
    for name in cs.SECRET_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict, dict, str]:
    out = tmp_path / "sources.json"
    code = cs.main([*args, "--json", str(out)])
    stdout = capsys.readouterr().out
    payload = json.loads(out.read_text(encoding="utf-8"))
    return code, {r["source"]: r for r in payload["results"]}, payload, stdout


def _prices(last_day: str = "2026-10-23") -> pd.DataFrame:
    index = pd.date_range(end=last_day, periods=3, freq="B")
    return pd.DataFrame(
        {
            "Open": [70000.0, 70500.0, 71000.0],
            "High": [71000.0, 71500.0, 72000.0],
            "Low": [69500.0, 70000.0, 70500.0],
            "Close": [70500.0, 71000.0, 71500.0],
            "Volume": [1_000_000, 1_100_000, 1_200_000],
            "Change": [0.01, 0.007, 0.007],
        },
        index=index,
    )


def _corpcode_zip() -> bytes:
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?><result>"
        "<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>"
        "<stock_code>005930</stock_code><modify_date>20260101</modify_date></list>"
        "<list><corp_code>00999999</corp_code><corp_name>비상장사</corp_name>"
        "<stock_code> </stock_code><modify_date>20260101</modify_date></list>"
        "</result>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buffer.getvalue()


def _company_json() -> dict[str, Any]:
    return {
        "status": "000",
        "message": "정상",
        "corp_code": "00126380",
        "corp_name": "삼성전자(주)",
        "stock_name": "삼성전자",
        "stock_code": "005930",
        "corp_cls": "Y",
        "acc_mt": "12",
    }


def _financials_rows(year: int) -> list[dict[str, str]]:
    common = {"rcept_no": f"{year + 1}0311000123", "bsns_year": str(year), "thstrm_dt": f"{year}.12.31 현재"}
    return [
        {
            **common,
            "fs_div": "CFS",
            "fs_nm": "연결재무제표",
            "account_nm": "매출액",
            "thstrm_amount": "300,870,903,000,000",
        },
        {
            **common,
            "fs_div": "CFS",
            "fs_nm": "연결재무제표",
            "account_nm": "영업이익",
            "thstrm_amount": "32,725,961,000,000",
        },
        {
            **common,
            "fs_div": "OFS",
            "fs_nm": "재무제표",
            "account_nm": "매출액",
            "thstrm_amount": "209,052,241,000,000",
        },
    ]


def _register_dart_success(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, f"{DART}/corpCode.xml", body=_corpcode_zip(), content_type="application/zip")
    rsps.add(responses.GET, f"{DART}/company.json", json=_company_json())
    rsps.add(
        responses.GET,
        f"{DART}/fnlttSinglAcnt.json",
        json={"status": "013", "message": "조회된 데이타가 없습니다."},
        match=[
            matchers.query_param_matcher(
                {"bsns_year": str(kst_year(-1)), "reprt_code": "11011"}, strict_match=False
            )
        ],
    )
    rsps.add(
        responses.GET,
        f"{DART}/fnlttSinglAcnt.json",
        json={"status": "000", "message": "정상", "list": _financials_rows(kst_year(-2))},
        match=[
            matchers.query_param_matcher(
                {"bsns_year": str(kst_year(-2)), "reprt_code": "11011"}, strict_match=False
            )
        ],
    )


def _ecos_rows() -> dict[str, Any]:
    rows = [
        {"TIME": "20261023", "DATA_VALUE": "2.5", "UNIT_NAME": "연%"},
        {"TIME": "20261024", "DATA_VALUE": "2.5", "UNIT_NAME": "연%"},
    ]
    return {"StatisticSearch": {"list_total_count": 2, "row": rows}}


# ---------------------------------------------------------------------------
# key missing
# ---------------------------------------------------------------------------


def test_missing_keys_send_nothing_and_exit_1(
    mocked_responses: responses.RequestsMock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_import() -> Any:
        raise AssertionError("pykrx must not be imported without KRX_ID/KRX_PW")

    monkeypatch.setattr(cs, "_import_pykrx_stock", must_not_import)
    keyed = [s.source for s in cs.SPECS if s.keys]

    code, rows, payload, stdout = _run(tmp_path, capsys, "--only", ",".join(keyed))

    assert code == 1
    assert payload["exit_code"] == 1
    assert payload["minimum"]["ok"] is False
    assert len(mocked_responses.calls) == 0
    for source in keyed:
        row = rows[source]
        assert (row["key"], row["request"], row["data"], row["as_of"]) == ("missing", "not_sent", "n/a", None)
        assert "not configured; no request sent" in row["note"]
    assert "docs/API_KEYS.md 4.4" in rows["naver_news"]["note"]
    assert "DART_API_KEY not configured" in stdout


def test_alpha_vantage_needs_opt_in_even_with_a_key(
    mocked_responses: responses.RequestsMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings.alpha_vantage_api_key = "AV-TEST-SECRET-VALUE"

    _, rows, _, stdout = _run(tmp_path, capsys, "--only", "alpha_vantage_fx")

    row = rows["alpha_vantage_fx"]
    assert (row["key"], row["request"], row["data"]) == ("set", "not_sent", "n/a")
    assert "--include-alpha-vantage" in row["note"]
    assert len(mocked_responses.calls) == 0
    assert "AV-TEST-SECRET-VALUE" not in stdout


# ---------------------------------------------------------------------------
# HTTP error
# ---------------------------------------------------------------------------


def test_http_error_is_request_failed_with_status(
    mocked_responses: responses.RequestsMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mocked_responses.add(responses.GET, CNN_URL, status=418, body="I'm a teapot")

    _, rows, _, _ = _run(tmp_path, capsys, "--only", "fear_greed")

    row = rows["fear_greed"]
    assert (row["key"], row["request"], row["data"], row["as_of"]) == ("not_required", "failed", "n/a", None)
    assert row["http_status"] == 418
    assert row["error_type"] == "DataSourceUnavailableError"
    # Whatever the client handed agents (older clients: score 50; newer: available=False), the
    # check reports the transport failure and names what the client returned.
    assert "client returned" in row["note"]


def test_dart_auth_failure_is_typed_and_dependents_are_not_sent(
    mocked_responses: responses.RequestsMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings.dart_api_key = DART_SECRET
    mocked_responses.add(responses.GET, f"{DART}/corpCode.xml", status=401, body="unauthorized")

    code, rows, _, stdout = _run(tmp_path, capsys, "--only", "dart_corp_code,dart_company,dart_financials")

    assert code == 1
    corp = rows["dart_corp_code"]
    assert (corp["key"], corp["request"], corp["data"]) == ("set", "failed", "n/a")
    assert (corp["error_type"], corp["http_status"]) == ("AuthenticationError", 401)
    for source in ("dart_company", "dart_financials"):
        assert rows[source]["request"] == "not_sent"
        assert "dart_corp_code" in rows[source]["note"]
    assert DART_SECRET not in stdout


def test_key_in_client_error_message_is_redacted(
    mocked_responses: responses.RequestsMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """requests puts the full URL (with crtfc_key) in HTTPError; DART's client returns that string."""
    settings.dart_api_key = DART_SECRET
    mocked_responses.add(
        responses.GET, f"{DART}/corpCode.xml", body=_corpcode_zip(), content_type="application/zip"
    )
    mocked_responses.add(responses.GET, f"{DART}/company.json", status=404, body="not found")

    _, rows, payload, stdout = _run(tmp_path, capsys, "--only", "dart_corp_code,dart_company", "--verbose")

    company = rows["dart_company"]
    assert (company["request"], company["http_status"]) == ("failed", 404)
    assert "crtfc_key=***" in company["note"]
    assert DART_SECRET not in stdout
    assert DART_SECRET not in json.dumps(payload, ensure_ascii=False)
    assert "captured output: dart_company" in stdout  # the client's own error log, redacted


# ---------------------------------------------------------------------------
# empty data
# ---------------------------------------------------------------------------


def test_empty_responses_are_request_ok_data_empty(
    mocked_responses: responses.RequestsMock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("FinanceDataReader.DataReader", lambda *a, **kw: pd.DataFrame())
    settings.ecos_api_key = ECOS_SECRET
    mocked_responses.add(
        responses.GET,
        ECOS_RE,
        json={"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}},
    )

    code, rows, _, stdout = _run(tmp_path, capsys, "--only", "fdr_prices,ecos_base_rate")

    assert code == 1
    for source in ("fdr_prices", "ecos_base_rate"):
        row = rows[source]
        assert (row["request"], row["data"], row["as_of"]) == ("ok", "empty", None)
    assert "INFO-200" in rows["ecos_base_rate"]["note"]
    assert ECOS_SECRET not in stdout


# ---------------------------------------------------------------------------
# success with as-of
# ---------------------------------------------------------------------------


def test_minimum_set_with_as_of_exits_0(
    mocked_responses: responses.RequestsMock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("FinanceDataReader.DataReader", lambda *a, **kw: _prices("2026-10-23"))
    settings.dart_api_key = DART_SECRET
    settings.ecos_api_key = ECOS_SECRET
    _register_dart_success(mocked_responses)
    mocked_responses.add(responses.GET, ECOS_RE, json=_ecos_rows())

    code, rows, payload, stdout = _run(
        tmp_path, capsys, "--only", "fdr_prices,dart_corp_code,dart_company,dart_financials,ecos_base_rate"
    )

    assert code == 0
    assert payload["minimum"] == {
        "ok": True,
        "required": [*cs.MINIMUM_REQUIRED, "one of fdr_prices|pykrx_index_ohlcv"],
        "price_source": "fdr_prices",
        "missing": [],
    }
    assert payload["checked_at"].endswith("+09:00")
    assert all((r["request"], r["data"]) == ("ok", "ok") for r in rows.values())

    assert rows["fdr_prices"]["as_of"] == "2026-10-23"
    assert rows["fdr_prices"]["key"] == "not_required"
    assert rows["dart_corp_code"]["note"] == "corp_code=00126380"
    prev = kst_year(-2)
    fin = rows["dart_financials"]
    assert fin["as_of"] == f"FY{prev} 사업보고서 (11011), period end {prev}-12-31, filed {prev + 1}-03-11"
    assert f"FY{kst_year(-1)} annual report: none (013)" in fin["note"]
    assert "statement=CFS 연결재무제표" in fin["note"]
    assert fin["coverage"] == "accounts=2"
    assert rows["ecos_base_rate"]["as_of"] == "2026-10-24"
    assert "-> exit 0" in stdout
    assert DART_SECRET not in stdout and ECOS_SECRET not in stdout


def test_pykrx_checks_report_as_of_and_hide_login_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KRX_ID", "krx-test-user")
    monkeypatch.setenv("KRX_PW", "krx-test-password")
    days = pd.to_datetime(["2026-10-22", "2026-10-23"])
    fake = SimpleNamespace(
        get_index_ohlcv_by_date=lambda *a: pd.DataFrame(
            {
                "시가": [1.0, 2.0],
                "고가": [1.0, 2.0],
                "저가": [1.0, 2.0],
                "종가": [2600.5, 2610.0],
                "거래량": [1, 2],
            },
            index=days,
        ),
        get_market_fundamental=lambda *a: pd.DataFrame(
            {"BPS": [50000, 50000], "PER": [12.1, 12.3], "PBR": [1.2, 1.3], "EPS": [5000, 5000]}, index=days
        ),
        get_market_trading_value_by_investor=lambda *a: pd.DataFrame(
            {"매도": [10, 20, 30], "매수": [15, 15, 30], "순매수": [5, -5, 0]},
            index=["외국인", "기관합계", "개인"],
        ),
    )

    def fake_import() -> tuple[Any, bool]:
        print("KRX 로그인 시도...")
        print("  로그인 ID: krx-test-user")
        return fake, True

    monkeypatch.setattr(cs, "_import_pykrx_stock", fake_import)

    code, rows, _, stdout = _run(
        tmp_path, capsys, "--only", "pykrx_index_ohlcv,pykrx_fundamental,pykrx_investor_trading", "--verbose"
    )

    assert code == 1  # pykrx alone is not the minimum set
    assert all((r["key"], r["request"], r["data"]) == ("set", "ok", "ok") for r in rows.values())
    assert rows["pykrx_index_ohlcv"]["as_of"] == "2026-10-23"
    assert rows["pykrx_fundamental"]["as_of"] == "2026-10-23"
    assert rows["pykrx_investor_trading"]["as_of"] is None
    assert "window" in rows["pykrx_investor_trading"]["coverage"]
    assert "krx-test-user" not in stdout
    assert "로그인 ID" not in stdout


def test_pykrx_login_failure_is_authentication_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KRX_ID", "krx-test-user")
    monkeypatch.setenv("KRX_PW", "krx-test-password")
    monkeypatch.setattr(cs, "_import_pykrx_stock", lambda: (SimpleNamespace(), False))

    _, rows, _, _ = _run(tmp_path, capsys, "--only", "pykrx_index_ohlcv")

    row = rows["pykrx_index_ohlcv"]
    assert (row["key"], row["request"], row["data"], row["error_type"]) == (
        "set",
        "failed",
        "n/a",
        "AuthenticationError",
    )


# ---------------------------------------------------------------------------
# isolation and time bound
# ---------------------------------------------------------------------------


def test_one_failing_check_does_not_stop_the_next(
    mocked_responses: responses.RequestsMock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raise RuntimeError("unexpected library failure")

    monkeypatch.setattr("FinanceDataReader.DataReader", boom)
    mocked_responses.add(
        responses.GET,
        f"{COINGECKO}/simple/price",
        json={"bitcoin": {"usd": 65000.0, "krw": 9.0e7, "usd_24h_change": 1.2}, "ethereum": {"usd": 3000.0}},
    )
    mocked_responses.add(
        responses.GET,
        f"{COINGECKO}/global",
        json={"data": {"total_market_cap": {"usd": 1.0}, "updated_at": 1793000000}},
    )

    _, rows, _, _ = _run(tmp_path, capsys, "--only", "fdr_prices,coingecko")

    assert (rows["fdr_prices"]["request"], rows["fdr_prices"]["error_type"]) == ("failed", "RuntimeError")
    coin = rows["coingecko"]
    assert (coin["request"], coin["data"]) == ("ok", "ok")
    assert coin["as_of"] == datetime.fromtimestamp(1793000000, tz=KST).isoformat(timespec="minutes")


def test_slow_check_times_out_without_blocking_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(*args: Any, **kwargs: Any) -> pd.DataFrame:
        time.sleep(1.5)
        return _prices()

    monkeypatch.setattr("FinanceDataReader.DataReader", slow)
    monkeypatch.setattr(cs.shutil, "which", lambda name: None)

    started = time.monotonic()
    _, rows, _, _ = _run(tmp_path, capsys, "--only", "fdr_prices,paxnet", "--timeout", "0.2")

    assert time.monotonic() - started < 1.5
    assert (rows["fdr_prices"]["request"], rows["fdr_prices"]["data"]) == ("timeout", "n/a")
    pax = rows["paxnet"]
    assert (pax["key"], pax["request"], pax["data"]) == ("not_required", "not_sent", "n/a")
    assert "not on PATH" in pax["note"] and "--crawl-paxnet" in pax["note"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_redact_hides_configured_values_and_key_shaped_parameters() -> None:
    settings.ecos_api_key = ECOS_SECRET
    text = (
        "for url: https://opendart.fss.or.kr/api/company.json?corp_code=1&crtfc_key=abc123 "
        "https://ecos.bok.or.kr/api/StatisticSearch/anotherkey/json/kr/1/10 "
        f"value={ECOS_SECRET} Authorization: Bearer tok.en-1 tvly-abcDEF"
    )

    redacted = cs._redact(text)

    for secret in ("abc123", "anotherkey", ECOS_SECRET, "tok.en-1", "abcDEF"):
        assert secret not in redacted
    assert "crtfc_key=***" in redacted
    assert "StatisticSearch/***" in redacted


def test_unknown_source_id_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cs.parse_args(["--only", "fdr_prices,nope"])
    assert excinfo.value.code == 2
