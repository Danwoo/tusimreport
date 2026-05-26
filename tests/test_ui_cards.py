"""ui.cards 카드 빌더 단위 테스트.

LLM/네트워크 없이 순수 HTML 생성만 검증한다.
"""

from ui.cards import (
    AGENT_CONFIGS,
    create_investment_opinion_card,
    create_result_card,
    get_agent_config,
)


class TestAgentConfig:
    def test_known_agent_returns_full_config(self):
        cfg = get_agent_config("context_expert")
        assert cfg["icon"] and cfg["name"] and cfg["color"]

    def test_unknown_agent_returns_default(self):
        cfg = get_agent_config("nonexistent_expert")
        assert cfg["icon"] == "🤖"
        assert cfg["name"] == "nonexistent_expert"

    def test_all_agent_configs_match_signals(self):
        from core.signals import AGENT_TO_SIGNAL

        assert set(AGENT_CONFIGS.keys()) == set(AGENT_TO_SIGNAL.keys())


class TestResultCard:
    def test_waiting_card_shows_placeholder_text(self):
        cfg = get_agent_config("context_expert")
        html = create_result_card("context_expert", cfg, "waiting")
        assert "준비하고 있습니다" in html
        assert "status-waiting" in html

    def test_completed_card_includes_content(self):
        cfg = get_agent_config("context_expert")
        html = create_result_card("context_expert", cfg, "completed", content="분석 결과")
        assert "분석 결과" in html
        assert "status-completed" in html

    def test_sentiment_card_renders_news_sources(self):
        cfg = get_agent_config("sentiment_expert")
        sources = [{"title": "삼성전자 호재", "url": "https://example.com/1"}]
        html = create_result_card("sentiment_expert", cfg, "completed", "분석", sources)
        assert "분석된 뉴스" in html
        assert "삼성전자 호재" in html
        assert "https://example.com/1" in html

    def test_community_card_renders_post_sources(self):
        cfg = get_agent_config("community_expert")
        sources = [{"title": "내가 산 이유", "url": "https://example.com/post"}]
        html = create_result_card("community_expert", cfg, "completed", "분석", sources)
        assert "분석된 커뮤니티 게시글" in html
        assert "내가 산 이유" in html

    def test_running_status_does_not_render_sources(self):
        cfg = get_agent_config("sentiment_expert")
        sources = [{"title": "뉴스", "url": "https://x.com"}]
        html = create_result_card("sentiment_expert", cfg, "running", "in progress", sources)
        # running 상태에선 출처 섹션을 보여주지 않는다
        assert "분석된 뉴스" not in html


class TestInvestmentOpinionCard:
    def _minimal_data(self, **overrides):
        base = {
            "opinion": "BUY",
            "confidence": 75,
            "reasoning": "재무 건전성 양호",
            "key_positives": ["매출 성장", "기관 순매수"],
            "key_risks": ["과매수 구간"],
            "timeframe": "중기(3-6개월)",
            "current_price": 65000.0,
            "target_price": 78000.0,
            "stop_loss": 59000.0,
            "risk_reward_ratio": 2.2,
            "split_buy_strategy": [
                {"order": "1차", "price_range": "64000-66000", "weight": "30%", "timing": "지금"}
            ],
        }
        base.update(overrides)
        return base

    def test_buy_opinion_renders_buy_class(self):
        html = create_investment_opinion_card(self._minimal_data())
        assert "opinion-buy" in html
        assert "BUY" in html

    def test_sell_opinion_renders_sell_class(self):
        html = create_investment_opinion_card(self._minimal_data(opinion="SELL"))
        assert "opinion-sell" in html

    def test_unknown_opinion_falls_back_to_hold(self):
        html = create_investment_opinion_card(self._minimal_data(opinion="WTF"))
        assert "opinion-hold" in html

    def test_confidence_class_thresholds(self):
        assert "confidence-high" in create_investment_opinion_card(self._minimal_data(confidence=85))
        assert "confidence-medium" in create_investment_opinion_card(self._minimal_data(confidence=65))
        assert "confidence-low" in create_investment_opinion_card(self._minimal_data(confidence=45))
        assert "confidence-very-low" in create_investment_opinion_card(self._minimal_data(confidence=20))

    def test_zero_current_price_does_not_crash(self):
        # current_price=0이어도 ZeroDivisionError 없이 그려져야 한다
        html = create_investment_opinion_card(self._minimal_data(current_price=0))
        assert "investment-opinion-card" in html

    def test_split_buy_strategy_rows_rendered(self):
        html = create_investment_opinion_card(self._minimal_data())
        assert "1차" in html
        assert "64000-66000" in html


