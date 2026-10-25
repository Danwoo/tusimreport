#!/usr/bin/env python3
"""Per-source connectivity check for one stock (docs/PROJECT_PLAN.md stage 1).

Usage, from the repo root:

    python scripts/check_sources.py                        # 005930 삼성전자
    python scripts/check_sources.py --stock 000660 --name SK하이닉스
    python scripts/check_sources.py --only dart_corp_code,ecos_base_rate
    python scripts/check_sources.py --json /tmp/sources.json --verbose
    python scripts/check_sources.py --include-alpha-vantage --crawl-paxnet

Every external source the agents use is exercised once through the repo's own
client code (data/*.py, and the same library calls the agents' tools make), and
each source gets four separate states:

    key      set | missing | not_required
    request  ok | failed | timeout | not_sent    (not_sent: nothing left this process)
    data     ok | empty | invalid | n/a          (n/a: no response to judge)
    as_of    the date or period the data itself carries (latest trading day,
             DART report period, ECOS observation date, newest news item, ...)

plus a note with the typed error (core.errors), the HTTP status, and the agents
that depend on the source.

Exit code 0 when the minimum set works: DART (corp code, company, financial
statements) + ECOS + one price source (FinanceDataReader or pykrx index OHLCV).
Otherwise 1. The LLM is not part of this check (`python setup_check.py
--llm-probe` covers it).

Key values are never printed. Client error messages and library output are
redacted before they reach stdout or the JSON file, and anything a check prints
while it runs is captured instead of shown (see --verbose).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from core.errors import (  # noqa: E402
    AuthenticationError,
    ConfigurationError,
    DataQualityError,
    DataSourceUnavailableError,
    ExternalAPIError,
    RateLimitError,
    TusimError,
)
from utils.time import (  # noqa: E402
    KST,
    kst_days_ago_compact,
    kst_isoformat,
    kst_now,
    kst_today_compact,
    kst_year,
    kst_yesterday_compact,
)

DEFAULT_STOCK_CODE = "005930"
DEFAULT_TIMEOUT_S = 60.0
PAXNET_CRAWL_TIMEOUT_S = 180.0
NOTE_MAX_CHARS = 400

KEY_SET, KEY_MISSING, KEY_NOT_REQUIRED = "set", "missing", "not_required"
REQ_OK, REQ_FAILED, REQ_TIMEOUT, REQ_NOT_SENT = "ok", "failed", "timeout", "not_sent"
DATA_OK, DATA_EMPTY, DATA_INVALID, DATA_NA = "ok", "empty", "invalid", "n/a"

MINIMUM_REQUIRED = ("dart_corp_code", "dart_company", "dart_financials", "ecos_base_rate")
PRICE_SOURCES = ("fdr_prices", "pykrx_index_ohlcv")

FDR_LOOKBACK_DAYS = 60
FDR_PRICE_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
PYKRX_INDEX_LOOKBACK_DAYS = 30
# korean_institutional_trading_agent asks for period_days(20) + 10 calendar days.
PYKRX_TRADING_LOOKBACK_DAYS = 30
CHROME_COMMANDS = ("google-chrome", "chromium", "chromium-browser", "chrome")
NAVER_HOLD_NOTE = "docs/API_KEYS.md 4.4: Naver 발급 보류 (약관이 AI 입력을 금지하고, 코드는 옛 openapi.naver.com 경로를 쓴다)"

# Env names whose values must never appear in output. Values come from os.environ and
# from config.settings (which also reads .env).
SECRET_ENV_NAMES = (
    "DART_API_KEY",
    "ECOS_API_KEY",
    "TAVILY_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "KRX_ID",
    "KRX_PW",
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "TYPESAFE_API_KEY",
    "KOSIS_SERVICE_KEY",
    "DEEPSEARCH_API_KEY",
)
# config.settings.validate_api_keys() flag per env name (pykrx reads KRX_* from os.environ).
_SETTINGS_FLAG = {
    "DART_API_KEY": "dart",
    "ECOS_API_KEY": "ecos",
    "TAVILY_API_KEY": "tavily",
    "ALPHA_VANTAGE_API_KEY": "alpha_vantage",
    "NAVER_CLIENT_ID": "naver",
    "NAVER_CLIENT_SECRET": "naver",
}
_MIN_SECRET_LEN = 4
_REDACT_PATTERNS = (
    (
        re.compile(r"(?i)\b(crtfc_key|apikey|api_key|access_key|servicekey|token|key)=([^&\s\"'<>]+)"),
        r"\1=***",
    ),
    (re.compile(r"(?i)(ecos\.bok\.or\.kr/api/[A-Za-z]+/)([^/\s\"']+)"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"tvly-[A-Za-z0-9_\-]+"), "tvly-***"),
)
_HTTP_STATUS_IN_TEXT = re.compile(
    r"\b([1-5]\d\d) (?:Client|Server) Error|\bstatus[ =:]+([1-5]\d\d)\b|HTTP Error ([1-5]\d\d)"
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SourceResult:
    source: str
    label: str
    agents: list[str]
    key: str
    request: str
    data: str
    as_of: str | None = None
    coverage: str | None = None
    note: str = ""
    error_type: str | None = None
    http_status: int | None = None
    elapsed_s: float = 0.0

    @property
    def works(self) -> bool:
        return self.request == REQ_OK and self.data == DATA_OK


@dataclass
class Outcome:
    """What a check returns when the request succeeded and the data is usable."""

    as_of: str | None = None
    coverage: str | None = None
    note: str = ""


@dataclass
class CheckContext:
    stock_code: str
    company_name: str | None = None
    include_alpha_vantage: bool = False
    crawl_paxnet: bool = False
    paxnet_max_posts: int = 3
    # Values one check hands to a later one (DART corp_code, company name).
    shared: dict[str, Any] = field(default_factory=dict)
    # Output each check printed or logged while running, keyed by source.
    outputs: dict[str, io.StringIO] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckSpec:
    source: str
    label: str
    agents: tuple[str, ...]
    run: Callable[[CheckContext], Outcome]
    keys: tuple[str, ...] = ()  # env names the source needs; empty means keyless
    gate: Callable[[CheckContext], str | None] | None = None  # returns why not to send
    timeout_s: float | None = None  # lower bound on the per-check timeout
    always_note: str = ""


class _NotSent(TusimError):
    """No request was sent: gated by a flag, a dependency failed, or the runtime is not ready."""


class _EmptyData(DataQualityError):
    """The request succeeded but carried no rows."""


# ---------------------------------------------------------------------------
# Redaction and output capture
# ---------------------------------------------------------------------------


def _loaded_settings() -> Any:
    try:
        from config.settings import settings
    except Exception:  # a broken .env must not stop redaction of os.environ values
        return None
    return settings


def _secret_values() -> list[str]:
    values: set[str] = set()
    settings = _loaded_settings()
    for name in SECRET_ENV_NAMES:
        for value in (os.environ.get(name), getattr(settings, name.lower(), None)):
            if isinstance(value, str) and len(value.strip()) >= _MIN_SECRET_LEN:
                values.add(value.strip())
    # Longest first so a key that contains another key is removed whole.
    return sorted(values, key=len, reverse=True)


def _redact(text: str) -> str:
    if not text:
        return text
    for value in _secret_values():
        text = text.replace(value, "***")
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _clip(text: str, limit: int = NOTE_MAX_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Thread ident -> buffer. Shared by the stdout and stderr routers.
_THREAD_BUFFERS: dict[int, io.StringIO] = {}
_ABANDONED_THREADS: list[threading.Thread] = []


class _OutputRouter(io.TextIOBase):
    """Stand-in for sys.stdout / sys.stderr while checks run.

    Writes from a worker thread bound to a buffer go to that buffer (pykrx prints
    the KRX login ID at import; clients log URLs that carry keys). Everything else
    is redacted and passed to the real stream.
    """

    def __init__(self, stream: Any) -> None:
        super().__init__()
        self._stream = stream

    def write(self, text: str) -> int:
        buffer = _THREAD_BUFFERS.get(threading.get_ident())
        if buffer is not None:
            buffer.write(text)
        else:
            self._stream.write(_redact(text))
        return len(text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def fileno(self) -> int:
        return int(self._stream.fileno())

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return str(getattr(self._stream, "encoding", "utf-8") or "utf-8")


def _abandoned_threads_alive() -> bool:
    return any(t.is_alive() for t in _ABANDONED_THREADS)


# ---------------------------------------------------------------------------
# HTTP evidence and error typing
# ---------------------------------------------------------------------------


@dataclass
class _HttpCall:
    method: str
    url: str  # scheme://host/path, redacted, without query string
    status: int | None = None
    error: str | None = None
    response: Any = None  # requests.Response; read for raw fields, never serialized


def _safe_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return _redact(f"{parts.scheme}://{host}{parts.path}")
    except ValueError:
        return "<unparseable url>"


def _record_http(session: requests.Session) -> list[_HttpCall]:
    """Record every request a client makes through `session` (status, exception, response).

    Wraps the instance's `request` so `session.get/post` of that client go through it;
    no other session is touched. Clients swallow HTTP errors into dicts, so this is the
    only place the status code survives.
    """
    calls: list[_HttpCall] = []
    original = session.request

    def request(method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        call = _HttpCall(method=str(method).upper(), url=_safe_url(str(url)))
        calls.append(call)
        try:
            response = original(method, url, *args, **kwargs)
        except Exception as e:
            call.error = f"{type(e).__name__}: {e}"
            raise
        call.status = response.status_code
        call.response = response
        return response

    session.request = request  # type: ignore[method-assign]
    return calls


def _json(call: _HttpCall | None) -> Any:
    if call is None or call.response is None:
        return None
    try:
        return call.response.json()
    except ValueError:
        return None


def _error_for_status(status: int, message: str, source: str) -> ExternalAPIError:
    if status in (401, 403):
        return AuthenticationError(message, source=source, status_code=status)
    if status == 429:
        return RateLimitError(message, source=source, status_code=status)
    return DataSourceUnavailableError(message, source=source, status_code=status)


def _status_from_text(text: str) -> int | None:
    match = _HTTP_STATUS_IN_TEXT.search(text or "")
    if not match:
        return None
    return int(next(g for g in match.groups() if g))


def _error_from_message(message: str, source: str) -> ExternalAPIError:
    """Type an error that a client returned as a string (it swallowed the exception)."""
    status = _status_from_text(message)
    if status is not None:
        return _error_for_status(status, message, source)
    return DataSourceUnavailableError(message, source=source)


def _raise_from_calls(calls: list[_HttpCall], source: str, what: str, detail: str = "") -> None:
    """Raise the typed transport/HTTP error of the last recorded call; return if it was 2xx/3xx."""
    suffix = f" ({detail})" if detail else ""
    if not calls:
        raise DataSourceUnavailableError(f"{what}: no HTTP request was recorded{suffix}", source=source)
    last = calls[-1]
    if last.error:
        raise DataSourceUnavailableError(f"{what}: {last.error}{suffix}", source=source)
    if last.status is not None and last.status >= 400:
        raise _error_for_status(last.status, f"{what}: HTTP {last.status} from {last.url}{suffix}", source)


def _describe_call(call: _HttpCall | None) -> str:
    if call is None:
        return "no request recorded"
    if call.error:
        return call.error.split(":", 1)[0]
    return f"HTTP {call.status}"


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> str:
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)[:10]


def _compact_to_iso(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if re.fullmatch(r"\d{8}", value or "") else value


def _lag_note(iso_date: str) -> str:
    try:
        lag = (kst_now().date() - datetime.strptime(iso_date[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return ""
    return f"as-of is {lag} calendar day(s) before KST today {kst_now().date().isoformat()}"


def _to_kst_iso(value: Any) -> str | None:
    """ISO8601 string or epoch (s or ms) -> KST ISO string, minute precision."""
    try:
        if isinstance(value, int | float):
            seconds = value / 1000 if value > 1e11 else value
            parsed = datetime.fromtimestamp(seconds, tz=KST)
        elif isinstance(value, str) and value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return value
        else:
            return None
    except (ValueError, OverflowError, OSError):
        return str(value)
    return parsed.astimezone(KST).isoformat(timespec="minutes")


def _company_name(ctx: CheckContext) -> str:
    return ctx.company_name or ctx.shared.get("dart_stock_name") or ctx.stock_code


def _setting(name: str) -> str | None:
    from config.settings import settings

    value = getattr(settings, name.lower(), None)
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------------
# FinanceDataReader
# ---------------------------------------------------------------------------


def check_fdr_prices(ctx: CheckContext) -> Outcome:
    """Daily OHLCV through fdr.DataReader, the call get_korean_stock_data / context / technical make."""
    import FinanceDataReader as fdr

    start = (kst_now() - timedelta(days=FDR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    df = fdr.DataReader(ctx.stock_code, start=start)
    if df is None or df.empty:
        raise _EmptyData(f"FinanceDataReader returned 0 rows since {start}", source="FinanceDataReader")
    missing = [c for c in FDR_PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise DataQualityError(
            f"columns missing {missing}; got {list(df.columns)[:10]}", source="FinanceDataReader"
        )
    try:
        close = float(df["Close"].iloc[-1])
    except (TypeError, ValueError) as e:
        raise DataQualityError(f"last Close is not numeric: {e}", source="FinanceDataReader") from e
    if not close > 0:
        raise DataQualityError(f"last Close is {close}", source="FinanceDataReader")
    first, last = _as_date(df.index[0]), _as_date(df.index[-1])
    return Outcome(as_of=last, coverage=f"rows={len(df)} {first}..{last}", note=_lag_note(last))


# ---------------------------------------------------------------------------
# pykrx (KRX data portal, login required since 2025-12-27)
# ---------------------------------------------------------------------------


def _import_pykrx_stock() -> tuple[Any, bool | None]:
    """Import pykrx.stock and report whether its import-time KRX login produced a session.

    pykrx logs in to data.krx.co.kr while it is imported (KRX_ID / KRX_PW from os.environ),
    which can end another session of the same account, and prints the login ID. It is
    therefore imported here, lazily, only when both values are set; the runner captures
    what it prints.
    """
    import pykrx.stock as stock

    auth = sys.modules.get("pykrx.website.comm.auth")
    if auth is None or not hasattr(auth, "_auth_session"):
        return stock, None
    return stock, auth._auth_session is not None


def _pykrx_stock() -> Any:
    stock, logged_in = _import_pykrx_stock()
    if logged_in is False:
        raise AuthenticationError(
            "KRX login at pykrx import did not produce a session (check KRX_ID/KRX_PW); "
            "data requests would be rejected with 400 LOGOUT",
            source="pykrx",
        )
    return stock


def check_pykrx_index_ohlcv(ctx: CheckContext) -> Outcome:
    """KOSPI (1001) via get_index_ohlcv_by_date, as context_expert does (KOSPI only here)."""
    from data.external_schemas import PYKRX_INDEX_OHLCV_COLUMNS, assert_pykrx_columns

    stock = _pykrx_stock()
    start, end = kst_days_ago_compact(PYKRX_INDEX_LOOKBACK_DAYS), kst_today_compact()
    df = stock.get_index_ohlcv_by_date(start, end, "1001")
    if df is None or df.empty:
        raise _EmptyData(f"KOSPI index OHLCV: 0 rows for {start}..{end}", source="pykrx")
    assert_pykrx_columns(
        list(df.columns), expected=PYKRX_INDEX_OHLCV_COLUMNS, source="pykrx/get_index_ohlcv_by_date"
    )
    if "종가" not in df.columns:
        raise DataQualityError(f"no 종가 column; got {list(df.columns)}", source="pykrx")
    first, last = _as_date(df.index[0]), _as_date(df.index[-1])
    return Outcome(as_of=last, coverage=f"KOSPI rows={len(df)} {first}..{last}", note=_lag_note(last))


def check_pykrx_fundamental(ctx: CheckContext) -> Outcome:
    """get_market_fundamental(week_ago, yesterday, code): the window get_pykrx_market_data uses."""
    from data.external_schemas import validate_pykrx_fundamental

    stock = _pykrx_stock()
    start, end = kst_days_ago_compact(7), kst_yesterday_compact()
    df = stock.get_market_fundamental(start, end, ctx.stock_code)
    if df is None or df.empty:
        raise _EmptyData(f"0 rows for {start}..{end}", source="pykrx")
    row = validate_pykrx_fundamental(df.iloc[-1].to_dict())
    if not any((row.per, row.pbr, row.eps, row.bps, row.market_cap)):
        raise _EmptyData("PER/PBR/EPS/BPS are all 0 or missing (pykrx 'no data')", source="pykrx")
    last = _as_date(df.index[-1])
    return Outcome(
        as_of=last,
        coverage=f"rows={len(df)} PER={row.per} PBR={row.pbr}",
        note=_lag_note(last) + "; comparative_expert calls the market-wide form for today's date",
    )


def check_pykrx_investor_trading(ctx: CheckContext) -> Outcome:
    """get_market_trading_value_by_investor, the institutional_trading_expert call."""
    from data.external_schemas import PYKRX_TRADING_VALUE_COLUMNS, assert_pykrx_columns

    stock = _pykrx_stock()
    end = kst_now()
    start_str = (end - timedelta(days=PYKRX_TRADING_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    df = stock.get_market_trading_value_by_investor(start_str, end_str, ctx.stock_code)
    if df is None or df.empty:
        raise _EmptyData(f"0 rows for {start_str}..{end_str}", source="pykrx")
    assert_pykrx_columns(
        list(df.columns),
        expected=PYKRX_TRADING_VALUE_COLUMNS,
        source="pykrx/get_market_trading_value_by_investor",
    )
    if "순매수" not in df.columns:
        raise DataQualityError(f"no 순매수 column; got {list(df.columns)}", source="pykrx")
    investors = [name for name in ("외국인", "기관합계", "개인") if name in df.index]
    if not investors:
        raise DataQualityError(f"none of 외국인/기관합계/개인 in rows {list(df.index)[:8]}", source="pykrx")
    return Outcome(
        as_of=None,
        coverage=f"window {start_str}..{end_str}, investor rows={len(df)}",
        note="period aggregate: this pykrx call carries no per-day dates",
    )


# ---------------------------------------------------------------------------
# DART (OpenDART)
# ---------------------------------------------------------------------------

_DART_AUTH_STATUS = {"010", "011", "012", "901"}
_DART_LIMIT_STATUS = {"020", "021"}
_DART_NO_DATA = "013"


def _dart_client() -> tuple[Any, list[_HttpCall]]:
    from data.dart_api_client import DARTAPIClient

    client = DARTAPIClient(api_key=_setting("DART_API_KEY"))
    return client, _record_http(client.session)


def _dart_status(call: _HttpCall | None) -> tuple[str | None, str | None]:
    payload = _json(call)
    if isinstance(payload, dict) and "status" in payload:
        return str(payload.get("status")), payload.get("message")
    if call is None or call.response is None:
        return None, None
    try:
        text = call.response.text[:2000]
    except Exception:
        return None, None
    status = re.search(r"<status>\s*(\d+)\s*</status>", text)
    message = re.search(r"<message>(.*?)</message>", text, re.S)
    return (status.group(1) if status else None), (message.group(1).strip() if message else None)


def _raise_dart(calls: list[_HttpCall], what: str, detail: str = "") -> NoReturn:
    _raise_from_calls(calls, "DART", what, detail)
    status, message = _dart_status(calls[-1])
    text = f"{what}: DART status {status}: {message}"
    if status is None:
        raise DataQualityError(f"{what}: response is not a DART envelope ({detail})", source="DART")
    if status in _DART_AUTH_STATUS:
        raise AuthenticationError(text, source="DART")
    if status in _DART_LIMIT_STATUS:
        raise RateLimitError(text, source="DART")
    if status in (_DART_NO_DATA, "000"):
        raise _EmptyData(text, source="DART")
    raise DataSourceUnavailableError(text, source="DART")


def check_dart_corp_code(ctx: CheckContext) -> Outcome:
    """stock_code -> corp_code through CORPCODE.xml, the first step of get_comprehensive_company_data."""
    client, calls = _dart_client()
    corp_code = client.get_stock_code_to_corp_code_mapping(ctx.stock_code)
    listed = getattr(client, "_corp_code_map_cache", None) or {}
    if corp_code:
        if not re.fullmatch(r"\d{8}", str(corp_code)):
            raise DataQualityError(f"corp_code {corp_code!r} is not 8 digits", source="DART")
        ctx.shared["dart_corp_code"] = corp_code
        return Outcome(coverage=f"CORPCODE.xml listed codes={len(listed)}", note=f"corp_code={corp_code}")
    _raise_from_calls(calls, "DART", "corpCode.xml")
    if listed:
        raise _EmptyData(
            f"{ctx.stock_code} is not in CORPCODE.xml ({len(listed)} listed codes)", source="DART"
        )
    _raise_dart(calls, "corpCode.xml", "response was not the ZIP")


def check_dart_company(ctx: CheckContext) -> Outcome:
    """company.json through DARTAPIClient.get_company_info, validated by validate_dart_corp_info."""
    from data.external_schemas import validate_dart_corp_info

    corp_code = ctx.shared.get("dart_corp_code")
    if not corp_code:
        raise _NotSent("needs the corp_code from dart_corp_code, which did not succeed")
    client, calls = _dart_client()
    info = client.get_company_info(corp_code)
    if info.get("error"):
        _raise_dart(calls, "company.json", str(info["error"]))
    model = validate_dart_corp_info(info)
    if not model.corp_name:
        raise DataQualityError("company.json has no corp_name", source="DART")
    if model.stock_code and model.stock_code != ctx.stock_code:
        raise DataQualityError(
            f"company.json stock_code {model.stock_code} != requested {ctx.stock_code}", source="DART"
        )
    ctx.shared["dart_stock_name"] = model.stock_name or model.corp_name
    return Outcome(
        coverage=f"corp_cls={model.corp_cls} acc_mt={info.get('acc_mt')}",
        note=f"{model.corp_name}; company profile carries no reporting period",
    )


def check_dart_financials(ctx: CheckContext) -> Outcome:
    """fnlttSinglAcnt.json annual report (11011) for last year, then the year before.

    Same order as get_comprehensive_company_data; get_dart_company_data uses the
    latest annual report that has rows. A year's annual report is filed the next March.
    """
    from data.dart_api_client import ANNUAL_REPORT

    corp_code = ctx.shared.get("dart_corp_code")
    if not corp_code:
        raise _NotSent("needs the corp_code from dart_corp_code, which did not succeed")
    client, calls = _dart_client()
    skipped: list[str] = []
    for year in (kst_year(-1), kst_year(-2)):
        result = client.get_financial_statements(corp_code, str(year), ANNUAL_REPORT)
        accounts = result.get("financial_data") or {}
        if accounts:
            return _dart_financials_outcome(year, result, skipped)
        try:
            _raise_dart(calls, f"fnlttSinglAcnt.json FY{year}", str(result.get("error", "")))
        except _EmptyData:
            skipped.append(f"FY{year} annual report: none (013)")
    raise _EmptyData("; ".join(skipped) or "no annual report rows", source="DART")


def _dart_financials_outcome(year: int, result: dict[str, Any], skipped: list[str]) -> Outcome:
    period = re.findall(r"\d{4}\.\d{2}\.\d{2}", str(result.get("period") or ""))
    receipt = str(result.get("rcept_no") or "")[:8]
    as_of = f"FY{year} {result.get('report_name')} ({result.get('report_code')})"
    if period:
        as_of += f", period end {period[-1].replace('.', '-')}"
    if re.fullmatch(r"\d{8}", receipt):
        as_of += f", filed {_compact_to_iso(receipt)}"
    notes = list(skipped)
    if skipped:
        notes.append("get_dart_company_data falls back to this earlier annual report")
    notes.append(f"statement={result.get('fs_div')} {result.get('fs_name')}")
    accounts = result.get("financial_data") or {}
    return Outcome(as_of=as_of, coverage=f"accounts={len(accounts)}", note="; ".join(notes))


# ---------------------------------------------------------------------------
# ECOS (Bank of Korea)
# ---------------------------------------------------------------------------


def check_ecos_base_rate(ctx: CheckContext) -> Outcome:
    """Base rate table 722Y001 through BOKAPIClient.get_base_rate (one of the macro indicators)."""
    from data.bok_api_client import BOKAPIClient

    client = BOKAPIClient(api_key=_setting("ECOS_API_KEY"))
    calls = _record_http(client.session)
    result = client.get_base_rate()
    if result.get("error"):
        _raise_from_calls(calls, "ECOS", "StatisticSearch 722Y001", str(result["error"]))
        payload = _json(calls[-1]) or {}
        status = payload.get("RESULT") if isinstance(payload, dict) else None
        code = str(status.get("CODE", "")) if isinstance(status, dict) else ""
        text = f"ECOS {code}: {status.get('MESSAGE') if isinstance(status, dict) else ''}"
        if code == "INFO-200":
            raise _EmptyData(text, source="ECOS")
        if code == "INFO-100":
            raise AuthenticationError(text, source="ECOS")
        if code == "ERROR-602":
            raise RateLimitError(text, source="ECOS")
        if code:
            raise DataSourceUnavailableError(text, source="ECOS")
        raise DataQualityError("response has neither StatisticSearch.row nor RESULT", source="ECOS")
    raw = _json(calls[-1]) if calls else None
    raw_rows = raw.get("StatisticSearch", {}).get("row", []) if isinstance(raw, dict) else []
    raw_latest = max((str(r.get("TIME", "")) for r in raw_rows if isinstance(r, dict)), default="")
    latest = result.get("latest_rate")
    if not latest:
        raise _EmptyData(
            f"upstream rows={len(raw_rows)} but none was a parsable base rate (item 0101000)",
            source="ECOS",
        )
    date, rate = str(latest.get("date", "")), latest.get("rate")
    if not re.fullmatch(r"\d{8}", date) or not isinstance(rate, int | float):
        raise DataQualityError(f"latest_rate has unexpected shape: {latest!r}", source="ECOS")
    return Outcome(
        as_of=_compact_to_iso(date),
        coverage=f"points={len(result.get('base_rates') or [])} upstream rows={len(raw_rows)} "
        f"upstream latest={_compact_to_iso(raw_latest) or '-'}",
        note=f"base rate {rate}%; " + _lag_note(_compact_to_iso(date)),
    )


# ---------------------------------------------------------------------------
# News: Tavily, Naver
# ---------------------------------------------------------------------------


def check_tavily_news(ctx: CheckContext) -> Outcome:
    """TavilyNewsClient.search_company_news, what sentiment_expert calls (1 search credit)."""
    from data.tavily_api_client import TavilyNewsClient

    name = _company_name(ctx)
    result = TavilyNewsClient(_setting("TAVILY_API_KEY")).search_company_news(name, max_results=10)
    if result.get("error"):
        raise _error_from_message(str(result["error"]), "Tavily")
    items = result.get("news_items")
    if not isinstance(items, list):
        raise DataQualityError("response has no news_items list", source="Tavily")
    if not items:
        raise _EmptyData(f"0 news items for query on {name!r}", source="Tavily")
    if not all(isinstance(i, dict) and i.get("title") and i.get("url") for i in items):
        raise DataQualityError("news item without title/url", source="Tavily")
    return Outcome(
        coverage=f"items={len(items)} query={name}",
        note="client output carries no publication dates (only search_timestamp); 1 search credit used",
    )


def check_naver_news(ctx: CheckContext) -> Outcome:
    """data.naver_api_client.fetch_naver_news (same endpoint and headers as sentiment_expert)."""
    from data.naver_api_client import fetch_naver_news

    name = _company_name(ctx)
    raw = fetch_naver_news(name, display=10)
    if raw.get("error"):
        raise _error_from_message(str(raw["error"]), "Naver")
    items = raw.get("items")
    if not isinstance(items, list):
        raise DataQualityError("response has no items list", source="Naver")
    if not items:
        raise _EmptyData(f"0 news items for {name!r}", source="Naver")
    dates = []
    for item in items:
        try:
            dates.append(parsedate_to_datetime(str(item.get("pubDate"))).astimezone(KST))
        except (TypeError, ValueError):
            continue
    if not dates:
        raise DataQualityError("no parseable pubDate in items", source="Naver")
    return Outcome(
        as_of=max(dates).isoformat(timespec="minutes"),
        coverage=f"items={len(items)} oldest={min(dates).date().isoformat()}",
    )


# ---------------------------------------------------------------------------
# Global context: Alpha Vantage, CoinGecko, CNN Fear & Greed
# ---------------------------------------------------------------------------


def _client_failed(result: dict[str, Any]) -> bool:
    """Both client shapes: older ones add a 'note' next to placeholder numbers, newer ones
    return available=False with a reason and None values."""
    return "note" in result or result.get("available") is False


def _client_failure_detail(result: dict[str, Any], placeholder: str) -> str:
    if result.get("available") is False:
        return f"client returned available=False: {result.get('reason') or 'no reason given'}"
    return f"client returned placeholder values ({placeholder}) that agents would read as data"


def check_alpha_vantage_fx(ctx: CheckContext) -> Outcome:
    """AlphaVantageClient.get_exchange_rate('USD', 'KRW'): one of the 25 daily requests, cache bypassed."""
    from data.alpha_vantage_client import AlphaVantageClient

    client = AlphaVantageClient(api_key=_setting("ALPHA_VANTAGE_API_KEY"))
    client.cache_dir = None  # a live check must not answer from (or write to) the app cache
    calls = _record_http(client.session)
    result = client.get_exchange_rate("USD", "KRW")
    if _client_failed(result):
        detail = _client_failure_detail(result, "USD/KRW 1320.0")
        _raise_from_calls(calls, "Alpha Vantage", "CURRENCY_EXCHANGE_RATE", detail)
        payload = _json(calls[-1]) if calls else None
        payload = payload if isinstance(payload, dict) else {}
        text = str(payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "")
        lowered = text.lower()
        if "rate limit" in lowered or "requests per day" in lowered:
            raise RateLimitError(f"Alpha Vantage: {text}", source="Alpha Vantage")
        if "apikey" in lowered or "api key" in lowered:
            raise AuthenticationError(f"Alpha Vantage: {text}", source="Alpha Vantage")
        if text:
            raise DataSourceUnavailableError(f"Alpha Vantage: {text}", source="Alpha Vantage")
        raise DataQualityError(
            f"no usable 'Realtime Currency Exchange Rate' ({detail})", source="Alpha Vantage"
        )
    rate = result.get("rate")
    if not isinstance(rate, int | float) or rate <= 0:
        raise DataQualityError(f"rate is {rate!r}", source="Alpha Vantage")
    raw = _json(calls[-1]) if calls else None
    block = raw.get("Realtime Currency Exchange Rate", {}) if isinstance(raw, dict) else {}
    refreshed = block.get("6. Last Refreshed")
    zone = block.get("7. Time Zone")
    return Outcome(
        as_of=f"{refreshed} {zone or ''}".strip() if refreshed else None,
        coverage=f"USD/KRW rate={rate}",
        note="1 of 25 daily requests used",
    )


def check_coingecko(ctx: CheckContext) -> Outcome:
    """CoinGeckoClient.get_market_overview (simple/price + global), cache bypassed."""
    from data.coingecko_client import CoinGeckoClient

    client = CoinGeckoClient()
    client.cache_dir = None
    calls = _record_http(client.session)
    result = client.get_market_overview()
    if _client_failed(result):
        detail = _client_failure_detail(result, "0.0 prices")
        _raise_from_calls(calls, "CoinGecko", "simple/price", detail)
        raise DataQualityError(f"simple/price response not usable ({detail})", source="CoinGecko")
    coins = [k for k, v in result.items() if isinstance(v, dict) and "current_price_usd" in v]
    if not coins:
        raise _EmptyData("simple/price returned none of the requested coins", source="CoinGecko")
    btc = result.get("bitcoin") or {}
    try:
        btc_price = float(btc.get("current_price_usd") or 0)
    except (TypeError, ValueError):
        btc_price = 0.0
    if btc_price <= 0:
        raise DataQualityError("bitcoin price missing or 0", source="CoinGecko")
    global_call = next((c for c in calls if c.url.endswith("/global")), None)
    as_of = None
    notes = []
    if result.get("global"):
        payload = _json(global_call)
        updated = payload.get("data", {}).get("updated_at") if isinstance(payload, dict) else None
        as_of = _to_kst_iso(updated)
    else:
        notes.append(f"/global failed ({_describe_call(global_call)}): crypto market totals missing")
    return Outcome(as_of=as_of, coverage=f"coins={len(coins)}", note="; ".join(notes))


def check_fear_greed(ctx: CheckContext) -> Outcome:
    """FearGreedClient.get_current_index (unofficial CNN JSON), cache bypassed."""
    from data.fear_greed_client import FearGreedClient

    client = FearGreedClient()
    client.cache_dir = None
    calls = _record_http(client.session)
    result = client.get_current_index()
    if _client_failed(result):
        detail = _client_failure_detail(result, "score 50 'Neutral'")
        _raise_from_calls(calls, "CNN Fear & Greed", "graphdata", detail)
        raise DataQualityError(f"no usable 'fear_and_greed' ({detail})", source="CNN Fear & Greed")
    score = result.get("score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise DataQualityError(f"score is {score!r}", source="CNN Fear & Greed")
    raw = _json(calls[-1]) if calls else None
    block = raw.get("fear_and_greed", {}) if isinstance(raw, dict) else {}
    return Outcome(
        as_of=_to_kst_iso(block.get("timestamp")),
        coverage=f"score={score} rating={result.get('rating')}",
        note="unofficial endpoint",
    )


# ---------------------------------------------------------------------------
# Paxnet (Selenium)
# ---------------------------------------------------------------------------


def check_paxnet(ctx: CheckContext) -> Outcome:
    """Chrome + selenium readiness; with --crawl-paxnet, fetch_paxnet_discussions as community_expert."""
    chrome = next((path for path in (shutil.which(c) for c in CHROME_COMMANDS) if path), None)
    try:
        from data import paxnet_crawl_client

        selenium_ok = bool(paxnet_crawl_client.SELENIUM_AVAILABLE)
    except Exception:
        paxnet_crawl_client = None
        selenium_ok = False
    env = (
        f"Chrome/Chromium: {chrome or 'not on PATH'}; selenium: {'importable' if selenium_ok else 'missing'}"
    )
    if not ctx.crawl_paxnet:
        raise _NotSent(f"{env}; crawl skipped (pass --crawl-paxnet)")
    if not chrome or not selenium_ok or paxnet_crawl_client is None:
        raise _NotSent(f"{env}; cannot crawl")
    result = paxnet_crawl_client.fetch_paxnet_discussions(ctx.stock_code, max_posts=ctx.paxnet_max_posts)
    if result.get("error"):
        if "게시글을 찾을 수 없습니다" in str(result["error"]):
            raise _EmptyData(str(result["error"]), source="paxnet")
        raise DataSourceUnavailableError(str(result["error"]), source="paxnet")
    posts = result.get("posts") or []
    if not posts:
        raise _EmptyData("0 posts", source="paxnet")
    return Outcome(coverage=f"posts={len(posts)}", note=f"{env}; client output carries no post dates")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _gate_alpha_vantage(ctx: CheckContext) -> str | None:
    if ctx.include_alpha_vantage:
        return None
    return "skipped: free quota is 25 requests/day; pass --include-alpha-vantage to spend one"


SPECS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "fdr_prices",
        "FinanceDataReader 일봉",
        ("financial_expert", "context_expert", "advanced_technical_expert"),
        check_fdr_prices,
    ),
    CheckSpec(
        "pykrx_index_ohlcv",
        "pykrx KOSPI 지수 OHLCV",
        ("context_expert",),
        check_pykrx_index_ohlcv,
        keys=("KRX_ID", "KRX_PW"),
    ),
    CheckSpec(
        "pykrx_fundamental",
        "pykrx PER/PBR 등 기본지표",
        ("financial_expert", "comparative_expert"),
        check_pykrx_fundamental,
        keys=("KRX_ID", "KRX_PW"),
    ),
    CheckSpec(
        "pykrx_investor_trading",
        "pykrx 투자자별 거래대금",
        ("institutional_trading_expert",),
        check_pykrx_investor_trading,
        keys=("KRX_ID", "KRX_PW"),
    ),
    CheckSpec(
        "dart_corp_code",
        "DART 고유번호(corpCode.xml)",
        ("financial_expert", "esg_expert"),
        check_dart_corp_code,
        keys=("DART_API_KEY",),
    ),
    CheckSpec(
        "dart_company",
        "DART 기업개황(company.json)",
        ("financial_expert", "esg_expert"),
        check_dart_company,
        keys=("DART_API_KEY",),
    ),
    CheckSpec(
        "dart_financials",
        "DART 단일회사 주요계정(fnlttSinglAcnt.json)",
        ("financial_expert", "esg_expert"),
        check_dart_financials,
        keys=("DART_API_KEY",),
    ),
    CheckSpec(
        "ecos_base_rate",
        "ECOS 기준금리(722Y001)",
        ("context_expert", "financial_expert"),
        check_ecos_base_rate,
        keys=("ECOS_API_KEY",),
    ),
    CheckSpec(
        "tavily_news",
        "Tavily 뉴스 검색",
        ("sentiment_expert",),
        check_tavily_news,
        keys=("TAVILY_API_KEY",),
    ),
    CheckSpec(
        "naver_news",
        "Naver 뉴스 검색",
        ("sentiment_expert",),
        check_naver_news,
        keys=("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"),
        always_note=NAVER_HOLD_NOTE,
    ),
    CheckSpec(
        "alpha_vantage_fx",
        "Alpha Vantage USD/KRW",
        ("global_market_expert",),
        check_alpha_vantage_fx,
        keys=("ALPHA_VANTAGE_API_KEY",),
        gate=_gate_alpha_vantage,
    ),
    CheckSpec("coingecko", "CoinGecko 암호화폐 시세", ("global_market_expert",), check_coingecko),
    CheckSpec("fear_greed", "CNN Fear & Greed", ("global_market_expert",), check_fear_greed),
    CheckSpec(
        "paxnet",
        "Paxnet 종목토론 (Selenium)",
        ("community_expert",),
        check_paxnet,
        timeout_s=PAXNET_CRAWL_TIMEOUT_S,
    ),
)
SOURCE_IDS = tuple(spec.source for spec in SPECS)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _key_state(names: tuple[str, ...]) -> tuple[str, str]:
    """(state, note when missing). Uses the app's own validity rule (blank / placeholder = unset)."""
    if not names:
        return KEY_NOT_REQUIRED, ""
    try:
        from config.settings import validate_api_keys

        flags = validate_api_keys()
    except Exception as e:  # invalid .env values make Settings() raise at import
        return KEY_MISSING, f"config.settings could not be loaded ({type(e).__name__}); no request sent"
    missing = []
    for name in names:
        if name in _SETTINGS_FLAG:
            present = bool(flags.get(_SETTINGS_FLAG[name]))
        else:  # KRX_ID / KRX_PW: pykrx reads os.environ directly
            present = bool(os.environ.get(name, "").strip())
        if not present:
            missing.append(name)
    if missing:
        return KEY_MISSING, f"{'/'.join(missing)} not configured; no request sent"
    return KEY_SET, ""


