"""LLM 인스턴스 빌더.

12개 에이전트/supervisor 파일에 복붙되어 있던 provider-분기 코드를 한 곳으로 모은다.
provider 추가/모델 변경 시 한 줄만 고치면 된다.

Thread-safety 가정:
- ChatOpenAI/ChatGoogleGenerativeAI는 내부적으로 `requests.Session` 또는
  google sdk 클라이언트를 들고 있다. 이들 SDK는 `invoke()`가 thread-safe
  하다고 *문서화는 되어 있지 않지만*, requests.Session.request은 connection
  pool에 대해 thread-safe하다고 공식 문서가 보증한다.
- 따라서 같은 인스턴스를 여러 스레드가 동시에 invoke()하는 것은 안전하다고
  본다. supervisor의 ThreadPoolExecutor는 이 가정에 의존한다.
- 이 가정을 검증하는 동시성 부하 테스트는 아직 없다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.settings import get_llm_model

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


def build_llm(temperature: float = 0.0, raise_on_missing: bool = True) -> BaseChatModel | None:
    """settings에 맞춰 ChatOpenAI 또는 ChatGoogleGenerativeAI 인스턴스를 반환한다.

    OpenAI 호환 엔드포인트(LLM_BASE_URL)도 ChatOpenAI에 base_url만 바꿔 연결한다.

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

    if llm_config.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=llm_config.model_name,
            temperature=temperature,
            google_api_key=llm_config.api_key,
        )

    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    return ChatOpenAI(
        model=llm_config.model_name,
        temperature=temperature,
        api_key=SecretStr(llm_config.api_key),
        base_url=llm_config.base_url,
    )
