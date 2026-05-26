"""TUSIM_CACHE_DIR 환경변수가 캐시 위치 override를 정상 수행하는지."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from data.base_client import BaseAPIClient


def test_env_var_overrides_default_tempdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TUSIM_CACHE_DIR가 설정되면 캐시 루트를 거기로 옮긴다."""
    monkeypatch.setenv("TUSIM_CACHE_DIR", str(tmp_path))

    client = BaseAPIClient(cache_subdir="env_test")
    # cache_dir이 tmp_path/env_test로 잡혔는지
    assert client.cache_dir is not None
    assert client.cache_dir.startswith(str(tmp_path))
    # 디렉토리도 자동 생성됐는지
    assert os.path.isdir(client.cache_dir)


def test_without_env_var_uses_tempdir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUSIM_CACHE_DIR", raising=False)
    client = BaseAPIClient(cache_subdir="default_test")
    assert client.cache_dir is not None
    # tempdir이 거의 항상 /tmp 또는 OS 기본 경로
    # 환경변수 미설정 시 그 아래에 자리 잡아야 함
    import tempfile as _t

    assert client.cache_dir.startswith(_t.gettempdir())


def test_empty_env_var_falls_back_to_tempdir(monkeypatch: pytest.MonkeyPatch) -> None:
    """빈 문자열은 None과 동등하게 취급 — 일반적인 unix shell 관행."""
    monkeypatch.setenv("TUSIM_CACHE_DIR", "")
    client = BaseAPIClient(cache_subdir="empty_env_test")
    import tempfile as _t

    assert client.cache_dir is not None
    assert client.cache_dir.startswith(_t.gettempdir())