def _result_from_error(error: BaseException) -> dict[str, Any]:
    """Map an exception raised inside a check to the request/data states."""
    if isinstance(error, _NotSent):
        return {"request": REQ_NOT_SENT, "data": DATA_NA, "note": str(error)}
    if isinstance(error, _EmptyData):
        return {"request": REQ_OK, "data": DATA_EMPTY, "note": str(error)}
    if isinstance(error, DataQualityError):
        return {
            "request": REQ_OK,
            "data": DATA_INVALID,
            "note": str(error),
            "error_type": "DataQualityError",
        }
    if isinstance(error, ConfigurationError):
        return {
            "request": REQ_NOT_SENT,
            "data": DATA_NA,
            "note": str(error),
            "error_type": "ConfigurationError",
        }
    if isinstance(error, ExternalAPIError):
        return {
            "request": REQ_FAILED,
            "data": DATA_NA,
            "note": str(error),
            "error_type": type(error).__name__,
            "http_status": error.status_code,
        }
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "code", None)
    if not isinstance(status, int) or not 100 <= status <= 599:
        status = _status_from_text(str(error))
    note = f"{type(error).__name__}: {error}"
    if status is not None:
        typed = type(_error_for_status(status, note, "")).__name__
    elif isinstance(error, requests.RequestException | ConnectionError | TimeoutError):
        typed = "DataSourceUnavailableError"
    else:
        typed = type(error).__name__
    return {"request": REQ_FAILED, "data": DATA_NA, "note": note, "error_type": typed, "http_status": status}


