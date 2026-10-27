"""Investment opinion agent의 순수 함수와 LLM 호출 경로 단위 테스트.

근거 없는 값은 None으로 둔다: 현재가를 못 받거나, LLM 가격이 숫자가 아니거나 현재가 대비
범위를 벗어나면 가격 필드는 None이고, 손익비는 가격에서 직접 계산한다.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from agents.korean_investment_opinion_agent import (
    _parse_opinion,
    _parse_price,
    _risk_reward,
    generate_investment_opinion,
)


class TestParsePrice:
    def test_keeps_a_price_in_range(self) -> None:
        assert _parse_price(78000, current_price=65000) == 78000

    @pytest.mark.parametrize("raw", [200000, 1000, 0, -1000, "N/A", None])
    def test_drops_out_of_range_or_unparseable_prices(self, raw: object) -> None:
        assert _parse_price(raw, current_price=65000) is None

    @pytest.mark.parametrize("current", [None, 0])
    def test_no_price_without_a_current_price(self, current: float | None) -> None:
        assert _parse_price(70000, current_price=current) is None


def test_risk_reward_is_computed_from_prices() -> None:
    assert _risk_reward(65000, 78000, 60000) == 2.6
    assert _risk_reward(65000, None, 60000) is None
    assert _risk_reward(65000, 60000, 70000) is None


@pytest.mark.parametrize(
    ("raw", "label"),
    [("BUY", "BUY"), ("buy", "BUY"), ("강력매수", "BUY"), ("중립", "HOLD"), ("매도", "SELL")],
)
def test_opinion_aliases(raw: str, label: str) -> None:
    assert _parse_opinion(raw) == label


def _make_stub_llm(opinion_payload: dict) -> MagicMock:
    """build_llm()이 돌려줄 가짜 ChatModel."""
    stub = MagicMock()
    response = MagicMock()
    response.content = json.dumps(opinion_payload, ensure_ascii=False)
    stub.invoke.return_value = response
    return stub


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "opinion": "BUY",
        "confidence": 70,
        "reasoning": "test",
        "key_positives": ["a"],
        "key_risks": ["x"],
        "timeframe": "중기(3-6개월)",
        "target_price": 78000,
        "stop_loss": 60000,
        "split_buy_strategy": [
            {"order": "1차", "price_range": "64,000-66,000", "weight": "30%", "timing": "현재가 근처"}
        ],
    }
    return {**base, **overrides}


def _run(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any], current_price: float | None = 65000.0
) -> dict:
    monkeypatch.setattr(
        "agents.korean_investment_opinion_agent.build_llm", lambda **_kw: _make_stub_llm(payload)
    )
    monkeypatch.setattr("agents.korean_investment_opinion_agent._extract_current_price", lambda *_a: None)
    args: dict[str, Any] = {"company_name": "삼성전자", "stock_code": "005930", "agent_results": {}}
    if current_price is not None:
        args["current_price"] = current_price
    return generate_investment_opinion.invoke(args)


def test_valid_payload_keeps_prices_and_computes_risk_reward(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, _payload())

    assert (result["target_price"], result["stop_loss"]) == (78000, 60000)
    assert result["risk_reward_ratio"] == 2.6
    assert result["split_buy_strategy"][0]["order"] == "1차"


def test_unknown_opinion_is_an_error_not_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, _payload(opinion="maybe"))

    assert "error" in result


@pytest.mark.parametrize(("bad", "expected"), [(150, 100), (-5, 0), ("abc", None), (None, None)])
def test_confidence_is_clamped_or_none(
    monkeypatch: pytest.MonkeyPatch, bad: object, expected: int | None
) -> None:
    assert _run(monkeypatch, _payload(confidence=bad))["confidence"] == expected


def test_out_of_range_prices_are_dropped_not_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, _payload(target_price=999_999_999, stop_loss=-5000))

    assert result["target_price"] is None
    assert result["stop_loss"] is None
    assert result["risk_reward_ratio"] is None


def test_unknown_current_price_leaves_every_price_field_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch, _payload(), current_price=None)

    assert result["current_price"] is None
    assert (result["target_price"], result["stop_loss"], result["risk_reward_ratio"]) == (None, None, None)
    assert result["split_buy_strategy"] == []


def test_invalid_json_returns_an_error_result_without_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_llm = MagicMock()
    bad_llm.invoke.return_value = MagicMock(content="this is not json at all")
    monkeypatch.setattr("agents.korean_investment_opinion_agent.build_llm", lambda **_kw: bad_llm)

    result = generate_investment_opinion.invoke(
        {"company_name": "삼성전자", "stock_code": "005930", "agent_results": {}, "current_price": 65000.0}
    )

    assert "error" in result
    assert result["target_price"] is None and result["stop_loss"] is None


def test_summary_covers_every_agent_and_names_missing_areas() -> None:
    from agents.korean_investment_opinion_agent import _summarize_agent_results, opinion_sections
    from core.korean_supervisor_langgraph import EXPERT_LABELS
    from core.signals import AGENT_TO_SIGNAL

    results = {
        "global_market_expert": "글로벌 시장 본문",
        "context_expert": "시장 환경 본문",
        "esg_expert": "   ",
    }

    assert list(opinion_sections(results)) == ["context_expert", "global_market_expert"]
    summary = _summarize_agent_results(results)
    assert "글로벌 시장 본문" in summary
    assert summary.index("시장 환경 본문") < summary.index("글로벌 시장 본문")
    missing_section = summary.split("데이터 없음", 1)[1]
    for name in AGENT_TO_SIGNAL:
        label = EXPERT_LABELS[name]
        if name in ("context_expert", "global_market_expert"):
            assert label not in missing_section
        else:
            assert label in missing_section


def test_prompt_counts_come_from_the_sections_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.signals import AGENT_TO_SIGNAL

    stub = _make_stub_llm({"opinion": "HOLD", "confidence": 50})
    monkeypatch.setattr("agents.korean_investment_opinion_agent.build_llm", lambda **_kw: stub)
    results = {name: f"{name} 본문" for name in list(AGENT_TO_SIGNAL)[:5]}

    generate_investment_opinion.invoke(
        {"company_name": "삼성전자", "stock_code": "005930", "agent_results": results, "current_price": 70000}
    )

    messages = stub.invoke.call_args.args[0]
    prompt = "\n".join(m.content for m in messages)
    assert "8개" not in prompt
    assert f"5/{len(AGENT_TO_SIGNAL)}" in prompt
