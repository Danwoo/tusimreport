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
from core.korean_supervisor_langgraph import EXPERT_LABELS
from core.signals import AGENT_TO_SIGNAL
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


class ChatSession:
    """
    분석 결과 기반 대화 세션 관리 클래스

    근거 데이터가 있는 전문 에이전트 분석 결과만 컨텍스트로 삼고,
    나머지 영역은 '데이터 없음'으로 프롬프트에 밝힌다.
    """

    def __init__(
        self,
        stock_code: str,
        company_name: str,
        analysis_result: dict[str, Any],
        excluded: dict[str, str] | None = None,
    ):
        """
        세션 초기화

        Args:
            stock_code: 종목 코드
            company_name: 회사명
            analysis_result: 에이전트명 → {"status", "content"}. status가 'completed'인
                (근거 데이터가 있는) 항목만 대화 컨텍스트에 들어간다.
            excluded: 빠진 영역과 그 사유. 없는 영역은 사유 없이 '데이터 없음'으로 적는다.
        """
        self.stock_code = stock_code
        self.company_name = company_name
        self.analysis_result = analysis_result
        self.excluded = excluded or {}
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

    def _grounded_results(self) -> dict[str, str]:
        """근거 데이터가 있는 에이전트의 분석 텍스트 (AGENT_TO_SIGNAL 순서)."""
        grounded = {}
        for name in AGENT_TO_SIGNAL:
            state = self.analysis_result.get(name)
            if not isinstance(state, dict) or state.get("status") != "completed":
                continue
            content = str(state.get("content") or "").strip()
            if content:
                grounded[name] = content
        return grounded

    def _missing_section(self, grounded: dict[str, str]) -> str:
        missing = [name for name in AGENT_TO_SIGNAL if name not in grounded]
        if not missing:
            return ""
        lines = []
        for name in missing:
            reason = self.excluded.get(name)
            label = EXPERT_LABELS.get(name, name)
            lines.append(f"- {label}: 데이터 없음 ({reason})" if reason else f"- {label}: 데이터 없음")
        return (
            "\n**데이터 없음 영역** (근거 데이터가 없어 위 결과에 넣지 않은 분석):\n"
            + "\n".join(lines)
            + "\n"
        )

    def _create_system_prompt(self) -> str:
        """근거 있는 분석 결과와 빠진 영역을 담은 시스템 프롬프트."""
        grounded = self._grounded_results()
        analysis_summary = self._summarize_analysis(grounded)

        prompt = f"""당신은 한국 주식 투자 전문 AI 어시스턴트입니다.

**현재 분석 대상:**
- 종목: {self.company_name} ({self.stock_code})
- 분석 시간: {self.created_at.strftime("%Y-%m-%d %H:%M")}

**전문 에이전트 분석 결과 ({len(grounded)}/{len(AGENT_TO_SIGNAL)}개 영역):**
{analysis_summary}
{self._missing_section(grounded)}

**역할:**
1. 위 분석 결과를 바탕으로 사용자 질문에 답변합니다
2. "왜 이렇게 분석했어?", "더 자세히 설명해줘" 같은 질문에 답합니다
3. 투자 의견을 물으면 분석 결과를 종합하여 조언합니다
4. 한국어로 친절하게, 투자 초보자도 이해하기 쉽게 설명합니다
5. 항상 객관적이고 분석 결과 기반으로 답변합니다

**주의사항:**
- 분석 결과에 없는 내용은 추측하지 말고 "분석 결과에 없습니다"라고 말합니다
- '데이터 없음' 영역을 물으면 그 영역은 근거 데이터가 없어 분석하지 못했다고 답합니다
- 투자 권유가 아니라 참고 정보임을 명시합니다
- 리스크를 항상 함께 언급합니다

**대화 스타일:**
- 친근하고 전문적
- 구체적 수치와 근거 제시
- 이모지 적절히 사용 (📊, 💡, ⚠️ 등)
"""
        return prompt

    def _summarize_analysis(self, grounded: dict[str, str]) -> str:
        """근거 있는 분석 결과를 영역별로 앞부분만 옮긴다."""
        summary_parts = []
        for name, content in grounded.items():
            if len(content) > 500:
                content = content[:500] + "..."
            summary_parts.append(f"{EXPERT_LABELS.get(name, name)}:\n{content}\n")
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
    stock_code: str,
    company_name: str,
    analysis_result: dict[str, Any],
    excluded: dict[str, str] | None = None,
) -> ChatSession | None:
    """
    채팅 세션 생성 헬퍼 함수

    Args:
        stock_code: 종목 코드
        company_name: 회사명
        analysis_result: 에이전트명 → {"status", "content"} (근거 있는 항목만 쓰인다)
        excluded: 빠진 영역과 그 사유

    Returns:
        ChatSession 또는 None (실패 시)
    """
    try:
        return ChatSession(stock_code, company_name, analysis_result, excluded)
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        return None
