"""외부 응답 스키마 (Pydantic).

목적: PyKRX, DART, Alpha Vantage 등이 응답 포맷을 바꾸면 silent break가
일어나지 않도록 데이터 경계에서 검증한다. 검증 실패 시 `DataQualityError`를
raise해 호출자가 fallback 경로로 분기하게 한다.

설계 원칙:
- pydantic v2 사용 (이미 `pydantic-settings`를 통해 의존성에 들어와 있음).
- `extra="ignore"` — 외부가 새 필드 추가하는 건 OK, 우리가 의존하는 필드만
  검증.
- 필드는 Optional이 default — DART/PyKRX는 누락 필드가 흔하므로
  required=True로 잡으면 그 자체로 brittle.
- 가격/수치는 `Decimal` 대신 `float` — 표시 정확도가 paramount하지 않고
  JSON 직렬화가 단순함. 회계 정확도가 필요한 곳은 호출자가 다시 변환.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from core.errors import DataQualityError


class DartCorpInfo(BaseModel):
    """DART `/company.json` 응답 (회사 기본정보).

    실제 응답에는 30+ 필드가 있지만 우리가 의존하는 핵심 키만 묶는다.
    누락된 필드는 None — DART는 자주 부분 응답을 돌려준다.
    """

    model_config = ConfigDict(extra="ignore")

    corp_name: str | None = None
    corp_name_eng: str | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    ceo_nm: str | None = None
    corp_cls: str | None = None  # 법인구분(Y/K/N/E)
    jurir_no: str | None = None  # 법인등록번호
    bizr_no: str | None = None  # 사업자등록번호
    adres: str | None = None
    induty_code: str | None = None  # 업종코드
    est_dt: str | None = None  # 설립일


class DartStatusEnvelope(BaseModel):
    """DART API 공통 envelope: `{"status": "000", "message": "...", ...}`.

    status='000'이 성공. 그 외 (013='조회된 데이터가 없습니다', 020='요청
    제한 초과') 모두 실패. 호출자는 status만 보고 분기할 수 있다.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    message: str | None = None


class PykrxFundamentalRow(BaseModel):
    """PyKRX `stock.get_market_fundamental(...)` 행 단위 검증.

    원본은 한국어 컬럼명 DataFrame — DataFrame → dict로 변환한 뒤 검증.
    어느 컬럼이 사라지면 None으로 들어오고, 0/음수 같은 sentinel 처리는
    호출자가 한다 (PER=0은 PyKRX의 'no data' 약속).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    market_cap: int | None = None  # 시가총액
    per: float | None = None  # PER
    pbr: float | None = None  # PBR
    eps: int | None = None  # EPS
    bps: int | None = None  # BPS


def validate_dart_envelope(payload: Any, *, source: str = "DART") -> DartStatusEnvelope:
    """DART 응답을 envelope로 파싱. ValidationError → DataQualityError.

    호출자 코드:

        env = validate_dart_envelope(response.json(), source="company.json")
        if env.status != "000":
            raise DataQualityError(env.message or "no rows", source="DART")
    """
    try:
        return DartStatusEnvelope.model_validate(payload)
    except ValidationError as e:
        raise DataQualityError(f"unexpected DART envelope shape: {e.errors()[:1]}", source=source) from e


def validate_dart_corp_info(payload: Any) -> DartCorpInfo:
    """DART corp 정보 검증. status='000' 가드 통과 후 호출."""
    try:
        return DartCorpInfo.model_validate(payload)
    except ValidationError as e:
        raise DataQualityError(
            f"unexpected DART corp_info shape: {e.errors()[:1]}", source="DART/company.json"
        ) from e


# PyKRX 컬럼명 → Pydantic 필드명 매핑.
# 라이브러리가 컬럼명을 바꾸면 한 곳에서 알아챌 수 있도록 명시.
PYKRX_FUNDAMENTAL_COLUMN_MAP: dict[str, str] = {
    "시가총액": "market_cap",
    "PER": "per",
    "PBR": "pbr",
    "EPS": "eps",
    "BPS": "bps",
}


def validate_pykrx_fundamental(row_dict: dict[str, Any]) -> PykrxFundamentalRow:
    """PyKRX get_market_fundamental의 한 행을 검증.

    Args:
        row_dict: DataFrame.iloc[-1].to_dict() 결과 (한국어 키).

    Returns:
        영문 키로 정규화된 PykrxFundamentalRow.

    Raises:
        DataQualityError: 필수 컬럼이 모두 누락된 경우 (시가총액조차 없음).
    """
    normalised: dict[str, Any] = {}
    for ko_key, en_key in PYKRX_FUNDAMENTAL_COLUMN_MAP.items():
        if ko_key in row_dict:
            normalised[en_key] = row_dict[ko_key]

    if not normalised:
        # 한 컬럼도 못 찾았다 → PyKRX가 컬럼명을 통째로 바꾼 것.
        raise DataQualityError(
            f"PyKRX fundamental row has none of expected columns "
            f"({list(PYKRX_FUNDAMENTAL_COLUMN_MAP.keys())!r}), got {list(row_dict.keys())!r}",
            source="pykrx/get_market_fundamental",
        )

    try:
        return PykrxFundamentalRow.model_validate(normalised)
    except ValidationError as e:
        raise DataQualityError(
            f"PyKRX fundamental row failed validation: {e.errors()[:1]}",
            source="pykrx/get_market_fundamental",
        ) from e
