import logging
from typing import Dict, Any
from datetime import datetime
import json

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import settings

logger = logging.getLogger(__name__)

# ====================
# REPORT GENERATION TOOLS
# ====================

@tool
def generate_executive_summary(financial_data: dict, sentiment_data: dict, stock_code: str) -> Dict[str, Any]:
    """재무 및 감정 데이터를 바탕으로 경영진 요약 보고서 생성
    
    Args:
        financial_data: 재무 분석 데이터
        sentiment_data: 감정 분석 데이터  
        stock_code: 종목코드
    """
    try:
        logger.info(f"Generating executive summary for {stock_code}")
        
        # 재무 데이터에서 핵심 지표 추출
        financial_score = 5  # 기본값
        if isinstance(financial_data, dict) and 'messages' in financial_data:
            # ReAct Agent 결과에서 데이터 추출 시도
            messages = financial_data.get('messages', [])
            latest_message = messages[-1] if messages else None
            financial_content = latest_message.content if latest_message else ""
            
            # 간단한 점수 계산 (실제로는 더 복잡한 로직)
            if "상승" in financial_content or "긍정" in financial_content:
                financial_score = 7
            elif "하락" in financial_content or "부정" in financial_content:
                financial_score = 3
        
        # 감정 데이터에서 핵심 지표 추출
        sentiment_score = 5  # 기본값
        if isinstance(sentiment_data, dict) and 'messages' in sentiment_data:
            messages = sentiment_data.get('messages', [])
            latest_message = messages[-1] if messages else None
            sentiment_content = latest_message.content if latest_message else ""
            
            # 간단한 점수 계산
            if "긍정" in sentiment_content:
                sentiment_score = 7
            elif "부정" in sentiment_content:
                sentiment_score = 3
        
        # 종합 점수 계산
        overall_score = round((financial_score * 0.6 + sentiment_score * 0.4), 1)
        
        # 투자 추천 결정
        if overall_score >= 7:
            recommendation = "매수"
            risk_level = "낮음"
        elif overall_score >= 5:
            recommendation = "보유"  
            risk_level = "보통"
        else:
            recommendation = "관망"
            risk_level = "높음"
        
        summary = {
            "stock_code": stock_code,
            "overall_score": overall_score,
            "recommendation": recommendation,
            "risk_level": risk_level,
            "key_metrics": {
                "financial_score": financial_score,
                "sentiment_score": sentiment_score
            },
            "summary_type": "executive_summary",
            "generated_at": datetime.now().isoformat()
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generating executive summary: {str(e)}")
        return {
            "stock_code": stock_code,
            "error": str(e),
            "summary_type": "executive_summary_error",
            "generated_at": datetime.now().isoformat()
        }

@tool
def generate_detailed_analysis_report(
    stock_code: str, 
    company_name: str,
    financial_data: dict,
    sentiment_data: dict
) -> Dict[str, Any]:
    """상세 분석 보고서 생성 (GPT-4 기반)
    
    Args:
        stock_code: 종목코드
        company_name: 회사명
        financial_data: 재무 분석 데이터
        sentiment_data: 감정 분석 데이터
    """
    try:
        logger.info(f"Generating detailed report for {stock_code}")
        
        # GPT-4로 상세 보고서 생성
        report_llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.3,
            api_key=settings.openai_api_key
        )
        
        # 입력 데이터 요약
        financial_summary = str(financial_data)[:1000] if financial_data else "재무 데이터 없음"
        sentiment_summary = str(sentiment_data)[:1000] if sentiment_data else "감정 데이터 없음"
        
        detailed_prompt = f"""
        당신은 한국 주식 시장 전문 애널리스트입니다.
        
        다음 데이터를 바탕으로 {company_name} ({stock_code})에 대한 상세 투자 분석 보고서를 작성해주세요:
        
        재무 분석 데이터:
        {financial_summary}
        
        감정 분석 데이터: 
        {sentiment_summary}
        
        보고서 구성:
        1. 투자 포인트 (3-5개)
        2. 위험 요인 (3-5개)  
        3. 재무 건전성 평가
        4. 시장 감정 분석
        5. 단기/중기 전망
        6. 투자 의견 및 목표가 (선택적)
        
        한국어로 전문적이고 구체적으로 작성해주세요.
        투자 조언이 아닌 분석 정보임을 명시해주세요.
        """
        
        response = report_llm.invoke([{"role": "user", "content": detailed_prompt}])
        
        detailed_report = {
            "stock_code": stock_code,
            "company_name": company_name,
            "report_content": response.content,
            "report_type": "detailed_analysis",
            "word_count": len(response.content),
            "generated_at": datetime.now().isoformat(),
            "disclaimer": "본 보고서는 투자 판단의 참고자료이며 투자 권유가 아닙니다."
        }
        
        return detailed_report
        
    except Exception as e:
        logger.error(f"Error generating detailed report: {str(e)}")
        return {
            "stock_code": stock_code,
            "error": str(e),
            "report_type": "detailed_analysis_error",
            "generated_at": datetime.now().isoformat()
        }

