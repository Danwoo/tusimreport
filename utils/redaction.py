"""로그에 섞여 들어가는 API 키를 가린다.

ECOS 키는 URL 경로에, DART `crtfc_key`·Alpha Vantage `apikey`는 쿼리
파라미터에 실린다. requests 예외 메시지는 요청 URL을 그대로 담으므로
`logger.warning(f"... {e}")` 한 줄이 키를 로그 파일에 남길 수 있다.

두 가지를 가린다:
  (a) `config.settings`에 설정된 비밀 값(필드명이 `_key`/`_secret`/`_api_key`로
      끝나는 것)과 `os.environ["KRX_PW"]` — 6자 미만 값은 흔한 문자열을
      망가뜨릴 수 있어 건드리지 않는다.
  (b) 이름이 crtfc_key/apikey/api_key/key/serviceKey인 쿼리 파라미터 값과
      ECOS URL 경로의 키 세그먼트 — 위치로 식별하므로 길이와 무관하게 가린다.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from typing import Any

MASK = "***"
MIN_SECRET_LENGTH = 6

_SECRET_FIELD_SUFFIXES = ("_key", "_secret", "_api_key")
_SECRET_ENV_VARS = ("KRX_PW",)
SECRET_QUERY_PARAMS = ("crtfc_key", "apikey", "api_key", "key", "serviceKey")

_PARAM_NAMES = "|".join(re.escape(name) for name in SECRET_QUERY_PARAMS)
# `?apikey=...` / `&crtfc_key=...` in URLs and exception messages.
_QUERY_PARAM_RE = re.compile(rf"([?&](?:{_PARAM_NAMES})=)[^&\s#'\"<>]+", re.IGNORECASE)
# `'apikey': '...'` in a logged params dict repr.
_DICT_PARAM_RE = re.compile(rf"(['\"](?:{_PARAM_NAMES})['\"]\s*:\s*['\"])[^'\"]+", re.IGNORECASE)
# ECOS puts the key in the path: /api/StatisticSearch/<KEY>/json/...
_ECOS_PATH_RE = re.compile(r"(ecos\.bok\.or\.kr/api/[A-Za-z]+/)[^/\s'\"]+")


def _settings_secrets() -> list[str]:
    try:
        from config.settings import settings
    except Exception:  # settings can be mid-import when it logs during its own import
        return []
    values: list[str] = []
    for name in type(settings).model_fields:
        if name.endswith(_SECRET_FIELD_SUFFIXES):
            value = getattr(settings, name, None)
            if isinstance(value, str):
                values.append(value.strip())
    return values


def configured_secrets() -> list[str]:
    """현재 설정된 비밀 값 목록 (6자 이상, 긴 것부터).

    설정은 런타임에 바뀔 수 있어(사이드바 입력, 테스트) 매번 다시 읽는다.
    """
    values = _settings_secrets()
    for env_name in _SECRET_ENV_VARS:
        env_value = os.environ.get(env_name)
        if env_value:
            values.append(env_value.strip())
    unique = {value for value in values if len(value) >= MIN_SECRET_LENGTH}
    return sorted(unique, key=len, reverse=True)


def redact(text: str, secrets: Iterable[str] | None = None) -> str:
    """`text`에서 비밀 값과 키 파라미터 값을 `***`로 바꾼다.

    Args:
        text: 원문.
        secrets: 가릴 값 목록. None이면 `configured_secrets()`를 쓴다.
    """
    if not text:
        return text
    if secrets is None:
        values = configured_secrets()
    else:
        values = sorted({s for s in secrets if s and len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True)
    for value in values:
        if value in text:
            text = text.replace(value, MASK)
    text = _QUERY_PARAM_RE.sub(lambda m: m.group(1) + MASK, text)
    text = _DICT_PARAM_RE.sub(lambda m: m.group(1) + MASK, text)
    return _ECOS_PATH_RE.sub(lambda m: m.group(1) + MASK, text)


def redact_record(record: logging.LogRecord) -> None:
    """LogRecord의 메시지·예외 텍스트·스택을 제자리에서 가린다. 절대 raise하지 않는다."""
    try:
        try:
            message = record.getMessage()
        except Exception:  # malformed %-args: leave it for logging's own handleError
            message = None
        if message is not None:
            redacted = redact(message)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        if record.exc_info and not record.exc_text:
            exc_text = logging.Formatter().formatException(record.exc_info)
            redacted_exc = redact(exc_text)
            if redacted_exc != exc_text:
                record.exc_text = redacted_exc
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
    except Exception:  # redaction must never break logging
        pass


class SecretRedactionFilter(logging.Filter):
    """핸들러에 붙이는 비밀 값 마스킹 필터. 레코드를 버리지 않는다."""

    def filter(self, record: logging.LogRecord) -> bool:
        redact_record(record)
        return True


class _RedactingRecordFactory:
    """기존 LogRecord 팩토리를 감싸 만들어지는 모든 레코드를 가린다."""

    def __init__(self, wrapped: Callable[..., logging.LogRecord]) -> None:
        self.wrapped = wrapped

    def __call__(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        record = self.wrapped(*args, **kwargs)
        redact_record(record)
        return record


def install_record_redaction() -> None:
    """프로세스 전역 LogRecord 팩토리에 마스킹을 건다 (중복 설치 안 함).

    핸들러 필터만으로는 부족하다: main.py는 `configure_logging()` 뒤에
    `utils.helpers.setup_logging()`을 불러 루트 핸들러를 전부 갈아 끼우고
    파일 핸들러를 새로 단다. 팩토리 단계에서 가리면 나중에 붙는 핸들러,
    propagate=False인 서드파티 로거의 핸들러까지 모두 가려진 레코드를 받는다.
    """
    current = logging.getLogRecordFactory()
    if isinstance(current, _RedactingRecordFactory):
        return
    logging.setLogRecordFactory(_RedactingRecordFactory(current))
