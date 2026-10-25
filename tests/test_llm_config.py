"""OpenAI 호환 엔드포인트(LLM_BASE_URL) 선택 규칙과 build_llm 연결 검증."""

from __future__ import annotations

from typing import Any

import pytest

from config import llm_factory
from config.settings import (
    LLMConfig,
    check_minimum_requirements,
    get_api_key_status,
    get_llm_model,
    resolve_llm_config,
    settings,
)


@pytest.fixture
def clean_llm_settings(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """실행 환경의 LLM 관련 env 값이 테스트 결과에 섞이지 않게 비운다."""
    for field in (
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_max_requests_per_minute",
        "openai_api_key",
        "google_api_key",
    ):
        monkeypatch.setattr(settings, field, None)
    monkeypatch.setattr(settings, "use_gemini", False)
    return monkeypatch


@pytest.fixture
def fake_chat_openai(clean_llm_settings: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """ChatOpenAI 생성자에 넘어간 kwargs를 호출마다 기록한다."""
    calls: list[dict[str, Any]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    clean_llm_settings.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    clean_llm_settings.setattr(settings, "llm_base_url", "https://kiraai.vn/api/v1")
    clean_llm_settings.setattr(settings, "llm_model", "kira-mini-1.0")
    clean_llm_settings.setattr(settings, "llm_api_key", "kira_test")
    return calls


def test_openai_compatible_takes_precedence_over_openai(clean_llm_settings: pytest.MonkeyPatch) -> None:
    clean_llm_settings.setattr(settings, "llm_base_url", "https://api.groq.com/openai/v1")
    clean_llm_settings.setattr(settings, "llm_model", "llama-3.3-70b-versatile")
    clean_llm_settings.setattr(settings, "llm_api_key", "gsk_test")
    clean_llm_settings.setattr(settings, "openai_api_key", "sk-test")

    assert get_llm_model() == LLMConfig(
        "openai_compatible", "llama-3.3-70b-versatile", "gsk_test", "https://api.groq.com/openai/v1"
    )


@pytest.mark.parametrize("missing", ["llm_model", "llm_api_key"])
def test_incomplete_openai_compatible_does_not_fall_back(
    clean_llm_settings: pytest.MonkeyPatch, missing: str
) -> None:
    clean_llm_settings.setattr(settings, "llm_base_url", "https://api.groq.com/openai/v1")
    clean_llm_settings.setattr(settings, "llm_model", "llama-3.3-70b-versatile")
    clean_llm_settings.setattr(settings, "llm_api_key", "gsk_test")
    clean_llm_settings.setattr(settings, missing, None)
    clean_llm_settings.setattr(settings, "openai_api_key", "sk-test")

    assert get_llm_model(raise_on_missing=False) is None
    with pytest.raises(ValueError, match=missing.upper()):
        get_llm_model(raise_on_missing=True)

    has_llm, warnings = check_minimum_requirements()
    assert has_llm is False
    assert warnings
    assert missing.upper() in get_api_key_status()["llm"]


def test_build_llm_passes_base_url_to_chat_openai(clean_llm_settings: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    clean_llm_settings.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    clean_llm_settings.setattr(settings, "llm_base_url", "http://localhost:8080/v1")
    clean_llm_settings.setattr(settings, "llm_model", "Qwen/Qwen2.5-7B-Instruct")
    clean_llm_settings.setattr(settings, "llm_api_key", "EMPTY")

    llm = llm_factory.build_llm(temperature=0.2)

    assert isinstance(llm, FakeChatOpenAI)
    assert captured.pop("api_key").get_secret_value() == "EMPTY"
    assert captured == {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "temperature": 0.2,
        "base_url": "http://localhost:8080/v1",
    }


def test_status_matches_agents_when_use_gemini_has_no_google_key(
    clean_llm_settings: pytest.MonkeyPatch,
) -> None:
    """USE_GEMINI=true + OpenAI 키만: 에이전트의 build_llm()은 실패하므로 상태도 실패여야 한다."""
    clean_llm_settings.setattr(settings, "use_gemini", True)
    clean_llm_settings.setattr(settings, "google_api_key", "your_google_api_key_here")
    clean_llm_settings.setattr(settings, "openai_api_key", "sk-test")

    with pytest.raises(ValueError):
        llm_factory.build_llm(temperature=0.1)
    config, problem = resolve_llm_config()
    assert config is None
    assert problem is not None and "Google API" in problem
    assert check_minimum_requirements()[0] is False
    assert get_api_key_status()["llm"].startswith("❌")


def test_openai_path_keeps_default_base_url(clean_llm_settings: pytest.MonkeyPatch) -> None:
    clean_llm_settings.setattr(settings, "openai_api_key", "sk-test")

    config = get_llm_model()

    assert config is not None
    assert config.provider == "openai"
    assert config.base_url is None


def test_no_rate_limiter_by_default(fake_chat_openai: list[dict[str, Any]]) -> None:
    llm_factory.build_llm()

    assert "rate_limiter" not in fake_chat_openai[0]


def test_rate_limiter_is_shared_across_instances(
    fake_chat_openai: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_max_requests_per_minute", 25)

    llm_factory.build_llm(temperature=0.1)
    llm_factory.build_llm(temperature=0.3)

    first, second = (call["rate_limiter"] for call in fake_chat_openai)
    assert first is second
    assert first.requests_per_second == pytest.approx(25 / 60)


@pytest.mark.parametrize(("raw", "expected"), [("", None), ("25", 25.0)])
def test_blank_rate_limit_env_is_unset(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float | None
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_MAX_REQUESTS_PER_MINUTE", raw)

    assert Settings(_env_file=None).llm_max_requests_per_minute == expected
