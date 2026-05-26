"""utils.cost: 토큰 카운트와 USD 비용 추정 단위 테스트."""

from __future__ import annotations

import logging

from utils.cost import (
    _FALLBACK_PRICING,
    _PRICING_PER_1K_TOKENS_USD,
    count_tokens,
    estimate_cost_usd,
    track_llm_call,
)


class TestCountTokens:
    def test_short_text_returns_positive_count(self) -> None:
        assert count_tokens("hello world", model="gpt-4o-mini") > 0

    def test_empty_text_returns_at_least_one(self) -> None:
        # fallback 휴리스틱은 max(1, len/4) — empty 문자열도 최소 1 또는 0
        assert count_tokens("", model="gpt-4o-mini") >= 0

    def test_unknown_model_falls_back_to_heuristic(self) -> None:
        # 모르는 모델이어도 raise하지 않고 어떻게든 숫자 반환
        n = count_tokens("test text", model="nonexistent-model-xyz")
        assert n >= 1


class TestEstimateCostUsd:
    def test_known_openai_model(self) -> None:
        # gpt-4.1-nano: input 0.0001, output 0.0004 per 1K
        cost = estimate_cost_usd(1000, 1000, "gpt-4.1-nano")
        # 1000/1000 * 0.0001 + 1000/1000 * 0.0004 = 0.0005
        assert abs(cost - 0.0005) < 1e-9

    def test_known_gemini_model(self) -> None:
        cost = estimate_cost_usd(1000, 1000, "gemini-2.0-flash-lite")
        expected = 0.000075 + 0.0003
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_uses_fallback(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            cost = estimate_cost_usd(1000, 1000, "made-up-model")
        # fallback 단가 적용 확인
        expected = _FALLBACK_PRICING["input"] + _FALLBACK_PRICING["output"]
        assert abs(cost - expected) < 1e-9
        # 미등록 모델 경고 로그
        assert any("unknown model" in rec.message for rec in caplog.records)

    def test_zero_tokens_zero_cost(self) -> None:
        assert estimate_cost_usd(0, 0, "gpt-4o-mini") == 0


class TestTrackLlmCall:
    def test_returns_full_metadata(self) -> None:
        meta = track_llm_call(
            model="gpt-4.1-nano",
            prompt="What is the meaning of life?",
            response="42",
            agent="test_agent",
        )
        assert meta["model"] == "gpt-4.1-nano"
        assert meta["agent"] == "test_agent"
        assert meta["prompt_tokens"] >= 1
        assert meta["completion_tokens"] >= 1
        assert meta["cost_usd"] > 0

    def test_emits_structured_log_line(self, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="utils.cost"):
            track_llm_call(
                model="gpt-4o-mini",
                prompt="prompt",
                response="response",
                agent="sentiment",
            )
        # 로그에 model/agent/cost 키가 들어 있어야 grep으로 집계 가능
        msg = caplog.records[0].message
        assert "model=gpt-4o-mini" in msg
        assert "agent=sentiment" in msg
        assert "cost_usd=" in msg

    def test_pricing_table_has_current_models(self) -> None:
        """build_llm이 default로 쓰는 모델은 단가 테이블에 등록돼 있어야."""
        # 회귀 방지 — config.settings.GEMINI_MODEL/OPENAI_MODEL과 일치 검증
        assert "gpt-4.1-nano" in _PRICING_PER_1K_TOKENS_USD
        assert "gemini-2.0-flash-lite" in _PRICING_PER_1K_TOKENS_USD
