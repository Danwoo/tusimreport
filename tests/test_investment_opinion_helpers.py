"""투자 의견 에이전트의 순수 헬퍼 함수 테스트.

LLM/네트워크 호출 없이 검증 가능한 부분만 다룬다.
"""

from unittest.mock import patch

from agents.korean_investment_opinion_agent import _clamp_price, _extract_current_price


class TestClampPrice:
    """LLM이 비정상 가격을 뱉어도 UI %계산이 깨지지 않도록 막는 clamp 함수."""

    def test_negative_falls_back_to_default(self):
        # LLM이 음수 반환 → current * default_mult
        assert _clamp_price(-5000, 100000, 1.1) == 110000

    def test_zero_falls_back_to_default(self):
        assert _clamp_price(0, 100000, 0.9) == 90000

    def test_non_numeric_falls_back_to_default(self):
        assert _clamp_price("garbage", 100000, 1.1) == 110000
        assert _clamp_price(None, 100000, 1.1) == 110000

    def test_extreme_high_is_clamped_to_2x(self):
        # 9억(LLM 환각)도 2배(20만)로 clamp
        assert _clamp_price(900_000_000, 100_000, 1.1) == 200_000

    def test_extreme_low_is_clamped_to_half(self):
        # 1000원(현재가의 1%)도 절반(5만)으로 clamp
        assert _clamp_price(1000, 100_000, 0.9) == 50_000

    def test_reasonable_value_passes_through(self):
        # 1.1x 영역의 정상 LLM 반환은 그대로 통과
        assert _clamp_price(108000, 100000, 1.1) == 108000

    def test_zero_current_price_returns_default_mult(self):
        # current_price가 0이면 어떻게든 fallback (division 등 회피)
        assert _clamp_price(50000, 0, 1.1) == 0


class TestExtractCurrentPrice:
    """`_extract_current_price`의 regex 파싱 분기를 검증."""

    def test_extracts_from_korean_current_price_pattern(self):
        results = {"technical_expert": "현재가: 65,000원, 거래량 100만주"}
        # FDR fallback이 안 타도록 패치 필요 없음 - regex가 먼저 matches
        assert _extract_current_price("005930", results) == 65000.0

    def test_extracts_from_close_pattern(self):
        results = {"technical_expert": "Close: 78,500"}
        assert _extract_current_price("005930", results) == 78500.0

    def test_extracts_with_no_comma(self):
        results = {"context_expert": "현재가: 1234원"}
        assert _extract_current_price("005930", results) == 1234.0

    def test_picks_first_match_in_iteration_order(self):
        # Python 3.7+ dict는 insertion-ordered가 보장됨 → 첫 매치가 결정적이어야 한다.
        results = {
            "a": "현재가: 10,000원",
            "b": "현재가: 20,000원",
        }
        assert _extract_current_price("005930", results) == 10000.0

    def test_non_string_content_is_skipped(self):
        # dict/None content는 skip되고 fallback으로 떨어진다
        results = {"agent_a": {"nested": "dict"}, "agent_b": None}
        with patch("FinanceDataReader.DataReader", return_value=None):
            price = _extract_current_price("005930", results)
            assert price == 100000.0  # 최종 fallback

    def test_fallback_when_no_pattern_and_fdr_empty(self):
        import pandas as pd

        results = {"a": "분석에 가격 언급 없음"}
        with patch("FinanceDataReader.DataReader", return_value=pd.DataFrame()):
            assert _extract_current_price("005930", results) == 100000.0

    def test_fallback_when_fdr_raises(self):
        results = {}
        with patch("FinanceDataReader.DataReader", side_effect=Exception("network")):
            # exception은 함수 내부에서 잡혀서 fallback 반환되어야 한다
            assert _extract_current_price("005930", results) == 100000.0
