"""data.base_client.BaseAPIClient 단위 테스트."""

from __future__ import annotations

import os
import tempfile
import time

from data.base_client import BaseAPIClient


def test_cache_roundtrip(tmp_path, monkeypatch):
    """저장 → 조회가 정상 작동하고 TTL 내라면 동일 데이터 반환."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    # base client는 /tmp/<subdir>을 쓰므로 임시 디렉토리로 격리
    client = BaseAPIClient(cache_subdir=f"test_cache_{os.getpid()}")
    client.save_cache("foo", {"x": 1, "y": [1, 2, 3]})
    assert client.get_cached("foo", max_age_hours=1) == {"x": 1, "y": [1, 2, 3]}


def test_cache_miss_returns_none():
    client = BaseAPIClient(cache_subdir=f"test_cache_miss_{os.getpid()}")
    assert client.get_cached("nonexistent_key", max_age_hours=1) is None


def test_cache_expired_returns_none():
    """TTL을 0에 가깝게 두면 즉시 만료된 것으로 간주."""
    client = BaseAPIClient(cache_subdir=f"test_cache_expire_{os.getpid()}")
    client.save_cache("foo", {"a": 1})
    time.sleep(0.05)
    assert client.get_cached("foo", max_age_hours=1e-9) is None


def test_no_cache_subdir_disables_cache():
    """cache_subdir=None이면 캐싱 비활성, save/get 모두 안전."""
    client = BaseAPIClient(cache_subdir=None)
    client.save_cache("foo", {"a": 1})  # no-op이어야 함 (raise 안 됨)
    assert client.get_cached("foo", max_age_hours=1) is None


def test_session_has_user_agent_header():
    client = BaseAPIClient(cache_subdir=None, user_agent="TestAgent/9.9")
    assert client.session.headers["User-Agent"] == "TestAgent/9.9"


def test_default_user_agent():
    client = BaseAPIClient(cache_subdir=None)
    assert "TuSimReport" in client.session.headers["User-Agent"]
