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
# process_conversational_question 삭제됨 - process_conversational_question_v2로 대체
# import는 _stream_response_wrapper 내부에서 수행
from data.sqlite_client import get_db_client

logger = logging.getLogger(__name__)

class StreamlitConversationManager:
    """Streamlit 네이티브 대화형 관리자"""

    def __init__(self):
        """대화형 매니저 초기화"""
        self._initialize_session_state()
        self.llm = self._get_cached_llm()

        # v2: Supervisor가 내부적으로 agents 관리하므로 여기서는 필요 없음
        # self.agents, self.agent_keywords, self.question_patterns 모두 제거됨
        # LangGraph Supervisor가 동적으로 모든 라우팅 처리

        logger.info("StreamlitConversationManager 초기화 완료 (v2 - LangGraph Supervisor 사용)")

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

        # ✅ NEW: 예시 질문 버튼 클릭 처리용 pending question
        if "pending_question" not in st.session_state:
            st.session_state.pending_question = None

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

    def _stream_llm_response(self, prompt: str):
        """
        Generator that streams LLM response chunks for st.write_stream()

        Args:
            prompt: The prompt to send to LLM

        Yields:
            str: Content chunks from LLM (compatible with st.write_stream)
        """
        try:
            if not self.llm:
                yield "죄송합니다. AI 서비스에 일시적인 문제가 발생했습니다."
                return

            # Use LangChain's .stream() method
            for chunk in self.llm.stream(prompt):
                # Extract content from AIMessageChunk
                if hasattr(chunk, 'content') and chunk.content:
                    yield chunk.content

        except Exception as e:
            logger.error(f"LLM 스트리밍 오류: {str(e)}")
            yield f"\n\n⚠️ 스트리밍 중 오류 발생: {str(e)}"

    def _stream_response_wrapper(self, question: str):
        """
        단순화된 스트리밍 래퍼 - LangGraph Supervisor v2 사용

        하드코딩된 분류/라우팅 제거:
        - Supervisor LLM이 모든 판단 수행 (질문 분석, 에이전트 선택)
        - 대화 히스토리 자동 전달 (멀티턴 대화 지원)
        - Command 패턴 기반 동적 라우팅

        Args:
            question: User's question

        Yields:
            str: Streamed response chunks
        """
        try:
            logger.info(f"🤖 LangGraph Conversational Supervisor v2 실행: {question[:50]}...")

            # 대화 히스토리 가져오기 (멀티턴 대화 지원)
            conversation_history = st.session_state.get("chat_messages", [])

            # ✅ NEW: process_conversational_question_v2 사용
            # - 하드코딩 제거: Supervisor가 질문 분석 + 에이전트 선택
            # - 대화 히스토리 포함: 멀티턴 대화 완벽 지원
            from core.korean_supervisor_langgraph import process_conversational_question_v2

            for chunk in process_conversational_question_v2(
                question=question,
                stock_code=st.session_state.get("stock_code", ""),
                company_name=st.session_state.get("company_name", ""),
                conversation_history=conversation_history  # ✅ 대화 히스토리 전달
            ):
                yield chunk

        except Exception as e:
            logger.error(f"Conversational Supervisor v2 오류: {str(e)}")
            yield f"⚠️ 답변 생성 중 오류가 발생했습니다: {str(e)}"

    def _build_synthesis_prompt(self, question: str, reanalysis_result: str) -> str:
        """Build prompt for synthesizing agent reanalysis results"""
        return f"""
사용자 질문: {question}

전문 에이전트 분석 결과:
{reanalysis_result}

위 전문가 분석 결과를 바탕으로 사용자 질문에 명확하고 간결하게 답변해주세요.

답변 가이드라인:
- 사용자 질문에 직접적으로 답변하세요
- 핵심 데이터와 수치를 포함하세요
- 불필요한 반복은 피하세요
- 투자 참고 정보임을 명시하세요

답변:
"""

    def _build_report_prompt(self, question: str) -> str:
        """Build prompt for answering from existing report"""
        question_type = self._classify_question_type(question)
        relevant_context = self._get_relevant_context(question, question_type)
        conversation_history = self._get_recent_conversation_history(3)

        return f"""
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

    def _process_question(self, prompt: str):
        """
        공통 질문 처리 로직 - pending_question과 chat_input 통합
        멀티턴 대화 + 스트리밍 출력 지원 + DB 저장

        Args:
            prompt: 사용자 질문 (예시 버튼 또는 채팅 입력에서)
        """
        logger.info(f"질문 처리 시작: {prompt}")

        # 사용자 메시지 추가
        user_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_message = {
            "role": "user",
            "content": prompt,
            "timestamp": user_timestamp
        }
        st.session_state.chat_messages.append(user_message)

        # ✅ NEW: 사용자 메시지 DB 저장
        report_id = st.session_state.get("current_report_id")
        if report_id:
            try:
                db = get_db_client()
                db.save_conversation_message(
                    report_id=report_id,
                    role="user",
                    content=prompt,
                    timestamp=user_timestamp
                )
                logger.debug(f"사용자 메시지 DB 저장 완료: {prompt[:30]}...")
            except Exception as e:
                logger.error(f"사용자 메시지 DB 저장 실패: {str(e)}")

        # 사용자 메시지 즉시 표시
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답 생성 및 스트리밍 표시
        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                try:
                    # ✅ 스트리밍 출력 사용
                    response = st.write_stream(
                        self._stream_response_wrapper(prompt)
                    )

                    # AI 응답 세션에 저장
                    assistant_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    assistant_message = {
                        "role": "assistant",
                        "content": response,
                        "timestamp": assistant_timestamp
                    }
                    st.session_state.chat_messages.append(assistant_message)
                    st.session_state.conversation_started = True

                    # ✅ NEW: AI 응답 DB 저장
                    if report_id:
                        try:
                            db = get_db_client()
                            db.save_conversation_message(
                                report_id=report_id,
                                role="assistant",
                                content=response,
                                timestamp=assistant_timestamp
                            )
                            logger.debug(f"AI 응답 DB 저장 완료: {len(response)}자")
                        except Exception as e:
                            logger.error(f"AI 응답 DB 저장 실패: {str(e)}")

                except Exception as e:
                    logger.error(f"스트리밍 실패, fallback 모드 전환: {str(e)}")
                    # Fallback: 스트리밍 실패 시 기존 방식 사용
                    try:
                        response = self._generate_contextual_response(prompt)
                        st.markdown(response)
                        fallback_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        assistant_message = {
                            "role": "assistant",
                            "content": response,
                            "timestamp": fallback_timestamp
                        }
                        st.session_state.chat_messages.append(assistant_message)
                        st.session_state.conversation_started = True

                        # ✅ NEW: Fallback 응답도 DB 저장
                        if report_id:
                            try:
                                db = get_db_client()
                                db.save_conversation_message(
                                    report_id=report_id,
                                    role="assistant",
                                    content=response,
                                    timestamp=fallback_timestamp
                                )
                                logger.debug(f"Fallback AI 응답 DB 저장 완료")
                            except Exception as db_error:
                                logger.error(f"Fallback AI 응답 DB 저장 실패: {str(db_error)}")
                    except Exception as fallback_error:
                        error_msg = f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(fallback_error)}"
                        st.error(error_msg)
                        error_message = {
                            "role": "assistant",
                            "content": error_msg,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.chat_messages.append(error_message)

    def _handle_user_input(self):
        """사용자 입력 처리 - ✅ Multi-turn conversation + Streaming support"""

        # 1️⃣ Handle pending_question from example button clicks
        # Process first to ensure it's displayed before new input
        pending = st.session_state.get("pending_question")
        if pending:
            st.session_state.pending_question = None  # Clear immediately to prevent re-processing
            self._process_question(pending)

        # 2️⃣ ALWAYS render chat_input (critical for multi-turn!)
        # This ensures the input box is visible after every AI response
        # NO early return - this must execute on every rerun
        if prompt := st.chat_input(
            "분석 보고서에 대해 궁금한 점을 물어보세요...",
            key="conversation_chat_input"
        ):
            self._process_question(prompt)

    def _generate_contextual_response(self, question: str) -> str:
        """✅ Enhanced: 기존 보고서 OR 에이전트 재호출 자동 선택"""
        try:
            # 1️⃣ 재분석이 필요한지 판단
            needs_reanalysis = self._check_if_reanalysis_needed(question)

            if needs_reanalysis:
                # 2️⃣ 어떤 에이전트를 호출할지 식별
                target_agent = self._identify_target_agent(question)

                if target_agent:
                    # 3️⃣ 특정 에이전트 재호출
                    st.info(f"🔄 최신 데이터를 확인하고 있습니다... ({target_agent})")
                    reanalysis_result = self._invoke_specific_agent(
                        target_agent,
                        question,
                        st.session_state.get("stock_code", ""),
                        st.session_state.get("company_name", "")
                    )

                    # 4️⃣ LLM으로 답변 합성
                    return self._synthesize_response(question, reanalysis_result)

            # 5️⃣ 기존 보고서에서 답변
            return self._answer_from_existing_report(question)

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

    # ✅ NEW: 에이전트 재호출 지원 메서드

    # ⚠️ DELETED: 하드코딩 기반 분류 함수들 제거
    # - _classify_question_complexity() 삭제 (하드코딩 복잡도 분류)
    # - _check_if_reanalysis_needed() 삭제 (하드코딩 키워드 매칭)
    # - _identify_target_agent() 삭제 (하드코딩 에이전트 선택)
    # → LangGraph Supervisor가 동적으로 판단합니다

    def _invoke_specific_agent(
        self,
        agent_name: str,
        user_question: str,
        stock_code: str,
        company_name: str
    ) -> str:
        """특정 에이전트를 재호출하여 최신 분석 수행"""
        try:
            agent = self.agents.get(agent_name)
            if not agent:
                logger.error(f"에이전트를 찾을 수 없음: {agent_name}")
                return f"❌ 에이전트 {agent_name}을 찾을 수 없습니다."

            # 에이전트에게 전달할 재분석 요청 구성
            reanalysis_request = f"""
