#!/usr/bin/env python3
"""
Korean Stock Analysis Supervisor - LangGraph 기반
8개 전문가 에이전트를 통합하는 Supervisor 워크플로우
"""

import logging
from datetime import datetime
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph_supervisor import create_supervisor
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model

# Import existing agents from agents folder
from agents.korean_context_agent import create_context_agent
from agents.korean_sentiment_agent import create_sentiment_agent
from agents.korean_financial_react_agent import korean_financial_react_agent
from agents.korean_advanced_technical_agent import create_advanced_technical_agent
from agents.korean_institutional_trading_agent import create_institutional_trading_agent
from agents.korean_comparative_agent import create_comparative_agent
from agents.korean_esg_analysis_agent import create_esg_agent
from agents.korean_community_agent import create_community_agent

logger = logging.getLogger(__name__)

# ====================
# LLM 설정
# ====================

def get_supervisor_llm():
    """Supervisor용 LLM 설정"""
    provider, model_name, api_key = get_llm_model()
    if provider == "gemini":
        return ChatGoogleGenerativeAI(model=model_name, temperature=0.1, google_api_key=api_key)
    else:
        return ChatOpenAI(model=model_name, temperature=0.1, api_key=api_key)

# ====================
# 전문 에이전트 생성 (총 8개)
# ====================

def create_all_agents():
    """모든 8개의 전문 분석 에이전트를 생성합니다."""
    try:
        agents = {
            "context_expert": create_context_agent(),
            "sentiment_expert": create_sentiment_agent(),
            "financial_expert": korean_financial_react_agent,  # 이미 생성된 인스턴스
            "advanced_technical_expert": create_advanced_technical_agent(),
            "institutional_trading_expert": create_institutional_trading_agent(),
            "comparative_expert": create_comparative_agent(),
            "esg_expert": create_esg_agent(),
            "community_expert": create_community_agent(),
        }

        # 에이전트 생성 완료
        return agents

    except Exception as e:
        logger.error(f"Error creating agents: {str(e)}")
        raise e

# ====================
# 종합 보고서 생성 함수
# ====================

