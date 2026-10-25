"""OpenAI 호환 엔드포인트(LLM_BASE_URL) 선택 규칙과 build_llm 연결 검증."""

from __future__ import annotations

from typing import Any

import pytest

from config import llm_factory
from config.settings import LLMConfig, check_minimum_requirements, get_api_key_status, get_llm_model, settings


@pytest.fixture
def clean_llm_settings(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """실행 환경의 LLM 관련 env 값이 테스트 결과에 섞이지 않게 비운다."""
    for field in ("llm_base_url", "llm_api_key", "llm_model", "openai_api_key", "google_api_key"):
        monkeypatch.setattr(settings, field, None)
    monkeypatch.setattr(settings, "use_gemini", False)
    return monkeypatch


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


def test_openai_path_keeps_default_base_url(clean_llm_settings: pytest.MonkeyPatch) -> None:
    clean_llm_settings.setattr(settings, "openai_api_key", "sk-test")

    config = get_llm_model()

    assert config is not None
    assert config.provider == "openai"
    assert config.base_url is None
