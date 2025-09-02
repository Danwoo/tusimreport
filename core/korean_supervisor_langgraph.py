import logging
from datetime import datetime
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from agents.korean_financial_react_agent import financial_tools
from agents.korean_sentiment_react_agent import sentiment_tools
from agents.korean_report_react_agent import report_tools

logger = logging.getLogger(__name__)

# ====================
# LLM 설정
# ====================

def get_supervisor_llm():
    """Supervisor용 LLM 설정"""
    provider, model_name, api_key = get_llm_model()
    
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.1,
            google_api_key=api_key
        )
    else:
        return ChatOpenAI(
            model=model_name,
            temperature=0.1,
            api_key=api_key
        )

# ====================
# 전문 에이전트 생성 
# ====================

def create_korean_financial_agent():
    """한국 재무 분석 ReAct 에이전트 생성"""
    llm = get_supervisor_llm()
    
    return create_react_agent(
        model=llm,
        tools=financial_tools,
        name="financial_expert",
        prompt=(
            "You are a Korean Financial Analysis Expert specializing in Korean stock market data.\n\n"
            "CAPABILITIES:\n"
            "- Korean stock data (FinanceDataReader, PyKRX)\n"
            "- Technical indicators and market fundamentals\n" 
            "- Korean stock price charts with Korean labels\n"
            "- DART company disclosure and financial statements\n"
            "- Bank of Korea macro economic indicators\n"
            "- Sector analysis and peer comparison\n\n"
            "MANDATORY WORKFLOW (YOU MUST COMPLETE ALL STEPS):\n"
            "1. get_korean_stock_data - Basic stock information\n"
            "2. get_pykrx_market_data - Market fundamentals\n"
            "3. save_stock_chart - REQUIRED: Create visual stock chart (MUST DO THIS)\n"
            "4. get_dart_company_data - Official company data\n"
            "5. get_macro_economic_data - Economic context\n"
            "6. get_sector_analysis - Industry comparison\n"
            "7. Comprehensive analysis and insights\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "- YOU MUST USE save_stock_chart TOOL to create visual chart - THIS IS MANDATORY\n"
            "- Perform comprehensive financial analysis using ALL available tools in order\n"
            "- Chart creation is REQUIRED for every analysis - do not skip this step\n"
            "- Provide DEEP INSIGHTS and PROFESSIONAL ANALYSIS, not just data listing\n"
            "- Connect technical indicators to market trends and future prospects\n"
            "- Include specific price targets and technical resistance/support levels\n"
            "- Explain what the data means for investors and trading strategies\n"
            "- Always conclude analysis with 'FINANCIAL_ANALYSIS_COMPLETE' when done\n"
            "- Focus on actionable insights and investment implications\n"
        )
    )

def create_korean_sentiment_agent():
    """한국 뉴스 감정 분석 ReAct 에이전트 생성"""
    llm = get_supervisor_llm()
    
    return create_react_agent(
        model=llm,
        tools=sentiment_tools,
        name="sentiment_expert", 
        prompt=(
            "You are a Korean News Sentiment Analysis Expert.\n\n"
            "CAPABILITIES:\n"
            "- Korean news collection from official APIs (Naver, HashScraper)\n"
            "- Korean language sentiment analysis\n"
            "- Market sentiment evaluation and keyword extraction\n"
            "- News impact assessment on stock prices\n\n"
            "WORKFLOW:\n"
            "1. collect_korean_news_official_sources - Gather latest news\n"
            "2. analyze_korean_sentiment - Sentiment analysis with LLM\n"
            "3. extract_market_keywords - Key themes and topics\n"
            "4. evaluate_news_impact - Market impact assessment\n\n"
            "INSTRUCTIONS:\n"
            "- Use ONLY official news APIs, NO web scraping or dummy data\n"
            "- Provide COMPREHENSIVE SENTIMENT INSIGHTS with market implications\n"
            "- Analyze how news sentiment affects stock price movements and investor behavior\n"
            "- Identify key themes, catalysts, and market drivers from news analysis\n"
            "- Connect sentiment trends to potential price impacts and trading volumes\n"
            "- Include sentiment score with confidence intervals and trend direction\n"
            "- Always conclude analysis with 'SENTIMENT_ANALYSIS_COMPLETE' when done\n"
            "- Focus on actionable sentiment-based investment insights\n"
        )
    )

