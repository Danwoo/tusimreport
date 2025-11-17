"""
통합 테스트 - 실제 워크플로우 검증
API 키 없이도 시스템이 graceful하게 동작하는지 확인
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAPIKeyGracefulDegradation:
    """API 키 없을 때 graceful degradation 테스트"""

    def test_get_llm_model_without_keys_no_raise(self):
        """API 키 없을 때 None 반환 (raise_on_missing=False)"""
        from config.settings import get_llm_model, settings

        # 기존 키 백업
        original_google = settings.google_api_key
        original_openai = settings.openai_api_key

        try:
            # 키 제거
            settings.google_api_key = None
            settings.openai_api_key = None

            # raise_on_missing=False면 None 반환
            result = get_llm_model(raise_on_missing=False)
            assert result is None, "API 키 없을 때 None을 반환해야 함"

        finally:
            # 복원
            settings.google_api_key = original_google
            settings.openai_api_key = original_openai

    def test_get_llm_model_without_keys_raises(self):
        """API 키 없을 때 한글 에러 (raise_on_missing=True)"""
        from config.settings import get_llm_model, settings

        original_google = settings.google_api_key
        original_openai = settings.openai_api_key

        try:
            settings.google_api_key = None
            settings.openai_api_key = None

            with pytest.raises(ValueError) as exc_info:
                get_llm_model(raise_on_missing=True)

            error_msg = str(exc_info.value)
            assert "❌" in error_msg, "에러 메시지에 이모지 포함"
            assert "💡" in error_msg, "해결 방법 포함"
            assert "LLM" in error_msg or "API" in error_msg

        finally:
            settings.google_api_key = original_google
            settings.openai_api_key = original_openai

    def test_check_minimum_requirements(self):
        """최소 요구사항 체크"""
        from config.settings import check_minimum_requirements

        has_llm, warnings = check_minimum_requirements()

        # 반환 타입 확인
        assert isinstance(has_llm, bool)
        assert isinstance(warnings, list)

        # 경고 메시지가 있으면 문자열이어야 함
        for warning in warnings:
            assert isinstance(warning, str)
            assert len(warning) > 0

    def test_get_api_key_status(self):
        """API 키 상태 확인"""
        from config.settings import get_api_key_status

        status = get_api_key_status()

        # 필수 키 확인
        assert "llm" in status
        assert "dart" in status
        assert "ecos" in status
        assert "naver" in status

        # 상태 메시지 형식 확인
        for key, msg in status.items():
            assert isinstance(msg, str)
            assert any(emoji in msg for emoji in ["✅", "❌", "⚠️", "ℹ️"])


class TestAgentHelpers:
    """에이전트 헬퍼 유틸리티 테스트"""

    def test_validate_stock_code_valid(self):
        """유효한 종목 코드"""
        from utils.agent_helpers import validate_stock_code

        valid_codes = ["005930", "035420", "000660", "051910"]

        for code in valid_codes:
            is_valid, message = validate_stock_code(code)
            assert is_valid, f"{code}는 유효한 종목 코드"
            assert "✅" in message

    def test_validate_stock_code_invalid(self):
        """무효한 종목 코드"""
        from utils.agent_helpers import validate_stock_code

        invalid_cases = [
            ("", "비어있음"),
            ("123", "3자리"),
            ("1234567", "7자리"),
            ("abc123", "문자 포함"),
            ("05930", "5자리"),
        ]

        for code, reason in invalid_cases:
            is_valid, message = validate_stock_code(code)
            assert not is_valid, f"{code}는 무효한 종목 코드 ({reason})"
            assert "❌" in message

    def test_create_fallback_message(self):
        """Fallback 메시지 생성"""
        from utils.agent_helpers import create_fallback_message

        msg = create_fallback_message(
            agent_name="Test Agent",
            company_name="삼성전자",
            stock_code="005930",
            reason="API 키 없음",
            data_source="Test API"
        )

        assert msg["status"] == "limited"
        assert msg["agent"] == "Test Agent"
        assert msg["company_name"] == "삼성전자"
        assert msg["stock_code"] == "005930"
        assert "⚠️" in msg["message"]
        assert "💡" in msg["suggestion"]

    def test_format_error_message_korean(self):
        """에러 메시지 한글화"""
        from utils.agent_helpers import format_error_message_korean

        error = ValueError("테스트 에러")
        msg = format_error_message_korean(error, "데이터 수집")

        assert "❌" in msg
        assert "데이터 수집" in msg
        assert "테스트 에러" in msg

    def test_create_success_message(self):
        """성공 메시지 생성"""
        from utils.agent_helpers import create_success_message

        msg = create_success_message(
            agent_name="Test Agent",
            company_name="네이버",
            stock_code="035420",
            analysis_result={"score": 85},
            data_sources=["API1", "API2"]
        )

        assert msg["status"] == "success"
        assert msg["company_name"] == "네이버"
        assert msg["analysis"]["score"] == 85
        assert len(msg["data_sources"]) == 2
        assert "✅" in msg["message"]


class TestSettingsValidation:
    """설정 검증 테스트"""

    def test_validate_api_keys(self):
        """API 키 검증 함수"""
        from config.settings import validate_api_keys

        validation = validate_api_keys()

        # 딕셔너리 형식
        assert isinstance(validation, dict)

        # 필수 키 포함
        assert "openai" in validation
        assert "google" in validation
        assert "dart" in validation
        assert "ecos" in validation
        assert "naver" in validation

        # 불린 값
        for key, value in validation.items():
            assert isinstance(value, bool)

    def test_is_valid_api_key_function(self):
        """API 키 유효성 체크 함수"""
        from config.settings import _is_valid_api_key

        # 유효한 키
        assert _is_valid_api_key("sk-1234567890abcdef")
        assert _is_valid_api_key("AIzaSyABC123DEF456")

        # 무효한 키
        assert not _is_valid_api_key(None)
        assert not _is_valid_api_key("")
        assert not _is_valid_api_key("your_api_key_here")
        assert not _is_valid_api_key("your_google_api_key_here")


class TestWorkflowIntegration:
    """워크플로우 통합 테스트 (API 호출 없음)"""

    def test_settings_import(self):
        """설정을 import할 수 있는지"""
        from config.settings import settings
        assert settings is not None

    def test_helpers_import(self):
        """헬퍼를 import할 수 있는지"""
        from utils.agent_helpers import (
            create_fallback_message,
            validate_stock_code,
            format_error_message_korean
        )
        assert create_fallback_message is not None
        assert validate_stock_code is not None
        assert format_error_message_korean is not None

    def test_safe_agent_execution_decorator(self):
        """에이전트 실행 데코레이터 동작"""
        from utils.agent_helpers import safe_agent_execution

        @safe_agent_execution("Test Agent", "Test API", fallback_on_error=True)
        def test_function(company_name, stock_code):
            raise ValueError("테스트 에러")

        # Fallback 메시지 반환
        result = test_function("삼성전자", "005930")

        assert result["status"] == "limited"
        assert result["company_name"] == "삼성전자"
        assert "❌" in result["error"]

    def test_safe_agent_execution_success(self):
        """에이전트 실행 성공 케이스"""
        from utils.agent_helpers import safe_agent_execution

        @safe_agent_execution("Test Agent", "Test API")
        def success_function(company_name, stock_code):
            return {
                "status": "success",
                "company_name": company_name,
                "data": "분석 결과"
            }

        result = success_function("네이버", "035420")

        assert result["status"] == "success"
        assert result["company_name"] == "네이버"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
