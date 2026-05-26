"""BaseAPIClient force_refresh + LRU eviction 동작 검증."""

from __future__ import annotations

import os
import time
from pathlib import Path

from data.base_client import BaseAPIClient


def test_force_refresh_bypasses_live_cache(tmp_path: Path) -> None:
    """캐시가 TTL 안이어도 force_refresh=True면 None을 돌려준다."""
    client = BaseAPIClient(cache_subdir="t1")
    client.cache_dir = str(tmp_path)

    client.save_cache("key1", {"v": 1})

    # 캐시 hit 정상 동작
    assert client.get_cached("key1", max_age_hours=24) == {"v": 1}
    # force_refresh로 우회
    assert client.get_cached("key1", max_age_hours=24, force_refresh=True) is None
    # 캐시 파일 자체는 보존 (다음 호출에서 재사용 가능)
    assert os.path.exists(os.path.join(str(tmp_path), "key1.json"))


def test_lru_eviction_keeps_most_recent(tmp_path: Path, monkeypatch) -> None:
    """MAX_CACHE_ENTRIES 초과 시 가장 오래된 파일부터 삭제."""
    # 한도를 작게 잡아 테스트 시간 단축
    monkeypatch.setattr(BaseAPIClient, "MAX_CACHE_ENTRIES", 5)
    client = BaseAPIClient(cache_subdir="t2")
    client.cache_dir = str(tmp_path)

    # 10개 쓰면 5개로 줄어야 함. 그리고 가장 마지막에 쓴 5개가 살아 있어야.
    for i in range(10):
        client.save_cache(f"key{i:02d}", {"i": i})
        # mtime 차이를 강제 — 같은 시각에 쓰면 sort 순서가 불안정
        time.sleep(0.01)

    remaining = sorted(f for f in os.listdir(str(tmp_path)) if f.endswith(".json"))
    assert len(remaining) == 5
    # 살아남은 건 key05..key09 (가장 최근 5개)
    assert remaining == [f"key{i:02d}.json" for i in range(5, 10)]


def test_eviction_skips_hidden_tempfiles(tmp_path: Path, monkeypatch) -> None:
    """`.tmp` 부산물이나 hidden file은 카운트하지 않는다.

    여기서 카운트되면 정상 캐시가 의도치 않게 evict됨.
    """
    monkeypatch.setattr(BaseAPIClient, "MAX_CACHE_ENTRIES", 3)
    client = BaseAPIClient(cache_subdir="t3")
    client.cache_dir = str(tmp_path)

    # 정상 3개
    for i in range(3):
        client.save_cache(f"key{i}", {"i": i})
        time.sleep(0.01)

    # hidden file 5개 직접 만들기 (atomic write 중간 부산물 시뮬레이션)
    for i in range(5):
        with open(os.path.join(str(tmp_path), f".garbage{i}.tmp"), "w") as f:
            f.write("trash")

    # 4번째 정상 캐시 추가 — 한도 초과 시 hidden은 무시하고 정상 1개 evict
    client.save_cache("key3", {"i": 3})

    visible = sorted(f for f in os.listdir(str(tmp_path)) if f.endswith(".json"))
    assert len(visible) == 3
    # 가장 오래된 key0가 evict되고 key1, key2, key3 살아 있음
    assert visible == ["key1.json", "key2.json", "key3.json"]
