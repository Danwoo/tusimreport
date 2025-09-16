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

            # 시가총액 및 기본 지표 (날짜 범위로 조회)
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
            fundamental_data = stock.get_market_fundamental(
                week_ago, yesterday, stock_code
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

        # 주요 재무 지표 추출 (current_year 오류시 previous_year 사용)
        financial_summary = {}
        financial_statements = result.get("financial_statements", {})

        # current_year부터 시도, 없으면 previous_year 사용
        fin_data = None
        data_year = "정보없음"

        if financial_statements.get("current_year", {}).get("financial_data"):
            fin_data = financial_statements["current_year"]["financial_data"]
            data_year = "당기"
        elif financial_statements.get("previous_year", {}).get("financial_data"):
            fin_data = financial_statements["previous_year"]["financial_data"]
            data_year = "전기"

        if fin_data:
            # 실제 DART API 응답 구조에 맞춘 키워드 (수입, 수익 등 포함)
            key_accounts_mapping = {
                # 매출액 관련 (실제 DART에서 '수입'으로 나오는 경우가 많음)
                "revenue": ["수입", "매출", "매출액", "수익", "Sales", "Revenue"],
                "operating_income": ["영업이익", "Operating Income"],
                "net_income": ["당기순이익", "순이익", "Net Income"],
                "total_assets": ["자산총계", "Total Assets"],
                "total_liabilities": ["부채총계", "Total Liabilities"],
                "total_equity": ["자본총계", "자본금", "Total Equity"]
            }

            # 각 지표별로 실제 존재하는 키를 찾아 매핑
            for metric, possible_keys in key_accounts_mapping.items():
                for key in possible_keys:
                    if key in fin_data and fin_data[key] != 0:
                        financial_summary[metric] = {
                            "value": fin_data[key],
                            "source_key": key,
                            "data_year": data_year
                        }
                        break  # 첫 번째로 찾은 유효한 값 사용

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
    name="financial_expert",
    prompt=(
        "당신은 기업의 재무 상태를 분석하는 재무 분석 전문가입니다. "
        "투자자들이 쉽게 이해할 수 있도록 회사의 재무 건전성과 성과를 분석해주세요.\n\n"

        "다음 도구들을 사용해서 종합적인 데이터를 수집한 후, 자연스럽고 이해하기 쉽게 설명해주세요:\n"
        "1. get_korean_stock_data - 기본 주식 데이터 수집\n"
        "2. get_pykrx_market_data - 시장 데이터 수집\n"
        "3. get_dart_company_data - 공식 재무제표 데이터\n"
        "4. get_macro_economic_data - 경제 환경 파악\n"
        "5. get_sector_analysis - 동종업계 비교\n"
        "6. save_stock_chart - 주가 차트 생성\n\n"

        "분석할 때는 다음과 같이 친근하게 설명해주세요:\n\n"

        "1. 이 회사가 어떤 사업을 하는 회사인지 간단히 소개해주세요\n"
        "   - 주요 사업 영역과 어떻게 돈을 버는지\n"
        "   - 회사 규모와 시장에서의 위치\n\n"

        "2. 회사의 성장세는 어떤지 알려주세요\n"
        "   - 매출이나 이익이 늘고 있는지, 줄고 있는지\n"
        "   - 최근 몇 년간의 추세를 쉽게 설명해주세요\n"
        "   - 같은 업종 다른 회사들과 비교했을 때는 어떤지\n\n"

        "3. 회사의 재무 건전성은 어떤지 평가해주세요\n"
        "   - 빚이 너무 많지는 않은지\n"
        "   - 현금 보유 상황은 어떤지\n"
        "   - 앞으로도 안정적으로 사업을 이어갈 수 있을지\n\n"

        "4. 투자자 관점에서 이 회사의 매력도를 설명해주세요\n"
        "   - 주가가 기업 가치 대비 적정한지\n"
        "   - 배당은 얼마나 주는지\n"
        "   - 투자할 때 어떤 점들을 고려해야 하는지\n\n"

        "5. 주의해서 봐야 할 위험 요소가 있다면 알려주세요\n"
        "   - 재무적으로 취약한 부분이 있는지\n"
        "   - 앞으로 어떤 변화를 주의 깊게 봐야 하는지\n\n"

        "전문 용어를 사용할 때는 간단한 설명을 함께 해주시고, "
        "숫자를 제시할 때는 그것이 좋은 건지 나쁜 건지, 평균적인 수준인지 함께 설명해주세요. "
        "마치 친구가 투자 조언을 해주듯이 따뜻하고 이해하기 쉬운 톤으로 작성해주세요.\n\n"

        "참고: 이 분석은 재무 참고자료이며 투자 추천이 아닙니다. 객관적인 정보 제공을 목적으로 합니다.\n\n"
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'FINANCIAL_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
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
