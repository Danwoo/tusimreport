import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """한국 주식 분석 시스템 설정"""
    
    # 필수 API 키
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    
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
        "openai": bool(settings.openai_api_key and settings.openai_api_key != "your_openai_api_key_here"),
        "naver": bool(settings.naver_client_id and settings.naver_client_secret and 
                     settings.naver_client_id != "your_naver_client_id_here" and 
                     settings.naver_client_secret != "your_naver_client_secret_here")
    }