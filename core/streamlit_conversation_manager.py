#!/usr/bin/env python3
"""
Streamlit 네이티브 대화형 서비스 관리자
st.chat_message + st.chat_input 기반 대화형 Q&A 시스템
"""

import streamlit as st
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import re

from config.settings import get_llm_model

logger = logging.getLogger(__name__)

class StreamlitConversationManager:
    """Streamlit 네이티브 대화형 관리자"""

    def __init__(self):
        """대화형 매니저 초기화"""
        self._initialize_session_state()
        self.llm = self._get_cached_llm()

        # 질문 유형 분류를 위한 키워드 패턴
        self.question_patterns = {
            "financial": ["재무", "매출", "영업이익", "순이익", "부채", "자산", "ROE", "ROA", "PER", "PBR", "배당", "현금흐름"],
            "technical": ["차트", "기술적", "RSI", "MACD", "이평선", "볼린저밴드", "골든크로스", "저항선", "지지선", "캔들"],
            "sentiment": ["뉴스", "여론", "감정", "시장심리", "투자심리", "분위기", "평가", "전망"],
            "esg": ["ESG", "환경", "지배구조", "사회적", "지속가능", "친환경", "탄소", "윤리"],
            "forecast": ["전망", "목표가", "예상", "미래", "향후", "앞으로", "내년", "장기"],
            "comparison": ["비교", "동종업계", "경쟁사", "업계", "섹터", "vs", "대비"],
            "institutional": ["기관", "수급", "매매", "외국인", "개인", "투자자", "거래량"],
            "risk": ["위험", "리스크", "변동성", "하락", "손실", "불확실성", "위기"]
        }

        logger.info("StreamlitConversationManager 초기화 완료")

    def _initialize_session_state(self):
        """Session State 초기화"""
        # 채팅 메시지 히스토리
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        # 보고서 및 분석 데이터
        if "final_report" not in st.session_state:
            st.session_state.final_report = ""

        if "agent_summaries" not in st.session_state:
            st.session_state.agent_summaries = {}

        # 대화 컨텍스트 관리
        if "conversation_context" not in st.session_state:
            st.session_state.conversation_context = ""

        # 사용자 세션 정보
        if "conversation_started" not in st.session_state:
            st.session_state.conversation_started = False

        logger.debug("대화형 세션 상태 초기화 완료")

    @st.cache_resource
    def _get_cached_llm(_self):
        """LLM 인스턴스 캐싱 (세션간 공유)"""
        try:
            provider, model_name, api_key = get_llm_model()

            if provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=0.1,
                    google_api_key=api_key
                )
            else:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=model_name,
                    temperature=0.1,
                    api_key=api_key
                )
        except Exception as e:
            logger.error(f"LLM 초기화 실패: {str(e)}")
            return None

    def is_conversation_available(self) -> bool:
        """대화형 서비스 사용 가능 여부 확인"""
        return bool(
            st.session_state.get("final_report") or
            st.session_state.get("agent_summaries")
        )

    def render_conversation_interface(self):
        """메인 대화형 인터페이스 렌더링"""

        if not self.is_conversation_available():
            st.info("💬 분석 보고서가 생성된 후 대화형 Q&A를 사용할 수 있습니다.")
            return

        # 대화형 서비스 제목
        st.markdown("### 💬 투자 분석 Q&A")
        st.markdown("분석 보고서를 바탕으로 궁금한 점을 자유롭게 물어보세요!")

        # 채팅 히스토리 표시
        self._render_chat_history()

        # 사용자 입력 처리
        self._handle_user_input()

        # 대화 시작 안내
        # 🔧 Session state 방어적 초기화
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        if not st.session_state.chat_messages:
            self._show_conversation_starter()

    def _render_chat_history(self):
        """채팅 히스토리 렌더링"""
        # 🔧 Session state 방어적 초기화
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    # AI 응답에는 추가 정보 표시
                    st.markdown(message["content"])
                    if "timestamp" in message:
                        st.caption(f"응답 시간: {message['timestamp']}")
                else:
                    # 사용자 메시지
                    st.markdown(message["content"])

    def _handle_user_input(self):
        """사용자 입력 처리"""
        # Streamlit 네이티브 채팅 입력 (분석 유형별 유니크 키)
        import time
        analysis_type = st.session_state.get('current_analysis_type', 'default')
        timestamp = int(time.time() * 1000)  # 밀리초 타임스탬프
        unique_key = f"conversation_input_{analysis_type}_{timestamp}_{hash(str(st.session_state.get('final_report', '')))}"
        if prompt := st.chat_input(
            "분석 보고서에 대해 궁금한 점을 물어보세요...",
            key=unique_key
        ):
            # 사용자 메시지 추가
            user_message = {
                "role": "user",
                "content": prompt,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.chat_messages.append(user_message)

            # 사용자 메시지 즉시 표시
            with st.chat_message("user"):
                st.markdown(prompt)

            # AI 응답 생성 및 표시
            with st.chat_message("assistant"):
                with st.spinner("분석 중..."):
                    try:
                        response = self._generate_contextual_response(prompt)
                        st.markdown(response)

                        # AI 응답 세션에 저장
                        assistant_message = {
                            "role": "assistant",
                            "content": response,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.chat_messages.append(assistant_message)

                        # 대화 시작 플래그 설정
                        st.session_state.conversation_started = True

                    except Exception as e:
                        error_msg = f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(e)}"
                        st.error(error_msg)

                        # 오류 메시지도 히스토리에 저장
                        error_message = {
                            "role": "assistant",
                            "content": error_msg,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.chat_messages.append(error_message)

    def _generate_contextual_response(self, question: str) -> str:
        """보고서 컨텍스트 기반 응답 생성"""
        try:
            # 질문 유형 분류
            question_type = self._classify_question_type(question)

            # 관련 컨텍스트 구성
            relevant_context = self._get_relevant_context(question, question_type)

            # 대화 히스토리 요약 (최근 3개 메시지)
            conversation_history = self._get_recent_conversation_history(3)

            # 프롬프트 구성
            context_prompt = f"""
당신은 전문 투자 분석가입니다. 다음 종합 투자 분석 보고서를 바탕으로 사용자의 질문에 정확하고 도움이 되는 답변을 제공해주세요.

## 분석 보고서 내용:
{relevant_context}

## 최근 대화 내역:
{conversation_history}

## 사용자 질문:
{question}

## 답변 가이드라인:
- 보고서의 내용을 근거로 답변하세요
- 구체적인 수치나 데이터가 있다면 인용하세요
- 불확실한 내용은 명확히 구분하여 표현하세요
- 투자 조언이 아닌 분석 정보임을 명시하세요
- 간결하고 이해하기 쉽게 답변하세요

답변:
"""

            # LLM 호출
            if self.llm:
                response = self.llm.invoke(context_prompt)
                return response.content if hasattr(response, 'content') else str(response)
            else:
                return "죄송합니다. AI 서비스에 일시적인 문제가 발생했습니다."

        except Exception as e:
            logger.error(f"응답 생성 오류: {str(e)}")
            return f"응답 생성 중 오류가 발생했습니다: {str(e)}"

    def _classify_question_type(self, question: str) -> str:
        """질문 유형 분류"""
        question_lower = question.lower()

        # 각 유형별 키워드 매칭
        for category, keywords in self.question_patterns.items():
            if any(keyword in question_lower for keyword in keywords):
                return category

        return "general"

    def _get_relevant_context(self, question: str, question_type: str) -> str:
        """질문과 관련된 컨텍스트 추출"""
        contexts = []

        # 최종 보고서에서 관련 섹션 추출
        if st.session_state.final_report:
            report_sections = self._extract_relevant_report_sections(
                question, st.session_state.final_report
            )
            if report_sections:
                contexts.append(f"## 종합 보고서 관련 내용:\n{report_sections}")

        # 에이전트별 분석에서 관련 내용 추출
        if st.session_state.agent_summaries:
            agent_contexts = self._extract_relevant_agent_analysis(
                question, question_type, st.session_state.agent_summaries
            )
            if agent_contexts:
                contexts.append(f"## 전문가 분석 관련 내용:\n{agent_contexts}")

        # 컨텍스트 길이 제한 (5000자)
        combined_context = "\n\n".join(contexts)
        if len(combined_context) > 5000:
            combined_context = combined_context[:5000] + "..."

        return combined_context

    def _extract_relevant_report_sections(self, question: str, report: str) -> str:
        """보고서에서 관련 섹션 추출"""
        # 질문의 핵심 키워드 추출
        keywords = re.findall(r'\b\w{2,}\b', question.lower())

        # 보고서를 섹션별로 분할 (## 또는 ### 기준)
        sections = re.split(r'\n##+ ', report)

        relevant_sections = []
        for section in sections:
            section_lower = section.lower()
            if any(keyword in section_lower for keyword in keywords):
                # 섹션 길이 제한 (1000자)
                if len(section) > 1000:
                    section = section[:1000] + "..."
                relevant_sections.append(section)

        return "\n\n".join(relevant_sections[:3])  # 최대 3개 섹션

    def _extract_relevant_agent_analysis(
        self,
        question: str,
        question_type: str,
        agent_summaries: Dict[str, str]
    ) -> str:
        """에이전트 분석에서 관련 내용 추출"""

        # 질문 유형에 따른 관련 에이전트 매핑
        relevant_agents = {
            "financial": ["financial_expert"],
            "technical": ["advanced_technical_expert"],
            "sentiment": ["sentiment_expert"],
            "esg": ["esg_expert"],
            "forecast": ["financial_expert", "advanced_technical_expert"],
            "comparison": ["comparative_expert"],
            "institutional": ["institutional_trading_expert"],
            "risk": ["financial_expert", "advanced_technical_expert"]
        }

        target_agents = relevant_agents.get(question_type, list(agent_summaries.keys()))

        relevant_analyses = []
        for agent_name in target_agents:
            if agent_name in agent_summaries:
                analysis = agent_summaries[agent_name]
                if len(analysis) > 800:
                    analysis = analysis[:800] + "..."
                relevant_analyses.append(f"**{agent_name}**: {analysis}")

        return "\n\n".join(relevant_analyses[:2])  # 최대 2개 에이전트

    def _get_recent_conversation_history(self, num_messages: int) -> str:
        """최근 대화 히스토리 가져오기"""
        if not st.session_state.chat_messages:
            return "이전 대화 없음"

        recent_messages = st.session_state.chat_messages[-num_messages*2:]  # Q&A 쌍 고려

        history_text = []
        for msg in recent_messages:
            role = "사용자" if msg["role"] == "user" else "AI"
            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
            history_text.append(f"{role}: {content}")

        return "\n".join(history_text)

    def _show_conversation_starter(self):
        """대화 시작 안내 및 예시 질문"""
        st.markdown("#### 💡 이런 질문을 해보세요:")

        example_questions = [
            "이 기업의 재무상태는 어떤가요?",
            "주가 전망은 어떻게 되나요?",
            "투자 시 주의할 점은 무엇인가요?",
            "동종업계 대비 어떤 위치인가요?",
            "최근 뉴스가 주가에 미치는 영향은?",
            "기술적 분석 관점에서 매수 시점인가요?"
        ]

        cols = st.columns(2)
        for i, question in enumerate(example_questions):
            with cols[i % 2]:
                if st.button(
                    question,
                    key=f"example_q_{i}",
                    use_container_width=True,
                    help="클릭하면 자동으로 질문이 입력됩니다"
                ):
                    # 예시 질문을 채팅에 추가하고 답변 생성
                    st.session_state.chat_messages.append({
                        "role": "user",
                        "content": question,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    st.rerun()

    def clear_conversation_history(self):
        """대화 히스토리 초기화"""
        if st.button("🗑️ 대화 내역 초기화", help="모든 대화 내역을 삭제합니다"):
            st.session_state.chat_messages = []
            st.session_state.conversation_started = False
            st.success("대화 내역이 초기화되었습니다.")
            st.rerun()

    def get_conversation_stats(self) -> Dict[str, Any]:
        """대화 통계 정보 반환"""
        if not st.session_state.chat_messages:
            return {
                "total_messages": 0,
                "user_questions": 0,
                "ai_responses": 0,
                "conversation_started": False
            }

        user_questions = len([msg for msg in st.session_state.chat_messages if msg["role"] == "user"])
        ai_responses = len([msg for msg in st.session_state.chat_messages if msg["role"] == "assistant"])

        return {
            "total_messages": len(st.session_state.chat_messages),
            "user_questions": user_questions,
            "ai_responses": ai_responses,
            "conversation_started": st.session_state.get("conversation_started", False)
        }

# 🔧 전역 대화형 매니저 인스턴스 (싱글톤)
_conversation_manager = None

def get_conversation_manager():
    """전역 대화형 매니저 인스턴스 (싱글톤)"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = StreamlitConversationManager()
    return _conversation_manager