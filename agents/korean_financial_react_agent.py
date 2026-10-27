import logging
import os
import re
import tempfile
from typing import Any

# matplotlib backend는 pyplot import 전에 set해야 적용된다.
# isort가 import 순서를 재배열하지 않도록 별도 블록으로 묶는다.
import matplotlib

matplotlib.use("Agg")

# 한국 주식 데이터 라이브러리
import FinanceDataReader as fdr  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pykrx.stock as stock  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from config.llm_factory import build_llm  # noqa: E402
from core.agent_status import has_payload  # noqa: E402
from core.signals import AgentSignal  # noqa: E402
from data.bok_api_client import get_macro_economic_indicators  # noqa: E402
from data.dart_api_client import get_comprehensive_company_data  # noqa: E402
from data.external_schemas import (  # noqa: E402
    PYKRX_MARKET_CAP_COLUMNS,
    assert_pykrx_columns,
    validate_pykrx_fundamental,
)
from data.sector_analysis_client import analyze_sector_relative_performance  # noqa: E402
from utils.agent_helpers import create_fallback_message, format_error_message_korean  # noqa: E402
from utils.helpers import convert_numpy_types  # noqa: E402
from utils.redaction import redact  # noqa: E402
from utils.time import kst_days_ago_compact, kst_isoformat, kst_yesterday_compact  # noqa: E402

logger = logging.getLogger(__name__)


@tool
def get_korean_stock_data(stock_code: str) -> dict[str, Any]:
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
                    float(df["SMA_20"].iloc[-1]) if not pd.isna(df["SMA_20"].iloc[-1]) else current_price
                ),
                "sma_60": (
                    float(df["SMA_60"].iloc[-1]) if not pd.isna(df["SMA_60"].iloc[-1]) else current_price
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
            "last_updated": kst_isoformat(),
        }

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Error fetching Korean stock data: {str(e)}")
        return {"error": str(e)}


LISTING_MARKETS = ("KOSPI", "KOSDAQ", "KONEX")


def _lookup_listing(stock_code: str) -> dict[str, str]:
    """종목명과 상장 시장. `get_market_ticker_list()`의 기본값은 KOSPI뿐이라 시장별로 찾는다."""
    for market in LISTING_MARKETS:
        if stock_code in stock.get_market_ticker_list(market=market):
            return {"name": stock.get_market_ticker_name(stock_code), "market": market}
    return {}


def _latest_market_cap(fromdate: str, todate: str, stock_code: str) -> tuple[int | None, str | None]:
    """기간 중 마지막 거래일 시가총액(원)과, 없으면 그 사유.

    stock.get_market_fundamental()은 BPS/PER/PBR/EPS/DIV/DPS만 주고 시가총액 컬럼이 없어 따로 받는다.
    """
    try:
        cap_df = stock.get_market_cap(fromdate, todate, stock_code)
        if cap_df is None or cap_df.empty:
            return None, f"{fromdate}~{todate} PyKRX 시가총액 응답이 비어 있음"
        assert_pykrx_columns(
            list(cap_df.columns), expected=PYKRX_MARKET_CAP_COLUMNS, source="pykrx/get_market_cap"
        )
        if "시가총액" not in cap_df.columns:
            return None, f"PyKRX 시가총액 컬럼 없음 (받은 컬럼: {', '.join(map(str, cap_df.columns))})"
        value = cap_df["시가총액"].iloc[-1]
    except Exception as e:
        logger.warning(f"PyKRX market cap failed: {str(e)}")
        return None, f"PyKRX 시가총액 조회 실패: {redact(str(e))}"
    if pd.isna(value) or value <= 0:
        return None, f"{fromdate}~{todate} PyKRX 시가총액이 0 또는 비어 있음"
    return int(value), None


