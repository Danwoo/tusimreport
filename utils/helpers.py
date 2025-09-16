import logging
from datetime import datetime
from typing import Any, Dict
import numpy as np
import pandas as pd
import os
from pathlib import Path

def setup_logging(log_level: str = "INFO", enable_file_logging: bool = True) -> logging.Logger:
    """로깅 설정 - 콘솔 및 파일 로깅 지원"""
    # 루트 로거 설정으로 모든 모듈의 로그 캡처
    root_logger = logging.getLogger()

    # 중복 핸들러 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 로거 레벨 설정
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 상세 포매터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 파일 로깅 활성화시 파일 핸들러 추가
    if enable_file_logging:
        # logs 디렉토리 생성
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # 타임스탬프 기반 로그 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"streamlit_analysis_{timestamp}.log"

        # 파일 핸들러 추가 - 모든 레벨 캡처
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # 파일에는 모든 로그 저장
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        print(f"\n[LOG] 로그 파일 생성: {log_file}")
        print(f"[LOG] 로그 레벨: {log_level}")
        print(f"[LOG] 로그 저장 경로: {log_file.absolute()}\n")

    # 특정 모듈 로거 반환
    return logging.getLogger("streamlit_analysis")

def format_korean_currency(amount: float) -> str:
    """한국 원화 형식으로 포맷"""
    if amount >= 1e12:
        return f"₩{amount/1e12:.2f}조"
    elif amount >= 1e8:
        return f"₩{amount/1e8:.0f}억"
    elif amount >= 1e4:
        return f"₩{amount/1e4:.0f}만"
    else:
        return f"₩{amount:,.0f}"

def convert_numpy_types(obj: Any) -> Any:
    """numpy 타입을 Python 네이티브 타입으로 변환"""
    if isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj