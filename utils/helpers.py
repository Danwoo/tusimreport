import logging
from datetime import datetime
from typing import Any, Dict
import numpy as np
import pandas as pd

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """로깅 설정"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

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