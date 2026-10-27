"""Sentiment agent의 뉴스 수집 도구 단위 테스트.

도구는 Tavily 기사만 잘라서 돌려주고, LLM을 부르지 않으며 Naver API도 호출하지 않는다.
"""

from __future__ import annotations

import pytest

import agents.korean_sentiment_agent as sentiment
from agents.korean_sentiment_agent import get_enhanced_news_sentiment_logic
from core.agent_status import classify_tool_output


def _stub_tavily(item_count: int = 2) -> dict:
    """TavilyNewsClient.search_company_news 응답 모양."""
    return {
        "status": "success",
        "search_query": "삼성전자 stock earnings financial",
        "news_items": [
            {
                "title": f"Samsung global news {i}",
                "url": f"https://reuters.com/{i}",
                "content": f"Global perspective {i} " * 40,
                "source": "reuters.com",
                "score": 0.9 - i * 0.05,
            }
            for i in range(item_count)
        ],
        "ai_summary": "Strong fundamentals, supply chain concerns",
    }


@pytest.fixture(autouse=True)
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sentiment, "build_llm", lambda **_kw: pytest.fail("the tool must not call an LLM"))


def test_returns_truncated_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sentiment, "_fetch_tavily_news", lambda _name: _stub_tavily(2))

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert result["status"] == "success"
    assert result["total_articles"] == 2
    assert [a["article_number"] for a in result["articles"]] == [1, 2]
    assert all(len(a["content"]) <= sentiment.MAX_CONTENT_CHARS for a in result["articles"])
    assert result["articles"][0]["source"] == "reuters.com"
    assert classify_tool_output(result) == (False, True)


def test_search_service_summary_is_not_passed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tavily가 생성한 요약 문장은 원천 기사가 아니므로 도구 출력에 넣지 않는다."""
    monkeypatch.setattr(sentiment, "_fetch_tavily_news", lambda _name: _stub_tavily(1))

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert "Strong fundamentals" not in str(result)


def test_no_articles_is_an_error_with_the_client_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sentiment,
        "_fetch_tavily_news",
        lambda _name: {"error": "Tavily API 키가 설정되지 않았습니다.", "news_items": []},
    )

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert result == {"error": "Tavily API 키가 설정되지 않았습니다."}
    assert classify_tool_output(result) == (True, False)


def test_naver_api_is_not_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """약관상 Naver 검색 결과를 LLM에 넣지 않는다 — 분석 경로에서 Naver로 요청이 나가면 안 된다."""
    requested: list[str] = []

    def record(url: str, *_a: object, **_kw: object) -> None:
        requested.append(url)
        raise AssertionError("no HTTP from this test")

    monkeypatch.setattr("requests.get", record)
    monkeypatch.setattr("requests.post", record)
    monkeypatch.setattr(sentiment, "_fetch_tavily_news", lambda _name: _stub_tavily(1))

    get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert not any("naver" in url for url in requested)


def test_unexpected_failure_becomes_korean_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_name: str) -> dict:
        raise RuntimeError("network down")

    monkeypatch.setattr(sentiment, "_fetch_tavily_news", boom)

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert result["status"] == "limited"
    assert classify_tool_output(result) == (True, False)