def create_korean_report_agent():
    """한국 투자 보고서 생성 ReAct 에이전트 생성"""
    llm = get_supervisor_llm()
    
    return create_react_agent(
        model=llm,
        tools=report_tools,
        name="report_expert",
        prompt=(
            "You are a Korean Investment Report Generation Expert.\n\n"
            "CAPABILITIES:\n"
            "- Comprehensive investment report generation\n"
            "- Executive summary creation\n"
            "- Risk assessment and mitigation strategies\n"
            "- Investment recommendations based on data analysis\n\n"
            "WORKFLOW:\n"
            "1. generate_executive_summary - Key findings and recommendations\n"
            "2. create_detailed_analysis - In-depth analysis report\n"
            "3. assess_investment_risks - Risk evaluation\n"
            "4. provide_investment_recommendation - Final investment opinion\n\n"
            "INSTRUCTIONS:\n"
            "- Generate comprehensive investment reports in Korean with PROFESSIONAL QUALITY\n"
            "- Synthesize financial and sentiment data into actionable investment strategies\n"
            "- Provide specific BUY/HOLD/SELL recommendations with clear rationale\n"
            "- Include detailed risk-reward analysis and portfolio allocation suggestions\n"
            "- Set realistic price targets with timeframes (3M, 6M, 12M outlook)\n"
            "- Address different investor profiles (conservative, moderate, aggressive)\n"
            "- Always conclude with 'REPORT_GENERATION_COMPLETE' when done\n"
            "- Focus on creating institutional-quality investment research\n"
        )
    )

# ====================
# SUPERVISOR 생성
# ====================

def create_korean_supervisor():
    """한국 주식 분석 Supervisor 워크플로우 생성 (공식 create_supervisor 사용)"""
    try:
        logger.info("Creating Korean Stock Analysis Supervisor with official create_supervisor()")
        
        # Supervisor LLM
        supervisor_llm = get_supervisor_llm()
        
        # 전문 에이전트들 생성
        financial_agent = create_korean_financial_agent()
        sentiment_agent = create_korean_sentiment_agent()
        report_agent = create_korean_report_agent()
        
        # Supervisor 생성 (공식 create_supervisor 사용)
        workflow = create_supervisor(
            agents=[financial_agent, sentiment_agent, report_agent],
            model=supervisor_llm,
            prompt=(
                "You are a Korean Stock Analysis Supervisor managing three specialized experts.\n\n"
                "WORKFLOW SEQUENCE:\n"
                "1. FINANCIAL EXPERT (financial_expert): Collects Korean stock data, technical analysis, charts\n"
                "2. SENTIMENT EXPERT (sentiment_expert): Analyzes Korean news sentiment from official APIs\n"
                "3. REPORT EXPERT (report_expert): Generates comprehensive investment reports\n\n"
                "ROUTING RULES:\n"
                "- Start with financial_expert for basic stock data collection\n"
                "- Move to sentiment_expert after financial analysis is complete\n"
                "- Move to report_expert after both financial and sentiment analyses are complete\n"
                "- Each agent will conclude with 'ANALYSIS_COMPLETE' when finished\n\n"
                "FINAL SYNTHESIS INSTRUCTIONS:\n"
                "After all three agents complete their analysis, you MUST provide a comprehensive synthesis that:\n"
                "1. **INTEGRATES** all findings from financial, sentiment, and report analyses\n"
                "2. **IDENTIFIES KEY INSIGHTS** by connecting financial metrics with market sentiment\n"
                "3. **PROVIDES SPECIFIC INVESTMENT RECOMMENDATION** with clear reasoning\n"
                "4. **HIGHLIGHTS RISKS AND OPPORTUNITIES** based on combined analysis\n"
                "5. **GIVES CONCRETE PRICE TARGETS** and timeline expectations\n"
                "\n"
                "Your final response should be a cohesive investment thesis that demonstrates:\n"
                "- How technical indicators align with sentiment trends\n"
                "- What the news sentiment reveals about future performance\n"
                "- Specific actionable insights beyond simple data listing\n"
                "- Professional investment recommendation with confidence level\n"
                "\n"
                "Format your final synthesis in Korean with clear sections:\n"
                "🎯 **핵심 투자 포인트**\n"
                "📊 **재무-감정 분석 종합**\n"
                "⚠️ **주요 리스크 요인**\n"
                "🚀 **투자 기회 및 전략**\n"
                "💰 **목표 주가 및 투자 의견**\n"
            )
        )
        
        logger.info("Korean Stock Analysis Supervisor created successfully")
        return workflow.compile()
        
    except Exception as e:
        logger.error(f"Error creating Korean supervisor: {str(e)}")
        raise e

