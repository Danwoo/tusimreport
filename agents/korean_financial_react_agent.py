import logging
import os
from typing import Dict, Any, Optional, Annotated
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import tempfile

# Korean stock data libraries
import FinanceDataReader as fdr
import pykrx.stock as stock

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import settings
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)

# ====================
# FINANCIAL DATA TOOLS
# ====================

@tool
def get_korean_stock_data(stock_code: str) -> Dict[str, Any]:
    """한국 주식 기본 데이터 수집 (FinanceDataReader)
    
    Args:
        stock_code: 한국 종목코드 (예: 005930)
    """
    try:
        logger.info(f"Fetching Korean stock data for {stock_code}")
        
        # FinanceDataReader로 기본 정보 가져오기
        df = fdr.DataReader(stock_code, start='2024-01-01')
        
        if df.empty:
            return {"error": f"No data found for stock code {stock_code}"}
        
        # 최근 데이터
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # 기본 분석
        current_price = float(latest['Close'])
        change = float(latest['Close'] - prev['Close'])
        change_percent = float((change / prev['Close']) * 100)
        
        # 거래량 분석
        avg_volume = float(df['Volume'].tail(20).mean())
        current_volume = float(latest['Volume'])
        volume_ratio = float(current_volume / avg_volume) if avg_volume > 0 else 1.0
        
        # 기술적 지표
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['SMA_60'] = df['Close'].rolling(60).mean()
        
        result = {
            "stock_info": {
                "code": stock_code,
                "current_price": current_price,
                "change": change,
                "change_percent": change_percent,
                "volume": current_volume,
                "volume_ratio": volume_ratio
            },
            "technical_indicators": {
                "sma_20": float(df['SMA_20'].iloc[-1]) if not pd.isna(df['SMA_20'].iloc[-1]) else current_price,
                "sma_60": float(df['SMA_60'].iloc[-1]) if not pd.isna(df['SMA_60'].iloc[-1]) else current_price,
                "price_vs_sma20": (current_price / df['SMA_20'].iloc[-1] - 1) * 100 if not pd.isna(df['SMA_20'].iloc[-1]) else 0,
                "price_vs_sma60": (current_price / df['SMA_60'].iloc[-1] - 1) * 100 if not pd.isna(df['SMA_60'].iloc[-1]) else 0
            },
            "data_points": len(df),
            "last_updated": datetime.now().isoformat()
        }
        
        return convert_numpy_types(result)
        
    except Exception as e:
        logger.error(f"Error fetching Korean stock data: {str(e)}")
        return {"error": str(e)}

