"""LLM 인스턴스 빌더.

12개 에이전트/supervisor 파일에 복붙되어 있던 provider-분기 코드를 한 곳으로 모은다.
provider 추가/모델 변경 시 한 줄만 고치면 된다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from config.settings import get_llm_model

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


def build_llm(
    temperature: float = 0.0, raise_on_missing: bool = True
) -> Optional["BaseChatModel"]:
    """settings에 맞춰 ChatOpenAI 또는 ChatGoogleGenerativeAI 인스턴스를 반환한다.

    Args:
        temperature: 샘플링 temperature.
        raise_on_missing: API 키 누락 시 ValueError를 던질지 여부.
            True가 default인 이유: 호출자가 즉시 .invoke()를 호출하는 시맨틱이라
            None을 받으면 무조건 NoneType 에러로 이어지기 때문에 즉시 실패가 안전함.
            (settings.get_llm_model은 상태 조회 시맨틱이라 default=False로 다름.)

    Returns:
        LangChain BaseChatModel 인스턴스. raise_on_missing=False이고 키가 없으면 None.
    """
    llm_config = get_llm_model(raise_on_missing=raise_on_missing)
    if llm_config is None:
        return None

    provider, model_name, api_key = llm_config

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=api_key,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model_name, temperature=temperature, api_key=api_key)