def generate_comprehensive_report(supervisor_llm, all_analyses: Dict[str, str], stock_code: str, company_name: str) -> str:
    """Supervisor가 직접 생성하는 종합 투자 참고자료"""
    try:
        # 모든 전문가 분석 내용을 하나의 문자열로 결합
        expert_analyses_text = ""
        for expert_key, analysis in all_analyses.items():
            expert_name = {
                "context_expert": "시장·경제 전문가",
                "sentiment_expert": "뉴스·여론 전문가",
                "financial_expert": "재무·공시 전문가",
                "advanced_technical_expert": "기술적 분석 전문가",
                "institutional_trading_expert": "수급 분석 전문가",
                "comparative_expert": "상대 가치 전문가",
                "esg_expert": "ESG 분석 전문가",
                "community_expert": "커뮤니티 여론 전문가"
            }.get(expert_key, expert_key)

            expert_analyses_text += f"\n\n=== {expert_name} 분석 ===\n{analysis}\n"

        # 🔍 전문가 분석 데이터 품질 확인
        total_analysis_length = sum(len(str(analysis)) for analysis in all_analyses.values())
        logger.info(f"🔍 전문가 분석 총 길이: {total_analysis_length:,}자")
        logger.info(f"🔍 참여 전문가 수: {len(all_analyses)}/8")

        # 🚨 데이터 부족 시 조기 반환
        if len(all_analyses) < 4:
            logger.warning(f"⚠️ 전문가 분석 부족: {len(all_analyses)}/8")
            return f"## 분석 데이터 부족\n\n{len(all_analyses)}/8개 전문가 분석만 완료되어 종합 보고서 생성이 제한됩니다."

        if total_analysis_length < 1000:
            logger.warning(f"⚠️ 분석 내용 부족: {total_analysis_length}자")
            return f"## 분석 내용 부족\n\n전문가 분석 내용이 {total_analysis_length}자로 부족하여 종합 보고서 생성이 어렵습니다."

        report_prompt = f"""
🎯 당신은 **대한민국 최고 증권사의 Chief Investment Research Director**로서, {len(all_analyses)}개 전문가의 심층 분석을 바탕으로 기관투자자급 투자 리서치 보고서를 작성해야 합니다.

📊 **분석 대상**: {stock_code} ({company_name})
📈 **전문가 분석 총량**: {total_analysis_length:,}자

🔍 **전문가 팀 분석 결과:**
{expert_analyses_text}

🏆 **증권사 Chief Analyst 급 보고서 작성 가이드:**

**📚 스타일 가이드:**
- **투자 스토리텔링**: 단순 나열이 아닌 설득력 있는 투자 내러티브 구성
- **차별화된 관점**: 시장 컨센서스를 뛰어넘는 독창적 인사이트 제시
- **실용적 가치**: 실제 투자 결정에 도움되는 구체적이고 실행 가능한 가이드
- **자연스러운 흐름**: 딱딱한 보고서가 아닌 읽기 편한 대화체로 작성
- **핵심 메시지 우선**: 가장 중요한 투자 포인트를 명확히 부각

**🎯 필수 작성 요구사항:**
- **길이**: 최소 5,000자 이상의 심층 분석
- **구조**: 투자 스토리 중심의 자연스러운 흐름
- **통찰력**: 7개 전문가 의견을 종합한 독창적 관점
- **실용성**: 구체적 수치와 실행 가능한 투자 가이드
- **가독성**: 핵심 메시지가 명확히 전달되는 구성

# 📈 투자 리서치 보고서 - 증권사 Chief Analyst 스타일

## 🎯 Executive Summary (투자 의견 요약)
**[핵심 투자 논리를 3-4줄로 명확하게 제시]**

## 📊 Investment Thesis (투자 스토리)

### 🔥 핵심 투자 포인트 TOP 3
**1. [첫 번째 핵심 강점]**: [구체적 근거와 임팩트]
**2. [두 번째 핵심 강점]**: [구체적 근거와 임팩트]
**3. [세 번째 핵심 강점]**: [구체적 근거와 임팩트]

### 💡 숨겨진 투자 기회 (Hidden Gems)
**[시장이 놓치고 있는 독특한 관점이나 기회]**

## 🏢 기업 심층 분석

### 재무 건전성 & 성장성
**[재무 전문가 분석을 바탕으로 한 핵심 인사이트]**

### 경쟁력 & 시장 포지션
**[상대가치 및 업계 분석 기반 차별화 요소]**

## 📈 시장 환경 & 타이밍

### 거시경제 환경 영향
**[거시경제 요인이 해당 기업에 미치는 구체적 영향]**

### 기술적 분석 & 진입 타이밍
**[차트 분석 기반 최적 진입 시점 가이드]**

### 수급 동향 & 시장 심리
**[기관 수급 및 시장 센티멘트 종합 평가]**

## ⚖️ 리스크 & 기회 분석

### 🚨 주요 리스크 요인
**[구체적 리스크와 대응 방안]**

### 🎯 업사이드 시나리오
**[긍정적 시나리오와 확률]**

## 🎪 ESG & 지속가능성 관점
**[ESG 요소가 기업 가치에 미치는 영향]**

## 🔮 향후 전망 & 모니터링 포인트

### 단기 전망 (3-6개월)
**[단기 주가 변동 요인과 전망]**

### 중장기 전망 (1-2년)
**[중장기 성장 드라이버와 목표가]**

### 📊 핵심 모니터링 지표
**[추적해야 할 핵심 지표들]**

## 💰 밸류에이션 & 투자 가이드

### 적정 주가 밴드
**[현재 주가 대비 적정 가치 평가]**

### 포트폴리오 관점
**[포트폴리오 내 적정 비중과 투자 전략]**

---

## ⚠️ Investment Disclaimer

본 리서치 보고서는 공개된 정보와 7개 전문가 분석을 바탕으로 작성된 투자 참고자료입니다.

**주요 유의사항:**
- 투자 권유나 특정 매매 추천이 아님
- 투자 결정은 본인의 판단과 책임 하에 수행
- 시장 상황 변화에 따른 전망 수정 가능
- 과거 성과가 미래 수익을 보장하지 않음

**Report Completion Signal**: SUPERVISOR_REPORT_GENERATION_COMPLETE
"""

        # 🤖 Supervisor LLM으로 종합 보고서 생성
        response = supervisor_llm.invoke(report_prompt)
        report_content = response.content if hasattr(response, 'content') else str(response)

        # 🔍 생성된 보고서 품질 검증
        logger.info("🎯 Supervisor가 종합 보고서 생성 완료")
        logger.info(f"📊 보고서 길이: {len(report_content):,}자")

        # 🚨 품질 검증 - 증권사 급 보고서 기준
        if len(report_content) < 3000:
            logger.warning(f"⚠️ 생성된 보고서가 너무 짧습니다: {len(report_content)}자 (목표: 5,000자+)")
            logger.warning(f"⚠️ 프롬프트 길이: {len(report_prompt):,}자")
            logger.warning(f"⚠️ 전문가 분석 데이터: {total_analysis_length:,}자")
        elif len(report_content) < 5000:
            logger.info(f"📊 중급 보고서 생성: {len(report_content):,}자 (목표: 5,000자+)")
        else:
            logger.info(f"🏆 증권사 급 고품질 보고서 생성 완료: {len(report_content):,}자")

        return report_content

    except Exception as e:
        logger.error(f"종합 보고서 생성 오류: {str(e)}")
        return f"## 종합 보고서 생성 오류\n\n보고서 생성 중 오류가 발생했습니다: {str(e)}"

