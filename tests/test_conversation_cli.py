#!/usr/bin/env python3
"""
CLI 기반 대화형 테스트 스크립트
Streamlit 없이 대화 서비스 테스트

사용법:
    python tests/test_conversation_cli.py

특징:
- 실제 대화처럼 질문-답변 반복
- 에이전트 선택 로그 실시간 출력
- 대화 히스토리 자동 관리
- 멀티턴 대화 테스트
"""

import sys
import os

# 상위 디렉토리를 경로에 추가 (tusimreport 모듈 import 가능하도록)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.korean_supervisor_langgraph import process_conversational_question_v2


class ConversationTester:
    """대화형 테스트 클래스"""

    def __init__(self, stock_code: str, company_name: str):
        self.stock_code = stock_code
        self.company_name = company_name
        self.conversation_history = []
        self.session_start = datetime.now()
        self.turn_count = 0

    def ask(self, question: str, auto_continue: bool = False):
        """
        질문하고 답변 받기

        Args:
            question: 사용자 질문
            auto_continue: True면 자동 진행, False면 Enter 대기
        """
        self.turn_count += 1

        print(f"\n{'='*80}")
        print(f"[Turn {self.turn_count}] User: {question}")
        print(f"{'='*80}\n")

        # 사용자 메시지 추가
        self.conversation_history.append({
            "role": "user",
            "content": question,
            "timestamp": datetime.now().isoformat()
        })

        # Supervisor 실행
        response = ""
        try:
            print("[🤖 Conversational Supervisor v2 실행 중...]\n")

            for chunk in process_conversational_question_v2(
                question=question,
                stock_code=self.stock_code,
                company_name=self.company_name,
                conversation_history=self.conversation_history
            ):
                print(chunk, end="", flush=True)
                response += chunk

            print("\n")

            # AI 응답 추가
            self.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            })

            # 응답 통계
            print(f"\n[응답 통계]")
            print(f"- 답변 길이: {len(response):,}자")
            print(f"- 대화 턴: {self.turn_count}턴")
            print(f"- 대화 히스토리: {len(self.conversation_history)}개 메시지")

        except Exception as e:
            print(f"\n⚠️ 오류 발생: {str(e)}\n")
            import traceback
            traceback.print_exc()

        # 계속 진행 여부
        if not auto_continue:
            input("\n[Enter를 눌러 계속...]")

    def show_history(self):
        """대화 히스토리 출력"""
        print("\n" + "="*80)
        print("[📜 대화 히스토리]")
        print("="*80)

        for i, msg in enumerate(self.conversation_history, 1):
            role = "사용자" if msg["role"] == "user" else "AI"
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            timestamp = msg.get("timestamp", "N/A")
            print(f"{i}. [{role}] ({timestamp})")
            print(f"   {content}\n")

    def show_summary(self):
        """세션 요약"""
        duration = (datetime.now() - self.session_start).total_seconds()

        print("\n" + "="*80)
        print("[📊 세션 요약]")
        print("="*80)
        print(f"종목: {self.stock_code} ({self.company_name})")
        print(f"총 대화 턴: {self.turn_count}턴")
        print(f"총 메시지: {len(self.conversation_history)}개")
        print(f"세션 시간: {duration:.1f}초")
        print("="*80)


def run_test_scenario(scenario_name: str, stock_code: str, company_name: str, questions: list, auto_continue: bool = False):
    """
    테스트 시나리오 실행

    Args:
        scenario_name: 시나리오 이름
        stock_code: 종목 코드
        company_name: 회사명
        questions: 질문 리스트
        auto_continue: 자동 진행 여부
    """
    print(f"\n\n{'#'*80}")
    print(f"# 테스트 시나리오: {scenario_name}")
    print(f"# 종목: {stock_code} ({company_name})")
    print(f"# 질문 수: {len(questions)}개")
    print(f"{'#'*80}\n")

    tester = ConversationTester(stock_code, company_name)

    for i, question in enumerate(questions, 1):
        print(f"\n[질문 {i}/{len(questions)}]")
        tester.ask(question, auto_continue=auto_continue)

    # 최종 요약
    tester.show_history()
    tester.show_summary()

    print(f"\n✅ {scenario_name} 완료!")


def interactive_mode():
    """대화형 모드 - 사용자가 직접 질문 입력"""
    print("\n" + "="*80)
    print("대화형 모드 (Interactive Mode)")
    print("="*80)
    print("종료하려면 'quit' 또는 'exit'를 입력하세요\n")

    # 종목 정보 입력
    stock_code = input("종목 코드: ").strip() or "005930"
    company_name = input("회사명: ").strip() or "삼성전자"

    tester = ConversationTester(stock_code, company_name)

    print(f"\n💬 {company_name}({stock_code})에 대해 질문해보세요!\n")

    while True:
        try:
            question = input("\n[You] ").strip()

            if question.lower() in ["quit", "exit", "종료", "그만"]:
                print("\n대화를 종료합니다.")
                break

            if not question:
                continue

            tester.ask(question, auto_continue=True)

        except KeyboardInterrupt:
            print("\n\n대화를 종료합니다.")
            break
        except Exception as e:
            print(f"\n오류 발생: {str(e)}")
            continue

    # 최종 요약
    tester.show_summary()


if __name__ == "__main__":
    print("="*80)
    print("TuSimReport 대화형 서비스 CLI 테스트")
    print("="*80)
    print("\n테스트 모드를 선택하세요:")
    print("1. 자동 테스트 (시나리오 기반)")
    print("2. 대화형 모드 (직접 질문)")
    print("3. 모든 테스트 실행")

    choice = input("\n선택 (1-3): ").strip() or "1"

    if choice == "1":
        # 자동 테스트 시나리오
        print("\n[자동 테스트 시작]")

        # 시나리오 1: 멀티턴 대화
        run_test_scenario(
            "멀티턴 대화 테스트",
            "005930",
            "삼성전자",
            [
                "삼성전자 주가가 어떤가요?",
                "그럼 SK하이닉스와 비교하면 어떤가요?",
                "지금 매수해도 될까요?"
            ],
            auto_continue=False
        )

        # 시나리오 2: 에이전트 선택 확인
        run_test_scenario(
            "에이전트 선택 테스트",
            "000660",
            "SK하이닉스",
            [
                "주가는?",  # financial만
                "최근 뉴스는?",  # sentiment만
                "외국인이 사고 있나요?",  # institutional_trading만
            ],
            auto_continue=False
        )

    elif choice == "2":
        # 대화형 모드
        interactive_mode()

    elif choice == "3":
        # 모든 테스트 실행
        print("\n[모든 테스트 실행]")

        run_test_scenario(
            "기본 기능 테스트",
            "005930",
            "삼성전자",
            ["삼성전자를 분석해주세요"],
            auto_continue=True
        )

        run_test_scenario(
            "멀티턴 대화 테스트",
            "000270",
            "기아",
            [
                "기아 주가는?",
                "현대차와 비교하면?",
                "투자 가치는?"
            ],
            auto_continue=True
        )

        run_test_scenario(
            "다양한 질문 유형 테스트",
            "035420",
            "네이버",
            [
                "재무 상태는?",
                "기술적으로 어떤가요?",
                "동종업계 대비 밸류에이션은?"
            ],
            auto_continue=True
        )

    print("\n\n🎉 모든 테스트 완료!")
