"""FearGreedClient: 응답 파싱, unavailable 처리, 한글 해석 검증."""

from __future__ import annotations

from pathlib import Path

import responses

from data.fear_greed_client import UNAVAILABLE_INTERPRETATION, FearGreedClient

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def test_parses_index_payload(mocked_responses: responses.RequestsMock, isolated_cache_dir: Path) -> None:
    mocked_responses.add(
        responses.GET,
        CNN_URL,
        json={
            "fear_and_greed": {
                "score": 32.5,
                "rating": "Fear",
                "previous_close": 35,
                "previous_1_week": 40,
                "previous_1_month": 55,
                "previous_1_year": 48,
            }
        },
        status=200,
    )

    client = FearGreedClient()
    result = client.get_current_index()

    assert result["score"] == 32
    assert result["rating"] == "Fear"
    assert result["previous_week"] == 40
    assert result["available"] is True
    assert client.get_cached("fear_greed_index", max_age_hours=1)["score"] == 32


def test_schema_change_is_unavailable_not_neutral(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """CNN이 응답 포맷을 바꿔 'fear_and_greed'가 사라지면 중립 50이 아니라 unavailable."""
    mocked_responses_loose.add(responses.GET, CNN_URL, json={"unexpected": "shape"}, status=200)

    client = FearGreedClient()
    result = client.get_current_index()

    assert result["available"] is False
    assert result["score"] is None
    assert result["rating"] is None
    assert result["previous_week"] is None
    assert result["reason"]
    assert client.get_cached("fear_greed_index", max_age_hours=1) is None


def test_missing_score_is_unavailable(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses_loose.add(
        responses.GET, CNN_URL, json={"fear_and_greed": {"rating": "Neutral"}}, status=200
    )

    result = FearGreedClient().get_current_index()
    assert result["available"] is False
    assert result["score"] is None


def test_http_error_is_unavailable(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses_loose.add(responses.GET, CNN_URL, json={}, status=418)

    result = FearGreedClient().get_current_index()
    assert result["available"] is False
    assert result["score"] is None


def test_missing_previous_values_stay_none(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses_loose.add(
        responses.GET, CNN_URL, json={"fear_and_greed": {"score": 61, "rating": "Greed"}}, status=200
    )

    client = FearGreedClient()
    index_data = client.get_current_index()
    assert index_data["previous_week"] is None

    trend = client.get_trend_analysis(index_data)
    assert trend["current_score"] == 61
    assert trend["trend"] is None
    assert trend["change_from_week"] is None
    assert trend["change_from_month"] is None


def test_trend_analysis_when_unavailable_has_no_numbers(isolated_cache_dir: Path) -> None:
    client = FearGreedClient()
    unavailable = client._unavailable_index("CNN 연결 실패")

    trend = client.get_trend_analysis(unavailable)
    assert trend["available"] is False
    assert trend["current_score"] is None
    assert trend["trend"] is None
    assert trend["change_from_week"] is None
    assert trend["interpretation_korean"] == UNAVAILABLE_INTERPRETATION
    assert "/100" not in trend["interpretation_korean"]


def test_interpretation_without_data_does_not_invent_score(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    mocked_responses_loose.add(responses.GET, CNN_URL, json={}, status=500)

    text = FearGreedClient().get_interpretation_korean()
    assert text == UNAVAILABLE_INTERPRETATION
    assert "50" not in text


def test_trend_computed_from_previous_week(isolated_cache_dir: Path) -> None:
    client = FearGreedClient()
    trend = client.get_trend_analysis(
        {"score": 30, "previous_week": 45, "previous_month": 20, "available": True}
    )
    assert trend["trend"] == "worsening"
    assert trend["change_from_week"] == -15
    assert trend["change_from_month"] == 10


def test_korean_interpretation_buckets(isolated_cache_dir: Path) -> None:
    """0-25 / 26-45 / 46-55 / 56-75 / 76-100 구간별 표현 검증."""
    client = FearGreedClient()
    extreme_fear = client.get_interpretation_korean(score=10)
    fear = client.get_interpretation_korean(score=35)
    neutral = client.get_interpretation_korean(score=50)
    greed = client.get_interpretation_korean(score=70)
    extreme_greed = client.get_interpretation_korean(score=90)

    assert "극단적 공포" in extreme_fear
    assert "공포" in fear and "극단적" not in fear
    # 구체 단어는 구현에 잠겨 있어 부분 검증만. 점수 echo는 모든 케이스에 있어야.
    for text in (extreme_fear, fear, neutral, greed, extreme_greed):
        assert "/100" in text


def test_cache_short_circuits_call(isolated_cache_dir: Path) -> None:
    client = FearGreedClient()
    client.save_cache(
        "fear_greed_index",
        {
            "score": 77,
            "rating": "Greed",
            "previous_close": 75,
            "previous_week": 70,
            "previous_month": 65,
            "previous_year": 60,
            "available": True,
            "timestamp": "2025-11-17T00:00:00",
        },
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_current_index()
        assert result["score"] == 77
        assert len(rsps.calls) == 0
