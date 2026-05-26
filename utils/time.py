"""한국 시장 기준 시간 유틸.

문제: 코드 전반에 `datetime.now()`가 무방비로 쓰여 있다. 컨테이너가
UTC면 한국 거래소(KOSPI/KOSDAQ) 마감(15:30 KST = 06:30 UTC) 판정,
'어제 종가' 계산, ISO timestamp 등이 모두 9시간 어긋난다.

원칙:
- 한국 시장 데이터를 다루는 코드는 `kst_now()`를 쓴다.
- 외부 API/로그 timestamp 등 timezone-naive로 남기면 안 되는 곳은
  `kst_now().isoformat()`을 사용한다 (오프셋 +09:00이 붙는다).
- 거래일 계산 (어제/일주일 전)은 `kst_yesterday_compact()` 등 헬퍼를 쓴다.

마이그레이션 정책:
- 새 코드는 무조건 여기 함수를 쓴다.
- 기존 `datetime.now()` 사용처는 점진적으로 교체 중. 거래일/장 마감
  판정에 영향을 주는 위치(PyKRX/DART 호출 인근)부터 우선 교체.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 한국은 일광절약시간이 없어 고정 오프셋이면 충분. zoneinfo("Asia/Seoul")을
# 쓰지 않는 이유: tzdata가 깔리지 않은 슬림 컨테이너에서도 동작해야 한다.
KST = timezone(timedelta(hours=9), name="KST")


def kst_now() -> datetime:
    """현재 시각 (Asia/Seoul, tz-aware)."""
    return datetime.now(tz=KST)


def kst_today_compact() -> str:
    """오늘 날짜를 PyKRX 인자 형식(YYYYMMDD)으로 반환."""
    return kst_now().strftime("%Y%m%d")


def kst_yesterday_compact() -> str:
    """어제 날짜를 PyKRX 인자 형식으로. 장 마감 후 가장 최근 거래일 추정용.

    NOTE: 휴장일(주말/공휴일) 보정은 호출자가 한다. 여기서는 단순 -1일.
    """
    return (kst_now() - timedelta(days=1)).strftime("%Y%m%d")


def kst_days_ago_compact(days: int) -> str:
    """N일 전 날짜를 PyKRX 인자 형식으로."""
    return (kst_now() - timedelta(days=days)).strftime("%Y%m%d")


def kst_isoformat() -> str:
    """현재 시각의 ISO8601 문자열 (오프셋 +09:00 포함)."""
    return kst_now().isoformat()
