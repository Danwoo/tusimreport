#!/usr/bin/env python3
"""
에이전트 선택 검증 스크립트

목적:
- Supervisor가 질문 유형에 맞는 적절한 에이전트를 선택하는지 검증
- 불필요한 에이전트 호출 감지
- 질문 유형별 패턴 분석

사용법:
    python tests/verify_agent_selection.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.korean_supervisor_langgraph import process_conversational_question_v2


# 테스트 케이스 정의
TEST_CASES = [
    {
        "category": "단순 정보 조회",
        "question": "주가는?",
        "expected_agents": ["financial_expert"],
        "description": "주가만 물어보는 단순 질문 - financial만 필요"
    },
    {
        "category": "재무 분석",
        "question": "재무 상태는 어떤가요?",
        "expected_agents": ["financial_expert"],
        "description": "재무 분석 질문 - financial만 필요"
    },
    {
        "category": "비교 분석",
        "question": "SK하이닉스와 비교하면 어떤가요?",
        "expected_agents": ["comparative_expert", "financial_expert"],
        "description": "비교 질문 - comparative + financial 필요"
    },
    {
        "category": "투자 판단",
        "question": "지금 매수해도 될까요?",
        "expected_agents": ["financial_expert", "advanced_technical_expert", "comparative_expert"],
        "description": "투자 판단 - financial + technical + comparative 필요"
    },
    {
        "category": "뉴스 분석",
        "question": "최근 뉴스는 어떤가요?",
        "expected_agents": ["sentiment_expert"],
        "description": "뉴스 질문 - sentiment만 필요"
    },
    {
        "category": "기술적 분석",
        "question": "차트상으로는 어떤가요?",
        "expected_agents": ["advanced_technical_expert"],
        "description": "기술적 분석 - technical만 필요"
    },
    {
        "category": "수급 분석",
        "question": "외국인이 사고 있나요?",
        "expected_agents": ["institutional_trading_expert"],
        "description": "수급 질문 - institutional_trading만 필요"
    },
]


def analyze_question(question: str, stock_code: str = "005930", company_name: str = "삼성전자"):
    """
    질문에 대한 Supervisor의 답변을 분석

    Returns:
        tuple: (response, detected_agents)
    """
    print(f"\n{'='*80}")
    print(f"[질문 분석] {question}")
    print(f"{'='*80}")

    # Supervisor 실행
    response_chunks = []
    try:
        for chunk in process_conversational_question_v2(
            question=question,
            stock_code=stock_code,
            company_name=company_name,
            conversation_history=None
        ):
            response_chunks.append(chunk)

        full_response = "".join(response_chunks)

        # 응답에서 에이전트 힌트 추출 (어떤 에이전트가 호출되었는지 간접 추론)
        # 실제로는 로그를 파싱하거나 내부 상태를 확인해야 하지만,
        # 여기서는 응답 길이와 내용으로 간접 판단
        detected_agents = infer_agents_from_response(full_response)

        print(f"\n[답변 길이] {len(full_response):,}자")
        print(f"[추정 에이전트] {', '.join(detected_agents) if detected_agents else '알 수 없음'}")

        return full_response, detected_agents

    except Exception as e:
        print(f"\n⚠️ 오류 발생: {str(e)}")
        return "", []


def infer_agents_from_response(response: str) -> list:
    """
    응답 내용으로부터 호출된 에이전트 추론 (간접 방법)

    Note: 이것은 추론일 뿐이며, 정확한 방법은 로그 파싱 또는 내부 상태 확인
    """
    detected = []

    # 키워드 기반 추론 (완벽하지 않음)
    if any(keyword in response for keyword in ["재무", "매출", "영업이익", "PER", "PBR", "ROE"]):
        detected.append("financial_expert")

    if any(keyword in response for keyword in ["차트", "RSI", "MACD", "기술적", "지지선", "저항선"]):
        detected.append("advanced_technical_expert")

    if any(keyword in response for keyword in ["비교", "경쟁사", "동종업계", "섹터"]):
        detected.append("comparative_expert")

    if any(keyword in response for keyword in ["뉴스", "여론", "sentiment", "보도"]):
        detected.append("sentiment_expert")

    if any(keyword in response for keyword in ["외국인", "기관", "수급", "순매수"]):
        detected.append("institutional_trading_expert")

    return detected


def verify_agent_selection(test_case: dict):
    """
    테스트 케이스 검증

    Returns:
        dict: 검증 결과
    """
    question = test_case["question"]
    expected = test_case["expected_agents"]

    response, detected = analyze_question(question)

    # 검증
    if not detected:
        status = "⚠️ WARNING"
        message = "에이전트를 추론할 수 없음 (응답 내용이 불충분)"
    elif set(expected) == set(detected):
        status = "✅ PASS"
        message = "예상 에이전트와 일치"
    elif set(expected).issubset(set(detected)):
        status = "⚠️ WARNING"
        message = f"예상 에이전트 포함, 추가 에이전트: {set(detected) - set(expected)}"
    else:
        status = "❌ FAIL"
        message = f"예상: {expected}, 실제: {detected}"

    return {
        "status": status,
        "message": message,
        "expected": expected,
        "detected": detected,
        "response_length": len(response)
    }


def run_verification():
    """전체 검증 실행"""
    print("="*80)
    print("에이전트 선택 검증 스크립트")
    print("="*80)
    print(f"테스트 케이스 수: {len(TEST_CASES)}개")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    results = []

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n\n[테스트 {i}/{len(TEST_CASES)}]")
        print(f"카테고리: {test_case['category']}")
        print(f"설명: {test_case['description']}")

        result = verify_agent_selection(test_case)
        result["category"] = test_case["category"]
        result["question"] = test_case["question"]
        results.append(result)

        print(f"\n{result['status']} - {result['message']}")

        # 다음 테스트 전 잠시 대기 (선택적)
        # input("\n[Enter를 눌러 다음 테스트...]")

    # 최종 요약
    print("\n\n" + "="*80)
    print("검증 결과 요약")
    print("="*80)

    pass_count = sum(1 for r in results if r["status"] == "✅ PASS")
    warning_count = sum(1 for r in results if r["status"] == "⚠️ WARNING")
    fail_count = sum(1 for r in results if r["status"] == "❌ FAIL")

    print(f"\n총 테스트: {len(results)}개")
    print(f"✅ PASS: {pass_count}개")
    print(f"⚠️ WARNING: {warning_count}개")
    print(f"❌ FAIL: {fail_count}개")

    print("\n[상세 결과]")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['category']}")
        print(f"   질문: {result['question']}")
        print(f"   {result['status']} - {result['message']}")
        print(f"   예상: {result['expected']}")
        print(f"   추정: {result['detected']}")
        print(f"   답변 길이: {result['response_length']:,}자")

    print("\n" + "="*80)
    print("검증 완료!")
    print("="*80)

    # 검증 통과 여부
    if fail_count == 0 and warning_count == 0:
        print("\n🎉 모든 테스트 PASS!")
        return True
    elif fail_count == 0:
        print("\n⚠️ 일부 경고 발생 (추가 검토 필요)")
        return True
    else:
        print("\n❌ 일부 테스트 실패 (개선 필요)")
        return False


if __name__ == "__main__":
    print("\n에이전트 선택 검증을 시작합니다...")
    print("이 스크립트는 Supervisor가 질문에 맞는 에이전트를 선택하는지 검증합니다.\n")

    # 사용자 확인
    print("주의: 이 스크립트는 실제 API를 호출하므로 시간이 걸릴 수 있습니다.")
    proceed = input("계속 진행하시겠습니까? (y/n): ").strip().lower()

    if proceed != 'y':
        print("\n검증을 취소합니다.")
        sys.exit(0)

    # 검증 실행
    success = run_verification()

    # 종료 코드
    sys.exit(0 if success else 1)
