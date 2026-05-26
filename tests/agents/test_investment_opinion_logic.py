"""Investment opinion agent의 순수 함수와 LLM 호출 경로 단위 테스트.

테스트되는 시나리오:
- _clamp_price: 0/음수/문자열/너무 큰 값/너무 작은 값에 대한 방어
- generate_investment_opinion: LLM이 반환한 JSON을 파싱·정규화·clamp하는 경로
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agents.korean_investment_opinion_agent import (
    _clamp_price,
    generate_investment_opinion,
)


class TestClampPrice:
    def test_returns_raw_when_in_range(self) -> None:
        # 현재가 65000, raw=78000 → 78000 (1.2x, 한도 내)
        assert _clamp_price(78000, current_price=65000, default_mult=1.1) == 78000

    def test_clamps_to_upper_bound_when_too_high(self) -> None:
        # 2.0x 상한 — 200000 입력은 130000으로 clamp
        assert _clamp_price(200000, current_price=65000, default_mult=1.1) == 130000

    def test_clamps_to_lower_bound_when_too_low(self) -> None:
        # 0.5x 하한 — 1000 입력은 32500으로 clamp
        assert _clamp_price(1000, current_price=65000, default_mult=1.1) == 32500

    def test_falls_back_when_unparseable(self) -> None:
        # "N/A" → default_mult 적용
        assert _clamp_price("N/A", current_price=65000, default_mult=1.1) == 71500
        assert _clamp_price(None, current_price=65000, default_mult=1.1) == 71500

    def test_falls_back_when_zero_or_negative(self) -> None:
        assert _clamp_price(0, current_price=65000, default_mult=1.1) == 71500
        assert _clamp_price(-1000, current_price=65000, default_mult=1.1) == 71500

    def test_handles_current_price_zero(self) -> None:
        # current_price 0이면 default_mult 적용해도 0 — 정상 동작
        assert _clamp_price(50, current_price=0, default_mult=1.1) == 0


def _make_stub_llm(opinion_payload: dict) -> MagicMock:
    """build_llm()이 돌려줄 가짜 ChatModel.

    .invoke(messages) → response.content에 JSON 문자열을 넣어 반환.
    """
    stub = MagicMock()
    response = MagicMock()
    response.content = json.dumps(opinion_payload, ensure_ascii=False)
    stub.invoke.return_value = response
    return stub


def test_normalizes_buy_hold_sell_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM이 '강력매수' 같은 비표준 값을 돌려도 HOLD로 정규화."""
    monkeypatch.setattr(
        "agents.korean_investment_opinion_agent.build_llm",
        lambda **_kw: _make_stub_llm(
            {
                "opinion": "강력매수",  # 비표준
                "confidence": 80,
                "reasoning": "test",
                "key_positives": ["a", "b"],
                "key_risks": ["x", "y"],
                "timeframe": "중기(3-6개월)",
                "target_price": 70000,
                "stop_loss": 60000,
                "risk_reward_ratio": 2.0,
                "split_buy_strategy": [],
            }
        ),
    )

    result = generate_investment_opinion.invoke(
        {
            "company_name": "삼성전자",
            "stock_code": "005930",
            "agent_results": {},
            "current_price": 65000.0,
        }
    )

    assert result["opinion"] == "HOLD"


@pytest.mark.parametrize(
    ("bad", "expected_in"),
    [
        (150, range(99, 101)),
        (-5, range(0, 1)),
        ("abc", range(50, 51)),
    ],
)
def test_clamps_confidence_to_0_100(monkeypatch: pytest.MonkeyPatch, bad: object, expected_in: range) -> None:
    """LLM이 150 또는 -5를 돌려도 0-100으로 clamp."""
    payload = {
        "opinion": "BUY",
        "confidence": bad,
        "reasoning": "x",
        "key_positives": [],
        "key_risks": [],
        "timeframe": "중기(3-6개월)",
        "target_price": 70000,
        "stop_loss": 60000,
        "risk_reward_ratio": 1.5,
        "split_buy_strategy": [],
    }
    monkeypatch.setattr(
        "agents.korean_investment_opinion_agent.build_llm",
        lambda **_kw: _make_stub_llm(payload),
    )
    result = generate_investment_opinion.invoke(
        {
            "company_name": "삼성전자",
            "stock_code": "005930",
            "agent_results": {},
            "current_price": 65000.0,
        }
    )
    assert result["confidence"] in expected_in, f"bad={bad!r} got {result['confidence']}"


def test_clamps_target_and_stop_loss_against_current_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM이 999999 또는 음수를 돌려도 0.5x-2.0x 범위로 clamp."""
    monkeypatch.setattr(
        "agents.korean_investment_opinion_agent.build_llm",
        lambda **_kw: _make_stub_llm(
            {
                "opinion": "BUY",
                "confidence": 70,
                "reasoning": "test",
                "key_positives": [],
                "key_risks": [],
                "timeframe": "중기(3-6개월)",
                "target_price": 999_999_999,  # 비현실
                "stop_loss": -5000,  # 음수
                "risk_reward_ratio": 100.0,  # 비현실
                "split_buy_strategy": [],
            }
        ),
    )

    result = generate_investment_opinion.invoke(
        {
            "company_name": "삼성전자",
            "stock_code": "005930",
            "agent_results": {},
            "current_price": 65000.0,
        }
    )
    # 2.0x 상한 = 130000, 0.9x default = 58500
    assert result["target_price"] == 130000
    assert result["stop_loss"] == 58500
    # R/R 10배 상한
    assert result["risk_reward_ratio"] <= 10.0


def test_falls_back_when_llm_returns_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM이 깨진 JSON을 돌려도 raise하지 않고 fallback opinion 반환."""
    bad_llm = MagicMock()
    response = MagicMock()
    response.content = "this is not json at all"
    bad_llm.invoke.return_value = response

    monkeypatch.setattr(
        "agents.korean_investment_opinion_agent.build_llm",
        lambda **_kw: bad_llm,
    )

    result = generate_investment_opinion.invoke(
        {
            "company_name": "삼성전자",
            "stock_code": "005930",
            "agent_results": {},
            "current_price": 65000.0,
        }
    )
    assert isinstance(result, dict)
    # fallback opinion은 무조건 BUY/HOLD/SELL 중 하나
    assert result.get("opinion") in ("BUY", "HOLD", "SELL")
