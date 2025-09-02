import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import tempfile

# matplotlib backend 설정 (GUI 경고 방지)
import matplotlib

matplotlib.use("Agg")

# 한국 주식 데이터 라이브러리
import FinanceDataReader as fdr
import pykrx.stock as stock

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from utils.helpers import convert_numpy_types
from data.dart_api_client import get_comprehensive_company_data
from data.bok_api_client import get_macro_economic_indicators
from data.sector_analysis_client import analyze_sector_relative_performance

logger = logging.getLogger(__name__)


@tool
def get_korean_stock_data(stock_code: str) -> Dict[str, Any]:
    """FinanceDataReader로 한국 주식 기본 데이터 수집"""
    try:
        logger.info(f"Fetching Korean stock data for {stock_code}")

        # FinanceDataReader로 기본 정보 가져오기
        df = fdr.DataReader(stock_code, start="2024-01-01")

        if df.empty:
            return {"error": f"No data found for stock code {stock_code}"}

        # 최근 데이터
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # 기본 분석
        current_price = float(latest["Close"])
        change = float(latest["Close"] - prev["Close"])
        change_percent = float((change / prev["Close"]) * 100)

        # 거래량 분석
        avg_volume = float(df["Volume"].tail(20).mean())
        current_volume = float(latest["Volume"])
        volume_ratio = float(current_volume / avg_volume) if avg_volume > 0 else 1.0

        # 기술적 지표
        df["SMA_20"] = df["Close"].rolling(20).mean()
        df["SMA_60"] = df["Close"].rolling(60).mean()

        result = {
            "stock_info": {
                "code": stock_code,
                "current_price": current_price,
                "change": change,
                "change_percent": change_percent,
                "volume": current_volume,
                "volume_ratio": volume_ratio,
            },
            "technical_indicators": {
                "sma_20": (
                    float(df["SMA_20"].iloc[-1])
                    if not pd.isna(df["SMA_20"].iloc[-1])
                    else current_price
                ),
                "sma_60": (
                    float(df["SMA_60"].iloc[-1])
                    if not pd.isna(df["SMA_60"].iloc[-1])
                    else current_price
                ),
                "price_vs_sma20": (
                    (current_price / df["SMA_20"].iloc[-1] - 1) * 100
                    if not pd.isna(df["SMA_20"].iloc[-1])
                    else 0
                ),
                "price_vs_sma60": (
                    (current_price / df["SMA_60"].iloc[-1] - 1) * 100
                    if not pd.isna(df["SMA_60"].iloc[-1])
                    else 0
                ),
            },
            "data_points": len(df),
            "last_updated": datetime.now().isoformat(),
        }

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Error fetching Korean stock data: {str(e)}")
        return {"error": str(e)}


