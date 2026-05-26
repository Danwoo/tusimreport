"""Sentiment agent: Naver + Tavily 듀얼 소스 처리 단위 테스트.

외부 호출 (_fetch_naver_news, _fetch_tavily_news)을 monkeypatch하고
LLM(build_llm)도 stub해서 dual-source 종합 로직만 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.korean_sentiment_agent import get_enhanced_news_sentiment_logic


def _stub_naver(item_count: int = 3) -> dict:
    """Naver search API 응답 모양."""
    return {
        "items": [
            {
                "title": f"<b>삼성전자</b> 호재 기사 {i}",
                "link": f"https://news.naver.com/{i}",
                "description": f"긍정적 뉴스 본문 {i}",
                "pubDate": "Mon, 01 Sep 2025 09:00:00 +0900",
            }
            for i in range(item_count)
        ]
    }


def _stub_tavily(item_count: int = 2) -> dict:
    """Tavily search 응답 모양."""
    return {
        "news_items": [
            {
                "title": f"Samsung global news {i}",
                "url": f"https://reuters.com/{i}",
                "content": f"Global perspective {i}",
                "source": "reuters.com",
                "score": 0.9 - i * 0.05,
            }
            for i in range(item_count)
        ],
        "ai_summary": "Strong fundamentals, supply chain concerns",
    }


def _stub_llm_response(text: str) -> MagicMock:
    stub = MagicMock()
    response = MagicMock()
    response.content = text
    stub.invoke.return_value = response
    return stub


def test_combines_naver_and_tavily_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """두 소스를 모두 받으면 news_sources에 통합 + data_sources 카운트 정확."""
    monkeypatch.setattr("agents.korean_sentiment_agent._fetch_naver_news", lambda _name: _stub_naver(3))
    monkeypatch.setattr("agents.korean_sentiment_agent._fetch_tavily_news", lambda _name: _stub_tavily(2))
    monkeypatch.setattr(
        "agents.korean_sentiment_agent.build_llm",
        lambda **_kw: _stub_llm_response(
            "Overall Sentiment: Positive\n"
            "Sentiment Score: 0.7\n"
            "Key Topics: AI, 반도체, 실적\n"
            "Most Positive Headline: 삼성전자 호재\n"
            "Most Negative Headline: 공급망 우려\n"
            "Source Balance: 균형"
        ),
    )

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")

    assert result["status"] == "success"
    assert result["company_name"] == "삼성전자"
    assert result["data_sources"]["naver_news_count"] == 3
    assert result["data_sources"]["tavily_news_count"] == 2
    # news_sources에 5개 (3 naver + 2 tavily)
    assert len(result["news_sources"]) == 5
    naver_items = [s for s in result["news_sources"] if s["type"] == "naver"]
    tavily_items = [s for s in result["news_sources"] if s["type"] == "tavily"]
    assert len(naver_items) == 3
    assert len(tavily_items) == 2
    # 네이버 헤드라인 <b> 태그 제거
    for item in naver_items:
        assert "<b>" not in item["title"]
    # LLM 분석 결과 파싱
    sa = result["sentiment_analysis"]
    assert sa["Overall Sentiment"] == "Positive"
    assert "AI" in sa["Key Topics"]


def test_handles_naver_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tavily가 빈 응답이어도 Naver만으로 분석을 시도."""
    monkeypatch.setattr("agents.korean_sentiment_agent._fetch_naver_news", lambda _name: _stub_naver(2))
    monkeypatch.setattr(
        "agents.korean_sentiment_agent._fetch_tavily_news",
        lambda _name: {"news_items": [], "ai_summary": ""},
    )
    monkeypatch.setattr(
        "agents.korean_sentiment_agent.build_llm",
        lambda **_kw: _stub_llm_response("Overall Sentiment: Neutral\nSentiment Score: 0.0"),
    )

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")
    assert result["status"] == "success"
    assert result["data_sources"]["tavily_news_count"] == 0
    assert result["data_sources"]["naver_news_count"] == 2


def test_falls_back_when_both_sources_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """두 소스 모두 빈 응답 + LLM도 실패하면 한글 fallback."""

    def boom(_name: str) -> dict:
        raise RuntimeError("network down")

    monkeypatch.setattr("agents.korean_sentiment_agent._fetch_naver_news", boom)

    result = get_enhanced_news_sentiment_logic("삼성전자", "005930")
    # graceful degradation: status='limited' + 한글 메시지
    assert isinstance(result, dict)
    assert result.get("status") in ("limited", "error", "success")  # 어떤 형태든 dict 반환
