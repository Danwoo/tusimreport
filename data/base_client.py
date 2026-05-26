"""모든 외부 API 클라이언트의 공통 베이스.

기존엔 Alpha Vantage / CoinGecko / Fear&Greed가 같은 캐싱 로직을 복붙해 썼다.
이 베이스는 다음을 한 곳에 모은다:
  - requests.Session (커넥션 풀)
  - 파일 기반 TTL 캐시
  - User-Agent 헤더
  - urllib3 Retry로 5xx/429에 지수 백오프 자동 적용
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.errors import (
    AuthenticationError,
    DataSourceUnavailableError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# 캐시 키 화이트리스트: 영숫자/하이픈/언더스코어/점만 허용. 첫 글자는
# 점이 될 수 없다 (리눅스 hidden file로 만들지 않기 위해).
# Path traversal(`..`, `/`)뿐 아니라 윈도우 예약 문자, NUL 등도 막는다.
_SAFE_CACHE_KEY = re.compile(r"^[A-Za-z0-9_\-][A-Za-z0-9_.\-]*$")


class BaseAPIClient:
    """HTTP 외부 API 호출용 공통 베이스.

    하위 클래스는 보통 base_url을 오버라이드하고 도메인 메서드를 추가한다.
    캐시 TTL은 호출 사이트에서 결정한다 (시장 심리는 6h, 시세는 5분 등).
    """

    DEFAULT_USER_AGENT = "TuSimReport/1.0"

    # urllib3 Retry 정책: 5xx/429에만 자동 재시도. 4xx 클라이언트 에러는
    # 즉시 raise하여 호출자가 인증/입력 문제로 분기하도록 둔다.
    RETRY_STATUS = (429, 500, 502, 503, 504)
    RETRY_TOTAL = 3
    RETRY_BACKOFF_FACTOR = 0.5  # 0.5, 1.0, 2.0초 대기 후 재시도

    # LRU eviction: 캐시 디렉토리에 이 갯수보다 많이 쌓이면 가장 오래된 파일부터 삭제.
    # 같은 cache_subdir을 공유하는 인스턴스 전반에 적용. 너무 작으면 hot key가
    # 자주 evict되고, 너무 크면 디스크가 무한히 자란다.
    MAX_CACHE_ENTRIES = 256

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
        # 모든 HTTP/HTTPS 요청에 동일한 retry 정책을 mount.
        # `allowed_methods` 명시: 기본은 HEAD/GET만 재시도지만, POST도 멱등인
        # 케이스(JSON RPC 등)가 있어 우리 코드 전반에서 안전하다고 본다.
        retry = Retry(
            total=self.RETRY_TOTAL,
            status_forcelist=self.RETRY_STATUS,
            allowed_methods=frozenset(["GET", "POST", "HEAD"]),
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.cache_dir: str | None = None
        if cache_subdir:
            # tempfile.gettempdir()로 cross-platform (/tmp on Linux/macOS, %TEMP% on Windows).
            self.cache_dir = os.path.join(tempfile.gettempdir(), cache_subdir)
            os.makedirs(self.cache_dir, exist_ok=True)

    # ---- HTTP 도우미 ----

    def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        """`session.request`를 감싸 status code → 도메인 예외로 매핑.

        4xx는 retry되지 않으므로 즉시 도메인 예외로 변환:
          401/403 → AuthenticationError
          429     → RateLimitError (urllib3 Retry로 3회 시도 후에도 실패한 경우)
          5xx     → DataSourceUnavailableError (마찬가지)
          그 외 4xx → DataSourceUnavailableError로 묶고 호출자에서 status로 분기
        """
        timeout = kwargs.pop("timeout", 10)
        try:
            resp = self.session.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            raise DataSourceUnavailableError(f"network failure calling {url}: {e}", source=url) from e

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"auth rejected by {url} (status {resp.status_code})",
                source=url,
                status_code=resp.status_code,
            )
        if resp.status_code == 429:
            raise RateLimitError(f"rate limit exceeded at {url}", source=url, status_code=429)
        if resp.status_code >= 500:
            raise DataSourceUnavailableError(
                f"upstream {resp.status_code} from {url}",
                source=url,
                status_code=resp.status_code,
            )
        if not resp.ok:
            raise DataSourceUnavailableError(
                f"http {resp.status_code} from {url}: {resp.text[:200]}",
                source=url,
                status_code=resp.status_code,
            )

        try:
            return resp.json()
        except ValueError as e:
            raise DataSourceUnavailableError(
                f"non-JSON response from {url}: {resp.text[:200]}", source=url
            ) from e

    # ---- 캐싱 ----

    @staticmethod
    def _validate_cache_key(key: str) -> None:
        """캐시 키에 path traversal 가능한 문자 차단.

        화이트리스트 방식: 영숫자/하이픈/언더스코어/점만 허용. 사용자 입력
        (종목명/뉴스 제목)을 key로 박는 실수와 NUL 바이트, 윈도우 예약 문자,
        UNC 경로 등을 한 줄로 차단한다.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"invalid cache key: {key!r}")
        if not _SAFE_CACHE_KEY.match(key):
            raise ValueError(f"unsafe cache key (allowed: [A-Za-z0-9_.-]+): {key!r}")

    def _cache_path(self, key: str) -> str:
        if not self.cache_dir:
            raise RuntimeError("Cache disabled: no cache_subdir configured")
        self._validate_cache_key(key)
        return os.path.join(self.cache_dir, f"{key}.json")

    def get_cached(self, key: str, max_age_hours: float, force_refresh: bool = False) -> Any | None:
        """TTL 내 캐시가 있으면 반환.

        Args:
            key: 캐시 키 (path-safe whitelist 통과 필요).
            max_age_hours: 캐시가 신선하다고 간주할 최대 나이.
            force_refresh: True면 캐시가 살아 있어도 무시. 호출자가
                'fresh data right now'를 요구하는 경로용. 캐시 파일은 그대로
                두고 (다음 호출이 재사용 가능) 그냥 None을 돌려준다.

        NOTE: 시간 비교는 둘 다 `datetime.now()` (tz-naive)로 한다. 파일
        mtime은 OS가 system clock으로 기록하므로 KST helper로 바꾸면 오히려
        다른 base를 비교해 음수 delta가 나올 수 있다.
        """
        if not self.cache_dir or force_refresh:
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
        - 쓰기 후 `MAX_CACHE_ENTRIES`를 초과하면 가장 오래된 파일부터 LRU
          eviction. 멀티프로세스 환경에선 race condition 가능하지만 best-
          effort 정리이므로 무시 (eviction이 한 번 실패해도 다음 쓰기에서 재시도).
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
        self._evict_if_over_limit()

    def _evict_if_over_limit(self) -> None:
        """LRU eviction: MAX_CACHE_ENTRIES 초과 시 mtime 가장 오래된 것부터 삭제.

        디렉토리 listing은 매번 호출돼 O(N log N). 256 정도 한도면 부담 없음.
        atomicity는 보장 안 함 — 두 인스턴스가 동시에 eviction을 시도하면
        한 쪽의 unlink가 ENOENT로 실패할 수 있는데 그건 swallow한다.
        """
        if not self.cache_dir:
            return
        try:
            files = [f for f in os.listdir(self.cache_dir) if f.endswith(".json") and not f.startswith(".")]
            if len(files) <= self.MAX_CACHE_ENTRIES:
                return
            # mtime 오름차순 (오래된 것 먼저)
            paths = [os.path.join(self.cache_dir, f) for f in files]
            paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
            for old_path in paths[: len(paths) - self.MAX_CACHE_ENTRIES]:
                with contextlib.suppress(OSError):
                    os.unlink(old_path)
        except OSError as e:
            logger.debug(f"cache eviction skipped: {e}")
