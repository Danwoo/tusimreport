import logging
from typing import Literal, Dict, Any
from datetime import datetime

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage

from config.settings import settings
from agents.korean_stock_state import KoreanStockState
from agents.korean_financial_react_agent import korean_financial_react_agent, analyze_korean_stock_financial
from agents.korean_sentiment_react_agent import korean_sentiment_react_agent, analyze_korean_stock_sentiment
from agents.korean_report_react_agent import korean_report_react_agent, generate_korean_stock_report

logger = logging.getLogger(__name__)

# ====================
# SUPERVISOR NODE
# ====================

def supervisor_node(state: KoreanStockState):
    """한국 주식 분석 Supervisor Node - LLM이 다음 에이전트 결정"""
    
    try:
        # Supervisor LLM 설정
        supervisor_llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=settings.openai_api_key
        )
        
        # 현재 상태 분석
        stock_code = state.get("stock_code", "")
        company_name = state.get("company_name", "")
        financial_data = state.get("financial_data")
        sentiment_data = state.get("sentiment_data")
        report_data = state.get("report_data")
        current_stage = state.get("current_stage", "starting")
        
        # Supervisor 판단을 위한 프롬프트
        supervisor_prompt = f"""
        You are a Supervisor managing Korean stock analysis workflow.
        
        Current Analysis Status:
        - Stock Code: {stock_code}
        - Company: {company_name or 'Unknown'}
        - Current Stage: {current_stage}
        - Financial Analysis: {'COMPLETED' if financial_data else 'PENDING'}
        - Sentiment Analysis: {'COMPLETED' if sentiment_data else 'PENDING'}
        - Report Generation: {'COMPLETED' if report_data else 'PENDING'}
        
        Available Agents:
        1. financial_agent - Collects Korean stock data, technical analysis, charts
        2. sentiment_agent - Analyzes Korean news sentiment from multiple sources  
        3. report_agent - Generates comprehensive investment reports
        
        Decision Rules:
        - Start with financial_agent if no financial data
        - Move to sentiment_agent after financial analysis is complete
        - Move to report_agent after both financial and sentiment are complete
        - Use __end__ when all analyses are complete
        
        Based on current status, which agent should be called next?
        Respond with ONLY the agent name: financial_agent, sentiment_agent, report_agent, or __end__
        """
        
        # Supervisor 결정
        messages = [
            {"role": "system", "content": "You are a workflow supervisor. Respond with only the next agent name."},
            {"role": "user", "content": supervisor_prompt}
        ]
        
        response = supervisor_llm.invoke(messages)
        next_agent = response.content.strip().lower()
        
        # 유효한 에이전트인지 확인
        valid_agents = ["financial_agent", "sentiment_agent", "report_agent", "__end__"]
        if next_agent not in valid_agents:
            # 기본 로직으로 폴백
            if not financial_data:
                next_agent = "financial_agent"
            elif not sentiment_data:
                next_agent = "sentiment_agent"
            elif not report_data:
                next_agent = "report_agent"
            else:
                next_agent = END
        
        # __end__ 를 END로 변환
        if next_agent == "__end__":
            next_agent = END
        
        # 상태 업데이트
        progress_map = {
            "financial_agent": 0.33,
            "sentiment_agent": 0.66,
            "report_agent": 0.90,
            END: 1.0
        }
        
        stage_map = {
            "financial_agent": "financial_analysis",
            "sentiment_agent": "sentiment_analysis", 
            "report_agent": "report_generation",
            END: "completed"
        }
        
        # 메시지 업데이트
        supervisor_message = AIMessage(
            content=f"Supervisor: Routing to {next_agent} for {stock_code} analysis",
            name="supervisor"
        )
        
        logger.info(f"Supervisor routing {stock_code} to {next_agent}")
        
        # 상태 업데이트 및 다음 에이전트 반환
        updated_state = {
            "next": next_agent,
            "current_stage": stage_map.get(next_agent, "unknown"),
            "progress": progress_map.get(next_agent, 0.0),
            "messages": state.get("messages", []) + [supervisor_message]
        }
        
        return updated_state
        
    except Exception as e:
        logger.error(f"Error in supervisor node: {str(e)}")
        return {
            "error": str(e),
            "current_stage": "supervisor_error", 
            "next": END,
            "messages": state.get("messages", []) + [
                AIMessage(content=f"Supervisor Error: {str(e)}", name="supervisor")
            ]
        }

