"""보고서 숫자와 도구 결과의 대조 규칙 검증."""

from __future__ import annotations

import pytest

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


def test_timestamps_and_dates_are_not_source_data() -> None:
    """시각·날짜에서 나온 숫자(27분, 12일, 25일, 15시)가 지어낸 퍼센트와 맞으면 안 된다."""
    outputs = [
        {
            "last_updated": "2026-10-27T12:27:31+09:00",
            "news": [{"pub_date": "Mon, 25 Oct 2026 09:00:00 +0900", "title": "실적 발표"}],
            "filing": {"rcept_dt": "20261027", "recordedAt": "2026-10-27 15:30"},
            "prices": [{"date": "2026-10-12", "close": 70000}],
            "headline": "2026-10-12 15:30 기준 발표",
            "headline_en": "Results released on 25 Oct 2026",
        }
    ]

    sources = collect_source_numbers(outputs)
    result = numeric_grounding("지분 27%, 변동성 12%, 비중 25%, 성장률 15%. 종가 70,000원.", outputs)

    assert sources == [70000.0]
    assert result.grounded == 1
    assert {item["number"] for item in result.ungrounded} == {"27%", "12%", "25%", "15%"}


def test_hundredfold_scaling_applies_only_to_percent_mentions() -> None:
    assert numeric_grounding("거래량 700", [{"x": 7}]).grounded == 0
    assert numeric_grounding("비율 0.07배", [{"x": 7}]).grounded == 0
    assert numeric_grounding("배당수익률 2.5%", [{"dividend_yield": 0.025}]).grounded == 1


def test_direction_word_carries_the_sign() -> None:
    outputs = [{"change_pct": -3.52, "foreign_net_won": -123_400_000_000}]

    result = numeric_grounding("주가는 3.52% 하락했고 외국인은 1,234억원 순매도했다.", outputs)

    assert (result.checked, result.grounded) == (2, 2)


def test_sign_is_still_checked_without_a_direction_word() -> None:
    assert numeric_grounding("등락률 +3.52%", [{"change_pct": -3.52}]).grounded == 0


def test_compound_units_merge_into_one_value() -> None:
    mentions = extract_report_numbers("시가총액 6조 5,670억원, 거래대금 1조 200억")

    assert [(m.raw, m.value) for m in mentions] == [("6조 5,670억원", 6.567e12), ("1조 200억", 1.02e12)]
    assert numeric_grounding("시가총액 6조 5,670억원", [{"market_cap": 6_567_000_000_000}]).grounded == 1
    assert collect_source_numbers([{"cap": "6조 5,670억원 수준"}]) == [6.567e12]


def test_week_periods_are_stripped_but_share_counts_are_checked() -> None:
    mentions = extract_report_numbers("52주 최고가 88,800원, 자사주 1,234,567주 매입")

    assert [m.raw for m in mentions] == ["88,800원", "1,234,567"]


def test_only_bare_four_digit_tokens_are_years() -> None:
    mentions = extract_report_numbers("2026 전망, 목표가 2,050원, 지수 2050원, 2050.5포인트")

    assert [m.value for m in mentions] == [2050.0, 2050.0, 2050.5]


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("영업이익 6조5,670억원", 6.567e12),
        ("영업이익 6조5670억원", 6.567e12),
        ("1조2,345억원 순매도", 1.2345e12),
    ],
)
def test_compound_units_without_spaces_merge_into_one_value(text: str, value: float) -> None:
    mentions = extract_report_numbers(text)

    assert [m.value for m in mentions] == [value]
    assert collect_source_numbers([text]) == [value]


def test_a_sentence_that_starts_with_a_date_keeps_its_other_numbers() -> None:
    assert collect_source_numbers(["Mar 5 2026 12:00 price 72,000"]) == [72000.0]
    assert collect_source_numbers(["Mon, 27 Oct 2026 09:00:00 +0900"]) == []