사용자 질문: {user_question}
종목: {stock_code} ({company_name})

위 사용자 질문에 답하기 위해 필요한 최신 데이터를 수집하고 간결하게 분석해주세요.
기존 전체 보고서가 아닌, 이 질문에 초점을 맞춘 답변을 제공해주세요.
"""

            logger.info(f"🚀 에이전트 {agent_name} 재호출 시작")

            # 에이전트 실행 (ReAct 패턴)
            result = agent.invoke({
                "messages": [{"role": "user", "content": reanalysis_request}]
            })

            # 결과 추출
            if 'messages' in result and result['messages']:
                last_message = result['messages'][-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)
                logger.info(f"✅ 에이전트 {agent_name} 실행 완료: {len(content)}자")
                return content

            return "❌ 에이전트 응답을 받지 못했습니다."

        except Exception as e:
            logger.error(f"에이전트 재실행 오류: {str(e)}")
            return f"재분석 중 오류가 발생했습니다: {str(e)}"

    def _synthesize_response(self, question: str, reanalysis_result: str) -> str:
        """재분석 결과를 사용자 친화적으로 합성"""
        try:
            synthesis_prompt = f"""
사용자 질문: {question}

전문 에이전트 분석 결과:
{reanalysis_result}

위 전문가 분석 결과를 바탕으로 사용자 질문에 명확하고 간결하게 답변해주세요.

