"""EnterpriseContextManager 단위 테스트.

tiktoken은 lazy load라 인터넷 없이도 import 시점엔 안전. 다만 인코딩
다운로드 시도가 실패할 수 있어 count_tokens는 fallback 휴리스틱 분기를
타게 된다 — 테스트는 두 경로 모두 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.context_manager import (
    ContextWindow,
    EnterpriseContextManager,
    get_context_manager,
)


class TestContextWindow:
    def test_available_tokens_is_max_minus_reserved(self) -> None:
        w = ContextWindow(max_tokens=100_000, reserved_tokens=20_000)
        assert w.available_tokens == 80_000


class TestCountTokens:
    def test_returns_int_with_real_tiktoken(self) -> None:
        cm = EnterpriseContextManager(model_name="gpt-4")
        n = cm.count_tokens("hello world")
        assert isinstance(n, int)
        assert n > 0

    def test_falls_back_when_encoding_load_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cm = EnterpriseContextManager(model_name="gpt-4")

        # encoding property가 raise하도록 한 번 강제 (네트워크 없는 환경 시뮬레이션)
        class _Boom:
            def encode(self, _text: str) -> list[int]:
                raise RuntimeError("encoding not downloaded")

        # _encoding을 직접 주입해 lazy load 우회
        cm._encoding = _Boom()
        n = cm.count_tokens("0123456789ABCDEF")  # 16 chars
        # fallback: len // 4 = 4
        assert n == 4


class TestPreserveAgentOutput:
    def test_returns_full_text_unchanged(self) -> None:
        cm = EnterpriseContextManager()
        text = "에이전트 출력 " * 100
        assert cm.preserve_agent_output("context_expert", text) == text


class TestCreateProgressiveSummary:
    def test_assembles_known_agent_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cm = EnterpriseContextManager()
        # compress_agent_output이 없는 메서드라 stub. 실제로는 클래스에
        # 메서드가 있을 거라 가정 — 없으면 AttributeError가 나서 테스트가
        # 'no method' 시그널로 작동.
        monkeypatch.setattr(cm, "compress_agent_output", lambda agent_name, output: f"[c:{agent_name}]")

        result = cm.create_progressive_summary(
            {
                "context_expert": "macro ok",
                "sentiment_expert": "긍정",
            }
        )
        # 한국어 라벨이 들어가야 한다
        assert "## 시장환경" in result
        assert "## 시장심리" in result
        # 압축 결과가 본문에 포함
        assert "[c:context_expert]" in result

    def test_unknown_agent_uses_key_as_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cm = EnterpriseContextManager()
        monkeypatch.setattr(cm, "compress_agent_output", lambda a, o: o)
        result = cm.create_progressive_summary({"unknown_expert": "내용"})
        assert "## unknown_expert" in result


class TestOptimizeDataRequests:
    def test_caches_repeated_request(self) -> None:
        cm = EnterpriseContextManager()
        req = {"stock": "005930"}
        r1 = cm.optimize_data_requests("context_expert", req)
        r2 = cm.optimize_data_requests("context_expert", req)
        assert r1 == r2 == req
        # 캐시에 들어 있어야
        assert len(cm.data_cache) == 1

    def test_lru_evicts_when_over_50(self) -> None:
        cm = EnterpriseContextManager()
        for i in range(60):
            cm.optimize_data_requests(f"agent{i}", {"i": i})
        # 한도 50을 초과한 채로 유지되지 않아야 함
        assert len(cm.data_cache) <= 50


class TestCreateContextAwarePrompt:
    def test_returns_unchanged_when_within_budget(self) -> None:
        cm = EnterpriseContextManager()
        prompt = "짧은 프롬프트"
        # 충분히 큰 budget을 주면 그대로 반환
        out = cm.create_context_aware_prompt(prompt, available_tokens=10_000)
        assert out == prompt

    def test_compresses_when_over_budget(self) -> None:
        cm = EnterpriseContextManager()
        # 길어서 budget 초과인 프롬프트
        long_prompt = (
            "## 분석 구조\n" + "## 헤더\n" * 200 + "상세 라인입니다. " * 200 + "CRITICAL 중요한 라인\n"
        )
        out = cm.create_context_aware_prompt(long_prompt, available_tokens=50)
        # 압축돼서 짧아져야
        assert len(out) < len(long_prompt)
        # CRITICAL 라인은 보존
        assert "CRITICAL" in out


class TestGetContextStats:
    def test_returns_expected_keys(self) -> None:
        cm = EnterpriseContextManager()
        stats = cm.get_context_stats()
        assert "max_tokens" in stats
        assert "available_tokens" in stats
        assert "cached_data_items" in stats
        assert "+09:00" in stats["timestamp"]


def test_singleton_returns_same_instance() -> None:
    a = get_context_manager()
    b = get_context_manager()
    assert a is b
