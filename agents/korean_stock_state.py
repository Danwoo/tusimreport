"""
Korean Stock Analysis State - LangGraph State 정의
"""
from typing import TypedDict, Annotated, Literal, Optional
from operator import add
from langchain_core.messages import BaseMessage

class KoreanStockState(TypedDict):
    """한국 주식 분석을 위한 LangGraph State"""
    
    # Core input
    stock_code: str  # 종목코드 (005930 등)
    company_name: Optional[str]  # 회사명
    
    # Messages for LLM communication
    messages: Annotated[list[BaseMessage], add]
    
    # Analysis results from each agent
    financial_data: Optional[dict]
    sentiment_data: Optional[dict] 
    report_data: Optional[dict]
    
    # Supervisor routing
    next: Literal["financial_agent", "sentiment_agent", "report_agent", "__end__"]
    
    # Progress tracking
    current_stage: str
    progress: float
    
    # Error handling
    error: Optional[str]
    
    # Metadata
    analysis_timestamp: Optional[str]
    data_sources: Optional[list[str]]