"""ESG와 Community agent 단위 테스트.

둘 다 외부 호출 한 군데 + LLM 한 군데 패턴이라 묶어서 테스트.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.korean_community_agent import get_community_sentiment_analysis_logic
from agents.korean_esg_analysis_agent import get_esg_analysis_logic


def _stub_llm(text: str) -> MagicMock:
    stub = MagicMock()
    response = MagicMock()
    response.content = text
    stub.invoke.return_value = response
    return stub


# ----------------------------------------------------------------------
# ESG agent
# ----------------------------------------------------------------------


class TestESGAgent:
    def test_structures_dart_payload_into_esg_pillars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: {
                "basic_info": {"corp_name": "삼성전자"},
                "ceo_info": {"name": "한종희"},
                "board_info": {"members": 10},
                "audit_opinion": "적정",
                "shareholders": [{"name": "이재용", "ratio": 0.18}],
                "dividend_info": {"yield": 0.022},
                "employee_info": {"count": 120000},
                "business_info": {"segment": "반도체"},
                "business_nature": "반도체 제조",
                "environmental_info": {"emissions": "공시"},
            },
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["status"] == "success"
        assert result["company_name"] == "삼성전자"
        # 3 pillar 모두 채워졌는지
        assert result["governance"]["audit_opinion"] == "적정"
        assert result["social"]["employee_info"]["count"] == 120000
        assert result["environmental"]["business_nature"] == "반도체 제조"
        # ISO timestamp + KST offset
        assert "+09:00" in result["last_updated"]

    def test_dart_unavailable_returns_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: {"error": "DART API key missing"},
        )

        result = get_esg_analysis_logic("005930", "삼성전자")
        assert "error" in result
        # 호출자가 진단할 수 있도록 원인 echo
        assert "DART" in result.get("details", "") or "DART" in result.get("error", "")

    def test_dart_raises_falls_back_korean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_code: str) -> dict:
            raise RuntimeError("upstream DART down")

        monkeypatch.setattr("agents.korean_esg_analysis_agent.get_comprehensive_company_data", boom)

        result = get_esg_analysis_logic("005930", "삼성전자")
        # graceful degradation
        assert isinstance(result, dict)
        assert result.get("status") in ("limited", "error", None)
        assert "error" in result or "message" in result


# ----------------------------------------------------------------------
# Community agent
# ----------------------------------------------------------------------


class TestCommunityAgent:
    def test_processes_paxnet_posts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_community_agent.fetch_paxnet_discussions",
            lambda _code, max_posts=10: {
                "posts": [
                    {"title": "삼성 호재", "content": "실적 좋다 " * 60},
                    {"title": "조정 의견", "content": "단기 매도세 " * 60},
                ],
                "total_posts": 2,
            },
        )
        monkeypatch.setattr(
            "agents.korean_community_agent.build_llm",
            lambda **_kw: _stub_llm(
                "Community Sentiment: Mixed\n"
                "Sentiment Score: 0.1\n"
                "Hot Topics: 실적, 매도세\n"
                "Bullish Headline: 실적 좋다\n"
                "Bearish Headline: 단기 매도세\n"
                "Investor Mindset: Cautious"
            ),
        )

        result = get_community_sentiment_analysis_logic("삼성전자", "005930")

        assert result["status"] in ("success", None) or "error" not in result
        # 게시글 카운트 정확
        if "data_sources" in result:
            assert result["data_sources"].get("total_posts", 0) == 2

    def test_no_posts_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_community_agent.fetch_paxnet_discussions",
            lambda _code, max_posts=10: {"posts": [], "total_posts": 0},
        )

        result = get_community_sentiment_analysis_logic("삼성전자", "005930")
        # 빈 데이터 → error 키 또는 부분 결과
        assert "error" in result or result.get("status") == "limited"

    def test_paxnet_failure_wraps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_code: str, max_posts: int = 10) -> dict:
            raise RuntimeError("selenium crashed")

        monkeypatch.setattr("agents.korean_community_agent.fetch_paxnet_discussions", boom)

        result = get_community_sentiment_analysis_logic("삼성전자", "005930")
        assert isinstance(result, dict)
        # graceful — raise하지 않음
        assert "error" in result or result.get("status") in ("limited", "error")
