import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd

# matplotlib import 제거됨 (Plotly 차트로 대체)

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

        # FinanceDataReader로 기본 정보 가져오기 (최근 90일)
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        df = fdr.DataReader(stock_code, start=start_date)

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


# save_stock_chart 함수 제거됨 (Plotly 인터랙티브 차트로 대체)
# main.py의 create_interactive_chart() 사용


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
    # save_stock_chart,  # 제거됨 (Plotly 인터랙티브 차트로 대체)
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
        "당신은 증권사의 재무 분석 애널리스트입니다. 중급 투자자를 대상으로 기업의 재무 상태와 투자 가치를 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 기업 개요(사업 구조, 시가총액, 최근 실적 트렌드), "
        "2) 재무 건전성(ROE, ROA, 부채비율 등 핵심 지표와 업종 평균 대비 평가), "
        "3) 밸류에이션(PER, PBR 지표와 저평가/적정/고평가 판단), "
        "4) 투자 매력도(성장성, 배당, 안정성 측면 종합 평가).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## 재무 및 투자 가치 분석\n\n"

        "### 기업 개요 및 재무 현황\n"
        "[사업 구조, 시가총액, 최근 실적을 전년/전분기 대비 성장률과 함께 3개 문단으로 서술. 500-600자]\n\n"

        "### 재무 건전성 및 수익성 평가\n"
        "[ROE, ROA, 부채비율 등 핵심 지표를 업종 평균과 비교하여 3개 문단으로 서술. 500-600자]\n\n"

        "### 밸류에이션 및 투자 의견\n"
        "[PER, PBR 평가와 투자 매력도를 성장성/배당/안정성 측면에서 2-3개 문단으로 서술. 400-500자]\n\n"

        "### 참고 데이터\n"
        "- DART API: [재무제표 기준일]\n"
        "- PyKRX: [시장 데이터 기준일]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 500-600자 목표)\n"
        "- 문단 중심 서술 (핵심 수치는 괄호 내 표기 예: ROE 15.2%, PER 12.3배)\n"
        "- 구체적 수치 필수 포함 (매출, 영업이익률, PER, PBR, ROE 등)\n"
        "- 전문 용어 사용시 간단한 설명 병기 (예: ROE 15.2% - 업종 평균 12% 대비 우수)\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- 투자 의견은 근거와 함께 명확히 제시 (저평가/적정/고평가)\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'FINANCIAL_ANALYSIS_COMPLETE'를 반드시 포함하세요."
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