# ====================
# AGENT NODES
# ====================

def financial_agent_node(state: KoreanStockState):
    """Korean Financial ReAct Agent Node"""
    
    try:
        stock_code = state.get("stock_code", "")
        company_name = state.get("company_name", "")
        
        logger.info(f"Financial Agent analyzing {stock_code}")
        
        # Financial Agent 실행
        result = analyze_korean_stock_financial(stock_code, company_name)
        
        # 결과 처리
        analysis_message = AIMessage(
            content=f"Financial analysis completed for {stock_code}",
            name="financial_agent"
        )
        
        return {
            "financial_data": result,
            "current_stage": "financial_analysis_complete",
            "next": "supervisor",
            "messages": state.get("messages", []) + [analysis_message]
        }
        
    except Exception as e:
        logger.error(f"Error in financial agent node: {str(e)}")
        error_message = AIMessage(
            content=f"Financial analysis failed: {str(e)}",
            name="financial_agent"
        )
        
        return {
            "error": str(e),
            "current_stage": "financial_analysis_error",
            "next": "supervisor",
            "messages": state.get("messages", []) + [error_message]
        }

def sentiment_agent_node(state: KoreanStockState):
    """Korean Sentiment ReAct Agent Node"""
    
    try:
        stock_code = state.get("stock_code", "")
        company_name = state.get("company_name", "")
        
        logger.info(f"Sentiment Agent analyzing {stock_code}")
        
        # Sentiment Agent 실행
        result = analyze_korean_stock_sentiment(stock_code, company_name)
        
        # 결과 처리
        analysis_message = AIMessage(
            content=f"Sentiment analysis completed for {stock_code}",
            name="sentiment_agent"
        )
        
        return {
            "sentiment_data": result,
            "current_stage": "sentiment_analysis_complete",
            "next": "supervisor",
            "messages": state.get("messages", []) + [analysis_message]
        }
        
    except Exception as e:
        logger.error(f"Error in sentiment agent node: {str(e)}")
        error_message = AIMessage(
            content=f"Sentiment analysis failed: {str(e)}",
            name="sentiment_agent"
        )
        
        return {
            "error": str(e),
            "current_stage": "sentiment_analysis_error",
            "next": "supervisor",
            "messages": state.get("messages", []) + [error_message]
        }

def report_agent_node(state: KoreanStockState) -> Command[Literal["supervisor"]]:
    """Korean Report ReAct Agent Node"""
    
    try:
        stock_code = state.get("stock_code", "")
        company_name = state.get("company_name", "")
        financial_data = state.get("financial_data")
        sentiment_data = state.get("sentiment_data")
        
        logger.info(f"Report Agent generating report for {stock_code}")
        
        # Report Agent 실행
        result = generate_korean_stock_report(
            stock_code, company_name, financial_data, sentiment_data
        )
        
        # 결과 처리
        analysis_message = AIMessage(
            content=f"Investment report generated for {stock_code}",
            name="report_agent"
        )
        
        return {
            "report_data": result,
            "current_stage": "report_generation_complete",
            "next": "supervisor",
            "messages": state.get("messages", []) + [analysis_message]
        }
        
    except Exception as e:
        logger.error(f"Error in report agent node: {str(e)}")
        error_message = AIMessage(
            content=f"Report generation failed: {str(e)}",
            name="report_agent"
        )
        
        return {
            "error": str(e),
            "current_stage": "report_generation_error",
            "next": "supervisor",
            "messages": state.get("messages", []) + [error_message]
        }

# ====================
# ROUTING FUNCTION
# ====================

