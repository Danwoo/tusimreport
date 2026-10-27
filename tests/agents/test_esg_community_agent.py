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
        # 대표자명은 기업개황(basic_info)일 뿐 지배구조 근거가 아니다.
        assert "ceo_name" not in governance
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
        """상장사는 DART가 늘 대표자명을 준다 — 그것만으로는 어느 축도 available이 아니다."""
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload(["분기보고서 (2025.09)", "[기재정정]분기보고서 (2025.06)"]),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["status"] == "no_data"
        assert result["basic_info"]["ceo_nm"] == "한종희"
        for pillar in ("governance", "social", "environmental"):
            assert result[pillar]["available"] is False, pillar
            assert result[pillar]["related_disclosures"] == []
            assert "최근 공시 2건(최대 20건) 중 관련 공시 없음" in result[pillar]["reason"]
            assert "90일 DART 공시 2건" not in result[pillar]["reason"]
        assert "ceo_name" not in result["governance"]
        assert "한종희" not in str(result["governance"])
        # 점수·등급을 지어내지 않는다.
        assert result["esg_rating"] is None
        for invented in ("esg_score", "audit_opinion", "employee_info", "board_composition"):
            assert invented not in str(result), invented

    def test_empty_disclosure_list_is_no_data_with_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload([]),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["status"] == "no_data"
        assert result["disclosures_reviewed"] == 0
        assert "0건" not in result["governance"]["reason"]
        assert "받지 못함" in result["governance"]["reason"]

    def test_board_resolution_titles_are_not_social_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """'이사회' 안의 '사회'를 사회(S) 축 근거로 세지 않는다."""
        board_titles = [
            "대규모내부거래에대한이사회의결",
            "[기재정정]대규모내부거래에대한이사회의결",
            "이사회내위원회설치및구성(자율공시)",
        ]
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload(board_titles),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert result["social"]["available"] is False
        assert result["social"]["related_disclosures"] == []
        assert "최근 공시 3건(최대 20건)" in result["social"]["reason"]
        assert [d["title"] for d in result["governance"]["related_disclosures"]] == board_titles
        assert result["status"] == "success"

    def test_social_contribution_titles_are_social_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agents.korean_esg_analysis_agent.get_comprehensive_company_data",
            lambda _code: _dart_payload(["기타경영사항(자율공시)(사회공헌기금 출연)"]),
        )

        result = get_esg_analysis_logic("005930", "삼성전자")

        assert [d["title"] for d in result["social"]["related_disclosures"]] == [
            "기타경영사항(자율공시)(사회공헌기금 출연)"
        ]
        assert result["governance"]["available"] is False

    def test_prompt_does_not_ask_to_judge_board_from_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, str] = {}

        def fake_create_react_agent(*, model: object, tools: list, prompt: str, name: str) -> object:
            captured["prompt"] = prompt
            return object()

        monkeypatch.setattr("agents.korean_esg_analysis_agent.build_llm", lambda **_kw: object())
        monkeypatch.setattr("agents.korean_esg_analysis_agent.create_react_agent", fake_create_react_agent)

        from agents.korean_esg_analysis_agent import create_esg_agent

        create_esg_agent()
        prompt = captured["prompt"]
        assert "이사회가 제대로 견제 역할을 하고 있는지" not in prompt
        assert "대표자 이름이나 기업개황만으로" in prompt
        assert "related_disclosures만 근거로" in prompt

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
    @pytest.fixture(autouse=True)
    def crawl_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("agents.korean_community_agent.settings.enable_paxnet_crawl", True)

    def test_crawl_is_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Paxnet 약관을 확인하지 못해 기본값에서는 요청하지 않는다."""
        monkeypatch.setattr("agents.korean_community_agent.settings.enable_paxnet_crawl", False)
        monkeypatch.setattr(
            "agents.korean_community_agent.fetch_paxnet_discussions",
            lambda *_a, **_kw: pytest.fail("must not crawl when ENABLE_PAXNET_CRAWL is off"),
        )

        result = get_community_sentiment_analysis_logic("삼성전자", "005930")

        assert "ENABLE_PAXNET_CRAWL" in result["error"]

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
