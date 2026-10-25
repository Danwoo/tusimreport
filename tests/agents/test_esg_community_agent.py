"""ESG와 Community agent 단위 테스트.

둘 다 외부 호출 한 군데 + LLM 한 군데 패턴이라 묶어서 테스트.
"""

from __future__ import annotations

import pytest

from agents.korean_community_agent import get_community_sentiment_analysis_logic
from agents.korean_esg_analysis_agent import get_esg_analysis_logic

# ----------------------------------------------------------------------
# ESG agent
# ----------------------------------------------------------------------


def _dart_payload(disclosure_titles: list[str], ceo: str | None = "한종희") -> dict:
    """`get_comprehensive_company_data`가 실제로 돌려주는 모양."""
    return {
        "stock_code": "005930",
        "corp_code": "00126380",
        "company_info": {
            "corp_name": "삼성전자(주)",
            "stock_name": "삼성전자",
            "ceo_nm": ceo,
            "corp_cls": "Y",
            "induty_code": "264",
            "est_dt": "19690113",
        },
        "financial_statements": {
            "current_year": {"error": "not found"},
            "previous_year": {"error": "not found"},
        },
        "recent_disclosures": [
            {"rcept_no": f"2025111700{i:04d}", "report_nm": title, "rcept_dt": "20251117"}
            for i, title in enumerate(disclosure_titles)
        ],
        "data_source": "DART OpenAPI",
        "last_updated": "2025-11-17T10:00:00+09:00",
    }


class TestESGAgent:
    def test_maps_real_dart_fields_into_pillars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload(
                [
                    "임원ㆍ주요주주특정증권등소유상황보고서",
                    "지속가능경영보고서등관련사항(자율공시)",
                    "온실가스 배출량 검증 결과(자율공시)",
                    "분기보고서 (2025.09)",
                ]
            ),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["status"] == "success"
        assert result["company_name"] == "삼성전자"
        assert result["basic_info"]["ceo_nm"] == "한종희"
        assert result["basic_info"]["induty_code"] == "264"
        assert result["disclosures_reviewed"] == 4

        governance = result["governance"]
        assert governance["available"] is True
        assert governance["ceo_name"] == "한종희"
        assert [d["title"] for d in governance["related_disclosures"]] == [
            "임원ㆍ주요주주특정증권등소유상황보고서"
        ]

        assert result["social"]["available"] is True
        assert result["social"]["related_disclosures"][0]["title"].startswith("지속가능경영보고서")

        env_titles = [d["title"] for d in result["environmental"]["related_disclosures"]]
        assert "온실가스 배출량 검증 결과(자율공시)" in env_titles
        assert "분기보고서 (2025.09)" not in env_titles
        # ISO timestamp + KST offset
        assert "+09:00" in result["last_updated"]

    def test_pillars_without_dart_evidence_are_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload(["분기보고서 (2025.09)"], ceo=None),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["status"] == "no_data"
        for pillar in ("governance", "social", "environmental"):
            assert result[pillar]["available"] is False, pillar
            assert result[pillar]["related_disclosures"] == []
            assert "1건" in result[pillar]["reason"]
        assert "ceo_name" not in result["governance"]
        # 점수·등급을 지어내지 않는다.
        assert result["esg_rating"] is None
        for invented in ("esg_score", "audit_opinion", "employee_info", "board_composition"):
            assert invented not in str(result), invented

    def test_dart_unavailable_returns_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: {"error": "DART API key missing"},
        )

        result = get_esg_analysis_logic("005930", "삼성전자")
        assert "error" in result
        # 호출자가 진단할 수 있도록 원인 echo
        assert "DART" in result.get("details", "") or "DART" in result.get("error", "")

    def test_dart_error_details_do_not_carry_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DART 요청 예외 문자열은 crtfc_key가 든 URL을 담는다 — 도구 출력(LLM 입력)에 실리면 안 된다."""
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: {
                "error": "Company info error: 500 Server Error for url: "
                "https://opendart.fss.or.kr/api/company.json?corp_code=00126380&crtfc_key=DARTKEY12345"
            },
        )

        result = get_esg_analysis_logic("005930", "삼성전자")
        assert "DARTKEY12345" not in str(result)
        assert "crtfc_key=***" in result["details"]

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
    def test_returns_truncated_posts_without_calling_an_llm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_community_agent.fetch_paxnet_discussions",
            lambda _code, max_posts=10: {
                "posts": [
                    {"title": "삼성 호재", "content": "실적 좋다 " * 60, "url": "https://paxnet/1"},
                    {"title": "조정 의견", "content": "단기 매도세 " * 60, "url": "https://paxnet/2"},
                ],
                "total_posts": 2,
            },
        )
        monkeypatch.setattr(
            "agents.korean_community_agent.build_llm",
            lambda **_kw: pytest.fail("the tool must not call an LLM"),
        )

        result = get_community_sentiment_analysis_logic("삼성전자", "005930")

        assert result["status"] == "success"
        assert result["total_posts"] == 2
        assert [post["title"] for post in result["posts"]] == ["삼성 호재", "조정 의견"]
        assert all(len(post["content"]) <= 300 for post in result["posts"])
        assert "sentiment_analysis" not in result

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
