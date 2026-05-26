"""FearGreedClient: 응답 파싱과 한글 해석 검증."""

from __future__ import annotations

from pathlib import Path

import responses

from data.fear_greed_client import FearGreedClient

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


def test_fallback_when_schema_missing(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """CNN이 응답 포맷을 바꿔서 'fear_and_greed' 키가 사라진 경우."""
    mocked_responses_loose.add(responses.GET, CNN_URL, json={"unexpected": "shape"}, status=200)

    client = FearGreedClient()
    result = client.get_current_index()
    # fallback은 score 키를 갖는 dict이고 합리적 디폴트(0-100 사이)여야 한다.
    assert isinstance(result, dict)
    assert "score" in result
    assert 0 <= int(result["score"]) <= 100


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
            "timestamp": "2025-11-17T00:00:00",
        },
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_current_index()
        assert result["score"] == 77
        assert len(rsps.calls) == 0
