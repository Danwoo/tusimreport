#!/usr/bin/env python3
"""
에이전트 헬퍼 유틸리티
모든 에이전트가 사용하는 공통 기능 제공
"""

import logging
from typing import Dict, Any, Callable, Optional
from functools import wraps

logger = logging.getLogger(__name__)


def create_fallback_message(
    agent_name: str,
    company_name: str,
    stock_code: str,
    reason: str,
    data_source: Optional[str] = None
) -> Dict[str, Any]:
    """
    API 실패 시 반환할 fallback 메시지 생성

    Args:
        agent_name: 에이전트 이름
        company_name: 기업명
        stock_code: 종목코드
        reason: 실패 이유
        data_source: 데이터 소스 (선택)

    Returns:
        표준화된 fallback 메시지 딕셔너리
    """
    message = {
        "status": "limited",
        "agent": agent_name,
        "company_name": company_name,
        "stock_code": stock_code,
        "error": reason,
        "message": f"⚠️ {agent_name} 분석이 제한적으로 제공됩니다",
        "reason_ko": reason,
    }

    if data_source:
        message["data_source"] = data_source
        message["suggestion"] = f"💡 {data_source} API 키를 설정하면 전체 분석이 가능합니다"

    return message


def format_error_message_korean(error: Exception, context: str = "") -> str:
    """
    에러 메시지를 한글로 포맷팅

    Args:
        error: 예외 객체
        context: 에러 발생 컨텍스트 (선택)

    Returns:
        한글로 포맷팅된 에러 메시지
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # 일반적인 에러 타입 한글화
    error_type_ko = {
        "ValueError": "값 오류",
        "KeyError": "키 오류",
        "TypeError": "타입 오류",
        "AttributeError": "속성 오류",
        "ImportError": "임포트 오류",
        "ModuleNotFoundError": "모듈 없음",
        "ConnectionError": "연결 오류",
        "TimeoutError": "시간 초과",
        "HTTPError": "HTTP 오류",
        "APIError": "API 오류",
    }.get(error_type, error_type)

    if context:
        return f"❌ {context} 중 {error_type_ko}: {error_msg}"
    else:
        return f"❌ {error_type_ko}: {error_msg}"


def safe_agent_execution(
    agent_name: str,
    data_source: Optional[str] = None,
    fallback_on_error: bool = True
):
    """
    에이전트 실행을 안전하게 감싸는 데코레이터

    Args:
        agent_name: 에이전트 이름
        data_source: 데이터 소스
        fallback_on_error: 에러 시 fallback 메시지 반환 (True) 또는 에러 발생 (False)

    사용 예:
        @safe_agent_execution("Korean Sentiment Agent", "Naver News API")
        def get_sentiment_analysis(company_name, stock_code):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            try:
                # 에이전트 실행
                logger.info(f"{agent_name} 실행 시작")
                result = func(*args, **kwargs)
                logger.info(f"{agent_name} 실행 완료")
                return result

            except Exception as e:
                error_msg = format_error_message_korean(e, agent_name)
                logger.error(error_msg)

                if fallback_on_error:
                    # Fallback 메시지 반환
                    company_name = kwargs.get("company_name", args[0] if args else "알 수 없음")
                    stock_code = kwargs.get("stock_code", args[1] if len(args) > 1 else "000000")

                    return create_fallback_message(
                        agent_name=agent_name,
                        company_name=company_name,
                        stock_code=stock_code,
                        reason=error_msg,
                        data_source=data_source
                    )
                else:
                    # 에러 재발생
                    raise

        return wrapper
    return decorator


def check_api_available(api_name: str, validation_func: Callable[[], bool]) -> tuple[bool, str]:
    """
    API 사용 가능 여부 확인

    Args:
        api_name: API 이름
        validation_func: 검증 함수

    Returns:
        (사용 가능 여부, 상태 메시지)
    """
    try:
        is_available = validation_func()
        if is_available:
            return True, f"✅ {api_name} 사용 가능"
        else:
            return False, f"⚠️ {api_name} API 키 미설정"
    except Exception as e:
        return False, f"❌ {api_name} 확인 실패: {str(e)}"


def create_limited_analysis_message(
    agent_name: str,
    company_name: str,
    stock_code: str,
    available_data: Dict[str, Any],
    missing_apis: list[str]
) -> Dict[str, Any]:
    """
    제한적 분석 메시지 생성 (일부 API만 사용 가능할 때)

    Args:
        agent_name: 에이전트 이름
        company_name: 기업명
        stock_code: 종목코드
        available_data: 사용 가능한 데이터
        missing_apis: 사용 불가능한 API 목록

    Returns:
        제한적 분석 메시지
    """
    return {
        "status": "partial",
        "agent": agent_name,
        "company_name": company_name,
        "stock_code": stock_code,
        "available_data": available_data,
        "missing_apis": missing_apis,
        "message": f"ℹ️ {agent_name} 부분 분석 (일부 API 미사용)",
        "suggestion": f"💡 전체 분석을 위해 다음 API 키 설정을 권장합니다: {', '.join(missing_apis)}",
    }


def get_demo_mode_message(agent_name: str) -> Dict[str, Any]:
    """
    데모 모드 메시지 생성

    Args:
        agent_name: 에이전트 이름

    Returns:
        데모 모드 메시지
    """
    return {
        "status": "demo",
        "agent": agent_name,
        "message": "🎭 데모 모드",
        "description": "실제 API 키 없이 샘플 데이터로 시스템을 체험할 수 있습니다",
        "note": "실제 분석을 위해서는 API 키 설정이 필요합니다",
    }


def validate_stock_code(stock_code: str) -> tuple[bool, str]:
    """
    종목 코드 유효성 검증

    Args:
        stock_code: 종목 코드

    Returns:
        (유효성 여부, 메시지)
    """
    if not stock_code:
        return False, "❌ 종목 코드가 비어있습니다"

    if not isinstance(stock_code, str):
        return False, "❌ 종목 코드는 문자열이어야 합니다"

    # 공백 제거
    stock_code = stock_code.strip()

    # 6자리 숫자 확인
    if len(stock_code) != 6:
        return False, f"❌ 종목 코드는 6자리여야 합니다 (현재: {len(stock_code)}자리)"

    if not stock_code.isdigit():
        return False, f"❌ 종목 코드는 숫자만 가능합니다 (입력: {stock_code})"

    return True, "✅ 유효한 종목 코드"


def create_success_message(
    agent_name: str,
    company_name: str,
    stock_code: str,
    analysis_result: Any,
    data_sources: list[str]
) -> Dict[str, Any]:
    """
    성공 메시지 생성 (표준화)

    Args:
        agent_name: 에이전트 이름
        company_name: 기업명
        stock_code: 종목코드
        analysis_result: 분석 결과
        data_sources: 사용한 데이터 소스 목록

    Returns:
        표준화된 성공 메시지
    """
    return {
        "status": "success",
        "agent": agent_name,
        "company_name": company_name,
        "stock_code": stock_code,
        "data_sources": data_sources,
        "analysis": analysis_result,
        "message": f"✅ {agent_name} 분석 완료",
    }
