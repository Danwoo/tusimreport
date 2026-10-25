"""setup_check.py가 출력하는 값에 비밀이 섞이지 않는지 검증."""

from __future__ import annotations

import builtins
import os
from typing import Any

import pytest

import setup_check


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://alice:s3cretpw@llm.internal.example/v1", "llm.internal.example"),
        ("http://user:pw@127.0.0.1:8080/v1", "127.0.0.1:8080"),
        ("https://kiraai.vn/api/v1", "kiraai.vn"),
        (None, "provider 기본값"),
    ],
)
def test_endpoint_host_drops_url_credentials(base_url: str | None, expected: str) -> None:
    assert setup_check._endpoint_host(base_url) == expected


def test_import_check_hides_and_restores_krx_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = {
        "config.settings",
        "utils.helpers",
        "agents.korean_context_agent",
        "core.korean_supervisor_langgraph",
    }
    real_import = builtins.__import__
    seen: dict[str, str | None] = {}

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in targets:
            seen[name] = os.environ.get("KRX_ID")
            return None
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("KRX_ID", "someone")
    monkeypatch.setenv("KRX_PW", "secret")
    monkeypatch.setattr(builtins, "__import__", fake_import)

    ok = setup_check.run_import_test()

    monkeypatch.setattr(builtins, "__import__", real_import)
    assert ok is True
    assert set(seen) == targets
    assert all(value is None for value in seen.values())
    assert os.environ["KRX_ID"] == "someone"
    assert os.environ["KRX_PW"] == "secret"
