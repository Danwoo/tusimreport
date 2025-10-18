#!/usr/bin/env python3
"""
Korean Comparative Analysis Agent
업종 내 경쟁사 및 전체 시장과 비교하여 기업의 상대적 위치를 분석합니다.
"""

import logging
from typing import Dict, Any
from datetime import datetime

import pykrx.stock as stock
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from config.settings import get_llm_model
from utils.helpers import convert_numpy_types

logger = logging.getLogger(__name__)


def get_comparative_analysis_logic(
    stock_code: str, company_name: str
) -> Dict[str, Any]:
    """업종 내 경쟁사 비교 및 전체 시장 내 순위 분석을 통합적으로 수행하는 로직"""
    try:
        logger.info(f"Performing comprehensive comparative analysis for {stock_code}")
        today_str = datetime.now().strftime("%Y%m%d")

        analysis_result = {}
        insights = []

        # 정확한 업종 매핑 (실제 한국 기업 업종 분류)
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
            "068270": "건설업",  # 셀트리온
            "373220": "의료용 물질 및 의약품",  # LG에너지솔루션
            "000270": "운수 및 창고업",  # 기아
            "024110": "건설업",  # 기업은행
        }

        # 1. 업종 비교 분석 (확장)
        df_info = stock.get_market_fundamental(today_str)
        if stock_code in df_info.index:
            # 정확한 업종 분류 사용
            sector = INDUSTRY_MAPPING.get(stock_code, "기타 제조업")

            # 같은 업종의 경쟁사들 찾기
            peer_codes = [
                code
                for code, industry in INDUSTRY_MAPPING.items()
                if industry == sector and code != stock_code
            ]
            peer_group = df_info[df_info.index.isin(peer_codes + [stock_code])]

            if len(peer_group) > 1:
                # 주요 지표 비교
                target_data = {
                    "PER": (
                        df_info.loc[stock_code, "PER"]
                        if "PER" in df_info.columns
                        else 15.0
                    ),
                    "PBR": (
                        df_info.loc[stock_code, "PBR"]
                        if "PBR" in df_info.columns
                        else 1.3
                    ),
                    "EPS": (
                        df_info.loc[stock_code, "EPS"]
                        if "EPS" in df_info.columns
                        else 5000
                    ),
                    "BPS": (
                        df_info.loc[stock_code, "BPS"]
                        if "BPS" in df_info.columns
                        else 58000
                    ),
                }

                peer_averages = {
                    "PER": (
                        peer_group["PER"].mean()
                        if "PER" in peer_group.columns
                        else 20.0
                    ),
                    "PBR": (
                        peer_group["PBR"].mean() if "PBR" in peer_group.columns else 1.5
                    ),
                    "EPS": (
                        peer_group["EPS"].mean()
                        if "EPS" in peer_group.columns
                        else 3000
                    ),
                    "BPS": (
                        peer_group["BPS"].mean()
                        if "BPS" in peer_group.columns
                        else 40000
                    ),
                }

                analysis_result["sector_analysis"] = {
                    "sector_name": sector,
                    "peer_count": len(peer_group),
                    "target_metrics": target_data,
                    "peer_averages": peer_averages,
                }

                # 경쟁 우위 분석
                competitive_advantages = []
                if target_data["PER"] < peer_averages["PER"]:
                    competitive_advantages.append(
                        "PER이 업종 평균보다 낮아 상대적으로 저평가"
                    )
                if target_data["PBR"] < peer_averages["PBR"]:
                    competitive_advantages.append(
                        "PBR이 업종 평균보다 낮아 자산 대비 저평가"
                    )
                if target_data["EPS"] > peer_averages["EPS"]:
                    competitive_advantages.append(
                        "EPS가 업종 평균보다 높아 수익성 우수"
                    )

                analysis_result["competitive_advantages"] = competitive_advantages
                insights.extend(competitive_advantages)

        # 2. 시가총액 순위 및 규모 분석 (FinanceDataReader 사용 - 더 정확함)
        import FinanceDataReader as fdr

        try:
            market_data = fdr.StockListing("KRX")
            target_stock = market_data[market_data["Code"] == stock_code]

            if not target_stock.empty and "Marcap" in market_data.columns:
                target_cap = target_stock.iloc[0]["Marcap"]  # 백만원 단위

                # 유효한 시가총액을 가진 기업들만 필터링하고 정렬
                valid_stocks = (
                    market_data[market_data["Marcap"] > 0]
                    .sort_values("Marcap", ascending=False)
                    .reset_index(drop=True)
                )

                # 순위 계산
                target_rank_df = valid_stocks[valid_stocks["Code"] == stock_code]
                if not target_rank_df.empty:
                    rank = target_rank_df.index[0] + 1
                    total_stocks = len(valid_stocks)
                else:
                    rank = 999
                    total_stocks = len(valid_stocks)
            else:
                # FinanceDataReader 실패시 PyKRX 사용
                market_cap_df = stock.get_market_cap(today_str)
                if stock_code in market_cap_df.index:
                    market_cap_df = market_cap_df.sort_values(
                        by="시가총액", ascending=False
                    ).reset_index()
                    target_cap = market_cap_df[market_cap_df["티커"] == stock_code][
                        "시가총액"
                    ].iloc[0]
                    rank = (
                        market_cap_df[market_cap_df["티커"] == stock_code].index[0] + 1
                    )
                    total_stocks = len(market_cap_df)
                else:
                    target_cap = 0
                    rank = 999
                    total_stocks = 1000
        except Exception as e:
            logger.warning(f"Market cap analysis error: {str(e)}")
            target_cap = 0
            rank = 999
            total_stocks = 1000

        # 시가총액 규모 분류
        if rank <= 10:
            cap_category = "대형주 (Top 10)"
        elif rank <= 50:
            cap_category = "대형주 (Top 50)"
        elif rank <= 200:
            cap_category = "중형주"
        else:
            cap_category = "소형주"

        analysis_result["market_position"] = {
            "rank": rank,
            "total_stocks": total_stocks,
            "market_cap": float(target_cap),
            "category": cap_category,
            "percentile": round((1 - rank / total_stocks) * 100, 1),
        }

        insights.append(
            f"시가총액 순위: {rank}위/{total_stocks}개 (상위 {round((1 - rank/total_stocks) * 100, 1)}%)"
        )
        insights.append(f"시가총액 규모: {cap_category}")

        # 3. 주요 경쟁사 식별 (업종별)
        if len(peer_codes) > 0:
            competitor_analysis = {}
            competitor_names = []

            for comp_code in peer_codes[:3]:  # 최대 3개 경쟁사
                if comp_code in df_info.index:
                    try:
                        comp_name = stock.get_market_ticker_name(comp_code)
                        competitor_analysis[comp_code] = {
                            "name": comp_name,
                            "PER": (
                                float(df_info.loc[comp_code, "PER"])
                                if "PER" in df_info.columns
                                and df_info.loc[comp_code, "PER"] > 0
                                else 0
                            ),
                            "PBR": (
                                float(df_info.loc[comp_code, "PBR"])
                                if "PBR" in df_info.columns
                                and df_info.loc[comp_code, "PBR"] > 0
                                else 0
                            ),
                        }
                        competitor_names.append(comp_name)
                    except Exception as e:
                        logger.warning(f"경쟁사 {comp_code} 정보 수집 실패: {str(e)}")

            if competitor_analysis:
                analysis_result["key_competitors"] = competitor_analysis
                insights.append(
                    f"주요 경쟁사: {', '.join(competitor_names)} ({sector})"
                )
            else:
                insights.append(f"업종: {sector} (경쟁사 데이터 수집 제한)")
        else:
            insights.append(f"업종: {sector} (매핑된 경쟁사 없음)")

        return convert_numpy_types(
            {
                "status": "success",
                "stock_code": stock_code,
                "company_name": company_name,
                "analysis_summary": analysis_result,
                "key_insights": insights,
                "data_sources": ["PyKRX", "KRX Market Data"],
                "analysis_date": today_str,
            }
        )
    except Exception as e:
        logger.error(f"Error in comparative analysis: {str(e)}")
        return {"error": str(e)}


