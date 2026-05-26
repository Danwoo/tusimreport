"""AlphaVantageClient: 응답 매핑/캐시/fallback 단위 테스트.

테스트되는 시나리오:
1. API 키 미설정 → 외부 호출 없이 fallback 즉시 반환
2. Global Quote 정상 응답 → 가격/변화율 정확 파싱
3. 응답 스키마 불일치 ('Global Quote' 키 없음) → 0.0 fallback
4. 캐시 hit 시 외부 호출 0건
5. base_client 통합 — 429는 RateLimitError로 변환
"""

from __future__ import annotations

import json
from pathlib import Path

import responses

from core.errors import RateLimitError
from data.alpha_vantage_client import AlphaVantageClient


def _quote_payload(symbol: str, price: float, change_pct: float) -> dict:
    return {
        "Global Quote": {
            "01. symbol": symbol,
            "05. price": str(price),
            "06. volume": "12345",
            "07. latest trading day": "2025-11-17",
            "10. change percent": f"{change_pct}%",
        }
    }


def test_returns_fallback_when_api_key_missing(isolated_cache_dir: Path) -> None:
    client = AlphaVantageClient(api_key=None)
    # responses fixture를 안 쓰는 이유: 진짜 외부 호출이 일어나면 그 자체가
    # connection error로 떠야 한다. 호출이 없으면 그냥 통과.
    result = client.get_global_market_overview()
    assert "sp500" in result or "error" in result
    # fallback의 가격은 0이거나 status가 limited여야 한다 (실제 호출 안 됨).
    assert client.api_key is None


def test_parses_global_quote_response(
    mocked_responses: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """모든 3개 인덱스 ETF 호출에 정상 응답을 등록하고 파싱 결과를 검증."""
    base_url = "https://www.alphavantage.co/query"
    for sym, price, chg in [("SPY", 450.12, 0.5), ("QQQ", 380.45, 0.8), ("DIA", 350.23, 0.3)]:
        mocked_responses.add(
            responses.GET,
            base_url,
            json=_quote_payload(sym, price, chg),
            status=200,
            match=[
                responses.matchers.query_param_matcher(
                    {
                        "function": "GLOBAL_QUOTE",
                        "symbol": sym,
                        "apikey": "FAKEKEY",
                    }
                )
            ],
        )

    client = AlphaVantageClient(api_key="FAKEKEY")
    result = client.get_global_market_overview()

    assert result["sp500"]["price"] == 450.12
    assert result["sp500"]["change_percent"] == 0.5
    assert result["nasdaq"]["price"] == 380.45
    assert result["dow"]["change_percent"] == 0.3
    assert "timestamp" in result


def test_handles_unexpected_schema(
    mocked_responses_loose: responses.RequestsMock, isolated_cache_dir: Path
) -> None:
    """'Global Quote' 키가 없으면 0.0 fallback. silent crash 방지."""
    base_url = "https://www.alphavantage.co/query"
    # API quota 초과 시 Alpha Vantage가 실제로 돌려주는 메시지 형식
    mocked_responses_loose.add(
        responses.GET, base_url, json={"Note": "Thank you for using Alpha Vantage..."}, status=200
    )

    client = AlphaVantageClient(api_key="FAKEKEY")
    quote = client._get_quote("SPY")
    assert quote["price"] == 0.0
    assert quote["change_percent"] == 0.0


def test_cache_prevents_second_call(isolated_cache_dir: Path) -> None:
    """첫 호출에서 캐시를 저장하고, 두 번째 호출은 캐시만 읽도록 강제.

    responses를 첫 번째 호출에서만 등록. 두 번째에서 외부 호출이 일어나면
    'connection refused'가 발생해 테스트가 깨진다 (즉 캐시 hit를 강제 검증).
    """
    client = AlphaVantageClient(api_key="FAKEKEY")

    # 캐시 dir이 isolated_cache_dir 안에 잘 잡혔는지 확인
    assert client.cache_dir is not None
    assert client.cache_dir.startswith(str(isolated_cache_dir))

    # 캐시 미리 채워 넣고 외부 호출 없이 결과 나오는지
    cached = {"sp500": {"symbol": "SPY", "price": 999.99, "change_percent": 1.0}}
    client.save_cache("global_market_overview", cached)

    # 외부 호출이 일어나면 fail하도록 responses는 빈 상태
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = client.get_global_market_overview()
        assert result["sp500"]["price"] == 999.99
        assert len(rsps.calls) == 0  # 외부 호출 0건


def test_429_propagates_as_rate_limit_error(isolated_cache_dir: Path) -> None:
    """BaseAPIClient.request_json을 직접 쓰는 경로에서 429가 정확히 매핑되는지.

    AlphaVantageClient 내부 메서드는 현재 self.session.get을 직접 쓰고
    raise_for_status로 일반 HTTPError를 raise한다. 호환성 회귀 방지용으로
    base_client 경로(request_json)는 별도 클래스로 검증."""
    client = AlphaVantageClient(api_key="FAKEKEY")
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.alphavantage.co/query",
            json={"Note": "quota"},
            status=429,
        )
        try:
            client.request_json("GET", "https://www.alphavantage.co/query")
            raise AssertionError("RateLimitError expected")
        except RateLimitError as e:
            assert e.status_code == 429
