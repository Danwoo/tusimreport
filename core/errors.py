"""도메인 예외 계층.

문제: 외부 API 실패가 모두 `Exception`으로 묶여 있어 호출자가 정책을
세울 수 없다. 429(레이트리밋)는 재시도, 401(인증)은 즉시 폴백,
503(서비스불가)은 캐시 사용 — 이런 분기를 하려면 타입 구분이 필요.

여기 정의된 예외는 `data/` 클라이언트가 raise하고, 에이전트는
`utils.agent_helpers.format_error_message_korean()`이 한글 메시지로 변환한다.

상속 트리:
    TusimError
    ├── ConfigurationError       # API 키 누락/형식 오류 등 사용자가 고쳐야 함
    └── ExternalAPIError         # 외부 시스템 문제. 재시도 또는 폴백 대상
        ├── RateLimitError       # 429류. backoff 후 재시도 가능
        ├── AuthenticationError  # 401/403. 키 재발급 필요
        ├── DataSourceUnavailableError  # 5xx/네트워크. 백오프 + 캐시 폴백
        └── DataQualityError     # 200 OK인데 응답이 비어 있거나 스키마가 다름
"""

from __future__ import annotations


class TusimError(Exception):
    """프로젝트 공통 베이스. catch-all을 피하면서도 한 번에 잡고 싶을 때 쓰는 루트."""


class ConfigurationError(TusimError):
    """사용자 환경 설정 문제 (API 키 누락, 잘못된 모델명 등). 재시도해도 무의미."""


class ExternalAPIError(TusimError):
    """외부 API 호출 실패의 공통 베이스."""

    def __init__(self, message: str, *, source: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.source = source
        self.status_code = status_code


class RateLimitError(ExternalAPIError):
    """429 또는 quota 초과. 호출자는 지수 백오프 후 재시도 또는 캐시 폴백."""


class AuthenticationError(ExternalAPIError):
    """401/403 또는 API 키 거부. 재시도 무의미, 키 점검 필요."""


class DataSourceUnavailableError(ExternalAPIError):
    """5xx, 타임아웃, 연결 실패 등. 일시적이라고 가정하고 재시도 대상."""


class DataQualityError(ExternalAPIError):
    """HTTP는 성공인데 본문이 비었거나 기대 스키마가 아님 (예: KOSPI 종목인데 0행)."""
