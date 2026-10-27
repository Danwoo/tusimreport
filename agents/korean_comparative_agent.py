#!/usr/bin/env python3
"""
Korean Comparative Analysis Agent
업종 내 경쟁사 및 전체 시장과 비교하여 기업의 상대적 위치를 분석합니다.
"""

import logging
import math
from typing import Any

import pandas as pd
import pykrx.stock as stock
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from core.signals import AgentSignal
from utils.agent_helpers import create_fallback_message, format_error_message_korean
from utils.helpers import convert_numpy_types
from utils.time import kst_today_compact

logger = logging.getLogger(__name__)


# 업종 매핑 (KRX 업종 분류). 같은 업종끼리 경쟁사로 묶는다.
INDUSTRY_MAPPING = {
    "005380": "자동차 및 트레일러",  # 현대차
    "000660": "전자부품, 컴퓨터, 영상, 음향 및 통신장비",  # SK하이닉스
    "005930": "전자부품, 컴퓨터, 영상, 음향 및 통신장비",  # 삼성전자
    "035420": "출판, 영상, 방송통신 및 정보서비스업",  # 네이버
    "207940": "의료용 물질 및 의약품",  # 삼성바이오로직스
    "006400": "전기장비",  # 삼성SDI
    "051910": "화학물질 및 화학제품",  # LG화학
    "028260": "건설업",  # 삼성물산
    "012330": "자동차 및 트레일러",  # 현대모비스
    "096770": "화학물질 및 화학제품",  # SK이노베이션
    "068270": "의료용 물질 및 의약품",  # 셀트리온
    "373220": "전기장비",  # LG에너지솔루션
    "000270": "자동차 및 트레일러",  # 기아
    "024110": "금융업",  # 기업은행
}

METRICS = ("PER", "PBR", "EPS", "BPS")


def _latest_business_day() -> str:
    """가장 최근 KRX 영업일 (YYYYMMDD). 휴장일·장 시작 전이면 직전 영업일.

    PyKRX의 전종목 조회는 휴장일에 빈/0 결과를 준다. 조회에 실패하면 오늘(KST)로 둔다.
    """
    today = kst_today_compact()
    try:
        day = stock.get_nearest_business_day_in_a_week(today, prev=True)
        if day:
            return str(day)
    except Exception as e:
        logger.warning(f"최근 영업일 조회 실패, 오늘 날짜 사용: {e}")
    return today