@tool
def generate_risk_assessment(financial_data: dict, sentiment_data: dict, stock_code: str) -> Dict[str, Any]:
    """리스크 평가 보고서 생성
    
    Args:
        financial_data: 재무 분석 데이터
        sentiment_data: 감정 분석 데이터
        stock_code: 종목코드
    """
    try:
        logger.info(f"Generating risk assessment for {stock_code}")
        
        # 기본 리스크 요인들
        risk_factors = []
        risk_level = "보통"
        
        # 재무 리스크 평가
        if isinstance(financial_data, dict):
            if 'error' in financial_data:
                risk_factors.append("재무 데이터 수집 실패")
                risk_level = "높음"
            else:
                # 재무 건전성 체크 (단순화된 로직)
                financial_content = str(financial_data).lower()
                if "하락" in financial_content or "감소" in financial_content:
                    risk_factors.append("재무 성과 악화 신호")
                if "volume" in financial_content and "낮" in financial_content:
                    risk_factors.append("거래량 부족")
        
        # 감정 리스크 평가  
        if isinstance(sentiment_data, dict):
            if 'error' in sentiment_data:
                risk_factors.append("시장 감정 분석 불가")
            else:
                sentiment_content = str(sentiment_data).lower()
                if "부정" in sentiment_content:
                    risk_factors.append("부정적 시장 감정")
                    risk_level = "높음"
                if "뉴스" in sentiment_content and ("적" in sentiment_content or "낮" in sentiment_content):
                    risk_factors.append("뉴스 노출 부족")
        
        # 일반적 시장 리스크
        risk_factors.extend([
            "한국 주식시장 변동성",
            "거시경제 환경 변화",
            "업종별 특수 리스크"
        ])
        
        # 리스크 점수 (1-10, 10이 가장 위험)
        risk_score = 7 if risk_level == "높음" else 5 if risk_level == "보통" else 3
        
        risk_assessment = {
            "stock_code": stock_code,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_factors": risk_factors[:7],  # 최대 7개
            "mitigation_strategies": [
                "분산 투자로 위험 분산",
                "정기적인 포트폴리오 리밸런싱", 
                "시장 뉴스 및 실적 모니터링",
                "적절한 손절 기준 설정"
            ],
            "assessment_type": "risk_assessment",
            "generated_at": datetime.now().isoformat()
        }
        
        return risk_assessment
        
    except Exception as e:
        logger.error(f"Error generating risk assessment: {str(e)}")
        return {
            "stock_code": stock_code,
            "error": str(e),
            "assessment_type": "risk_assessment_error", 
            "generated_at": datetime.now().isoformat()
        }

# ====================
# REACT AGENT SETUP
# ====================

# Tools list  
report_tools = [
    generate_executive_summary,
    generate_detailed_analysis_report,
    generate_risk_assessment
]

# LLM setup
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.4,
    api_key=settings.openai_api_key
)

# ReAct Agent 생성
korean_report_react_agent = create_react_agent(
    model=llm,
    tools=report_tools,
    state_modifier=(
        "You are a Korean Investment Report Agent specializing in comprehensive stock analysis reports.\n\n"
        "CAPABILITIES:\n"
        "- Generate executive summaries for investment decisions\n"
        "- Create detailed analysis reports in Korean\n"
        "- Perform risk assessments for Korean stocks\n\n"
        "INSTRUCTIONS:\n"
        "- Always use the provided tools to generate reports\n"
        "- Focus on Korean stock market context\n"
        "- Provide actionable investment insights\n"
        "- Maintain professional and objective tone\n"
        "- Include appropriate disclaimers\n\n"
        "WORKFLOW:\n"
        "1. Generate executive summary with generate_executive_summary\n"
        "2. Create detailed analysis with generate_detailed_analysis_report\n"
        "3. Perform risk assessment with generate_risk_assessment\n"
        "4. Synthesize all reports into comprehensive analysis\n\n"
        "Always conclude with 'REPORT_GENERATION_COMPLETE' when done."
    )
)

# 편의 함수
def generate_korean_stock_report(
    stock_code: str, 
    company_name: str = None,
    financial_data: dict = None,
    sentiment_data: dict = None
) -> dict:
    """Korean Report Agent 실행 함수"""
    try:
        messages = [
            HumanMessage(content=f"Generate comprehensive investment report for Korean stock {stock_code} "
                                f"({company_name or 'Unknown Company'}). "
                                f"Use the provided financial and sentiment analysis data to create: "
                                f"1) Executive summary, 2) Detailed analysis, 3) Risk assessment. "
                                f"Financial data available: {bool(financial_data)}, "
                                f"Sentiment data available: {bool(sentiment_data)}")
        ]
        
        # 데이터를 config로 전달 (ReAct Agent에서 접근 가능)
        config = {
            "configurable": {
                "financial_data": financial_data,
                "sentiment_data": sentiment_data,
                "stock_code": stock_code,
                "company_name": company_name
            }
        }
        
        result = korean_report_react_agent.invoke({"messages": messages}, config=config)
        return {
            "agent": "korean_report_agent",
            "messages": result["messages"],
            "analysis_complete": True,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in Korean Report Agent: {str(e)}")
        return {
            "agent": "korean_report_agent",
            "error": str(e),
            "analysis_complete": False,
            "timestamp": datetime.now().isoformat()
        }