#!/usr/bin/env python3
"""
대화형 AI 채팅 시스템 - 실행 가능한 예제

사용법:
    python examples/conversational_example.py

시나리오:
1. 삼성전자(005930) 초기 분석
2. 추가 질문 1: "왜 BUY 의견인가요?"
3. 추가 질문 2: "최근 뉴스 분위기는?"
4. 추가 질문 3: "재무 건전성은?"
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime
from dotenv import load_dotenv

from core.conversational_supervisor import get_conversational_supervisor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_separator(title=""):
    """구분선 출력"""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}\n")
    else:
        print(f"\n{'-'*80}\n")


def print_state_summary(state):
    """State 요약 정보 출력"""
    print("📊 State 요약:")
    print(f"  - 종목: {state['stock_code']} ({state['company_name']})")
    print(f"  - 세션 ID: {state['session_id']}")
    print(f"  - 초기 분석 완료: {state['initial_analysis_completed']}")
    print(f"  - 저장된 에이전트 결과: {len(state['agent_results'])}개")
    print(f"  - 대화 메시지 수: {len(state['messages'])}개")
    print(f"  - 마지막 업데이트: {state['last_updated']}")


def scenario_1_initial_analysis():
    """시나리오 1: 초기 전체 분석"""

    print_separator("시나리오 1: 삼성전자 초기 분석 (10개 전문가 에이전트)")

    supervisor = get_conversational_supervisor()

    print("🚀 초기 분석 시작...")
    print("   - 10개 전문가 에이전트 순차 실행")
    print("   - 투자 의견 생성")
    print("   - 종합 보고서 생성")

    # 초기 분석 실행
    state = supervisor.analyze(
        stock_code="005930",
        company_name="삼성전자",
        question=None,  # 초기 분석
        session_id=None  # 신규 세션
    )

    print("\n✅ 초기 분석 완료!")
    print_state_summary(state)

    # 투자 의견 출력
    if state.get("investment_opinion"):
        opinion = state["investment_opinion"]
        print("\n🎯 투자 의견:")
        print(f"  - 결론: {opinion.get('investment_opinion', {}).get('decision', 'N/A')}")
        print(f"  - 신뢰도: {opinion.get('investment_opinion', {}).get('confidence', 0)}%")
        print(f"  - 현재가: {opinion.get('current_price', 0):,}원")
        target_3m = opinion.get('target_prices', {}).get('3_months', {})
        print(f"  - 3개월 목표가: {target_3m.get('price', 0):,}원 ({target_3m.get('percentage', 0):+.1f}%)")

    # 최종 답변 출력 (일부만)
    final_answer = state["final_answer"]
    print(f"\n📄 종합 보고서 (앞부분 500자):")
    print(final_answer[:500] + "...")

    print_separator()

    return state


def scenario_2_follow_up_question_1(session_id):
    """시나리오 2: 추가 질문 1 - "왜 BUY 의견인가요?" """

    print_separator("시나리오 2: 추가 질문 1 - 투자 의견 근거")

    supervisor = get_conversational_supervisor()

    question = "왜 BUY 의견인가요? 주요 근거를 알려주세요."

    print(f"👤 사용자 질문: {question}")
    print("\n🤔 Question Router 동작 중...")
    print("   - 질문 의도 분석")
    print("   - 필요한 에이전트 선택")

    # 추가 질문 실행
    state = supervisor.analyze(
        stock_code="005930",
        company_name="삼성전자",
        question=question,
        session_id=session_id  # 기존 세션 재사용
    )

    print("\n✅ 답변 생성 완료!")
    print_state_summary(state)

    # 라우팅 정보 출력
    if state.get("router_decision"):
        router = state["router_decision"]
        print(f"\n🎯 선택된 에이전트: {', '.join(router.get('selected_agents', []))}")
        print(f"📋 선택 이유:\n   {router.get('reasoning', 'N/A')}")

    # 답변 출력
    print(f"\n🤖 AI 답변:")
    print(state["final_answer"])

    print_separator()

    return state


def scenario_3_follow_up_question_2(session_id):
    """시나리오 3: 추가 질문 2 - "최근 뉴스 분위기는?" """

    print_separator("시나리오 3: 추가 질문 2 - 실시간 뉴스 분석")

    supervisor = get_conversational_supervisor()

    question = "최근 뉴스 분위기는 어떤가요? 긍정적인가요 부정적인가요?"

    print(f"👤 사용자 질문: {question}")
    print("\n🤔 Question Router 동작 중...")
    print("   - '최근' 키워드 감지 → 실시간 데이터 필요")
    print("   - sentiment_expert 선택 예상")

    # 추가 질문 실행
    state = supervisor.analyze(
        stock_code="005930",
        company_name="삼성전자",
        question=question,
        session_id=session_id
    )

    print("\n✅ 답변 생성 완료!")
    print_state_summary(state)

    # 라우팅 정보 출력
    if state.get("router_decision"):
        router = state["router_decision"]
        print(f"\n🎯 선택된 에이전트: {', '.join(router.get('selected_agents', []))}")
        print(f"📋 선택 이유:\n   {router.get('reasoning', 'N/A')}")
        print(f"🔄 실시간 데이터 갱신: {router.get('needs_fresh_data', False)}")

    # 답변 출력
    print(f"\n🤖 AI 답변:")
    print(state["final_answer"])

    print_separator()

    return state


def scenario_4_follow_up_question_3(session_id):
    """시나리오 4: 추가 질문 3 - "재무 건전성은?" """

    print_separator("시나리오 4: 추가 질문 3 - 재무 건전성 분석")

    supervisor = get_conversational_supervisor()

    question = "재무 건전성은 어떤가요? 부채비율이나 현금 흐름은 괜찮나요?"

    print(f"👤 사용자 질문: {question}")
    print("\n🤔 Question Router 동작 중...")
    print("   - '재무', '부채', '현금흐름' 키워드 감지")
    print("   - financial_expert, quantitative_expert 선택 예상")

    # 추가 질문 실행
    state = supervisor.analyze(
        stock_code="005930",
        company_name="삼성전자",
        question=question,
        session_id=session_id
    )

    print("\n✅ 답변 생성 완료!")
    print_state_summary(state)

    # 라우팅 정보 출력
    if state.get("router_decision"):
        router = state["router_decision"]
        print(f"\n🎯 선택된 에이전트: {', '.join(router.get('selected_agents', []))}")
        print(f"📋 선택 이유:\n   {router.get('reasoning', 'N/A')}")

    # 답변 출력
    print(f"\n🤖 AI 답변:")
    print(state["final_answer"])

    print_separator()

    return state


def main():
    """메인 실행 함수"""

    print_separator("🤖 대화형 AI 채팅 시스템 - 통합 테스트")

    print("📋 테스트 시나리오:")
    print("  1. 삼성전자(005930) 초기 분석")
    print("  2. 추가 질문 1: '왜 BUY 의견인가요?'")
    print("  3. 추가 질문 2: '최근 뉴스 분위기는?'")
    print("  4. 추가 질문 3: '재무 건전성은?'")

    print("\n⚠️  주의사항:")
    print("  - .env 파일에 API 키가 설정되어 있어야 합니다")
    print("  - 초기 분석은 약 2-3분 소요됩니다")
    print("  - 추가 질문은 각각 10-30초 소요됩니다")

    input("\nEnter 키를 눌러 시작하세요...")

    # 시나리오 1: 초기 분석
    state = scenario_1_initial_analysis()
    session_id = state["session_id"]

    input("\n다음 시나리오로 진행하려면 Enter 키를 누르세요...")

    # 시나리오 2: 추가 질문 1
    state = scenario_2_follow_up_question_1(session_id)

    input("\n다음 시나리오로 진행하려면 Enter 키를 누르세요...")

    # 시나리오 3: 추가 질문 2
    state = scenario_3_follow_up_question_2(session_id)

    input("\n다음 시나리오로 진행하려면 Enter 키를 누르세요...")

    # 시나리오 4: 추가 질문 3
    state = scenario_4_follow_up_question_3(session_id)

    print_separator("🎉 모든 테스트 완료!")

    print("📊 최종 통계:")
    print(f"  - 총 대화 메시지 수: {len(state['messages'])}개")
    print(f"  - 저장된 에이전트 결과: {len(state['agent_results'])}개")
    print(f"  - 세션 ID: {state['session_id']}")
    print(f"  - 테스트 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n✅ 대화형 AI 채팅 시스템이 정상적으로 동작합니다!")


if __name__ == "__main__":
    # .env 파일 로드
    load_dotenv()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}", exc_info=True)
        sys.exit(1)
