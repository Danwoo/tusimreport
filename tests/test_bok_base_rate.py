"""BOKAPIClient.get_base_rate: 722Y001 통계표에서 기준금리 항목만 읽는지 검증.

722Y001에는 기준금리 외에 정부대출금금리·총액한도대출금리 등이 함께 있다.
"""

from __future__ import annotations

import responses

from data.bok_api_client import BASE_RATE_ITEM_CODE, BOKAPIClient


def _row(item: str, time: str, value: str) -> dict[str, str]:
    return {"ITEM_CODE1": item, "TIME": time, "DATA_VALUE": value, "UNIT_NAME": "연%"}


def test_requests_the_base_rate_item_and_ignores_other_rates(
    mocked_responses: responses.RequestsMock,
) -> None:
    rows = [
        _row("0102000", "20210104", "1.25"),
        _row(BASE_RATE_ITEM_CODE, "20210104", "0.5"),
        _row(BASE_RATE_ITEM_CODE, "20210105", "0.5"),
    ]
    mocked_responses.add(
        responses.GET,
        "https://ecos.bok.or.kr/api/StatisticSearch/ECOSKEY77/json/kr/1/1000/722Y001/D/20210101/20210105/0101000",
        json={"StatisticSearch": {"list_total_count": 3, "row": rows}},
    )

    result = BOKAPIClient(api_key="ECOSKEY77").get_base_rate("20210101", "20210105")

    # The base rate was 0.5% in 2020-2021, so no range filter may drop it.
    assert [r["rate"] for r in result["base_rates"]] == [0.5, 0.5]
    assert result["latest_rate"] == {"date": "20210105", "rate": 0.5, "unit": "연%"}