class TestXSSDefense:
    """LLM 출력/외부 API 응답이 HTML로 그대로 박혀 XSS가 되는 회귀를 막는 테스트."""

    def test_news_title_with_script_tag_is_escaped(self):
        cfg = get_agent_config("sentiment_expert")
        sources = [{"title": "<script>alert('xss')</script>해킹", "url": "https://x.com"}]
        html = create_result_card("sentiment_expert", cfg, "completed", "분석", sources)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_javascript_url_is_dropped(self):
        cfg = get_agent_config("sentiment_expert")
        sources = [{"title": "정상제목", "url": "javascript:alert(1)"}]
        html = create_result_card("sentiment_expert", cfg, "completed", "분석", sources)
        assert "javascript:" not in html
        assert "정상제목" in html  # 제목은 살아남아야 함

    def test_data_url_is_dropped(self):
        cfg = get_agent_config("sentiment_expert")
        sources = [{"title": "t", "url": "data:text/html,<script>1</script>"}]
        html = create_result_card("sentiment_expert", cfg, "completed", "분석", sources)
        assert "<script>" not in html
        assert "data:text/html" not in html

    def test_llm_reasoning_html_is_escaped(self):
        opinion = {
            "opinion": "BUY",
            "confidence": 75,
            "reasoning": "<img src=x onerror='alert(1)'>",
            "key_positives": [],
            "key_risks": [],
            "current_price": 100,
            "target_price": 110,
            "stop_loss": 95,
            "risk_reward_ratio": 2.0,
            "split_buy_strategy": [],
        }
        html = create_investment_opinion_card(opinion)
        # raw <img 태그가 살아있으면 안 됨 (escape된 &lt;img는 OK)
        assert "<img" not in html
        assert "&lt;img" in html

    def test_llm_positives_html_is_escaped(self):
        opinion = {
            "opinion": "BUY",
            "confidence": 60,
            "reasoning": "ok",
            "key_positives": ["<b>fake bold</b>", "<script>x</script>"],
            "key_risks": [],
            "current_price": 100,
            "target_price": 110,
            "stop_loss": 95,
            "risk_reward_ratio": 2.0,
            "split_buy_strategy": [],
        }
        html = create_investment_opinion_card(opinion)
        assert "<b>fake bold" not in html
        assert "<script>x" not in html
        assert "&lt;b&gt;" in html

    def test_invalid_opinion_string_cannot_inject(self):
        # opinion 필드를 통한 클래스 인젝션 시도도 차단되어야 함
        opinion = {
            "opinion": '"><script>alert(1)</script>',
            "confidence": 50,
            "reasoning": "r",
            "key_positives": [],
            "key_risks": [],
            "current_price": 100,
            "target_price": 110,
            "stop_loss": 95,
            "risk_reward_ratio": 1.5,
            "split_buy_strategy": [],
        }
        html = create_investment_opinion_card(opinion)
        assert "<script>" not in html
        # 화이트리스트 밖이므로 HOLD로 fallback
        assert "opinion-hold" in html

    def test_confidence_out_of_range_is_clamped(self):
        for bad in (-50, 150, "lol", None):
            opinion = {
                "opinion": "BUY",
                "confidence": bad,
                "reasoning": "r",
                "key_positives": [],
                "key_risks": [],
                "current_price": 100,
                "target_price": 110,
                "stop_loss": 95,
                "risk_reward_ratio": 1.5,
                "split_buy_strategy": [],
            }
            html = create_investment_opinion_card(opinion)
            # 부정값/문자열이 width:{x}%로 흘러들어가도 깨지지 않고 0-100 사이로 clamp
            assert "investment-opinion-card" in html


class TestEscapeHtmlPublic:
    """escape_html이 다른 모듈(main.py 등)에서 안전하게 쓰일 수 있는지."""

    def test_escapes_script(self):
        from ui.cards import escape_html

        assert escape_html("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"

    def test_handles_none(self):
        from ui.cards import escape_html

        assert escape_html(None) == ""

    def test_handles_non_string(self):
        from ui.cards import escape_html

        # int/float 같은 안전한 타입도 문자열로 변환 후 escape
        assert escape_html(123) == "123"


class TestThresholdHelpers:
    """경계값 회귀 테스트 (시니어 리뷰가 지적한 _confidence_class/_rr_label)."""

    def test_confidence_class_boundaries(self):
        from ui.cards import _confidence_class

        assert _confidence_class(80) == "confidence-high"
        assert _confidence_class(79) == "confidence-medium"
        assert _confidence_class(60) == "confidence-medium"
        assert _confidence_class(59) == "confidence-low"
        assert _confidence_class(40) == "confidence-low"
        assert _confidence_class(39) == "confidence-very-low"
        assert _confidence_class(0) == "confidence-very-low"

    def test_rr_label_boundaries(self):
        from ui.cards import _rr_label

        assert _rr_label(2.0) == "Very Good"
        assert _rr_label(1.99) == "Good"
        assert _rr_label(1.5) == "Good"
        assert _rr_label(1.49) == "Fair"
        assert _rr_label(1.0) == "Fair"
        assert _rr_label(0.99) == "Risky"
        assert _rr_label(0.0) == "Risky"
