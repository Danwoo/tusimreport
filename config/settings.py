import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """한국 주식 분석 시스템 설정"""

    # LLM API 키 (OpenAI 또는 Google)
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(None, env="GOOGLE_API_KEY")

    # LLM 설정
    use_gemini: bool = Field(
        False, env="USE_GEMINI"
    )  # Gemini 할당량 초과로 OpenAI로 변경
    gemini_model: str = Field("gemini-2.0-flash-lite", env="GEMINI_MODEL")
    openai_model: str = Field("gpt-4.1-nano", env="OPENAI_MODEL")

    # 한국 뉴스 API 키 (선택사항)
    naver_client_id: Optional[str] = Field(None, env="NAVER_CLIENT_ID")
    naver_client_secret: Optional[str] = Field(None, env="NAVER_CLIENT_SECRET")

    # Tavily Search API 키 (글로벌 뉴스 검색)
    tavily_api_key: Optional[str] = Field(None, env="TAVILY_API_KEY")

    # 딥서치 뉴스 API 키 (월 20회 제한)
    # Function Call API: https://api.deepsearch.com/note/v1/function
    # 주의: 월 20회 호출 제한으로 인해 현재 비활성화됨
    # 보안: API 키는 환경 변수로만 설정
    deepsearch_api_key: Optional[str] = Field(None, env="DEEPSEARCH_API_KEY")

    # KOSIS 국가통계포털 서비스 키 (무료)
    # 경제지표, 인구통계, 고용통계, 소비자물가지수 등
    # 134,586종 국가통계 데이터 제공
    kosis_service_key: Optional[str] = Field(None, env="KOSIS_SERVICE_KEY")

    # DART API 키 (무료)
    # 금융감독원 전자공시시스템 기업정보
    dart_api_key: Optional[str] = Field(None, env="DART_API_KEY")

    # ECOS API 키 (한국은행 경제통계시스템)
    # 거시경제 지표 데이터
    ecos_api_key: Optional[str] = Field(None, env="ECOS_API_KEY")

    # 🆕 P1-3: 실시간 데이터 통합
    # Alpha Vantage API 키 (글로벌 시장 데이터)
    # 무료: 25 requests/day → 캐싱 필수
    alpha_vantage_api_key: Optional[str] = Field(None, env="ALPHA_VANTAGE_API_KEY")

    # 애플리케이션 설정
    debug: bool = Field(True, env="DEBUG")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    # 경로 설정
    project_root: Path = Path(__file__).parent.parent

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 추가 필드 무시


settings = Settings()


def _is_valid_api_key(key: Optional[str], placeholder: str = "") -> bool:
    """API 키가 유효한지 확인 (None이거나 placeholder가 아니어야 함)"""
    if not key:
        return False
    if placeholder and key == placeholder:
        return False
    if key.startswith("your_") and key.endswith("_here"):
        return False
    return True


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
        "naver": _is_valid_api_key(settings.naver_client_id) and
                _is_valid_api_key(settings.naver_client_secret),
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
    return {
        "llm": "✅ 설정됨" if (validation["openai"] or validation["google"]) else "❌ 미설정 (필수)",
        "dart": "✅ 설정됨" if validation["dart"] else "⚠️ 미설정 (재무 분석 제한)",
        "ecos": "✅ 설정됨" if validation["ecos"] else "⚠️ 미설정 (경제 지표 제한)",
        "naver": "✅ 설정됨" if validation["naver"] else "⚠️ 미설정 (뉴스 분석 제한)",
        "tavily": "✅ 설정됨" if validation["tavily"] else "ℹ️ 미설정 (선택사항)",
        "alpha_vantage": "✅ 설정됨" if validation["alpha_vantage"] else "ℹ️ 미설정 (글로벌 시장 제한)",  # 🆕 P1-3
    }


def get_llm_model(raise_on_missing: bool = False):
    """
    현재 설정에 따라 LLM 모델 반환

    Args:
        raise_on_missing: True면 API 키 없을 때 에러 발생, False면 None 반환

    Returns:
        (provider, model_name, api_key) 튜플 또는 None

    Raises:
        ValueError: raise_on_missing=True이고 API 키가 없을 때
    """
    # Gemini 우선 시도
    if settings.use_gemini:
        if _is_valid_api_key(settings.google_api_key):
            return "gemini", settings.gemini_model, settings.google_api_key
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
        return "openai", settings.openai_model, settings.openai_api_key

    # Gemini도 시도 (USE_GEMINI=false여도)
    if _is_valid_api_key(settings.google_api_key):
        return "gemini", settings.gemini_model, settings.google_api_key

    if raise_on_missing:
        raise ValueError(
            "❌ LLM API 키가 설정되지 않았습니다.\n"
            "💡 해결 방법:\n"
            "   1. Google Gemini: .env 파일에 GOOGLE_API_KEY 추가\n"
            "      발급: https://aistudio.google.com/app/apikey\n"
            "   2. 또는 OpenAI: .env 파일에 OPENAI_API_KEY 추가\n"
            "      발급: https://platform.openai.com/api-keys\n"
            "   3. 최소 하나의 LLM API 키가 필요합니다"
        )

    return None


def check_minimum_requirements() -> tuple[bool, list[str]]:
    """
    최소 요구사항 확인

    Returns:
        (모든 요구사항 충족 여부, 경고 메시지 리스트)
    """
    warnings = []
    validation = validate_api_keys()

    # LLM은 필수
    has_llm = validation["openai"] or validation["google"]
    if not has_llm:
        warnings.append("❌ LLM API 키 필요 (Google Gemini 또는 OpenAI)")

    # 데이터 API는 경고만
    if not validation["dart"]:
        warnings.append("⚠️ DART API 키 권장 (재무 분석 기능 제한)")
    if not validation["ecos"]:
        warnings.append("⚠️ ECOS API 키 권장 (경제 지표 기능 제한)")
    if not validation["naver"]:
        warnings.append("⚠️ Naver API 키 권장 (뉴스 분석 기능 제한)")

    return has_llm, warnings
