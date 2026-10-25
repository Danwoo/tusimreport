"""utils.redaction + configure_logging: API 키가 로그 출력에 남지 않는지 검증."""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from utils.logging_context import configure_logging
from utils.redaction import (
    MASK,
    SecretRedactionFilter,
    configured_secrets,
    install_record_redaction,
    redact,
)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """루트 핸들러·레벨·LogRecord 팩토리를 테스트 뒤 원래대로 돌린다."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    factory = logging.getLogRecordFactory()
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        logging.setLogRecordFactory(factory)


@pytest.fixture
def dart_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    from config.settings import settings

    secret = "dartsecret0123456789"
    monkeypatch.setattr(settings, "dart_api_key", secret)
    return secret


def _stream_handler(*filters: logging.Filter) -> tuple[logging.Handler, io.StringIO]:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for f in filters:
        handler.addFilter(f)
    return handler, buffer


def _isolated_logger(name: str, handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers[:] = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


@pytest.mark.parametrize(
    "param",
    ["crtfc_key", "apikey", "api_key", "key", "serviceKey", "APIKEY", "servicekey"],
)
def test_query_param_values_are_masked(param: str) -> None:
    text = f"GET https://api.test/x?corp_code=1&{param}=abc123def&page=2 failed"
    assert redact(text, secrets=[]) == f"GET https://api.test/x?corp_code=1&{param}={MASK}&page=2 failed"


def test_similar_param_names_are_left_alone() -> None:
    text = "https://api.test/x?monkey=banana&keyword=samsung&key_id=7"
    assert redact(text, secrets=[]) == text


def test_dict_repr_and_ecos_path_are_masked() -> None:
    assert redact("params={'apikey': 'ZZZ999', 'symbol': 'SPY'}", secrets=[]) == (
        f"params={{'apikey': '{MASK}', 'symbol': 'SPY'}}"
    )
    url = "https://ecos.bok.or.kr/api/StatisticSearch/ECOSKEY77/json/kr/1/1000/722Y001/D/20240101/20241231"
    assert redact(url, secrets=[]) == (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{MASK}/json/kr/1/1000/722Y001/D/20240101/20241231"
    )


def test_configured_secret_values_are_masked(dart_secret: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRX_PW", "krx-password-1")

    secrets = configured_secrets()
    assert dart_secret in secrets
    assert "krx-password-1" in secrets

    text = f"failed: {dart_secret} / login krx-password-1"
    assert redact(text) == f"failed: {MASK} / login {MASK}"


def test_short_secret_values_are_not_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "tavily_api_key", "abc")
    monkeypatch.setenv("KRX_PW", "pw12")

    assert "abc" not in configured_secrets()
    assert redact("abc pw12 abcdef") == "abc pw12 abcdef"


def test_non_secret_fields_are_not_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "naver_client_id", "public-client-id")
    monkeypatch.setattr(settings, "naver_client_secret", "naver-secret-xyz")

    secrets = configured_secrets()
    assert "naver-secret-xyz" in secrets
    assert "public-client-id" not in secrets


def test_handler_filter_masks_message_args_and_traceback(dart_secret: str) -> None:
    handler, buffer = _stream_handler(SecretRedactionFilter())
    logger = _isolated_logger("test_redaction.handler", handler)

    logger.warning("request failed: %s", f"https://opendart.fss.or.kr/api/list.json?crtfc_key={dart_secret}")
    try:
        raise RuntimeError(f"boom with {dart_secret}")
    except RuntimeError:
        logger.exception("upstream error")

    output = buffer.getvalue()
    assert dart_secret not in output
    assert f"crtfc_key={MASK}" in output
    assert "RuntimeError: boom with ***" in output


def test_record_factory_covers_handlers_added_later(dart_secret: str, restore_logging: None) -> None:
    """main.py는 configure_logging() 뒤 setup_logging()으로 핸들러를 갈아 끼운다."""
    configure_logging("INFO")
    root = logging.getLogger()

    # utils.helpers.setup_logging과 같은 일: 핸들러 전부 제거 후 필터 없는 핸들러 부착.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    handler, buffer = _stream_handler()
    root.addHandler(handler)

    logging.getLogger("data.dart_api_client").error(f"DART API request failed: {dart_secret}")
    assert dart_secret not in buffer.getvalue()
    assert MASK in buffer.getvalue()


def test_configure_logging_attaches_filter_and_is_idempotent(restore_logging: None) -> None:
    configure_logging("INFO")
    configure_logging("INFO")

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert any(isinstance(f, SecretRedactionFilter) for f in root.handlers[0].filters)

    factory = logging.getLogRecordFactory()
    install_record_redaction()
    assert logging.getLogRecordFactory() is factory


def test_untouched_records_keep_their_args(restore_logging: None) -> None:
    install_record_redaction()
    record = logging.getLogRecordFactory()("x", logging.INFO, __file__, 1, "value=%s", ("plain",), None)
    assert record.args == ("plain",)
    assert record.getMessage() == "value=plain"


def test_main_py_logging_sequence_redacts_log_file(
    dart_secret: str, restore_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main.py 순서 그대로: configure_logging() → setup_logging(enable_file_logging=True)."""
    from utils.helpers import setup_logging

    monkeypatch.chdir(tmp_path)
    configure_logging("INFO")
    setup_logging("INFO", enable_file_logging=True)
    root = logging.getLogger()
    try:
        ecos_url = f"https://ecos.bok.or.kr/api/StatisticSearch/{dart_secret}/json/kr/1/1000/722Y001/D/20240101/20241231"
        logging.getLogger("data.bok_api_client").warning(f"BOK API request failed: 404 for url: {ecos_url}")
        logging.getLogger("urllib3.connectionpool").warning(
            '"GET /api/list.json?corp_code=00126380&crtfc_key=abcd1234efgh HTTP/1.1" 200'
        )
    finally:
        for handler in root.handlers:
            handler.flush()
            handler.close()

    log_text = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "logs").glob("*.log"))
    assert "BOK API request failed" in log_text
    assert dart_secret not in log_text
    assert "abcd1234efgh" not in log_text
    assert f"crtfc_key={MASK}" in log_text
