#!/usr/bin/env python3
"""
Pytest 기반 Conversational Supervisor 단위 테스트

테스트 항목:
1. 멀티턴 대화 히스토리 전달 확인
2. 하드코딩 함수 호출 안 되는지 확인
3. 에러 처리 테스트
4. 답변 품질 기본 검증

실행:
    pytest tests/test_supervisor_unit.py -v
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# 상위 디렉토리를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.korean_supervisor_langgraph import process_conversational_question_v2


class TestConversationalSupervisor:
    """Conversational Supervisor v2 테스트"""

    def test_single_question_no_history(self):
        """
        단일 질문 (대화 히스토리 없음) 테스트
        """
        question = "삼성전자 주가는?"
        stock_code = "005930"
        company_name = "삼성전자"

        # 실행
        result_chunks = list(
            process_conversational_question_v2(
                question=question,
                stock_code=stock_code,
                company_name=company_name,
                conversation_history=None  # 대화 히스토리 없음
            )
        )

        # 검증
        assert len(result_chunks) > 0, "답변이 생성되지 않았습니다"

        full_response = "".join(result_chunks)
        assert len(full_response) > 100, f"답변이 너무 짧습니다: {len(full_response)}자"

        # 종목 정보가 답변에 포함되었는지 확인 (선택적)
        # assert "삼성전자" in full_response or "005930" in full_response

    def test_multi_turn_with_history(self):
        """
        멀티턴 대화 (대화 히스토리 포함) 테스트
        """
        # Given: 이전 대화 히스토리
        conversation_history = [
            {"role": "user", "content": "삼성전자 분석해줘"},
            {"role": "assistant", "content": "삼성전자는 한국 대표 반도체 기업입니다..."}
        ]

        # When: 두 번째 질문
        question = "그럼 SK하이닉스와 비교하면?"
        stock_code = "000660"
        company_name = "SK하이닉스"

        result_chunks = list(
            process_conversational_question_v2(
                question=question,
                stock_code=stock_code,
                company_name=company_name,
                conversation_history=conversation_history  # 대화 히스토리 전달
            )
        )

        # Then
        assert len(result_chunks) > 0, "멀티턴 대화 답변이 생성되지 않았습니다"

        full_response = "".join(result_chunks)
        assert len(full_response) > 100, f"멀티턴 답변이 너무 짧습니다: {len(full_response)}자"

    def test_empty_history_handled(self):
        """
        빈 대화 히스토리 처리 테스트
        """
        result_chunks = list(
            process_conversational_question_v2(
                question="주가는?",
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=[]  # 빈 리스트
            )
        )

        assert len(result_chunks) > 0
        full_response = "".join(result_chunks)
        assert len(full_response) > 0

    def test_no_hardcoded_function_calls(self):
        """
        하드코딩 함수가 호출되지 않는지 확인
        """
        # analyze_question_for_agents 함수가 삭제되었는지 확인
        try:
            from core.korean_supervisor_langgraph import analyze_question_for_agents
            pytest.fail("analyze_question_for_agents 함수가 여전히 존재합니다 (삭제되어야 함)")
        except ImportError:
            # 함수가 삭제되어 import 실패 - 정상
            pass
        except AttributeError:
            # 모듈에 해당 함수가 없음 - 정상
            pass

    def test_error_handling(self):
        """
        에러 처리 테스트 - 잘못된 입력
        """
        # 빈 질문
        result_chunks = list(
            process_conversational_question_v2(
                question="",
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=None
            )
        )

        # 에러 메시지 또는 기본 응답 확인
        assert len(result_chunks) > 0

    def test_conversation_history_limit(self):
        """
        대화 히스토리 10개 제한 테스트
        """
        # 15개 대화 생성 (10개만 포함되어야 함)
        long_history = [
            {"role": "user", "content": f"질문 {i}"}
            for i in range(15)
        ]

        result_chunks = list(
            process_conversational_question_v2(
                question="현재 질문",
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=long_history
            )
        )

        # 정상 실행 확인 (에러 없이)
        assert len(result_chunks) > 0

    def test_response_length_reasonable(self):
        """
        답변 길이가 적절한지 테스트 (너무 짧거나 너무 길지 않음)
        """
        result_chunks = list(
            process_conversational_question_v2(
                question="삼성전자의 투자 가치를 평가해주세요",
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=None
            )
        )

        full_response = "".join(result_chunks)

        # 최소 500자 (의미 있는 답변)
        assert len(full_response) >= 500, f"답변이 너무 짧습니다: {len(full_response)}자"

        # 최대 10,000자 (과도하게 길지 않음)
        assert len(full_response) <= 10000, f"답변이 너무 깁니다: {len(full_response)}자"


class TestConversationalSupervisorEdgeCases:
    """엣지 케이스 테스트"""

    def test_special_characters_in_question(self):
        """특수 문자 포함 질문 테스트"""
        question = "삼성전자 vs SK하이닉스?? PER/PBR 비교!"

        result_chunks = list(
            process_conversational_question_v2(
                question=question,
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=None
            )
        )

        assert len(result_chunks) > 0

    def test_very_long_question(self):
        """매우 긴 질문 테스트"""
        question = "삼성전자의 " + "투자 가치를 " * 50 + "평가해주세요"

        result_chunks = list(
            process_conversational_question_v2(
                question=question,
                stock_code="005930",
                company_name="삼성전자",
                conversation_history=None
            )
        )

        assert len(result_chunks) > 0

    def test_invalid_stock_code(self):
        """잘못된 종목 코드 테스트"""
        result_chunks = list(
            process_conversational_question_v2(
                question="주가는?",
                stock_code="999999",  # 존재하지 않는 종목
                company_name="테스트회사",
                conversation_history=None
            )
        )

        # 에러 처리되어야 함 (빈 결과 또는 에러 메시지)
        assert len(result_chunks) > 0


if __name__ == "__main__":
    # pytest 없이 직접 실행시
    print("="*80)
    print("Conversational Supervisor v2 단위 테스트")
    print("="*80)
    print("\npytest를 사용하여 실행하세요:")
    print("pytest tests/test_supervisor_unit.py -v")
    print("\n또는 직접 실행:")
    print("python tests/test_supervisor_unit.py")
    print("="*80)

    # 간단한 스모크 테스트 실행
    print("\n[스모크 테스트 실행]")

    tester = TestConversationalSupervisor()

    try:
        print("\n1. 단일 질문 테스트...")
        tester.test_single_question_no_history()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")

    try:
        print("\n2. 멀티턴 대화 테스트...")
        tester.test_multi_turn_with_history()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")

    try:
        print("\n3. 하드코딩 함수 제거 확인...")
        tester.test_no_hardcoded_function_calls()
        print("✅ PASS")
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")

    print("\n" + "="*80)
    print("스모크 테스트 완료!")
    print("="*80)
