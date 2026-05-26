"""BaseAPIClient 캐시의 동시 쓰기 안전성 테스트.

기존 save_cache는 with open(...) → json.dump으로 직접 썼다.
한 스레드가 쓰는 도중 다른 스레드가 같은 키를 읽으면 partial JSON을
읽고 JSONDecodeError가 날 가능성이 있었다.

지금은 tempfile + os.replace로 atomic하게 바꿨다. 이 테스트는 그 회귀를 막는다.
"""

import os
import tempfile
import threading

from data.base_client import BaseAPIClient


class TestAtomicCacheWrite:
    def test_concurrent_writes_never_produce_partial_file(self, tmp_path, monkeypatch):
        # cache_subdir이 /tmp 아래 고정이므로 BaseAPIClient를 그대로 쓰되
        # 충돌 회피를 위해 서브디렉토리만 임시 경로로 우회
        client = BaseAPIClient(cache_subdir="test_atomic_write_cache")
        # 안전을 위해 cache_dir을 tmp_path로 강제
        client.cache_dir = str(tmp_path)

        large_payload = {"data": "x" * 50_000, "items": list(range(1000))}
        errors: list[Exception] = []
        results: list[dict] = []

        def writer():
            try:
                for _ in range(20):
                    client.save_cache("hotkey", large_payload)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(40):
                    val = client.get_cached("hotkey", max_age_hours=24)
                    if val is not None:
                        results.append(val)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"concurrent cache ops raised: {errors}"
        # writer 4개 x 20회 = 80번 쓰는 동안 reader 4개 x 40회 = 160회 시도하면
        # 워밍업 직후부터는 항상 캐시가 존재한다. 최소 한 번 이상 성공 읽기 필수.
        assert len(results) > 0, "reader가 한 번도 캐시를 못 읽음 (atomic write 깨졌을 가능성)"
        # 읽은 값은 전부 무결한 payload여야 한다 (partial JSON이면 None을 반환)
        assert all(r["data"] == large_payload["data"] for r in results)

    def test_path_traversal_in_cache_key_is_rejected(self, tmp_path):
        import pytest

        client = BaseAPIClient(cache_subdir="test_traversal_cache")
        client.cache_dir = str(tmp_path)

        # 사용자 입력이 cache_key로 흘러들어가도 file system 밖으로 못 나가야 함.
        unsafe_keys = ["../escape", "foo/bar", "..\\evil", ".hidden", "", None]
        for bad in unsafe_keys:
            with pytest.raises((ValueError, TypeError)):
                client._cache_path(bad)

    def test_safe_cache_keys_pass_validation(self, tmp_path):
        client = BaseAPIClient(cache_subdir="test_safe_cache")
        client.cache_dir = str(tmp_path)

        safe_keys = [
            "global_market_overview",
            "exchange_rate_USD_KRW",
            "news_sources_005930",
            "fear_greed_index",
        ]
        for k in safe_keys:
            # 예외 없이 path 생성 가능
            path = client._cache_path(k)
            assert path.endswith(f"{k}.json")

    def test_save_cache_does_not_leave_tmp_file_on_failure(self, tmp_path):
        client = BaseAPIClient(cache_subdir="test_atomic_failure_cache")
        client.cache_dir = str(tmp_path)

        # json.dump 실패를 유발하는 직렬화 불가 객체
        class Unserializable:
            pass

        client.save_cache("badkey", Unserializable())

        # 디렉토리에 .tmp 파일이 남으면 안 됨
        leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
        assert leftovers == [], f"tempfiles leaked: {leftovers}"
        # 정상 캐시 파일도 안 만들어졌어야 함
        assert not os.path.exists(os.path.join(tmp_path, "badkey.json"))
