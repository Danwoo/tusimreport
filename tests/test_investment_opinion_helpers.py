"""투자 의견 에이전트의 순수 헬퍼 함수 테스트.

LLM/네트워크 호출 없이 검증 가능한 부분만 다룬다.
"""

from unittest.mock import patch

from agents.korean_investment_opinion_agent import _extract_current_price


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
        # dict/None content는 skip된다
        results = {"agent_a": {"nested": "dict"}, "agent_b": None}
        with patch("FinanceDataReader.DataReader", return_value=None):
            assert _extract_current_price("005930", results) is None

    def test_fallback_when_no_pattern_and_fdr_empty(self):
        import pandas as pd

        results = {"a": "분석에 가격 언급 없음"}
        with patch("FinanceDataReader.DataReader", return_value=pd.DataFrame()):
            assert _extract_current_price("005930", results) is None

    def test_fallback_when_fdr_raises(self):
        results = {}
        with patch("FinanceDataReader.DataReader", side_effect=Exception("network")):
            # 가격을 지어내지 않고 None을 돌려준다
            assert _extract_current_price("005930", results) is None
