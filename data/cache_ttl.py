"""캐시 TTL 정책 — 단일 진실 source.

각 데이터 종류가 얼마나 자주 바뀌는지, 외부 API 호출이 얼마나 비싸는지에
기반해 정해진 값들. 호출 사이트에 매직 넘버를 박지 않기 위해 한곳에 모은다.

기준:
- 시세성 데이터(실시간 호가/체결가): 분 단위 — 너무 오래 캐시하면 stale
- 일별 지표(PER/PBR/시가총액): 거래일 1회면 충분 — 장 마감 후엔 거의 안 변함
- 시장 심리/지수(Fear&Greed/지수 전체): 수 시간 — CNN이 그 빈도로 업데이트
- 거시 경제(BOK/DART): 일/주 단위 — 통계 게시 주기에 맞춤
- 정적 메타(기업 코드/섹터 매핑): 거의 안 바뀜 → 일 단위
"""

from __future__ import annotations

from typing import Final

# ---- 시세성 (분 단위) ----

# CoinGecko simple/price: 5분이면 충분. 무료 호출 한도(분당 30회) 고려.
CRYPTO_PRICE_MINUTES: Final[float] = 5.0

# Alpha Vantage GLOBAL_QUOTE: 무료 25/일 제한 — 1시간 캐시로 일 25 ETF 호출 한계 안에 들어옴.
GLOBAL_QUOTE_HOURS: Final[float] = 1.0

# Alpha Vantage 환율: 1시간 단위 변동이 의미 있는 수준.
FX_RATE_HOURS: Final[float] = 1.0

# ---- 시장 심리/지수 ----

# CNN Fear & Greed Index: 하루에 몇 번 업데이트되므로 6시간이면 fresh.
FEAR_GREED_HOURS: Final[float] = 6.0

# CoinGecko global market summary: 시간 단위로만 의미 있음.
CRYPTO_GLOBAL_HOURS: Final[float] = 1.0

# ---- 거시 경제 / 공시 ----

# BOK ECOS 통계: 일별 게시. 12시간이면 같은 날 안에서는 변동 없음.
BOK_MACRO_HOURS: Final[float] = 12.0

# DART 공시: 일별 + 분기보고서. 12시간 캐시면 사내 ad-hoc 공시 누락 가능.
# 적시성이 중요한 분석에는 호출 사이트에서 force_refresh=True 옵션이 필요.
DART_FILING_HOURS: Final[float] = 12.0

# ---- 정적 메타 ----

# 종목 코드 ↔ 섹터 매핑: 거의 안 바뀜.
STATIC_METADATA_HOURS: Final[float] = 24.0


def _utils() -> dict[str, float]:
    """이 모듈이 export하는 모든 TTL의 dict view (테스트/관측용)."""
    import inspect
    import sys

    members = inspect.getmembers(sys.modules[__name__])
    return {n: v for n, v in members if n.endswith(("_HOURS", "_MINUTES")) and isinstance(v, float)}
