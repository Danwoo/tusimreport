"""모든 외부 API 클라이언트의 공통 베이스.

기존엔 Alpha Vantage / CoinGecko / Fear&Greed가 같은 캐싱 로직을 복붙해 썼다.
이 베이스는 다음을 한 곳에 모은다:
  - requests.Session (커넥션 풀)
  - 파일 기반 TTL 캐시
  - User-Agent 헤더
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """HTTP 외부 API 호출용 공통 베이스.

    하위 클래스는 보통 base_url을 오버라이드하고 도메인 메서드를 추가한다.
    캐시 TTL은 호출 사이트에서 결정한다 (시장 심리는 6h, 시세는 5분 등).
    """

    DEFAULT_USER_AGENT = "TuSimReport/1.0"

    def __init__(
        self,
        api_key: str | None = None,
        cache_subdir: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent or self.DEFAULT_USER_AGENT,
                "Accept": "application/json",
            }
        )
        self.cache_dir: str | None = None
        if cache_subdir:
            # tempfile.gettempdir()로 cross-platform (/tmp on Linux/macOS, %TEMP% on Windows).
            self.cache_dir = os.path.join(tempfile.gettempdir(), cache_subdir)
            os.makedirs(self.cache_dir, exist_ok=True)

    # ---- 캐싱 ----

    @staticmethod
    def _validate_cache_key(key: str) -> None:
        """캐시 키에 path traversal 가능한 문자 차단.

        현재 모든 호출자는 internal f-string으로 key를 만들지만, 새 contributor가
        사용자 입력(종목명/뉴스 제목 등)을 key로 박을 가능성을 차단하는 cheap defense.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"invalid cache key: {key!r}")
        if "/" in key or "\\" in key or ".." in key or key.startswith("."):
            raise ValueError(f"unsafe cache key (path traversal): {key!r}")

    def _cache_path(self, key: str) -> str:
        if not self.cache_dir:
            raise RuntimeError("Cache disabled: no cache_subdir configured")
        self._validate_cache_key(key)
        return os.path.join(self.cache_dir, f"{key}.json")

    def get_cached(self, key: str, max_age_hours: float) -> Any | None:
        """TTL 내 캐시가 있으면 반환, 없으면 None."""
        if not self.cache_dir:
            return None
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if datetime.now() - mtime > timedelta(hours=max_age_hours):
            logger.debug(f"cache expired: {key}")
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"cache read failed for {key}: {e}")
            return None

    def save_cache(self, key: str, data: Any) -> None:
        """캐시를 atomic하게 쓴다 (best-effort).

        - 두 스레드가 같은 key를 동시에 저장해도 partial write로 파일이
          corrupt되지 않도록 tempfile 생성 → os.replace로 교체.
        - 캐시는 best-effort 레이어이므로 모든 예외(직렬화 실패, 디스크 풀,
          권한 등)는 warning 로깅 후 swallow한다. 호출자는 캐시 성공/실패와
          무관하게 동작해야 한다.
        """
        if not self.cache_dir:
            return
        target = self._cache_path(key)
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=self.cache_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, target)
            tmp_path = None  # replace 성공 → 정리 불필요
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"cache write failed for {key}: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