답변 가이드라인:
- 사용자 질문에 직접적으로 답변하세요
- 핵심 데이터와 수치를 포함하세요
- 불필요한 반복은 피하세요
- 투자 참고 정보임을 명시하세요

답변:
"""

            if self.llm:
                response = self.llm.invoke(synthesis_prompt)
                return response.content if hasattr(response, 'content') else str(response)
            else:
                # LLM이 없으면 원본 결과 그대로 반환
                return reanalysis_result

        except Exception as e:
            logger.error(f"응답 합성 오류: {str(e)}")
            return reanalysis_result  # 실패 시 원본 반환

    def _answer_from_existing_report(self, question: str) -> str:
        """기존 보고서 기반 응답 생성 (기존 로직)"""
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
            logger.error(f"기존 보고서 답변 생성 오류: {str(e)}")
            return f"응답 생성 중 오류가 발생했습니다: {str(e)}"

    def _show_conversation_starter(self):
        """대화 시작 안내 및 예시 질문 - ✅ Callback 패턴 사용"""
        st.markdown("#### 💡 이런 질문을 해보세요:")

        example_questions = [
            "이 기업의 재무상태는 어떤가요?",
            "주가 전망은 어떻게 되나요?",
            "투자 시 주의할 점은 무엇인가요?",
            "동종업계 대비 어떤 위치인가요?",
            "최근 뉴스가 주가에 미치는 영향은?",
            "기술적 분석 관점에서 매수 시점인가요?"
        ]

        # ✅ Callback 함수: 버튼 클릭 시 pending_question 설정
        def set_pending_question(question: str):
            st.session_state.pending_question = question
            logger.info(f"예시 질문 선택됨: {question}")

        cols = st.columns(2)
        for i, question in enumerate(example_questions):
            with cols[i % 2]:
                st.button(
                    question,
                    key=f"example_q_{i}",
                    use_container_width=True,
                    help="클릭하면 자동으로 질문이 입력됩니다",
                    on_click=set_pending_question,  # ✅ Callback 사용 (st.rerun() 제거)
                    args=(question,)  # ✅ 질문을 인자로 전달
                )

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