def _finish(spec: CheckSpec, key: str, fields: dict[str, Any], elapsed: float) -> SourceResult:
    note = fields.get("note", "")
    if spec.always_note:
        note = f"{note}; {spec.always_note}" if note else spec.always_note
    as_of = fields.get("as_of")
    coverage = fields.get("coverage")
    return SourceResult(
        source=spec.source,
        label=spec.label,
        agents=list(spec.agents),
        key=key,
        request=fields["request"],
        data=fields["data"],
        as_of=_redact(as_of) if as_of else None,
        coverage=_clip(_redact(coverage)) if coverage else None,
        note=_clip(_redact(note)),
        error_type=fields.get("error_type"),
        http_status=fields.get("http_status"),
        elapsed_s=round(elapsed, 2),
    )


def run_check(spec: CheckSpec, ctx: CheckContext, timeout_s: float = DEFAULT_TIMEOUT_S) -> SourceResult:
    """Run one check in its own daemon thread, bounded by a timeout. Never raises."""
    key, key_note = _key_state(spec.keys)
    if key == KEY_MISSING:
        return _finish(spec, key, {"request": REQ_NOT_SENT, "data": DATA_NA, "note": key_note}, 0.0)
    if spec.gate is not None:
        reason = spec.gate(ctx)
        if reason:
            return _finish(spec, key, {"request": REQ_NOT_SENT, "data": DATA_NA, "note": reason}, 0.0)

    timeout = max(timeout_s, spec.timeout_s or 0.0)
    buffer = io.StringIO()
    ctx.outputs[spec.source] = buffer
    box: dict[str, Any] = {}

    def target() -> None:
        _THREAD_BUFFERS[threading.get_ident()] = buffer
        try:
            box["outcome"] = spec.run(ctx)
        except BaseException as e:  # a library calling sys.exit must not end the whole run
            box["error"] = e
        finally:
            _THREAD_BUFFERS.pop(threading.get_ident(), None)

    started = time.monotonic()
    thread = threading.Thread(target=target, name=f"check-{spec.source}", daemon=True)
    thread.start()
    thread.join(timeout)
    elapsed = time.monotonic() - started
    if thread.is_alive():
        _ABANDONED_THREADS.append(thread)
        fields = {
            "request": REQ_TIMEOUT,
            "data": DATA_NA,
            "note": f"no answer within {timeout:.0f}s; check abandoned",
            "error_type": "DataSourceUnavailableError",
        }
        return _finish(spec, key, fields, elapsed)
    if "error" in box:
        return _finish(spec, key, _result_from_error(box["error"]), elapsed)
    outcome: Outcome = box["outcome"]
    fields = {
        "request": REQ_OK,
        "data": DATA_OK,
        "as_of": outcome.as_of,
        "coverage": outcome.coverage,
        "note": outcome.note,
    }
    return _finish(spec, key, fields, elapsed)


