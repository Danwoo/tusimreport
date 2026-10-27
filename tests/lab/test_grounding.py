"""보고서 숫자와 도구 결과의 대조 규칙 검증."""

from __future__ import annotations

from lab.grounding import collect_source_numbers, extract_report_numbers, numeric_grounding


def test_units_percent_and_rounding_match() -> None:
    report = "현재가는 70,000원이고 PER은 12.3배, 배당수익률 2.5%, 시가총액 418.2조원이다."
    outputs = [{"price": 70000, "per": 12.34, "dividend_yield": 0.025, "market_cap": 418_234_000_000_000}]

    result = numeric_grounding(report, outputs)

    assert result.checked == 4
    assert result.grounded == 4
    assert result.ratio == 1.0


def test_ungrounded_number_is_reported_with_context() -> None:
    result = numeric_grounding("목표가는 95,000원으로 제시한다.", [{"price": 70000}])

    assert result.grounded == 0
    assert result.ungrounded[0]["number"].startswith("95,000")
    assert "목표가" in result.ungrounded[0]["context"]


def test_dates_counts_years_and_codes_are_not_checked() -> None:
    report = (
        "## 1. 개요\n2026-10-25 기준 005930 분석. 2025년 실적, 3가지 포인트, "
        "20일 이동평균, 3분기 실적, TOP 3, 000660과 비교."
    )

    assert extract_report_numbers(report, stock_code="005930") == []


def test_source_numbers_parse_strings_with_units() -> None:
    values = collect_source_numbers([{"a": "1,234억", "b": "12.5%", "c": ["70,000원", True, None]}])

    assert 1234e8 in values
    assert 12.5 in values
    assert 70000.0 in values


def test_generated_summary_and_reasons_are_not_source_data() -> None:
    """요약 문구의 라벨("24시간", "S&P 500")이 지어낸 숫자와 우연히 맞으면 안 된다."""
    outputs = [
        {
            "bitcoin": {"price_change_24h": 2.5},
            "summary": "Bitcoin (24시간 +2.50%), S&P 500 추종 ETF, NASDAQ-100 추종 ETF",
            "unavailable_data": ["USD/KRW 환율: 하루 25건 한도 초과"],
            "forex": {"available": False, "reason": "한도 25건 초과"},
        }
    ]

    result = numeric_grounding(
        "비트코인이 하루 새 24% 급등했고 나스닥은 100포인트 올랐다. 변동률 2.5%.", outputs
    )

    assert result.grounded == 1
    assert {item["number"] for item in result.ungrounded} == {"24%", "100"}
