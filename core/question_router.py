#!/usr/bin/env python3
"""
Question Router
사용자 질문을 분석하여 필요한 에이전트를 선택하는 라우터
"""

import logging
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import get_llm_model

logger = logging.getLogger(__name__)


class QuestionRouter:
    """
    사용자 질문을 분석하여 적절한 에이전트를 선택하는 라우터

    핵심 기능:
    1. 질문 의도 분석 (재무? 기술적? 뉴스? 종합?)
    2. 필요한 에이전트 선택 (1개 이상)
    3. 기존 분석 결과 재사용 vs 재실행 판단
    """

    # 에이전트별 전문 분야
    AGENT_EXPERTISE = {
        "context_expert": {
            "keywords": ["시장", "경제", "환경", "거시", "금리", "환율", "KOSPI", "업황", "경기"],
            "description": "시장 환경 및 거시경제 분석"
        },
        "sentiment_expert": {
            "keywords": ["뉴스", "여론", "심리", "감정", "분위기", "기사", "언론", "미디어", "최근"],
            "description": "뉴스 및 시장 심리 분석"
        },
        "financial_expert": {
            "keywords": ["재무", "매출", "영업이익", "순이익", "부채", "자산", "재무제표", "실적", "수익성", "건전성"],
            "description": "재무 상태 및 기업 실적 분석"
        },
        "advanced_technical_expert": {
            "keywords": ["차트", "기술적", "RSI", "MACD", "볼린저", "이동평균", "골든크로스", "지지", "저항"],
            "description": "기술적 차트 분석"
        },
        "institutional_trading_expert": {
            "keywords": ["기관", "외국인", "수급", "매수", "매도", "거래량", "순매수", "프로그램"],
            "description": "기관 및 외국인 수급 분석"
        },
        "comparative_expert": {
            "keywords": ["비교", "경쟁사", "동종업계", "밸류에이션", "PER", "PBR", "PSR", "상대가치"],
            "description": "동종업계 비교 및 상대가치 분석"
        },
        "esg_expert": {
            "keywords": ["ESG", "지속가능", "환경", "사회", "지배구조", "탄소", "윤리"],
            "description": "ESG 및 지속가능경영 분석"
        },
        "community_expert": {
            "keywords": ["커뮤니티", "투자자", "개인", "의견", "토론", "게시판"],
            "description": "커뮤니티 투자자 의견 분석"
        },
        "quantitative_expert": {
            "keywords": ["DCF", "밸류에이션", "적정가", "내재가치", "할인율", "현금흐름", "WACC"],
            "description": "DCF 및 Multiples 정량 분석"
        },
        "advanced_chart_expert": {
            "keywords": ["일목균형표", "피보나치", "엘리엇파동", "하모닉", "패턴", "AI패턴"],
            "description": "고급 차트 및 AI 패턴 분석"
        }
    }

    def __init__(self):
        """라우터 초기화 (LLM 기반 의사결정)"""
        llm_provider, llm_model_name, llm_api_key = get_llm_model()
        if llm_provider == "gemini":
            self.llm = ChatGoogleGenerativeAI(
                model=llm_model_name,
                temperature=0.0,
                google_api_key=llm_api_key
            )
        else:
            self.llm = ChatOpenAI(
                model=llm_model_name,
                temperature=0.0,
                api_key=llm_api_key
            )

        logger.info("QuestionRouter initialized with LLM-based decision making")

    def route_question(
        self,
        question: str,
        available_agents: List[str],
        existing_results: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        사용자 질문을 분석하여 필요한 에이전트 선택

        Args:
            question: 사용자 질문
            available_agents: 사용 가능한 에이전트 목록
            existing_results: 기존 분석 결과 (None이면 초기 분석)

        Returns:
            {
                "selected_agents": ["sentiment_expert", "financial_expert"],
                "reasoning": "사용자가 최근 뉴스와 재무 상태에 대해 질문했으므로...",
                "needs_fresh_data": True,  # 실시간 데이터 필요 여부
                "can_use_cache": False  # 기존 결과 재사용 가능 여부
            }
        """
        try:
            logger.info(f"Routing question: {question[:100]}...")

            # 초기 분석 vs 추가 질문 구분
            is_initial_analysis = existing_results is None or len(existing_results) == 0

            if is_initial_analysis:
                # 초기 분석: 모든 에이전트 실행
                return {
                    "selected_agents": available_agents,
                    "reasoning": "초기 분석이므로 모든 전문가 에이전트를 실행합니다.",
                    "needs_fresh_data": True,
                    "can_use_cache": False,
                    "question_type": "initial_analysis"
                }

            # LLM 기반 라우팅 (추가 질문)
            routing_prompt = self._create_routing_prompt(
                question, available_agents, existing_results
            )

            llm_response = self.llm.invoke(routing_prompt)
            response_text = llm_response.content.strip()

            # LLM 응답 파싱
            selected_agents = self._parse_llm_response(response_text, available_agents)

            # 빈 선택 방지: 최소 1개 에이전트 선택
            if not selected_agents:
                selected_agents = self._fallback_keyword_matching(question, available_agents)

            logger.info(f"Selected agents: {selected_agents}")

            return {
                "selected_agents": selected_agents,
                "reasoning": response_text,
                "needs_fresh_data": self._needs_fresh_data(question),
                "can_use_cache": not self._needs_fresh_data(question),
                "question_type": "follow_up_question"
            }

        except Exception as e:
            logger.error(f"Error in routing question: {str(e)}")
            # Fallback: 키워드 매칭
            return {
                "selected_agents": self._fallback_keyword_matching(question, available_agents),
                "reasoning": f"LLM 라우팅 실패로 키워드 매칭 사용: {str(e)}",
                "needs_fresh_data": True,
                "can_use_cache": False,
                "question_type": "follow_up_question"
            }

    def _create_routing_prompt(
        self,
        question: str,
        available_agents: List[str],
        existing_results: Dict[str, str]
    ) -> str:
        """라우팅을 위한 LLM 프롬프트 생성"""

        # 사용 가능한 에이전트 정보
        agent_info = []
        for agent_name in available_agents:
            expertise = self.AGENT_EXPERTISE.get(agent_name, {})
            agent_info.append(
                f"- {agent_name}: {expertise.get('description', 'N/A')}"
            )

        # 기존 분석 결과 요약
        existing_analysis_summary = []
        for agent_name, result in (existing_results or {}).items():
            summary = result[:200] + "..." if len(result) > 200 else result
            existing_analysis_summary.append(f"- {agent_name}: {summary}")

        prompt = f"""
당신은 주식 분석 AI 시스템의 질문 라우터입니다.
사용자의 질문을 분석하여 어떤 전문가 에이전트가 답변해야 하는지 선택하세요.

[사용자 질문]
{question}

[사용 가능한 전문가 에이전트]
{chr(10).join(agent_info)}

[기존 분석 결과 (참고)]
{chr(10).join(existing_analysis_summary) if existing_analysis_summary else "기존 분석 결과 없음 (초기 분석)"}

[라우팅 규칙]
1. 사용자 질문의 의도를 파악하세요
2. 답변에 필요한 에이전트를 1개 이상 선택하세요
3. 기존 분석 결과가 있으면 재사용을 고려하되, 실시간 데이터가 필요하면 재실행하세요
4. 종합적인 질문이면 여러 에이전트를 선택하세요

[출력 형식]
SELECTED_AGENTS: [agent_name1, agent_name2, ...]
REASONING: [선택 이유를 1-2문장으로 설명]

예시:
SELECTED_AGENTS: [sentiment_expert, financial_expert]
REASONING: 사용자가 최근 뉴스와 재무 실적에 대해 질문했으므로 뉴스 여론 전문가와 재무 전문가를 선택합니다.
"""

        return prompt

    def _parse_llm_response(
        self,
        response_text: str,
        available_agents: List[str]
    ) -> List[str]:
        """LLM 응답에서 선택된 에이전트 파싱"""

        selected_agents = []

        # "SELECTED_AGENTS:" 라인 찾기
        for line in response_text.split("\n"):
            if "SELECTED_AGENTS:" in line.upper():
                # [agent1, agent2, ...] 형식 파싱
                agents_part = line.split(":", 1)[1].strip()
                agents_part = agents_part.replace("[", "").replace("]", "")

                # 쉼표로 분리
                for agent_name in agents_part.split(","):
                    agent_name = agent_name.strip().strip("'").strip('"')
                    if agent_name in available_agents:
                        selected_agents.append(agent_name)

                break

        return selected_agents

    def _fallback_keyword_matching(
        self,
        question: str,
        available_agents: List[str]
    ) -> List[str]:
        """
        Fallback: 키워드 기반 에이전트 매칭

        LLM 라우팅 실패 시 사용
        """
        question_lower = question.lower()
        matched_agents = []

        for agent_name in available_agents:
            keywords = self.AGENT_EXPERTISE.get(agent_name, {}).get("keywords", [])
            for keyword in keywords:
                if keyword in question_lower:
                    matched_agents.append(agent_name)
                    break  # 한 번만 추가

        # 매칭 실패 시 모든 에이전트 선택 (안전장치)
        if not matched_agents:
            logger.warning(f"No agents matched for question: {question[:100]}")
            matched_agents = available_agents

        return matched_agents

    def _needs_fresh_data(self, question: str) -> bool:
        """
        실시간 데이터가 필요한 질문인지 판단

        "최근", "현재", "지금", "오늘" 등의 키워드 포함 시 True
        """
        time_keywords = ["최근", "현재", "지금", "오늘", "어제", "이번", "요즘", "최신"]

        question_lower = question.lower()
        for keyword in time_keywords:
            if keyword in question_lower:
                return True

        return False


# 전역 라우터 인스턴스
_router_instance = None


def get_question_router() -> QuestionRouter:
    """전역 QuestionRouter 인스턴스 반환 (싱글톤)"""
    global _router_instance
    if _router_instance is None:
        _router_instance = QuestionRouter()
    return _router_instance
