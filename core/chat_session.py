#!/usr/bin/env python3
"""
Chat Session Manager
분석 결과 기반 대화형 AI 세션 관리
"""

import logging
import threading
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config.llm_factory import build_llm
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


class ChatSession:
    """
    분석 결과 기반 대화 세션 관리 클래스

    8개 에이전트 분석 결과를 컨텍스트로 하여
    사용자와 대화형 상호작용 제공
    """

    def __init__(self, stock_code: str, company_name: str, analysis_result: dict[str, Any]):
        """
        세션 초기화

        Args:
            stock_code: 종목 코드
            company_name: 회사명
            analysis_result: 8개 에이전트 분석 결과
        """
        self.stock_code = stock_code
        self.company_name = company_name
        self.analysis_result = analysis_result
        self.created_at = datetime.now()

        # 대화 히스토리 + 갱신 락 (Streamlit fragment/동시 입력 보호)
        self.messages: list[dict[str, str]] = []
        self._messages_lock = threading.Lock()

        # LLM 초기화
        self.llm = self._initialize_llm()

        # 시스템 프롬프트 생성
        self.system_prompt = self._create_system_prompt()

        logger.info(f"ChatSession created for {company_name} ({stock_code})")

    def _initialize_llm(self):
        """LLM 초기화 (통합 팩토리)."""
        try:
            return build_llm(temperature=0.3)
        except Exception as e:
            logger.error(f"LLM 초기화 실패: {e}")
            raise

    def _create_system_prompt(self) -> str:
        """
        시스템 프롬프트 생성
        8개 에이전트 분석 결과를 컨텍스트로 포함
        """
        # 분석 결과 요약
        analysis_summary = self._summarize_analysis()

        prompt = f"""당신은 한국 주식 투자 전문 AI 어시스턴트입니다.

**현재 분석 대상:**
- 종목: {self.company_name} ({self.stock_code})
- 분석 시간: {self.created_at.strftime("%Y-%m-%d %H:%M")}

**8개 전문 에이전트 분석 결과:**
{analysis_summary}

**역할:**
1. 위 분석 결과를 바탕으로 사용자 질문에 답변합니다
2. "왜 이렇게 분석했어?", "더 자세히 설명해줘" 같은 질문에 답합니다
3. 투자 의견을 물으면 분석 결과를 종합하여 조언합니다
4. 한국어로 친절하게, 투자 초보자도 이해하기 쉽게 설명합니다
5. 항상 객관적이고 분석 결과 기반으로 답변합니다

**주의사항:**
- 분석 결과에 없는 내용은 추측하지 말고 "분석 결과에 없습니다"라고 말합니다
- 투자 권유가 아니라 참고 정보임을 명시합니다
- 리스크를 항상 함께 언급합니다

**대화 스타일:**
- 친근하고 전문적
- 구체적 수치와 근거 제시
- 이모지 적절히 사용 (📊, 💡, ⚠️ 등)
"""
        return prompt

    def _summarize_analysis(self) -> str:
        """분석 결과를 텍스트로 요약"""
        summary_parts = []

        # 각 에이전트 결과 요약
        agent_names = {
            "context_expert": "🌍 시장 환경",
            "sentiment_expert": "📰 뉴스 여론",
            "financial_expert": "💰 재무 상태",
            "advanced_technical_expert": "📈 기술적 분석",
            "institutional_trading_expert": "🏦 기관 수급",
            "comparative_expert": "⚖️ 상대 가치",
            "esg_expert": "🌱 ESG",
            "community_expert": "💬 커뮤니티",
        }

        for agent_key, agent_title in agent_names.items():
            if agent_key in self.analysis_result:
                content = self.analysis_result[agent_key].get("content", "분석 데이터 없음")
                # 너무 길면 앞부분만
                if len(content) > 500:
                    content = content[:500] + "..."
                summary_parts.append(f"{agent_title}:\n{content}\n")

        return "\n".join(summary_parts)

    def ask(self, user_question: str) -> str:
        """
        사용자 질문에 답변

        Args:
            user_question: 사용자 질문

        Returns:
            AI 답변
        """
        try:
            # 동시 입력 보호: messages 갱신과 스냅샷 채취를 한 lock 안에서 처리.
            # LLM 호출 자체는 락 밖에서 (블로킹 길어도 다른 작업이 멈추지 않게).
            with self._messages_lock:
                self.messages.append({"role": "user", "content": user_question, "timestamp": kst_isoformat()})
                # 최근 컨텍스트: user 메시지에서 시작하도록 정렬 (user→assistant 페어 보존).
                # 짝수 페어 경계를 맞추지 않으면 LLM이 assistant→user→... 같이
                # 끝나는 부자연스러운 컨텍스트를 받게 된다.
                tail = self.messages[-10:]
                while tail and tail[0]["role"] != "user":
                    tail = tail[1:]
                recent_messages = list(tail)

            # LangChain 메시지 구성
            langchain_messages = [SystemMessage(content=self.system_prompt)]
            for msg in recent_messages:
                if msg["role"] == "user":
                    langchain_messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    langchain_messages.append(AIMessage(content=msg["content"]))

            # LLM 호출 (락 밖)
            response = self.llm.invoke(langchain_messages)
            answer = response.content

            # 대화 히스토리에 답변 추가
            with self._messages_lock:
                self.messages.append({"role": "assistant", "content": answer, "timestamp": kst_isoformat()})

            logger.info(f"Question: {user_question[:50]}... | Answer length: {len(answer)}")
            return answer

        except Exception as e:
            error_msg = f"❌ 답변 생성 중 오류가 발생했습니다: {str(e)}"
            logger.error(f"Chat error: {e}", exc_info=True)
            return error_msg

    def get_conversation_history(self) -> list[dict[str, str]]:
        """대화 히스토리 반환 (snapshot)."""
        with self._messages_lock:
            return self.messages.copy()

    def clear_history(self):
        """대화 히스토리 초기화."""
        with self._messages_lock:
            self.messages = []
        logger.info("Conversation history cleared")


def create_chat_session(
    stock_code: str, company_name: str, analysis_result: dict[str, Any]
) -> ChatSession | None:
    """
    채팅 세션 생성 헬퍼 함수

    Args:
        stock_code: 종목 코드
        company_name: 회사명
        analysis_result: 분석 결과

    Returns:
        ChatSession 또는 None (실패 시)
    """
    try:
        return ChatSession(stock_code, company_name, analysis_result)
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        return None
