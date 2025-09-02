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
    use_gemini: bool = Field(True, env="USE_GEMINI")  # 기본값을 Gemini로 변경
    gemini_model: str = Field("gemini-2.0-flash-lite", env="GEMINI_MODEL")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")

    # 한국 뉴스 API 키 (선택사항)
    naver_client_id: Optional[str] = Field(None, env="NAVER_CLIENT_ID")
    naver_client_secret: Optional[str] = Field(None, env="NAVER_CLIENT_SECRET")

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