def supervisor_router(state: KoreanStockState):
    """차세대 에이전트를 결정하는 라우터"""
    next_agent = state.get("next")
    if next_agent == END:
        return END
    return next_agent

# ====================
# LANGGRAPH SUPERVISOR GRAPH
# ====================

def create_korean_supervisor_graph():
    """한국 주식 분석 LangGraph Supervisor Pattern 생성"""
    
    # StateGraph 생성
    builder = StateGraph(KoreanStockState)
    
    # 노드 추가
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("financial_agent", financial_agent_node) 
    builder.add_node("sentiment_agent", sentiment_agent_node)
    builder.add_node("report_agent", report_agent_node)
    
    # 엣지 정의
    builder.add_edge(START, "supervisor")  # 시작은 항상 supervisor
    
    # supervisor에서 에이전트로 가는 conditional edge
    builder.add_conditional_edges(
        "supervisor",
        supervisor_router,
        ["financial_agent", "sentiment_agent", "report_agent", END]
    )
    
    # agents에서 supervisor로 돌아가는 edge
    builder.add_edge("financial_agent", "supervisor")
    builder.add_edge("sentiment_agent", "supervisor")
    builder.add_edge("report_agent", "supervisor")
    
    # 그래프 컴파일
    graph = builder.compile()
    
    logger.info("Korean Supervisor Graph compiled successfully")
    return graph

# ====================
# MAIN INTERFACE
# ====================

# 글로벌 그래프 인스턴스
korean_supervisor_graph = create_korean_supervisor_graph()

def analyze_korean_stock_with_supervisor(stock_code: str, company_name: str = None) -> dict:
    """LangGraph Supervisor Pattern으로 한국 주식 분석 실행
    
    Args:
        stock_code: 한국 종목코드 (005930 등)
        company_name: 회사명 (선택적)
    
    Returns:
        완전한 분석 결과
    """
    try:
        logger.info(f"Starting supervised analysis for {stock_code}")
        
        # 초기 상태 설정
        initial_state = {
            "stock_code": stock_code,
            "company_name": company_name,
            "messages": [
                HumanMessage(content=f"Analyze Korean stock {stock_code} ({company_name or 'Unknown'})")
            ],
            "financial_data": None,
            "sentiment_data": None,
            "report_data": None,
            "next": "supervisor",
            "current_stage": "starting",
            "progress": 0.0,
            "error": None,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources": ["FinanceDataReader", "PyKRX", "Naver API", "Google News RSS", "GPT-4"]
        }
        
        # 그래프 실행
        final_state = korean_supervisor_graph.invoke(initial_state)
        
        logger.info(f"Supervised analysis completed for {stock_code}")
        return final_state
        
    except Exception as e:
        logger.error(f"Error in supervised analysis: {str(e)}")
        return {
            "stock_code": stock_code,
            "error": str(e),
            "current_stage": "supervisor_error",
            "analysis_timestamp": datetime.now().isoformat()
        }

def stream_korean_stock_analysis(stock_code: str, company_name: str = None):
    """LangGraph Supervisor Pattern 스트리밍 실행"""
    try:
        logger.info(f"Starting streaming supervised analysis for {stock_code}")
        
        # 초기 상태 설정
        initial_state = {
            "stock_code": stock_code,
            "company_name": company_name,
            "messages": [
                HumanMessage(content=f"Analyze Korean stock {stock_code} ({company_name or 'Unknown'})")
            ],
            "financial_data": None,
            "sentiment_data": None,
            "report_data": None,
            "next": "supervisor",
            "current_stage": "starting",
            "progress": 0.0,
            "error": None,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_sources": ["FinanceDataReader", "PyKRX", "Naver API", "Google News RSS", "GPT-4"]
        }
        
        # 스트리밍 실행
        for chunk in korean_supervisor_graph.stream(initial_state):
            yield chunk
            
    except Exception as e:
        logger.error(f"Error in streaming analysis: {str(e)}")
        yield {
            "error": {
                "stock_code": stock_code,
                "error": str(e),
                "current_stage": "streaming_error",
                "analysis_timestamp": datetime.now().isoformat()
            }
        }