# ====================
# SUPERVISOR 생성
# ====================

def create_korean_supervisor():
    """7개 전문가 에이전트 + Supervisor 종합 보고서 생성 워크플로우"""
    try:
        logger.info("Creating Korean Stock Analysis Supervisor with 7 expert agents.")
        supervisor_llm = get_supervisor_llm()
        all_agents = create_all_agents()

        supervisor_prompt = (
            """🎯 MISSION: You are the Chief Investment Research Director.

## 📋 EXECUTION SEQUENCE (7 EXPERT AGENTS):
1️⃣ context_expert → "MARKET_CONTEXT_ANALYSIS_COMPLETE"
2️⃣ sentiment_expert → "SENTIMENT_ANALYSIS_COMPLETE"
3️⃣ financial_expert → "FINANCIAL_ANALYSIS_COMPLETE"
4️⃣ advanced_technical_expert → "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE"
5️⃣ institutional_trading_expert → "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE"
6️⃣ comparative_expert → "COMPARATIVE_ANALYSIS_COMPLETE"
7️⃣ esg_expert → "ESG_ANALYSIS_COMPLETE"

## 🎯 NEW ARCHITECTURE:
- Execute 7 specialized expert agents sequentially
- Collect all expert analyses
- Supervisor will generate final comprehensive report
- NO separate report_expert agent needed

## ✅ SUCCESS CRITERIA:
- All 8 expert completion signals received
- Expert analyses collected and ready for final report
- System ready for supervisor report generation

Execute all 8 expert agents and signal completion."""
        )

        # 8개 전문가 에이전트만 확인 및 로깅
        logger.info(f"Available agents: {list(all_agents.keys())}")
        if len(all_agents) != 8:
            logger.error(f"Expected 8 agents, but got {len(all_agents)}: {list(all_agents.keys())}")
            raise ValueError("All 8 expert agents must be created")

        workflow = create_supervisor(
            agents=list(all_agents.values()),
            model=supervisor_llm,
            prompt=supervisor_prompt,
        )

        logger.info("Korean Stock Analysis Supervisor with 8 expert agents created successfully.")
        return workflow.compile()

    except Exception as e:
        logger.error(f"Error creating Korean supervisor: {str(e)}")
        raise e

# 글로벌 Supervisor 인스턴스
korean_supervisor_graph = create_korean_supervisor()

