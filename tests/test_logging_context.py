"""bind_session이 LogRecord에 correlation 정보를 정확히 주입하는지."""

from __future__ import annotations

import logging
import threading

from utils.logging_context import (
    KSTContextFilter,
    bind_session,
    current_session_id,
)


def _capture_record(do_log) -> logging.LogRecord:
    """주어진 콜러블 안에서 발생한 마지막 LogRecord를 잡아 반환."""
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture()
    handler.addFilter(KSTContextFilter())
    logger = logging.getLogger("test_capture")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    do_log(logger)
    return captured[-1]


def test_bind_session_injects_attributes():
    def do_log(lg: logging.Logger) -> None:
        with bind_session(session_id="abc123", stock_code="005930"):
            lg.info("hi")

    rec = _capture_record(do_log)
    assert rec.session_id == "abc123"
    assert rec.stock_code == "005930"


def test_outside_session_defaults_to_dash():
    def do_log(lg: logging.Logger) -> None:
        lg.info("orphan log")

    rec = _capture_record(do_log)
    assert rec.session_id == "-"
    assert rec.stock_code == "-"


def test_session_auto_id_when_not_provided():
    with bind_session() as sid:
        assert current_session_id() == sid
        assert len(sid) == 12
        assert all(c in "0123456789abcdef" for c in sid)


def test_nested_bindings_restore_outer_context():
    with bind_session(session_id="outer", stock_code="000001"):
        with bind_session(session_id="inner", stock_code="000002"):
            assert current_session_id() == "inner"
        # 안쪽 블록을 빠져나오면 outer 컨텍스트로 복원돼야 한다.
        assert current_session_id() == "outer"


def test_threads_have_independent_contexts():
    """ContextVar는 스레드별 격리. 한 스레드의 바인딩이 다른 스레드를 더럽혀선 안 된다."""
    seen: dict[str, str | None] = {}

    def worker(name: str) -> None:
        with bind_session(session_id=name):
            seen[name] = current_session_id()

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seen == {f"t{i}": f"t{i}" for i in range(5)}