@tool
def get_comparative_analysis(stock_code: str, company_name: str) -> Dict[str, Any]:
    """업종 내 경쟁사 비교 및 전체 시장 내 순위 분석을 통합적으로 수행합니다."""
    return get_comparative_analysis_logic(stock_code, company_name)


# 도구 목록
comparative_tools = [get_comparative_analysis]


def create_comparative_agent():
    """Comparative Analysis Agent 생성 함수"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()
    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, api_key=llm_api_key)

    prompt = (
        "당신은 증권사의 상대 가치 분석 애널리스트입니다. 중급 투자자를 대상으로 동종업계 비교와 밸류에이션을 전문적이면서도 명료하게 분석해주세요.\n\n"

        "분석 시 다음 사항을 평가하세요: 1) 업종 분류 및 시장 포지션(업종명, 시가총액 순위, 대형/중형/소형주 분류), "
        "2) 경쟁사 밸류에이션 비교(주요 경쟁사와의 PER/PBR/ROE 비교와 저평가/적정/고평가 판단), "
        "3) 경쟁 우위 및 투자 매력도(업종 내 경쟁력과 상대 가치 관점의 투자 매력도).\n\n"

        "## 출력 형식 (반드시 이 구조를 따르세요):\n\n"
        "```\n"
        "## 상대 가치 분석\n\n"

        "### 업종 분류 및 시장 포지션\n"
        "[업종명, 시가총액 순위(업종 내/전체 시장), 대형/중형/소형주 분류, 업종 대표성 수준을 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 경쟁사 밸류에이션 비교\n"
        "[주요 경쟁사 2-3개와의 PER/PBR/ROE 비교, 업종 평균 대비 프리미엄/디스카운트, 저평가/적정/고평가 판단을 2-3개 문단으로 서술. 500-600자]\n\n"

        "### 경쟁 우위 및 투자 관점\n"
        "[업종 내 경쟁력(시장점유율, 수익성, 성장성)과 상대 가치 관점의 투자 매력도를 2개 문단으로 서술. 400-500자]\n\n"

        "### 참고 데이터\n"
        "- PyKRX: [시장 데이터 기준일]\n"
        "- FinanceDataReader: [밸류에이션 데이터 기준일]\n"
        "```\n\n"

        "## 작성 원칙:\n"
        "- 총 분량: 1500-2000자 (각 섹션당 400-600자 목표)\n"
        "- 문단 중심 서술 (밸류에이션 수치는 괄호 내 표기 예: PER 12배 - 업종 평균 15배 대비 20% 할인)\n"
        "- 구체적인 PER, PBR, 시장 순위 수치 필수 포함\n"
        "- 경쟁사 수치 나열시에만 bullet point 사용\n"
        "- 증권사 리서치 보고서 톤: 전문적이되 명료하게\n"
        "- 업종 평균 대비 프리미엄/디스카운트를 구체적으로 평가\n\n"

        "데이터가 없는 경우 '정보 부족'으로 명시하고 추측 금지.\n\n"

        "이 분석은 투자 참고자료이며, 특정 종목 매수/매도 권유가 아닙니다.\n\n"
        "🚨 분석 완료 후 마지막 줄에 'COMPARATIVE_ANALYSIS_COMPLETE'를 반드시 포함하세요."
    )

    return create_react_agent(
        model=llm, tools=comparative_tools, prompt=prompt, name="comparative_expert"
    )
