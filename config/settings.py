from pathlib import Path
from typing import NamedTuple, TypeGuard

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class LLMConfig(NamedTuple):
    """build_llm이 인스턴스를 만들 때 필요한 값 묶음."""

    provider: str  # "openai_compatible" | "openai" | "gemini"
    model_name: str
    api_key: str
    base_url: str | None = None


class Settings(BaseSettings):
    """한국 주식 분석 시스템 설정.

    pydantic-settings v2 스타일. env_var 매핑은 alias_priority로 통일.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI 호환 엔드포인트 (Groq·OpenRouter·Gemini OpenAI 호환·로컬 vLLM 등).
    # LLM_BASE_URL이 있으면 아래 OpenAI/Gemini 설정보다 먼저 쓴다.
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    # LLM API 키 (OpenAI 또는 Google)
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # LLM 설정
    use_gemini: bool = False  # Gemini 할당량 초과 시 OpenAI fallback
    gemini_model: str = "gemini-2.0-flash-lite"
    openai_model: str = "gpt-4.1-nano"

    # 한국 뉴스 API 키 (선택사항)
    naver_client_id: str | None = None
    naver_client_secret: str | None = None

    # Tavily Search API 키 (글로벌 뉴스 검색)
    tavily_api_key: str | None = None

    # 딥서치 뉴스 API (월 20회 제한으로 현재 비활성화 — env 전용)
    deepsearch_api_key: str | None = None

    # KOSIS 국가통계포털 서비스 키
    kosis_service_key: str | None = None

    # DART (금융감독원 전자공시) API 키
    dart_api_key: str | None = None

    # ECOS (한국은행 경제통계시스템) API 키
    ecos_api_key: str | None = None

    # Alpha Vantage (글로벌 시장 데이터). 무료 25req/day → 캐싱 필수
    alpha_vantage_api_key: str | None = None

    # 애플리케이션 설정
    debug: bool = True
    log_level: str = "INFO"

    # 경로 설정
    project_root: Path = Path(__file__).parent.parent


settings = Settings()


def _is_valid_api_key(key: str | None, placeholder: str = "") -> TypeGuard[str]:
    """API 키가 유효한지 확인 (None이거나 placeholder가 아니어야 함)"""
    if not key:
        return False
    if placeholder and key == placeholder:
        return False
    return not (key.startswith("your_") and key.endswith("_here"))


def _missing_openai_compatible_fields() -> list[str]:
    """LLM_BASE_URL이 설정됐을 때 함께 필요한 값 중 비어 있는 env 이름."""
    required = {"LLM_MODEL": settings.llm_model, "LLM_API_KEY": settings.llm_api_key}
    return [name for name, value in required.items() if not _is_valid_api_key(value)]


def validate_api_keys() -> dict[str, bool]:
    """
    API 키 유효성 검증

    Returns:
        각 API 키의 유효성 여부를 담은 딕셔너리
    """
    return {
        "openai": _is_valid_api_key(settings.openai_api_key),
        "google": _is_valid_api_key(settings.google_api_key),
        "dart": _is_valid_api_key(settings.dart_api_key),
        "ecos": _is_valid_api_key(settings.ecos_api_key),
        "naver": _is_valid_api_key(settings.naver_client_id)
        and _is_valid_api_key(settings.naver_client_secret),
        "tavily": _is_valid_api_key(settings.tavily_api_key),
        "alpha_vantage": _is_valid_api_key(settings.alpha_vantage_api_key),  # 🆕 P1-3
    }


def get_api_key_status() -> dict[str, str]:
    """
    API 키 상태를 사람이 읽을 수 있는 형태로 반환

    Returns:
        각 API 키의 상태 메시지
    """
    validation = validate_api_keys()
    llm_config, llm_problem = resolve_llm_config()
    if llm_config is not None:
        llm_status = f"✅ 설정됨 ({llm_config.provider})"
    else:
        llm_status = (llm_problem or "❌ 미설정 (필수)").splitlines()[0]
    return {
        "llm": llm_status,
        "dart": "✅ 설정됨" if validation["dart"] else "⚠️ 미설정 (재무 분석 제한)",
        "ecos": "✅ 설정됨" if validation["ecos"] else "⚠️ 미설정 (경제 지표 제한)",
        "naver": "✅ 설정됨" if validation["naver"] else "⚠️ 미설정 (뉴스 분석 제한)",
        "tavily": "✅ 설정됨" if validation["tavily"] else "ℹ️ 미설정 (선택사항)",
        "alpha_vantage": "✅ 설정됨"
        if validation["alpha_vantage"]
        else "ℹ️ 미설정 (글로벌 시장 제한)",  # 🆕 P1-3
    }


def get_llm_model(raise_on_missing: bool = False) -> LLMConfig | None:
    """
    현재 설정에 따라 LLM 모델 반환

    우선순위: LLM_BASE_URL(OpenAI 호환) → USE_GEMINI=true면 Gemini → OpenAI → Gemini.

    Args:
        raise_on_missing: True면 API 키 없을 때 에러 발생, False면 None 반환

    Returns:
        LLMConfig 또는 None

    Raises:
        ValueError: raise_on_missing=True이고 API 키가 없을 때
    """
    base_url = settings.llm_base_url
    if _is_valid_api_key(base_url):
        model, api_key = settings.llm_model, settings.llm_api_key
        if _is_valid_api_key(model) and _is_valid_api_key(api_key):
            return LLMConfig("openai_compatible", model, api_key, base_url)
        # 불완전한 설정이면 다른(유료일 수 있는) provider로 넘어가지 않는다.
        if raise_on_missing:
            raise ValueError(
                f"❌ LLM_BASE_URL이 설정됐지만 {', '.join(_missing_openai_compatible_fields())}가 비어 있습니다.\n"
                "💡 해결 방법:\n"
                "   1. LLM_MODEL에 엔드포인트가 제공하는 모델 이름을 넣으세요\n"
                "   2. LLM_API_KEY에 그 엔드포인트의 키를 넣으세요 (키가 없는 로컬 서버는 EMPTY)\n"
                "   3. 설정 안내: docs/API_KEYS.md"
            )
        return None

    # Gemini 우선 시도
    if settings.use_gemini:
        if _is_valid_api_key(settings.google_api_key):
            return LLMConfig("gemini", settings.gemini_model, settings.google_api_key)
        elif raise_on_missing:
            raise ValueError(
                "❌ Google API 키가 설정되지 않았습니다.\n"
                "💡 해결 방법:\n"
                "   1. .env 파일에 GOOGLE_API_KEY를 추가하세요\n"
                "   2. 또는 USE_GEMINI=false로 설정하고 OpenAI를 사용하세요\n"
                "   3. API 키 발급: https://aistudio.google.com/app/apikey"
            )

    # OpenAI fallback
    if _is_valid_api_key(settings.openai_api_key):
        return LLMConfig("openai", settings.openai_model, settings.openai_api_key)

    # Gemini도 시도 (USE_GEMINI=false여도)
    if _is_valid_api_key(settings.google_api_key):
        return LLMConfig("gemini", settings.gemini_model, settings.google_api_key)

    if raise_on_missing:
        raise ValueError(
            "❌ LLM API 키가 설정되지 않았습니다.\n"
            "💡 해결 방법:\n"
            "   1. 무료 OpenAI 호환 엔드포인트: LLM_BASE_URL·LLM_MODEL·LLM_API_KEY 설정\n"
            "      안내: docs/API_KEYS.md\n"
            "   2. Google Gemini: .env 파일에 GOOGLE_API_KEY 추가\n"
            "      발급: https://aistudio.google.com/app/apikey\n"
            "   3. 또는 OpenAI: .env 파일에 OPENAI_API_KEY 추가\n"
            "      발급: https://platform.openai.com/api-keys"
        )

    return None


def resolve_llm_config() -> tuple[LLMConfig | None, str | None]:
    """에이전트의 build_llm()이 고르는 설정과, 고르지 못하면 그 이유.

    get_llm_model(raise_on_missing=False)는 USE_GEMINI=true인데 Google 키가 없을 때
    OpenAI로 넘어가지만, 에이전트가 쓰는 raise_on_missing=True 경로는 예외를 낸다.
    상태 표시와 점검 도구는 에이전트와 같은 판정을 보여줘야 하므로 이 함수를 쓴다.
    """
    try:
        return get_llm_model(raise_on_missing=True), None
    except ValueError as e:
        return None, str(e)


def check_minimum_requirements() -> tuple[bool, list[str]]:
    """
    최소 요구사항 확인

    Returns:
        (모든 요구사항 충족 여부, 경고 메시지 리스트)
    """
    warnings = []
    validation = validate_api_keys()

    # LLM은 필수
    llm_config, llm_problem = resolve_llm_config()
    has_llm = llm_config is not None
    if not has_llm:
        warnings.append((llm_problem or "❌ LLM 설정 필요").splitlines()[0])

    # 데이터 API는 경고만
    if not validation["dart"]:
        warnings.append("⚠️ DART API 키 권장 (재무 분석 기능 제한)")
    if not validation["ecos"]:
        warnings.append("⚠️ ECOS API 키 권장 (경제 지표 기능 제한)")
    if not validation["naver"]:
        warnings.append("⚠️ Naver API 키 권장 (뉴스 분석 기능 제한)")

    return has_llm, warnings