@tool
def get_pykrx_market_data(stock_code: str) -> dict[str, Any]:
    """PyKRX로 한국 주식 시장 데이터 및 기본 지표 수집"""
    try:
        logger.info(f"Fetching PyKRX market data for {stock_code}")

        # 거래일 인자는 한국 시장 기준이어야 한다 (utils.time.KST 참고).
        # UTC 컨테이너에서 `datetime.now()`를 쓰면 KOSPI 마감 직후 시간대에
        # 어제 날짜가 그제로 밀려 PyKRX가 휴장 응답을 돌려준다.
        yesterday = kst_yesterday_compact()

        # 종목 기본 정보
        ticker_info: dict[str, str] = {}
        try:
            ticker_info = _lookup_listing(stock_code)

            # 시가총액 및 기본 지표 (KST 기준 -7일 ~ 어제)
            week_ago = kst_days_ago_compact(7)
            fundamental_data = stock.get_market_fundamental(week_ago, yesterday, stock_code)

            market_cap, market_cap_reason = _latest_market_cap(week_ago, yesterday, stock_code)
            fundamentals: dict[str, Any] = {
                "market_cap": market_cap,
                "per": None,
                "pbr": None,
                "eps": None,
                "bps": None,
            }
            notes: list[str] = []
            if fundamental_data.empty:
                notes.append(f"{week_ago}~{yesterday} PyKRX PER·PBR·EPS·BPS 응답이 비어 있음")
            else:
                # PyKRX 컬럼명이 바뀌면 silent break 대신 DataQualityError를 받도록 schema로 검증.
                row = fundamental_data.iloc[-1].to_dict()
                validated = validate_pykrx_fundamental(row)
                # 0/None은 PyKRX의 'no data' 약속 — 숫자로 채우지 않고 None으로 둔다.
                fundamentals["per"] = float(validated.per) if validated.per else None
                fundamentals["pbr"] = float(validated.pbr) if validated.pbr else None
                fundamentals["eps"] = int(validated.eps) if validated.eps else None
                fundamentals["bps"] = int(validated.bps) if validated.bps else None
            if market_cap_reason:
                notes.append(f"시가총액: {market_cap_reason}")
            if notes:
                # "note" is a metadata key in core/agent_status, so a reason alone never counts as data.
                fundamentals["note"] = " / ".join(notes)

            result: dict[str, Any] = {
                "company_info": ticker_info,
                "fundamental_data": fundamentals,
                "market_data": {
                    "data_source": "PyKRX",
                    "last_updated": kst_isoformat(),
                },
            }
            return convert_numpy_types(result)

        except Exception as e:
            # KRX 로그인이 없거나 장애일 때 pykrx는 빈 응답 끝에 KeyError를 낸다.
            reason = redact(format_error_message_korean(e, "PyKRX 지표 조회"))
            logger.warning(f"PyKRX detailed data failed: {reason}")
            return {
                "status": "unavailable",
                "error": reason,
                "company_info": ticker_info,
                "fundamental_data": {key: None for key in ("market_cap", "per", "pbr", "eps", "bps")},
                "market_data": {"data_source": "PyKRX", "last_updated": kst_isoformat()},
            }

    except Exception as e:
        logger.error(f"Error fetching PyKRX data: {redact(str(e))}")
        return {"error": redact(str(e))}


def _chart_dir() -> str:
    """차트 저장 위치. 캐시와 같은 루트(`TUSIM_CACHE_DIR` 또는 임시 디렉토리) 아래 charts/."""
    root = os.environ.get("TUSIM_CACHE_DIR") or tempfile.gettempdir()
    path = os.path.join(root, "charts")
    os.makedirs(path, exist_ok=True)
    return path


@tool
def save_stock_chart(stock_code: str, chart_data: dict | None = None) -> dict[str, Any]:
    """한국어 라벨링된 주가 차트를 생성해 파일로 저장하고 경로를 돌려줍니다.

    시세는 항상 FinanceDataReader에서 직접 받습니다. chart_data는 호환용 인자로 쓰지 않습니다.
    """
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

        # LLM이 넘긴 chart_data는 검증할 원천이 없어 그리지 않는다 — 원천 시세만 쓴다.
        df = fdr.DataReader(stock_code, start="2024-01-01")
        if df.empty:
            return {"error": "No data available for charting", "chart_saved": False}

        # 차트 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1])

        # 주가 차트
        ax1.plot(df.index, df["Close"], linewidth=2, label="종가", color="#1f77b4")
        ax1.fill_between(df.index, df["Close"], alpha=0.3, color="#1f77b4")

        # 이동평균선
        if len(df) > 20:
            sma20 = df["Close"].rolling(20).mean()
            ax1.plot(df.index, sma20, linewidth=1, label="20일선", color="#ff7f0e", alpha=0.8)

        if len(df) > 60:
            sma60 = df["Close"].rolling(60).mean()
            ax1.plot(df.index, sma60, linewidth=1, label="60일선", color="#2ca02c", alpha=0.8)

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

        # 작업 디렉토리(레포 루트)에 쓰지 않는다. 종목코드는 LLM 입력이라 파일명에 쓰기 전에 거른다.
        safe_code = re.sub(r"[^0-9A-Za-z]", "", stock_code)[:12] or "unknown"
        chart_path = os.path.join(_chart_dir(), f"stock_chart_{safe_code}.png")
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "chart_saved": True,
            "chart_path": chart_path,
            "chart_type": "price_volume",
            "data_points": len(df),
            "created_at": kst_isoformat(),
            "message": f"Chart saved as {chart_path} for stock {stock_code}",
        }

    except Exception as e:
        logger.error(f"Error creating chart: {str(e)}")
        return {"error": str(e), "chart_saved": False}