def _metric(value: Any) -> float | None:
    """PyKRX는 값이 없으면 0(또는 NaN)을 준다 — 0을 실제 값으로 쓰지 않는다."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number == 0:
        return None
    return number


def _peer_average(peer_group: pd.DataFrame, column: str) -> float | None:
    values = [v for v in (_metric(x) for x in peer_group[column]) if v is not None]
    return sum(values) / len(values) if values else None


def _sector_analysis(
    df_info: pd.DataFrame,
    stock_code: str,
    sector: str | None,
    peer_codes: list[str],
    trading_day: str,
    empty_reason: str | None = None,
) -> dict[str, Any]:
    if df_info.empty:
        return {"available": False, "reason": empty_reason or f"{trading_day} PyKRX 전종목 지표가 비어 있음"}
    missing = [m for m in METRICS if m not in df_info.columns]
    if missing:
        return {"available": False, "reason": f"PyKRX 지표 컬럼 없음: {', '.join(missing)}"}
    # 휴장일 날짜로 조회하면 KRX는 빈 표가 아니라 전 종목이 0인 표를 준다.
    if all(_metric(value) is None for value in df_info[list(METRICS)].to_numpy().ravel()):
        return {
            "available": False,
            "reason": f"{trading_day} PyKRX 전종목 지표가 모두 0 (휴장일이거나 그날 지표가 집계되지 않음)",
        }
    if stock_code not in df_info.index:
        return {"available": False, "reason": f"{trading_day} PyKRX 지표에 {stock_code} 없음"}
    if not sector:
        return {"available": False, "reason": "업종 매핑에 없는 종목 (경쟁사 비교 불가)"}

    target_metrics = {m: _metric(df_info.loc[stock_code, m]) for m in METRICS}
    if all(value is None for value in target_metrics.values()):
        return {
            "available": False,
            "sector_name": sector,
            "reason": f"{trading_day} PyKRX 지표에서 {stock_code}의 {'·'.join(METRICS)}가 모두 0 또는 비어 있음",
        }

    peer_group = df_info[df_info.index.isin(peer_codes + [stock_code])]
    if len(peer_group) <= 1:
        return {"available": False, "sector_name": sector, "reason": "같은 업종 경쟁사 지표 없음"}

    return {
        "available": True,
        "sector_name": sector,
        "peer_count": len(peer_group),
        "target_metrics": target_metrics,
        "peer_averages": {m: _peer_average(peer_group, m) for m in METRICS},
    }


def _competitive_advantages(sector_analysis: dict[str, Any]) -> list[str]:
    target = sector_analysis["target_metrics"]
    peers = sector_analysis["peer_averages"]

    def both(metric: str) -> bool:
        return target[metric] is not None and peers[metric] is not None

    advantages = []
    if both("PER") and target["PER"] < peers["PER"]:
        advantages.append("PER이 업종 평균보다 낮아 상대적으로 저평가")
    if both("PBR") and target["PBR"] < peers["PBR"]:
        advantages.append("PBR이 업종 평균보다 낮아 자산 대비 저평가")
    if both("EPS") and target["EPS"] > peers["EPS"]:
        advantages.append("EPS가 업종 평균보다 높아 수익성 우수")
    return advantages


def _market_position(stock_code: str, trading_day: str) -> dict[str, Any]:
    """시가총액 순위. FinanceDataReader → PyKRX 순으로 시도하고, 둘 다 없으면 unavailable."""
    import FinanceDataReader as fdr

    target_cap = None
    rank = None
    total_stocks = None
    try:
        market_data = fdr.StockListing("KRX")
        if "Marcap" in market_data.columns:
            valid_stocks = (
                market_data[market_data["Marcap"] > 0]
                .sort_values("Marcap", ascending=False)
                .reset_index(drop=True)
            )
            target_rank_df = valid_stocks[valid_stocks["Code"] == stock_code]
            if not target_rank_df.empty:
                target_cap = target_rank_df.iloc[0]["Marcap"]
                rank = int(target_rank_df.index[0]) + 1
                total_stocks = len(valid_stocks)
    except Exception as e:
        logger.warning(f"FinanceDataReader 시가총액 조회 실패: {e}")

    if rank is None:
        try:
            market_cap_df = stock.get_market_cap(trading_day)
            if stock_code in market_cap_df.index and "시가총액" in market_cap_df.columns:
                ranked = market_cap_df[market_cap_df["시가총액"] > 0].sort_values(
                    by="시가총액", ascending=False
                )
                if stock_code in ranked.index:
                    target_cap = ranked.loc[stock_code, "시가총액"]
                    rank = list(ranked.index).index(stock_code) + 1
                    total_stocks = len(ranked)
        except Exception as e:
            logger.warning(f"PyKRX 시가총액 조회 실패: {e}")

    if rank is None or not total_stocks or target_cap is None:
        return {"available": False, "reason": "FinanceDataReader·PyKRX 모두에서 시가총액 순위를 받지 못함"}

    if rank <= 10:
        cap_category = "대형주 (Top 10)"
    elif rank <= 50:
        cap_category = "대형주 (Top 50)"
    elif rank <= 200:
        cap_category = "중형주"
    else:
        cap_category = "소형주"

    return {
        "available": True,
        "rank": rank,
        "total_stocks": total_stocks,
        "market_cap": float(target_cap),
        "category": cap_category,
        "top_percent": round(rank / total_stocks * 100, 2),
    }


def get_comparative_analysis_logic(stock_code: str, company_name: str) -> dict[str, Any]:
    """업종 내 경쟁사 비교 및 전체 시장 내 순위 분석을 통합적으로 수행하는 로직"""
    try:
        logger.info(f"Performing comprehensive comparative analysis for {stock_code}")
        trading_day = _latest_business_day()

        analysis_result: dict[str, Any] = {}
        insights: list[str] = []

        sector = INDUSTRY_MAPPING.get(stock_code)
        peer_codes = [
            code
            for code, industry in INDUSTRY_MAPPING.items()
            if sector and industry == sector and code != stock_code
        ]

        # 1. 업종 비교 분석 — KOSPI·KOSDAQ 전종목.
        # PyKRX는 KRX가 빈 응답을 주면(휴장일·로그인 없음) 내부에서 KeyError를 낸다.
        fundamental_error = None
        try:
            df_info = stock.get_market_fundamental(trading_day, market="ALL")
        except Exception as e:
            fundamental_error = format_error_message_korean(e, f"{trading_day} PyKRX 지표 조회")
            logger.warning(fundamental_error)
            df_info = None
        if df_info is None:
            df_info = pd.DataFrame()

        sector_analysis = _sector_analysis(
            df_info, stock_code, sector, peer_codes, trading_day, empty_reason=fundamental_error
        )
        analysis_result["sector_analysis"] = sector_analysis
        if sector_analysis["available"]:
            competitive_advantages = _competitive_advantages(sector_analysis)
            analysis_result["competitive_advantages"] = competitive_advantages
            insights.extend(competitive_advantages)

        # 2. 시가총액 순위 및 규모 분석
        market_position = _market_position(stock_code, trading_day)
        analysis_result["market_position"] = market_position
        if market_position["available"]:
            insights.append(
                f"시가총액 순위: {market_position['rank']}위/{market_position['total_stocks']}개 "
                f"(상위 {market_position['top_percent']}%)"
            )
            insights.append(f"시가총액 규모: {market_position['category']}")
        else:
            insights.append(f"시가총액 순위: 데이터 없음 ({market_position['reason']})")

        if not sector_analysis["available"] and not market_position["available"]:
            return create_fallback_message(
                agent_name="Korean Comparative Agent",
                company_name=company_name,
                stock_code=stock_code,
                reason=f"업종 비교: {sector_analysis['reason']} / 시가총액: {market_position['reason']}",
                data_source="FinanceDataReader, PyKRX",
            )

        # 3. 주요 경쟁사 식별 (업종별)
        sector_label = sector or "업종 미분류"
        if peer_codes:
            competitor_analysis = {}
            competitor_names = []

            for comp_code in peer_codes[:3]:  # 최대 3개 경쟁사
                if comp_code in df_info.index:
                    try:
                        comp_name = stock.get_market_ticker_name(comp_code)
                        competitor_analysis[comp_code] = {
                            "name": comp_name,
                            "PER": _metric(df_info.loc[comp_code, "PER"])
                            if "PER" in df_info.columns
                            else None,
                            "PBR": _metric(df_info.loc[comp_code, "PBR"])
                            if "PBR" in df_info.columns
                            else None,
                        }
                        competitor_names.append(comp_name)
                    except Exception as e:
                        logger.warning(f"경쟁사 {comp_code} 정보 수집 실패: {str(e)}")

            if competitor_analysis:
                analysis_result["key_competitors"] = competitor_analysis
                insights.append(f"주요 경쟁사: {', '.join(competitor_names)} ({sector_label})")
            else:
                insights.append(f"업종: {sector_label} (경쟁사 데이터 수집 제한)")
        else:
            insights.append(f"업종: {sector_label} (매핑된 경쟁사 없음)")

        return convert_numpy_types(
            {
                "status": "success",
                "stock_code": stock_code,
                "company_name": company_name,
                "analysis_summary": analysis_result,
                "key_insights": insights,
                "data_sources": ["PyKRX", "KRX Market Data", "FinanceDataReader"],
                "analysis_date": trading_day,
            }
        )
    except Exception as e:
        error_msg = format_error_message_korean(e, "상대 가치 분석")
        logger.error(error_msg)
        return create_fallback_message(
            agent_name="Korean Comparative Agent",
            company_name=company_name,
            stock_code=stock_code,
            reason=error_msg,
            data_source="FinanceDataReader, PyKRX",
        )


@tool
def get_comparative_analysis(stock_code: str, company_name: str) -> dict[str, Any]:
    """업종 내 경쟁사 비교 및 전체 시장 내 순위 분석을 통합적으로 수행합니다."""
    return get_comparative_analysis_logic(stock_code, company_name)


# 도구 목록
comparative_tools = [get_comparative_analysis]


def create_comparative_agent():
    """Comparative Analysis Agent 생성 함수"""
    llm = build_llm(temperature=0.1)

    prompt = (
        "당신은 동종업계 비교 분석 전문가입니다. "
        "`get_comparative_analysis` 도구가 돌려준 데이터만으로 이 회사의 업종 내·시장 내 상대 위치를 정리하세요.\n\n"
        "먼저 `get_comparative_analysis` 도구를 호출한 뒤, 아래 구조로 작성하세요. "
        "길이를 채우려고 항목을 늘리지 마세요.\n\n"
        "## 상대가치 분석\n\n"
        "- 기준일: analysis_date\n\n"
        "### A. 업종과 비교 대상\n"
        "- 업종: sector_analysis.sector_name (없으면 '업종 미분류')\n"
        "- 주요 경쟁사: key_competitors의 회사명과 각 PER·PBR\n"
        "- 업종 평균에 들어간 종목 수: sector_analysis.peer_count\n\n"
        "### B. 업종 평균 대비 지표\n"
        "- PER: 대상 기업 [target_metrics.PER]배 vs 업종 평균 [peer_averages.PER]배\n"
        "- PBR: 대상 기업 [target_metrics.PBR]배 vs 업종 평균 [peer_averages.PBR]배\n"
        "- EPS: 대상 기업 [target_metrics.EPS]원 vs 업종 평균 [peer_averages.EPS]원\n"
        "- BPS: 대상 기업 [target_metrics.BPS]원 vs 업종 평균 [peer_averages.BPS]원\n"
        "- 해석: competitive_advantages에 있는 항목을 근거로 업종 대비 위치를 설명하세요\n\n"
        "### C. 시장 내 규모\n"
        "- 시가총액: market_position.market_cap (원)\n"
        "- 시가총액 순위: [market_position.rank]위/[market_position.total_stocks]개 "
        "(상위 [market_position.top_percent]%)\n"
        "- 규모 분류: market_position.category\n\n"
        "### D. 받지 못한 데이터\n"
        "- available이 false인 항목마다 '데이터 없음'과 reason을 그대로 적으세요\n\n"
        "### E. 정리\n"
        "- 위 수치로 말할 수 있는 상대 위치만 2~3문장으로 정리하세요\n\n"
        "데이터 원칙:\n"
        "- 도구 결과에 있는 숫자만 쓰세요. ROE·ROA·EV/EBITDA·과거 PER/PBR 범위·Forward PER·성장률·"
        "부채비율·신용등급·시장점유율 등은 이 도구가 주지 않습니다 — 언급해야 하면 '데이터 없음'으로 적으세요\n"
        "- 값이 null인 지표도 '데이터 없음'으로 적으세요. 추정하거나 만들어내지 마세요\n"
        "- 이 자료는 동종업계 비교 참고자료이며 매수·매도 권유가 아닙니다\n"
        "DATA RULE: Use only numbers present in the tool result. Any metric the tool did not return (or whose section has available: false, or whose value is null) must be written as '데이터 없음' — never estimate or invent it.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.COMPARATIVE.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=comparative_tools, prompt=prompt, name="comparative_expert")