def run_checks(
    specs: Sequence[CheckSpec], ctx: CheckContext, timeout_s: float = DEFAULT_TIMEOUT_S
) -> list[SourceResult]:
    """Run checks one after another; each is isolated, so one failure never stops the rest."""
    return [run_check(spec, ctx, timeout_s) for spec in specs]


def evaluate_minimum(results: Sequence[SourceResult]) -> dict[str, Any]:
    by_source = {r.source: r for r in results}
    missing = [s for s in MINIMUM_REQUIRED if not (s in by_source and by_source[s].works)]
    price = next((s for s in PRICE_SOURCES if s in by_source and by_source[s].works), None)
    if price is None:
        missing.append("one of " + "|".join(PRICE_SOURCES))
    return {
        "ok": not missing,
        "required": [*MINIMUM_REQUIRED, "one of " + "|".join(PRICE_SOURCES)],
        "price_source": price,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def render_report(
    results: Sequence[SourceResult], ctx: CheckContext, checked_at: str, minimum: dict[str, Any]
) -> str:
    lines = [
        f"TuSimReport source check: {ctx.stock_code} {_company_name(ctx)}  checked_at={checked_at}",
        "",
        f"{'SOURCE':<24}{'KEY':<14}{'REQUEST':<10}{'DATA':<9}AS-OF [COVERAGE]",
    ]
    for r in results:
        as_of = r.as_of or "-"
        if r.coverage:
            as_of += f" [{r.coverage}]"
        lines.append(f"{r.source:<24}{r.key:<14}{r.request:<10}{r.data:<9}{as_of}")
    lines += ["", "Notes:"]
    for r in results:
        status = []
        if r.error_type:
            status.append(r.error_type)
        if r.http_status is not None:
            status.append(f"HTTP {r.http_status}")
        if r.elapsed_s:
            status.append(f"{r.elapsed_s:.1f}s")
        head = f"- {r.source} ({r.label}) agents: {', '.join(r.agents)}"
        if status:
            head += f" | {' '.join(status)}"
        lines.append(head)
        if r.note:
            lines.append(f"    {r.note}")
    by_source = {r.source: r for r in results}
    naver = by_source.get("naver_news")
    if naver is not None and naver.key == KEY_SET:
        lines += ["", f"Naver: {NAVER_HOLD_NOTE}. This run only shows connectivity."]
    lines.append("")
    if minimum["ok"]:
        lines.append(f"Minimum set (DART + ECOS + price via {minimum['price_source']}): OK -> exit 0")
    else:
        lines.append(
            f"Minimum set (DART + ECOS + one price source): NOT met, missing {minimum['missing']} -> exit 1"
        )
    return "\n".join(lines)


def render_captured(ctx: CheckContext, max_lines: int = 20) -> str:
    blocks = []
    for source, buffer in ctx.outputs.items():
        text = buffer.getvalue()
        if not text.strip():
            continue
        kept = [
            _redact(line)
            for line in text.splitlines()
            if line.strip() and "로그인 ID" not in line  # pykrx prints the KRX login ID
        ][-max_lines:]
        blocks.append(f"--- captured output: {source} (last {len(kept)} lines, redacted) ---")
        blocks.extend(kept)
    return "\n".join(blocks) if blocks else "(no output captured from checks)"


def build_payload(
    results: Sequence[SourceResult],
    ctx: CheckContext,
    checked_at: str,
    minimum: dict[str, Any],
    options: dict[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    return {
        "checked_at": checked_at,
        "stock_code": ctx.stock_code,
        "company_name": _company_name(ctx),
        "options": options,
        "states": {
            "key": [KEY_SET, KEY_MISSING, KEY_NOT_REQUIRED],
            "request": [REQ_OK, REQ_FAILED, REQ_TIMEOUT, REQ_NOT_SENT],
            "data": [DATA_OK, DATA_EMPTY, DATA_INVALID, DATA_NA],
        },
        "minimum": minimum,
        "exit_code": exit_code,
        "results": [asdict(r) for r in results],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _lookup_name(stock_code: str) -> str | None:
    try:
        from ui.stock_database import STOCK_DATABASE
    except Exception:
        return None
    for group in STOCK_DATABASE.values():
        if stock_code in group:
            return group[stock_code]
    return None


def _parse_only(value: str) -> list[str]:
    ids = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [v for v in ids if v not in SOURCE_IDS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown source id(s) {unknown}; choose from {', '.join(SOURCE_IDS)}"
        )
    return ids


def _parse_stock(value: str) -> str:
    if not re.fullmatch(r"[0-9A-Z]{6}", value):
        raise argparse.ArgumentTypeError("stock code must be 6 characters, e.g. 005930")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python scripts/check_sources.py",
        description=(
            "Exercise every external data source once through the repo's own client code and report, "
            "per source, key / request / data / as-of states. Exit 0 when DART + ECOS + one price "
            "source work, 1 otherwise. Key values are never printed."
        ),
        epilog=(
            "pykrx: importing pykrx logs in to data.krx.co.kr with KRX_ID/KRX_PW (it can end another "
            "session of the same account) and prints the login ID. This script imports pykrx lazily, "
            "inside the pykrx checks, only when both are set, and captures what it prints. "
            "Source ids: " + ", ".join(SOURCE_IDS)
        ),
    )
    parser.add_argument("--stock", type=_parse_stock, default=DEFAULT_STOCK_CODE, help="6-char code (005930)")
    parser.add_argument("--name", default=None, help="company name for news queries (default: lookup)")
    parser.add_argument("--only", type=_parse_only, default=None, help="comma-separated source ids")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="per-check timeout in seconds (default 60)"
    )
    parser.add_argument("--json", dest="json_path", default=None, help="also write the result as JSON here")
    parser.add_argument(
        "--include-alpha-vantage",
        action="store_true",
        help="spend 1 of the 25 free daily Alpha Vantage requests (USD/KRW)",
    )
    parser.add_argument(
        "--crawl-paxnet",
        action="store_true",
        help="actually crawl Paxnet with Selenium (default: only check Chrome/Chromium + selenium)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show what each check printed or logged (redacted)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    saved_streams = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = _OutputRouter(saved_streams[0]), _OutputRouter(saved_streams[1])
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    try:
        ctx = CheckContext(
            stock_code=args.stock,
            company_name=args.name or _lookup_name(args.stock),
            include_alpha_vantage=args.include_alpha_vantage,
            crawl_paxnet=args.crawl_paxnet,
        )
        specs = [s for s in SPECS if args.only is None or s.source in args.only]
        checked_at = kst_isoformat()
        results = run_checks(specs, ctx, timeout_s=args.timeout)
        minimum = evaluate_minimum(results)
        exit_code = 0 if minimum["ok"] else 1
        print(render_report(results, ctx, checked_at, minimum))
        if args.verbose:
            print()
            print(render_captured(ctx))
        if args.json_path:
            options = {
                "only": args.only,
                "timeout_s": args.timeout,
                "include_alpha_vantage": args.include_alpha_vantage,
                "crawl_paxnet": args.crawl_paxnet,
            }
            payload = build_payload(results, ctx, checked_at, minimum, options, exit_code)
            try:
                Path(args.json_path).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            except OSError as e:
                print(f"could not write {args.json_path}: {e}", file=sys.stderr)
                return 1
            print(f"JSON written to {args.json_path}")
        return exit_code
    finally:
        sys.stdout.flush()
        root.removeHandler(handler)
        root.setLevel(previous_level)
        sys.stdout, sys.stderr = saved_streams


if __name__ == "__main__":
    code = main()
    if _abandoned_threads_alive():
        # A check overran its timeout; do not wait for it (or for library worker threads it started).
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    sys.exit(code)