@tool
def get_dart_company_data(stock_code: str) -> dict[str, Any]:
    """DART API로 기업 공시 및 재무제표 데이터 수집"""
    try:
        logger.info(f"Fetching DART company data for {stock_code}")

        result = get_comprehensive_company_data(stock_code)

        if result.get("error"):
            return {"error": redact(f"DART API error: {result['error']}")}

        # 최근 사업보고서 기준. 최신 연도가 아직 공시 전이면 그 전 연도를 쓴다.
        financial_summary = {}
        financial_basis = None
        financial_statements = result.get("financial_statements", {})
        statement = next(
            (
                financial_statements[key]
                for key in ("latest_annual", "prior_annual")
                if financial_statements.get(key, {}).get("financial_data")
            ),
            None,
        )

        if statement:
            fin_data = statement["financial_data"]
            financial_basis = {
                "fiscal_year": statement.get("year"),
                "report": statement.get("report_name"),
                "statement": statement.get("fs_name"),
                "period": statement.get("period"),
            }
            data_year = (
                f"FY{statement.get('year')} {statement.get('report_name')} ({statement.get('fs_name')})"
            )
            # fnlttSinglAcnt의 표준 계정명. 자본금은 자본총계가 아니므로 대체값으로 쓰지 않는다.
            key_accounts_mapping = {
                "revenue": "매출액",
                "operating_income": "영업이익",
                "net_income": "당기순이익",
                "total_assets": "자산총계",
                "total_liabilities": "부채총계",
                "total_equity": "자본총계",
            }

            for metric, key in key_accounts_mapping.items():
                if key in fin_data:
                    financial_summary[metric] = {
                        "value": fin_data[key],
                        "source_key": key,
                        "data_year": data_year,
                    }

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
            "financial_basis": financial_basis,
            "recent_disclosures": disclosure_summary,
            "data_source": "DART OpenAPI",
            "last_updated": kst_isoformat(),
        }

    except Exception as e:
        logger.error(f"Error fetching DART company data: {str(e)}")
        return {"error": redact(str(e))}


@tool
def get_macro_economic_data() -> dict[str, Any]:
    """한국은행 API로 거시경제 지표 수집 (기준금리, 환율, GDP, CPI 등)"""
    try:
        logger.info("Fetching macro economic indicators from Bank of Korea")

        result = get_macro_economic_indicators()

        if result.get("error"):
            return {"error": redact(f"BOK API error: {result['error']}")}

        usable = {
            name: entry for name, entry in (result.get("indicators") or {}).items() if has_payload(entry)
        }
        if not usable:
            return {
                "status": "no_data",
                "error": "한국은행 ECOS 지표를 하나도 받지 못함 (키 미설정 또는 조회 실패)",
            }
        return {**result, "indicators": usable}

    except Exception as e:
        logger.error(f"Error fetching macro economic data: {str(e)}")
        return {"error": redact(str(e))}


@tool
def get_sector_analysis(stock_code: str) -> dict[str, Any]:
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

_FINANCIAL_PROMPT = (
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
    f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.FINANCIAL.value}'라고 정확히 적어주세요. "
    "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
)


# Lazy initialization: LLM/에이전트는 import 시점이 아니라 첫 호출 때 생성한다.
# 이전엔 모듈 import만으로 LLM 키 검증이 실행돼 테스트가 느려지고 import가 실패할 수 있었음.
_financial_react_agent = None


def get_financial_react_agent():
    """Lazy-singleton accessor for the financial ReAct agent."""
    global _financial_react_agent
    if _financial_react_agent is None:
        llm = build_llm(temperature=0)
        _financial_react_agent = create_react_agent(
            model=llm,
            tools=financial_tools,
            name="financial_expert",
            prompt=_FINANCIAL_PROMPT,
        )
    return _financial_react_agent


def reset_financial_react_agent() -> None:
    """캐시한 에이전트를 버린다. 다음 호출 때 현재 LLM 설정으로 다시 만든다."""
    global _financial_react_agent
    _financial_react_agent = None


def __getattr__(name):
    """모듈 레벨 lazy alias: `korean_financial_react_agent` 접근 시 lazy 빌드.

    PEP 562 module-level __getattr__.
    """
    if name == "korean_financial_react_agent":
        return get_financial_react_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 편의 함수
def get_financial_analysis_logic(stock_code: str, company_name: str = None) -> dict:
    """Korean Financial Agent 실행 로직"""
    try:
        messages = [
            HumanMessage(
                content=f"Analyze Korean stock {stock_code} ({company_name or 'Unknown Company'}). "
                f"Perform comprehensive financial analysis including data collection, "
                f"technical analysis, and chart generation."
            )
        ]

        result = get_financial_react_agent().invoke({"messages": messages})
        return {
            "agent": "korean_financial_agent",
            "messages": result["messages"],
            "analysis_complete": True,
            "timestamp": kst_isoformat(),
        }

    except Exception as e:
        error_msg = format_error_message_korean(e, "재무 상태 분석")
        logger.error(error_msg)
        return create_fallback_message(
            agent_name="Korean Financial ReAct Agent",
            company_name=company_name or "Unknown",
            stock_code=stock_code,
            reason=error_msg,
            data_source="DART API, FinanceDataReader",
        )


def analyze_korean_stock_financial(stock_code: str, company_name: str = None) -> dict:
    """Korean Financial Agent 실행 함수"""
    return get_financial_analysis_logic(stock_code, company_name)
