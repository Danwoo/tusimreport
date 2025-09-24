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
    deepsearch_api_key: Optional[str] = Field(
        "9a0ff6e5e09744fd8a536f2eca645d18", env="DEEPSEARCH_API_KEY"
    )

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

    # 애플리케이션 설정
    debug: bool = Field(True, env="DEBUG")
    log_level: str = Field("WARNING", env="LOG_LEVEL")

    # 경로 설정
    project_root: Path = Path(__file__).parent.parent

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 추가 필드 무시


settings = Settings()


def validate_api_keys() -> dict[str, bool]:
    """API 키 유효성 검증"""
    return {
        "openai": bool(
            settings.openai_api_key
            and settings.openai_api_key != "your_openai_api_key_here"
        ),
        "google": bool(
            settings.google_api_key
            and settings.google_api_key != "your_google_api_key_here"
        ),
        "naver": bool(
            settings.naver_client_id
            and settings.naver_client_secret
            and settings.naver_client_id != "your_naver_client_id_here"
            and settings.naver_client_secret != "your_naver_client_secret_here"
        ),
    }


def get_llm_model():
    """현재 설정에 따라 LLM 모델 반환"""
    if settings.use_gemini:
        if not settings.google_api_key:
            raise ValueError(
                "Google API Key가 설정되지 않았습니다. .env 파일에 GOOGLE_API_KEY를 추가하세요."
            )
        return "gemini", settings.gemini_model, settings.google_api_key
    else:
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API Key가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 추가하세요."
            )
        return "openai", settings.openai_model, settings.openai_api_key
