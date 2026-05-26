"""분석 세션별 correlation ID를 로그에 자동 주입.

문제: 사용자가 "어제 005930 분석할 때 어떤 에이전트가 실패했어?"라고
물어보면 답할 수 없다. 로그는 plain message만 있고 어느 종목/어느 세션
요청 와중이었는지 구분할 키가 없기 때문.

해결: `contextvars.ContextVar`로 (session_id, stock_code)를 한 곳에
저장하고, `KSTContextFilter`가 `LogRecord`에 attribute로 주입한다.
포맷터는 그 attribute를 사용해 `[session=... stock=...] message` 형태로
출력한다. asyncio/스레드 안전 (ContextVar의 보장).

사용:
    from utils.logging_context import bind_session, configure_logging
    configure_logging()  # 앱 부팅 시 한 번
    with bind_session(session_id="abc", stock_code="005930"):
        # 이 블록 안의 모든 로그에 [session=abc stock=005930] 접두사
        run_analysis(...)
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)
_stock_code: contextvars.ContextVar[str | None] = contextvars.ContextVar("stock_code", default=None)


class KSTContextFilter(logging.Filter):
    """LogRecord에 session_id / stock_code 속성을 채워 넣는다."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id.get() or "-"
        record.stock_code = _stock_code.get() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    """프로젝트 표준 로깅 포맷을 한 번 세팅.

    `level`은 string("INFO"/"DEBUG"). pyproject나 .env에서 LOG_LEVEL로
    제어할 수 있도록 string으로 받는다.
    """
    fmt = "%(asctime)s [%(levelname)s] [s=%(session_id)s c=%(stock_code)s] %(name)s: %(message)s"
    root = logging.getLogger()
    # 기존 핸들러 정리 후 표준 핸들러 1개만 부착. Streamlit이 자체적으로
    # 핸들러를 추가하기 전에 호출하면 중복 출력 방지에 효과적.
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(KSTContextFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())


@contextmanager
def bind_session(*, session_id: str | None = None, stock_code: str | None = None) -> Iterator[str]:
    """이 블록의 모든 로그에 session_id/stock_code 주입.

    `session_id=None`이면 새 uuid를 자동 발급해 yield한다 — 호출자가
    수동으로 ID를 만들지 않아도 되도록.

    Yields:
        실제로 바인딩된 session_id. 호출자가 응답에 echo back할 수 있다.
    """
    sid = session_id or uuid.uuid4().hex[:12]
    tok_s = _session_id.set(sid)
    tok_c = _stock_code.set(stock_code)
    try:
        yield sid
    finally:
        _session_id.reset(tok_s)
        _stock_code.reset(tok_c)


def current_session_id() -> str | None:
    """진단/응답 echo용. 컨텍스트 밖이면 None."""
    return _session_id.get()