# ====================
# 진행 상황 추적
# ====================

AGENT_STAGES = {
    "context_expert": ("시장/경제 분석", 0.14),
    "sentiment_expert": ("뉴스/여론 분석", 0.28),
    "financial_expert": ("재무 분석", 0.42),
    "advanced_technical_expert": ("기술적 분석", 0.57),
    "institutional_trading_expert": ("수급 분석", 0.71),
    "comparative_expert": ("상대 가치 분석", 0.85),
    "esg_expert": ("ESG 분석", 0.99),
    "supervisor": ("종합 보고서 생성", 1.0),
}

# ====================
# MAIN INTERFACE
# ====================

def stream_korean_stock_analysis(stock_code: str, company_name: str = None, use_progressive: bool = True):
    """개선된 LangGraph Supervisor - 7개 전문가 + Supervisor 종합 보고서

    Args:
        stock_code: 종목 코드
        company_name: 회사명 (선택)
        use_progressive: Progressive Analysis 사용 여부 (기본 True - 컨텍스트 최적화)
    """
    try:
        logger.info(f"Starting streaming supervised analysis for {stock_code} with 7 expert agents (Progressive: {use_progressive}).")

        # Progressive Analysis 사용시 새로운 엔진 사용
        if use_progressive:
            logger.info("✅ Progressive Analysis Engine 사용 - 컨텍스트 최적화 활성")
            from core.progressive_supervisor import get_progressive_engine

            progressive_engine = get_progressive_engine()

            # Progressive streaming 분석 실행
            for result in progressive_engine.stream_progressive_analysis(stock_code, company_name):
                # Progressive 결과를 기존 supervisor 형식으로 변환
                if result["type"] == "agent_complete":
                    stage_name, progress = AGENT_STAGES.get(result["agent_name"], (result["agent_name"], 0.5))
                    yield {
                        "supervisor": {
                            "stock_code": stock_code,
                            "company_name": company_name,
                            "current_stage": stage_name,
                            "progress": result["progress"],
                            "messages": [{"content": result["content"]}],
                            "executed_agents": result["completed_agents"],
                            "total_agents": result["total_agents"],
                            "progressive_mode": True
                        }
                    }
                elif result["type"] == "final_report":
                    # 최종 보고서 yield
                    yield {
                        "supervisor": {
                            "stock_code": stock_code,
                            "company_name": company_name,
                            "current_stage": "종합 보고서 생성",
                            "progress": 1.0,
                            "messages": [{"content": result["report"]}],
                            "executed_agents": result["completed_agents"],
                            "total_agents": result["total_agents"],
                            "final_report_generated": True,
                            "progressive_mode": True,
                            "context_stats": result.get("context_stats", {})
                        }
                    }
                elif result["type"] in ["agent_error", "system_error", "report_error"]:
                    yield {"error": {"error": result.get("error", "알 수 없는 오류"), "progressive_mode": True}}
                else:
                    # 진행 상황 업데이트
                    yield {
                        "supervisor": {
                            "stock_code": stock_code,
                            "company_name": company_name,
                            "current_stage": result.get("message", "분석 진행 중"),
                            "progress": result.get("progress", 0.0),
                            "messages": [],
                            "executed_agents": result.get("completed_agents", 0),
                            "total_agents": result.get("total_agents", 7),
                            "progressive_mode": True
                        }
                    }
            return

        # 기존 LangGraph 방식 (레거시 지원)
        logger.info("⚠️  레거시 LangGraph 방식 사용 - 컨텍스트 제한 위험")

        # 새로운 분석 요청 - 7개 전문가 에이전트 실행
        analysis_request = (
            f"COMPREHENSIVE STOCK ANALYSIS for {stock_code} ({company_name or 'Unknown'}): "
            f"Execute all 7 expert agents in sequence: "
            f"context_expert→sentiment_expert→financial_expert→advanced_technical_expert→"
            f"institutional_trading_expert→comparative_expert→esg_expert. "
            f"Collect all expert analyses for comprehensive final report generation."
        )

        executed_agents = set()
        all_analyses = {}  # 전문가 분석 결과 저장
        expected_agents = {
            "context_expert", "sentiment_expert", "financial_expert", "advanced_technical_expert",
            "institutional_trading_expert", "comparative_expert", "esg_expert"
        }

        chunk_count = 0
        max_chunks = 100  # 안전장치
        supervisor_llm = get_supervisor_llm()  # Supervisor LLM 인스턴스

        for chunk in korean_supervisor_graph.stream(
            {"messages": [{"role": "user", "content": analysis_request}]}
        ):
            chunk_count += 1
            logger.debug(f"Processing chunk {chunk_count}: {chunk}")

            agent_name = next(iter(chunk)) if chunk else "supervisor"
            stage_name, progress = AGENT_STAGES.get(agent_name, ("처리 중", 0.0))

            messages = []
            if agent_name in chunk and chunk[agent_name]:
                content = chunk[agent_name]
                if isinstance(content, dict):
                    messages = content.get("messages", [])

                    # 에이전트 완료 추적 및 분석 결과 저장
                    for msg in messages:
                        msg_content = msg.content if hasattr(msg, 'content') else str(msg)
                        for expected_agent in expected_agents:
                            completion_signal = {
                                "context_expert": "MARKET_CONTEXT_ANALYSIS_COMPLETE",
                                "sentiment_expert": "SENTIMENT_ANALYSIS_COMPLETE",
                                "financial_expert": "FINANCIAL_ANALYSIS_COMPLETE",
                                "advanced_technical_expert": "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
                                "institutional_trading_expert": "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
                                "comparative_expert": "COMPARATIVE_ANALYSIS_COMPLETE",
                                "esg_expert": "ESG_ANALYSIS_COMPLETE"
                            }.get(expected_agent, "")

                            if completion_signal and completion_signal in msg_content:
                                executed_agents.add(expected_agent)
                                # 분석 내용 저장 (시그널 제거)
                                analysis_content = msg_content.replace(completion_signal, "").strip()
                                if len(analysis_content) > 100:  # 의미 있는 내용만
                                    all_analyses[expected_agent] = analysis_content
                                logger.info(f"✅ Agent {expected_agent} completed. Total: {len(executed_agents)}/7")

            yield {
                "supervisor": {
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "chunk": chunk,
                    "current_stage": stage_name,
                    "progress": progress,
                    "messages": messages,
                    "executed_agents": len(executed_agents),
                    "total_agents": len(expected_agents)
                }
            }

            # 모든 7개 전문가 완료 시 Supervisor가 종합 보고서 생성
            if len(executed_agents) == len(expected_agents):
                logger.info("🎉 All 7 expert agents completed! Generating comprehensive report...")

                # Supervisor가 종합 보고서 생성
                try:
                    final_report = generate_comprehensive_report(
                        supervisor_llm, all_analyses, stock_code, company_name
                    )

                    # 최종 보고서 yield
                    yield {
                        "supervisor": {
                            "stock_code": stock_code,
                            "company_name": company_name,
                            "current_stage": "종합 보고서 생성",
                            "progress": 1.0,
                            "messages": [{"content": final_report}],
                            "executed_agents": len(executed_agents),
                            "total_agents": len(expected_agents),
                            "final_report_generated": True
                        }
                    }
                    logger.info("🎯 Supervisor comprehensive report generation completed!")
                except Exception as report_error:
                    logger.error(f"종합 보고서 생성 오류: {str(report_error)}")
                    yield {"error": {"error": f"Final report generation failed: {str(report_error)}"}}

                break

            if chunk_count >= max_chunks:
                logger.error(f"❌ Reached maximum chunks ({max_chunks}). Executed agents: {executed_agents}")
                yield {"error": {"error": f"Workflow incomplete. Only {len(executed_agents)}/7 agents completed: {executed_agents}"}}
                break

    except Exception as e:
        logger.error(f"Error in streaming analysis: {str(e)}")
        yield {"error": {"error": str(e)}}