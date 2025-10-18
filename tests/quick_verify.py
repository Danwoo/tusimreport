#!/usr/bin/env python3
"""
빠른 검증 스크립트 - pytest 없이 실행 가능

기본적인 기능만 확인:
1. 모듈 import 가능한지
2. 함수 호출 가능한지
3. 하드코딩 함수 삭제되었는지
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("="*80)
print("TuSimReport 빠른 검증")
print("="*80)

# 1. 모듈 import 테스트
print("\n[1/5] 모듈 import 테스트...")
try:
    from core.korean_supervisor_langgraph import (
        create_conversational_supervisor,
        process_conversational_question_v2,
        conversational_supervisor_graph
    )
    print("[PASS] All modules imported successfully")
except Exception as e:
    print(f"[FAIL] {str(e)}")
    sys.exit(1)

# 2. 하드코딩 함수 삭제 확인
print("\n[2/5] Hardcoded function removal check...")
try:
    from core.korean_supervisor_langgraph import analyze_question_for_agents
    print("[FAIL] analyze_question_for_agents function still exists")
    sys.exit(1)
except (ImportError, AttributeError):
    print("[PASS] analyze_question_for_agents function deleted")

# 3. streamlit_conversation_manager 확인
print("\n[3/5] streamlit_conversation_manager check...")
try:
    from core.streamlit_conversation_manager import StreamlitConversationManager
    print("[PASS] StreamlitConversationManager import success")
except Exception as e:
    print(f"[FAIL] {str(e)}")
    sys.exit(1)

# 4. Conversational Supervisor 인스턴스 확인
print("\n[4/5] Conversational Supervisor instance check...")
try:
    if conversational_supervisor_graph is not None:
        print("[PASS] conversational_supervisor_graph instance created")
    else:
        print("[FAIL] conversational_supervisor_graph is None")
        sys.exit(1)
except Exception as e:
    print(f"[FAIL] {str(e)}")
    sys.exit(1)

# 5. 함수 시그니처 확인
print("\n[5/5] Function signature check...")
try:
    import inspect
    sig = inspect.signature(process_conversational_question_v2)
    params = list(sig.parameters.keys())

    expected_params = ['question', 'stock_code', 'company_name', 'conversation_history']

    if params == expected_params:
        print(f"[PASS] Function parameters correct: {params}")
    else:
        print(f"[FAIL] Expected: {expected_params}, Actual: {params}")
        sys.exit(1)
except Exception as e:
    print(f"[FAIL] {str(e)}")
    sys.exit(1)

print("\n" + "="*80)
print("SUCCESS: All verifications passed!")
print("="*80)
print("\n다음 단계:")
print("1. python tests/test_conversation_cli.py - CLI 대화형 테스트")
print("2. pip install pytest && pytest tests/test_supervisor_unit.py -v")
print("3. python tests/verify_agent_selection.py - 에이전트 선택 검증")
print("="*80)