# 글로벌 Supervisor 인스턴스
korean_supervisor_graph = create_korean_supervisor()

# ====================
# MAIN INTERFACE
# ====================

def analyze_korean_stock_with_supervisor(stock_code: str, company_name: str = None) -> dict:
    """공식 LangGraph Supervisor Pattern으로 한국 주식 분석 실행
    
    Args:
        stock_code: 한국 종목코드 (005930 등)
        company_name: 회사명 (선택적)
    
    Returns:
        완전한 분석 결과
    """
    try:
        logger.info(f"Starting official supervised analysis for {stock_code}")
        
        # 분석 요청 메시지
        analysis_request = (
            f"Perform comprehensive Korean stock analysis for {stock_code} "
            f"({company_name or 'Company Name Unknown'}). "
            f"Execute the complete workflow: Financial Analysis → Sentiment Analysis → Investment Report. "
            f"Use all available tools and provide detailed insights in Korean."
        )
        
        # Supervisor 실행
        result = korean_supervisor_graph.invoke({
            "messages": [{
                "role": "user",
                "content": analysis_request
            }]
        })
        
        logger.info(f"Official supervised analysis completed for {stock_code}")
        return {
            "stock_code": stock_code,
            "company_name": company_name,
            "analysis_result": result,
            "analysis_timestamp": datetime.now().isoformat(),
            "supervisor_type": "official_langgraph_supervisor",
            "data_sources": ["FinanceDataReader", "PyKRX", "DART", "BOK", "Naver API", get_llm_model()[1]]
        }
        
    except Exception as e:
        logger.error(f"Error in official supervised analysis: {str(e)}")
        return {
            "stock_code": stock_code,
            "company_name": company_name,
            "error": str(e),
            "analysis_timestamp": datetime.now().isoformat(),
            "supervisor_type": "official_langgraph_supervisor_error"
        }

def stream_korean_stock_analysis(stock_code: str, company_name: str = None):
    """공식 LangGraph Supervisor Pattern 스트리밍 실행"""
    try:
        logger.info(f"Starting official streaming supervised analysis for {stock_code}")
        
        # 분석 요청 메시지
        analysis_request = (
            f"Perform comprehensive Korean stock analysis for {stock_code} "
            f"({company_name or 'Company Name Unknown'}). "
            f"Execute the complete workflow: Financial Analysis → Sentiment Analysis → Investment Report. "
            f"Use all available tools and provide detailed insights in Korean."
        )
        
        # 스트리밍 실행
        for chunk in korean_supervisor_graph.stream({
            "messages": [{
                "role": "user",
                "content": analysis_request
            }]
        }):
            # Streamlit UI를 위한 호환성 래퍼
            yield {
                "supervisor": {
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "chunk": chunk,
                    "current_stage": "supervisor_streaming",
                    "progress": 0.5,  # 스트리밍 중간 진행률
                    "messages": chunk.get("messages", []),
                    "supervisor_type": "official_langgraph_supervisor"
                }
            }
            
    except Exception as e:
        logger.error(f"Error in official streaming analysis: {str(e)}")
        yield {
            "error": {
                "stock_code": stock_code,
                "company_name": company_name,
                "error": str(e),
                "current_stage": "supervisor_streaming_error",
                "analysis_timestamp": datetime.now().isoformat(),
                "supervisor_type": "official_langgraph_supervisor_error"
            }
        }

# ====================
# 이전 버전 호환성 함수들
# ====================

# 기존 함수들을 새로운 supervisor로 리다이렉트
def create_korean_supervisor_graph():
    """이전 버전 호환성을 위한 래퍼 함수"""
    logger.warning("create_korean_supervisor_graph() is deprecated. Use create_korean_supervisor() instead.")
    return korean_supervisor_graph