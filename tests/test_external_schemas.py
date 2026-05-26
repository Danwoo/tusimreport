"""data.external_schemas: 외부 응답 검증 단위 테스트.

PyKRX/DART가 응답 포맷을 바꾸면 silent break 대신 DataQualityError가
나도록 하는 게 목적이라, 테스트는 두 갈래:
- happy path: 알려진 정상 응답 모양 → 검증 통과 + 정규화
- 회귀 시나리오: 컬럼 누락/타입 변경/envelope 깨짐 → DataQualityError
"""

from __future__ import annotations

import pytest

from core.errors import DataQualityError
from data.external_schemas import (
    PykrxFundamentalRow,
    validate_dart_corp_info,
    validate_dart_envelope,
    validate_pykrx_fundamental,
)


class TestDartEnvelope:
    def test_success_envelope_parses(self) -> None:
        env = validate_dart_envelope({"status": "000", "message": "정상", "list": []})
        assert env.status == "000"
        assert env.message == "정상"

    def test_business_error_envelope_parses(self) -> None:
        # status가 '000'이 아니어도 envelope 자체는 유효해야 한다.
        # 호출자가 status로 분기.
        env = validate_dart_envelope({"status": "013", "message": "조회된 데이터가 없습니다"})
        assert env.status == "013"

    def test_missing_status_raises_data_quality_error(self) -> None:
        with pytest.raises(DataQualityError) as exc_info:
            validate_dart_envelope({"message": "no status field"})
        # source는 호출자가 넘기는 값 (default="DART"). 적어도 'DART'를 포함.
        assert "DART" in (exc_info.value.source or "")

    def test_non_dict_payload_raises(self) -> None:
        with pytest.raises(DataQualityError):
            validate_dart_envelope(["not", "a", "dict"])


class TestDartCorpInfo:
    def test_full_payload(self) -> None:
        info = validate_dart_corp_info(
            {
                "corp_name": "삼성전자(주)",
                "corp_name_eng": "Samsung Electronics Co., Ltd.",
                "stock_code": "005930",
                "ceo_nm": "한종희",
                "corp_cls": "Y",
                "extra_new_field": "should be ignored",
            }
        )
        assert info.corp_name == "삼성전자(주)"
        assert info.stock_code == "005930"

    def test_partial_payload_keeps_none_for_missing(self) -> None:
        # DART는 자주 부분 응답을 돌려준다. 빠진 필드는 None.
        info = validate_dart_corp_info({"corp_name": "Acme"})
        assert info.corp_name == "Acme"
        assert info.stock_code is None
        assert info.ceo_nm is None

    def test_wrong_type_raises(self) -> None:
        # corp_name이 dict면 검증 실패해야 한다.
        with pytest.raises(DataQualityError):
            validate_dart_corp_info({"corp_name": {"nested": "object"}})


class TestPykrxFundamental:
    def test_korean_columns_normalize_to_english(self) -> None:
        row = validate_pykrx_fundamental(
            {"시가총액": 400_000_000_000_000, "PER": 12.5, "PBR": 1.3, "EPS": 5000, "BPS": 58000}
        )
        assert isinstance(row, PykrxFundamentalRow)
        assert row.market_cap == 400_000_000_000_000
        assert row.per == 12.5
        assert row.eps == 5000

    def test_partial_columns_allowed(self) -> None:
        # PyKRX가 일부 컬럼만 돌려줘도 (예: KOSDAQ 신규 상장 직후) OK.
        row = validate_pykrx_fundamental({"시가총액": 1_000_000_000, "PER": 0})
        assert row.market_cap == 1_000_000_000
        assert row.per == 0
        assert row.pbr is None
        assert row.eps is None

    def test_all_columns_missing_raises(self) -> None:
        """라이브러리가 컬럼명을 통째로 영문으로 바꾼 회귀 시나리오."""
        with pytest.raises(DataQualityError) as exc:
            validate_pykrx_fundamental({"MarketCap": 100, "PE": 12.5})  # 영문 키
        assert "pykrx" in (exc.value.source or "").lower()

    def test_per_zero_kept_as_zero_for_caller_normalisation(self) -> None:
        """PyKRX의 'no data' sentinel은 0. 호출자가 None으로 정규화하므로
        스키마 레벨에선 0이 그대로 통과해야 한다."""
        row = validate_pykrx_fundamental({"시가총액": 1, "PER": 0, "PBR": 0})
        assert row.per == 0
        assert row.pbr == 0


class TestAssertPykrxColumns:
    def test_overlap_passes(self) -> None:
        from data.external_schemas import (
            PYKRX_INDEX_OHLCV_COLUMNS,
            assert_pykrx_columns,
        )

        # KOSPI 응답에 모든 한국어 컬럼이 살아 있는 정상 케이스
        assert_pykrx_columns(
            ["시가", "고가", "저가", "종가", "거래량"],
            expected=PYKRX_INDEX_OHLCV_COLUMNS,
            source="pykrx/index_ohlcv",
        )

    def test_partial_overlap_passes_with_min_one(self) -> None:
        from data.external_schemas import (
            PYKRX_TRADING_VALUE_COLUMNS,
            assert_pykrx_columns,
        )

        # 컬럼 일부만 살아 있어도 min_overlap=1 기본이라 OK
        assert_pykrx_columns(
            ["순매수", "다른필드"],
            expected=PYKRX_TRADING_VALUE_COLUMNS,
            source="pykrx/trading_value",
        )

    def test_no_overlap_raises(self) -> None:
        """라이브러리가 컬럼명을 영문화한 회귀 시나리오."""
        from data.external_schemas import (
            PYKRX_INDEX_OHLCV_COLUMNS,
            assert_pykrx_columns,
        )

        with pytest.raises(DataQualityError) as exc:
            assert_pykrx_columns(
                ["Open", "High", "Low", "Close", "Volume"],  # 영문 컬럼
                expected=PYKRX_INDEX_OHLCV_COLUMNS,
                source="pykrx/index_ohlcv",
            )
        assert "drifted" in str(exc.value)
        assert "pykrx/index_ohlcv" in (exc.value.source or "")

    def test_higher_min_overlap_enforced(self) -> None:
        """min_overlap=3이면 1개 겹쳐도 raise."""
        from data.external_schemas import (
            PYKRX_INDEX_OHLCV_COLUMNS,
            assert_pykrx_columns,
        )

        with pytest.raises(DataQualityError):
            assert_pykrx_columns(
                ["종가"],  # 1개만
                expected=PYKRX_INDEX_OHLCV_COLUMNS,
                source="pykrx/x",
                min_overlap=3,
            )