@tool
def get_pykrx_market_data(stock_code: str) -> Dict[str, Any]:
    """PyKRX로 한국 주식 시장 데이터 및 기본 지표 수집"""
    try:
        logger.info(f"Fetching PyKRX market data for {stock_code}")

        # 오늘과 어제 날짜
        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        # 종목 기본 정보
        try:
            # 종목명 조회
            ticker_list = stock.get_market_ticker_list()
            ticker_info = {}
            for ticker in ticker_list:
                if ticker == stock_code:
                    ticker_info = {
                        "name": stock.get_market_ticker_name(ticker),
                        "market": (
                            "KOSPI"
                            if ticker in stock.get_market_ticker_list(market="KOSPI")
                            else "KOSDAQ"
                        ),
                    }
                    break

            # 시가총액 및 기본 지표
            fundamental_data = stock.get_market_fundamental(
                yesterday, yesterday, stock_code
            )

            result = {
                "company_info": ticker_info,
                "fundamental_data": {},
                "market_data": {
                    "data_source": "PyKRX",
                    "last_updated": datetime.now().isoformat(),
                },
            }

            if not fundamental_data.empty:
                latest_fundamental = fundamental_data.iloc[-1]
                result["fundamental_data"] = {
                    "market_cap": int(latest_fundamental.get("시가총액", 0)),
                    "per": (
                        float(latest_fundamental.get("PER", 0))
                        if latest_fundamental.get("PER", 0) != 0
                        else None
                    ),
                    "pbr": (
                        float(latest_fundamental.get("PBR", 0))
                        if latest_fundamental.get("PBR", 0) != 0
                        else None
                    ),
                    "eps": int(latest_fundamental.get("EPS", 0)),
                    "bps": int(latest_fundamental.get("BPS", 0)),
                }

            return convert_numpy_types(result)

        except Exception as e:
            logger.warning(f"PyKRX detailed data failed: {str(e)}")
            return {
                "company_info": {"name": "Unknown", "market": "Unknown"},
                "fundamental_data": {},
                "market_data": {"data_source": "PyKRX", "error": str(e)},
                "last_updated": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error(f"Error fetching PyKRX data: {str(e)}")
        return {"error": str(e)}


@tool
def save_stock_chart(
    stock_code: str, chart_data: Optional[dict] = None
) -> Dict[str, Any]:
    """한국어 라벨링된 주가 차트 생성 및 저장"""
    try:
        logger.info(f"Creating chart for {stock_code}")

        # 한국어 폰트 설정
        font_candidates = [
            "Malgun Gothic",
            "AppleGothic",
            "Noto Sans CJK KR",
            "DejaVu Sans",
        ]
        available_fonts = [f.name for f in font_manager.fontManager.ttflist]

        for font_name in font_candidates:
            if font_name in available_fonts:
                plt.rcParams["font.family"] = font_name
                plt.rcParams["font.size"] = 9
                plt.rcParams["axes.unicode_minus"] = False
                break

        # 데이터 가져오기 (chart_data가 없으면 직접 조회)
        if not chart_data:
            df = fdr.DataReader(stock_code, start="2024-01-01")
            if df.empty:
                return {"error": "No data available for charting"}

        # 차트 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1])

        # 주가 차트
        ax1.plot(df.index, df["Close"], linewidth=2, label="종가", color="#1f77b4")
        ax1.fill_between(df.index, df["Close"], alpha=0.3, color="#1f77b4")

        # 이동평균선
        if len(df) > 20:
            sma20 = df["Close"].rolling(20).mean()
            ax1.plot(
                df.index, sma20, linewidth=1, label="20일선", color="#ff7f0e", alpha=0.8
            )

        if len(df) > 60:
            sma60 = df["Close"].rolling(60).mean()
            ax1.plot(
                df.index, sma60, linewidth=1, label="60일선", color="#2ca02c", alpha=0.8
            )

        ax1.set_title(f"{stock_code} 주가 차트", fontsize=14, pad=20)
        ax1.set_ylabel("주가 (원)", fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 거래량 차트
        ax2.bar(df.index, df["Volume"], alpha=0.7, color="#d62728")
        ax2.set_title("거래량", fontsize=12)
        ax2.set_ylabel("거래량", fontsize=10)
        ax2.grid(True, alpha=0.3)

        # 날짜 포맷팅
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()

        # Streamlit에서 접근 가능한 고정 파일명으로 저장
        chart_filename = "korean_stock_chart.png"
        plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
        plt.close()

        return {
            "chart_saved": True,
            "chart_path": chart_filename,
            "chart_type": "price_volume",
            "data_points": len(df),
            "created_at": datetime.now().isoformat(),
            "message": f"Chart saved as {chart_filename} for stock {stock_code}"
        }

    except Exception as e:
        logger.error(f"Error creating chart: {str(e)}")
        return {"error": str(e), "chart_saved": False}


@tool
def get_dart_company_data(stock_code: str) -> Dict[str, Any]:
    """DART API로 기업 공시 및 재무제표 데이터 수집"""
    try:
        logger.info(f"Fetching DART company data for {stock_code}")

        result = get_comprehensive_company_data(stock_code)

        if result.get("error"):
            return {"error": f"DART API error: {result['error']}"}

        # 주요 재무 지표 추출
        financial_summary = {}

        if (
            result.get("financial_statements", {})
            .get("current_year", {})
            .get("financial_data")
        ):
            fin_data = result["financial_statements"]["current_year"]["financial_data"]

            # 주요 계정 추출 (계정명은 실제 DART API 응답에 따라 조정 필요)
            key_accounts = [
                "매출액",
                "영업이익",
                "당기순이익",
                "자산총계",
                "부채총계",
                "자본총계",
                "Sales",
                "Operating Income",
                "Net Income",
                "Total Assets",
                "Total Liabilities",
                "Total Equity",
            ]

            for account in key_accounts:
                if account in fin_data:
                    financial_summary[account] = fin_data[account]

        # 공시 요약
        disclosure_summary = []
        if result.get("recent_disclosures"):
            for disclosure in result["recent_disclosures"][:5]:  # 최근 5개만
                disclosure_summary.append(
                    {
                        "report_name": disclosure.get("report_nm"),
                        "receipt_date": disclosure.get("rcept_dt"),
                        "remarks": disclosure.get("rm", ""),
                    }
                )

        return {
            "company_name": result.get("company_info", {}).get("corp_name"),
            "ceo_name": result.get("company_info", {}).get("ceo_nm"),
            "industry_code": result.get("company_info", {}).get("induty_code"),
            "establishment_date": result.get("company_info", {}).get("est_dt"),
            "financial_summary": financial_summary,
            "recent_disclosures": disclosure_summary,
            "data_source": "DART OpenAPI",
            "last_updated": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error fetching DART company data: {str(e)}")
        return {"error": str(e)}


@tool
def get_macro_economic_data() -> Dict[str, Any]:
    """한국은행 API로 거시경제 지표 수집 (기준금리, 환율, GDP, CPI 등)"""
    try:
        logger.info("Fetching macro economic indicators from Bank of Korea")

        result = get_macro_economic_indicators()

        if result.get("error"):
            return {"error": f"BOK API error: {result['error']}"}

        return result

    except Exception as e:
        logger.error(f"Error fetching macro economic data: {str(e)}")
        return {"error": str(e)}


@tool
def get_sector_analysis(stock_code: str) -> Dict[str, Any]:
    """업종별 상대 평가 및 동종업계 비교 분석"""
    try:
        logger.info(f"Analyzing sector relative performance for {stock_code}")

        result = analyze_sector_relative_performance(stock_code)

        if result.get("error"):
            return {"error": f"Sector analysis error: {result['error']}"}

        return result

    except Exception as e:
        logger.error(f"Error in sector analysis: {str(e)}")
        return {"error": str(e)}


# 금융 분석 도구 목록
financial_tools = [
    get_korean_stock_data,
    get_pykrx_market_data,
    save_stock_chart,
    get_dart_company_data,
    get_macro_economic_data,
    get_sector_analysis,
]

# LLM 설정 (Gemini 또는 OpenAI)
provider, model_name, api_key = get_llm_model()

if provider == "gemini":
    llm = ChatGoogleGenerativeAI(
        model=model_name, temperature=0, google_api_key=api_key
    )
else:
    llm = ChatOpenAI(model=model_name, temperature=0, api_key=api_key)

# 한국 금융 분석 ReAct Agent 생성
korean_financial_react_agent = create_react_agent(
    model=llm,
    tools=financial_tools,
    prompt=(
        "You are a Korean Financial Analysis Agent specializing in Korean stock market data.\n\n"
        "CAPABILITIES:\n"
        "- Korean stock data (FinanceDataReader, PyKRX)\n"
        "- Technical indicators and market fundamentals\n"
        "- Korean stock price charts with Korean labels\n"
        "- DART company disclosure and financial statements\n"
        "- Bank of Korea macro economic indicators\n"
        "- Sector analysis and peer comparison\n"
        "- Comprehensive financial analysis combining multiple data sources\n\n"
        "WORKFLOW:\n"
        "1. get_korean_stock_data - Basic stock information\n"
        "2. get_pykrx_market_data - Market fundamentals\n"
        "3. get_dart_company_data - Official company data\n"
        "4. get_macro_economic_data - Economic context\n"
        "5. get_sector_analysis - Industry comparison\n"
        "6. save_stock_chart - Visual chart creation\n"
        "7. Comprehensive analysis and insights\n\n"
        "Always conclude with 'FINANCIAL_ANALYSIS_COMPLETE' when done."
    ),
)


# 편의 함수
def analyze_korean_stock_financial(stock_code: str, company_name: str = None) -> dict:
    """Korean Financial Agent 실행 함수"""
    try:
        messages = [
            HumanMessage(
                content=f"Analyze Korean stock {stock_code} ({company_name or 'Unknown Company'}). "
                f"Perform comprehensive financial analysis including data collection, "
                f"technical analysis, and chart generation."
            )
        ]

        result = korean_financial_react_agent.invoke({"messages": messages})
        return {
            "agent": "korean_financial_agent",
            "messages": result["messages"],
            "analysis_complete": True,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error in Korean Financial Agent: {str(e)}")
        return {
            "agent": "korean_financial_agent",
            "error": str(e),
            "analysis_complete": False,
            "timestamp": datetime.now().isoformat(),
        }
