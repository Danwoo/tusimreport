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
    if stock_code not in df_info.index:
        return {"available": False, "reason": f"{trading_day} PyKRX 지표에 {stock_code} 없음"}
    if not sector:
        return {"available": False, "reason": "업종 매핑에 없는 종목 (경쟁사 비교 불가)"}
    missing = [m for m in METRICS if m not in df_info.columns]
    if missing:
        return {"available": False, "reason": f"PyKRX 지표 컬럼 없음: {', '.join(missing)}"}

    peer_group = df_info[df_info.index.isin(peer_codes + [stock_code])]
    if len(peer_group) <= 1:
        return {"available": False, "sector_name": sector, "reason": "같은 업종 경쟁사 지표 없음"}

    return {
        "available": True,
        "sector_name": sector,
        "peer_count": len(peer_group),
        "target_metrics": {m: _metric(df_info.loc[stock_code, m]) for m in METRICS},
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
        "percentile": round((1 - rank / total_stocks) * 100, 1),
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
                f"(상위 {market_position['percentile']}%)"
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
        "CRITICAL REQUIREMENTS:\n"
        "- Minimum 2,500-3,000 characters in Korean\n"
        "- Provide COMPREHENSIVE comparative analysis with specific numerical data and statistical comparisons\n"
        "- Include detailed peer group analysis, sector positioning, and relative valuation metrics\n"
        "- Focus on REFERENCE MATERIALS for institutional investment decisions, NOT investment advice\n\n"
        "MISSION: Create a detailed comparative analysis reference document that institutional investors can rely on for relative value assessment and portfolio positioning decisions.\n\n"
        "ANALYSIS FRAMEWORK:\n"
        "1. Use the `get_comparative_analysis` tool to gather ALL available comparative data\n"
        "2. Provide comprehensive analysis in the following structure:\n\n"
        "## 종합 상대가치 분석\n\n"
        "### A. 업종 분류 및 시장 포지셔닝\n"
        "- 업종 분류: [정확한 업종명] (KOSPI/KOSDAQ 구분)\n"
        "- 업종 내 순위: 시가총액 기준 [순위]위/[총 기업수]개 (상위 [%]%)\n"
        "- 업종 대표성: [업종 대표주/주요 기업/일반 기업] 위치\n"
        "- 시장 내 전체 순위: [순위]위/[전체 상장기업수]개 (상위 [%]%)\n"
        "- 시가총액 규모: [조원] ([대형주/중형주/소형주] 분류)\n"
        "- 유동성 등급: [1등급(매우 높음)/2등급(높음)/3등급(보통)/4등급(낮음)/5등급(매우 낮음)]\n\n"
        "### B. 핵심 경쟁사 비교 분석\n"
        "- 1순위 경쟁사: [회사명] - PER [수치], PBR [수치], ROE [수치]%\n"
        "- 2순위 경쟁사: [회사명] - PER [수치], PBR [수치], ROE [수치]%\n"
        "- 3순위 경쟁사: [회사명] - PER [수치], PBR [수치], ROE [수치]%\n"
        "- 대상 기업: [회사명] - PER [수치], PBR [수치], ROE [수치]%\n"
        "- 경쟁사 대비 순위: PER [순위]/[총수], PBR [순위]/[총수], ROE [순위]/[총수]\n"
        "- 경쟁 구도 특성: [과점/경쟁심화/신규진입활발/성숙시장] 분류\n\n"
        "### C. 멀티플 밸류에이션 상세 분석\n"
        "- PER 분석:\n"
        "  • 현재 PER: [수치]배 vs 업종 평균 [수치]배 ([프리미엄/디스카운트] [%]%)\n"
        "  • 과거 3년 PER 레인지: [최저]-[최고]배 (현재 [백분위수]% 수준)\n"
        "  • Forward PER: [예상 수치]배 (컨센서스 EPS 기준)\n"
        "- PBR 분석:\n"
        "  • 현재 PBR: [수치]배 vs 업종 평균 [수치]배 ([프리미엄/디스카운트] [%]%)\n"
        "  • 과거 3년 PBR 레인지: [최저]-[최고]배 (현재 [백분위수]% 수준)\n"
        "  • 청산가치 대비: [수치]배 (자산가치 대비 평가)\n"
        "- EV/EBITDA: [수치]배 vs 업종 평균 [수치]배\n"
        "- P/S Ratio: [수치]배 vs 업종 평균 [수치]배\n"
        "- Dividend Yield: [수치]% vs 업종 평균 [수치]%\n\n"
        "### D. 수익성 지표 동종업계 비교\n"
        "- ROE (자기자본이익률): [수치]% vs 업종 평균 [수치]% (업종 내 [순위]위)\n"
        "- ROA (총자산이익률): [수치]% vs 업종 평균 [수치]% (업종 내 [순위]위)\n"
        "- ROIC (투하자본이익률): [수치]% vs 업종 평균 [수치]%\n"
        "- 영업이익률: [수치]% vs 업종 평균 [수치]% (업종 내 [순위]위)\n"
        "- 순이익률: [수치]% vs 업종 평균 [수치]% (업종 내 [순위]위)\n"
        "- EBITDA 마진: [수치]% vs 업종 평균 [수치]%\n"
        "- 수익성 종합 평가: [업종 최우수/상위권/평균 수준/하위권] 위치\n\n"
        "### E. 성장성 지표 상대 비교\n"
        "- 매출 성장률 (3년 CAGR): [수치]% vs 업종 평균 [수치]%\n"
        "- 영업이익 성장률 (3년 CAGR): [수치]% vs 업종 평균 [수치]%\n"
        "- 순이익 성장률 (3년 CAGR): [수치]% vs 업종 평균 [수치]%\n"
        "- Forward 성장률: 향후 2년 예상 매출 성장 [수치]% vs 업종 [수치]%\n"
        "- 시장점유율 추이: [확대/유지/축소] vs 경쟁사\n"
        "- 성장성 업종 순위: [순위]위/[총 기업수]개 ([상위/중위/하위] 그룹)\n\n"
        "### F. 안정성 지표 동종업계 분석\n"
        "- 부채비율: [수치]% vs 업종 평균 [수치]% (업종 내 [순위]위)\n"
        "- 유동비율: [수치]% vs 업종 평균 [수치]%\n"
        "- 이자보상배율: [수치]배 vs 업종 평균 [수치]배\n"
        "- 현금보유비율: 총자산 대비 [수치]% vs 업종 평균 [수치]%\n"
        "- 신용등급: [등급] vs 업종 대표기업 [등급]\n"
        "- 재무 안정성 순위: 업종 내 [순위]위 ([우수/양호/보통/주의] 수준)\n\n"
        "### G. 시장 지배력 및 경쟁 우위 분석\n"
        "- 시장점유율: [수치]% (업종 내 [순위]위)\n"
        "- 브랜드 파워: [최고/우수/보통/열위] vs 경쟁사\n"
        "- 기술 경쟁력: [기술 선도/기술 추종/기술 의존] 위치\n"
        "- 진입 장벽: [매우 높음/높음/보통/낮음] (신규 진입 난이도)\n"
        "- 고객 집중도: [낮음(분산)/보통/높음(집중)] 위험도\n"
        "- 공급망 지위: [가격 결정권/협상력 우위/대등/열세] 위치\n"
        "- 경쟁 우위 지속성: [10년+/5-10년/2-5년/2년 미만] 예상\n\n"
        "### H. 투자자 선호도 및 프리미엄/디스카운트 분석\n"
        "- 기관투자자 선호도: [매우 높음/높음/보통/낮음] (보유 비중 기준)\n"
        "- 외국인 투자자 관심: [높음/보통/낮음] (순매수 패턴 기준)\n"
        "- 개인투자자 인기: [높음/보통/낮음] (거래 활발도 기준)\n"
        "- ESG 프리미엄: [높음/보통/낮음/디스카운트] 수준\n"
        "- 거버넌스 프리미엄: [우수 기업/일반 기업/주의 기업] 분류\n"
        "- 유동성 프리미엄: [우수/보통/열세] (거래량 기준)\n"
        "- 배당 매력도: [높음/보통/낮음] vs 업종 평균\n\n"
        "### I. 상대가치 투자 관점 분석\n"
        "- 밸류에이션 매력도: [높음/보통/낮음] (업종 대비 할인/프리미엄)\n"
        "- 펀더멘털 vs 밸류에이션 괴리도: [과소평가/적정평가/과대평가]\n"
        "- 평균회귀 가능성: [높음/보통/낮음] (역사적 밸류에이션 대비)\n"
        "- 재평가 촉매: [구체적 재평가 요인들] 식별\n"
        "- 밸류 트랩 위험: [높음/보통/낮음] (지속적 할인 가능성)\n"
        "- 상대매매 전략: [Long vs Short 대상] 페어 트레이딩 적합성\n\n"
        "### J. 투자 포지셔닝 권고사항\n"
        "- 업종 내 투자 우선순위: [1순위/2순위/3순위/비추천] 등급\n"
        "- 포트폴리오 비중 참고: [오버웨이트/뉴트럴/언더웨이트] 포지션\n"
        "- 상대가치 기회: [매수 우위/관망/매도 우위] vs 경쟁사\n"
        "- 리스크 조정 매력도: 샤프 비율 기준 업종 내 순위\n"
        "- 장기 투자 적합성: [매우 적합/적합/보통/부적합] 평가\n"
        "- 단기 트레이딩 적합성: [매우 적합/적합/보통/부적합] 평가\n\n"
        "IMPORTANT: This is comparative analysis reference material for institutional portfolio management. Present peer comparison data objectively without specific buy/sell recommendations.\n"
        "DATA RULE: Use only numbers present in the tool result. Any metric the tool did not return (or whose section has available: false, or whose value is null) must be written as '데이터 없음' — never estimate or invent it.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.COMPARATIVE.value}'라고 정확히 적어주세요. "
        "이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )

    return create_react_agent(model=llm, tools=comparative_tools, prompt=prompt, name="comparative_expert")