@tool 
def get_pykrx_market_data(stock_code: str) -> Dict[str, Any]:
    """PyKRX를 이용한 한국 주식 시장 데이터 수집
    
    Args:
        stock_code: 한국 종목코드 (예: 005930)
    """
    try:
        logger.info(f"Fetching PyKRX market data for {stock_code}")
        
        # 오늘과 어제 날짜
        today = datetime.now().strftime('%Y%m%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        
        # 종목 기본 정보
        try:
            # 종목명 조회
            ticker_list = stock.get_market_ticker_list()
            ticker_info = {}
            for ticker in ticker_list:
                if ticker == stock_code:
                    ticker_info = {
                        "name": stock.get_market_ticker_name(ticker),
                        "market": "KOSPI" if ticker in stock.get_market_ticker_list(market="KOSPI") else "KOSDAQ"
                    }
                    break
            
            # 시가총액 및 기본 지표
            fundamental_data = stock.get_market_fundamental(yesterday, yesterday, stock_code)
            
            result = {
                "company_info": ticker_info,
                "fundamental_data": {},
                "market_data": {
                    "data_source": "PyKRX",
                    "last_updated": datetime.now().isoformat()
                }
            }
            
            if not fundamental_data.empty:
                latest_fundamental = fundamental_data.iloc[-1]
                result["fundamental_data"] = {
                    "market_cap": int(latest_fundamental.get('시가총액', 0)),
                    "per": float(latest_fundamental.get('PER', 0)) if latest_fundamental.get('PER', 0) != 0 else None,
                    "pbr": float(latest_fundamental.get('PBR', 0)) if latest_fundamental.get('PBR', 0) != 0 else None,
                    "eps": int(latest_fundamental.get('EPS', 0)),
                    "bps": int(latest_fundamental.get('BPS', 0))
                }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.warning(f"PyKRX detailed data failed: {str(e)}")
            return {
                "company_info": {"name": "Unknown", "market": "Unknown"},
                "fundamental_data": {},
                "market_data": {"data_source": "PyKRX", "error": str(e)},
                "last_updated": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error fetching PyKRX data: {str(e)}")
        return {"error": str(e)}

@tool
def save_stock_chart(stock_code: str, chart_data: Optional[dict] = None) -> Dict[str, Any]:
    """한국 주식 차트를 생성하고 저장
    
    Args:
        stock_code: 한국 종목코드
        chart_data: 차트 생성용 데이터 (선택적)
    """
    try:
        logger.info(f"Creating chart for {stock_code}")
        
        # 한국어 폰트 설정
        font_candidates = ['Malgun Gothic', 'AppleGothic', 'Noto Sans CJK KR', 'DejaVu Sans']
        available_fonts = [f.name for f in font_manager.fontManager.ttflist]
        
        for font_name in font_candidates:
            if font_name in available_fonts:
                plt.rcParams['font.family'] = font_name
                plt.rcParams['font.size'] = 9
                plt.rcParams['axes.unicode_minus'] = False
                break
        
        # 데이터 가져오기 (chart_data가 없으면 직접 조회)
        if not chart_data:
            df = fdr.DataReader(stock_code, start='2024-01-01')
            if df.empty:
                return {"error": "No data available for charting"}
        
        # 차트 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1])
        
        # 주가 차트
        ax1.plot(df.index, df['Close'], linewidth=2, label='종가', color='#1f77b4')
        ax1.fill_between(df.index, df['Close'], alpha=0.3, color='#1f77b4')
        
        # 이동평균선
        if len(df) > 20:
            sma20 = df['Close'].rolling(20).mean()
            ax1.plot(df.index, sma20, linewidth=1, label='20일선', color='#ff7f0e', alpha=0.8)
        
        if len(df) > 60:
            sma60 = df['Close'].rolling(60).mean() 
            ax1.plot(df.index, sma60, linewidth=1, label='60일선', color='#2ca02c', alpha=0.8)
        
        ax1.set_title(f'{stock_code} 주가 차트', fontsize=14, pad=20)
        ax1.set_ylabel('주가 (원)', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 거래량 차트
        ax2.bar(df.index, df['Volume'], alpha=0.7, color='#d62728')
        ax2.set_title('거래량', fontsize=12)
        ax2.set_ylabel('거래량', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        # 날짜 포맷팅
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        # 임시 파일로 저장
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'_{stock_code}_chart.png')
        plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
        plt.close()
        
        return {
            "chart_saved": True,
            "chart_path": temp_file.name,
            "chart_type": "price_volume",
            "data_points": len(df),
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating chart: {str(e)}")
        return {"error": str(e), "chart_saved": False}

# ====================
# REACT AGENT SETUP
# ====================

# Tools list
financial_tools = [
    get_korean_stock_data,
    get_pykrx_market_data,
    save_stock_chart
]

# LLM setup
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=settings.openai_api_key
)

# ReAct Agent 생성
korean_financial_react_agent = create_react_agent(
    model=llm,
    tools=financial_tools,
    state_modifier=(
        "You are a Korean Financial Analysis Agent specializing in Korean stock market data.\n\n"
        "CAPABILITIES:\n"
        "- Collect Korean stock data using FinanceDataReader and PyKRX\n"
        "- Analyze technical indicators and market fundamentals\n" 
        "- Generate and save Korean stock price charts\n\n"
        "INSTRUCTIONS:\n"
        "- Always use the provided tools to gather data\n"
        "- Focus on Korean stock market (KRX, KOSPI, KOSDAQ)\n"
        "- Provide comprehensive financial analysis\n"
        "- Create visual charts when possible\n"
        "- Use Korean stock code format (6 digits like 005930)\n"
        "- Report findings in a structured manner\n\n"
        "WORKFLOW:\n"
        "1. Get basic stock data with get_korean_stock_data\n"
        "2. Get market fundamentals with get_pykrx_market_data  \n"
        "3. Create chart with save_stock_chart\n"
        "4. Analyze and summarize findings\n\n"
        "Always conclude with 'FINANCIAL_ANALYSIS_COMPLETE' when done."
    )
)

# 편의 함수
def analyze_korean_stock_financial(stock_code: str, company_name: str = None) -> dict:
    """Korean Financial Agent 실행 함수"""
    try:
        messages = [
            HumanMessage(content=f"Analyze Korean stock {stock_code} ({company_name or 'Unknown Company'}). "
                                f"Perform comprehensive financial analysis including data collection, "
                                f"technical analysis, and chart generation.")
        ]
        
        result = korean_financial_react_agent.invoke({"messages": messages})
        return {
            "agent": "korean_financial_agent",
            "messages": result["messages"],
            "analysis_complete": True,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in Korean Financial Agent: {str(e)}")
        return {
            "agent": "korean_financial_agent", 
            "error": str(e),
            "analysis_complete": False,
            "timestamp": datetime.now().isoformat()
        }