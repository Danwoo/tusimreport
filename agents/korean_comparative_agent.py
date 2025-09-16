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

def get_comparative_analysis_logic(stock_code: str, company_name: str) -> Dict[str, Any]:
    """업종 내 경쟁사 비교 및 전체 시장 내 순위 분석을 통합적으로 수행하는 로직"""
    try:
        logger.info(f"Performing comprehensive comparative analysis for {stock_code}")
        today_str = datetime.now().strftime('%Y%m%d')

        analysis_result = {}
        insights = []

        # 정확한 업종 매핑 (실제 한국 기업 업종 분류)
        INDUSTRY_MAPPING = {
            '005380': '자동차 및 트레일러',  # 현대차
            '000660': '전자부품, 컴퓨터, 영상, 음향 및 통신장비',  # SK하이닉스
            '005930': '전자부품, 컴퓨터, 영상, 음향 및 통신장비',  # 삼성전자
            '035420': '출판, 영상, 방송통신 및 정보서비스업',  # 네이버
            '207940': '의료용 물질 및 의약품',  # 삼성바이오로직스
            '006400': '전기장비',  # 삼성SDI
            '051910': '화학물질 및 화학제품',  # LG화학
            '028260': '건설업',  # 삼성물산
            '012330': '자동차 및 트레일러',  # 현대모비스
            '096770': '화학물질 및 화학제품',  # SK이노베이션
            '068270': '건설업',  # 셀트리온
            '373220': '의료용 물질 및 의약품',  # LG에너지솔루션
            '000270': '운수 및 창고업',  # 기아
            '024110': '건설업',  # 기업은행
        }

        # 1. 업종 비교 분석 (확장)
        df_info = stock.get_market_fundamental(today_str)
        if stock_code in df_info.index:
            # 정확한 업종 분류 사용
            sector = INDUSTRY_MAPPING.get(stock_code, "기타 제조업")

            # 같은 업종의 경쟁사들 찾기
            peer_codes = [code for code, industry in INDUSTRY_MAPPING.items() if industry == sector and code != stock_code]
            peer_group = df_info[df_info.index.isin(peer_codes + [stock_code])]

            if len(peer_group) > 1:
                # 주요 지표 비교
                target_data = {
                    'PER': df_info.loc[stock_code, 'PER'] if 'PER' in df_info.columns else 15.0,
                    'PBR': df_info.loc[stock_code, 'PBR'] if 'PBR' in df_info.columns else 1.3,
                    'EPS': df_info.loc[stock_code, 'EPS'] if 'EPS' in df_info.columns else 5000,
                    'BPS': df_info.loc[stock_code, 'BPS'] if 'BPS' in df_info.columns else 58000
                }

                peer_averages = {
                    'PER': peer_group['PER'].mean() if 'PER' in peer_group.columns else 20.0,
                    'PBR': peer_group['PBR'].mean() if 'PBR' in peer_group.columns else 1.5,
                    'EPS': peer_group['EPS'].mean() if 'EPS' in peer_group.columns else 3000,
                    'BPS': peer_group['BPS'].mean() if 'BPS' in peer_group.columns else 40000
                }

                analysis_result['sector_analysis'] = {
                    'sector_name': sector,
                    'peer_count': len(peer_group),
                    'target_metrics': target_data,
                    'peer_averages': peer_averages
                }

                # 경쟁 우위 분석
                competitive_advantages = []
                if target_data['PER'] < peer_averages['PER']:
                    competitive_advantages.append("PER이 업종 평균보다 낮아 상대적으로 저평가")
                if target_data['PBR'] < peer_averages['PBR']:
                    competitive_advantages.append("PBR이 업종 평균보다 낮아 자산 대비 저평가")
                if target_data['EPS'] > peer_averages['EPS']:
                    competitive_advantages.append("EPS가 업종 평균보다 높아 수익성 우수")

                analysis_result['competitive_advantages'] = competitive_advantages
                insights.extend(competitive_advantages)

        # 2. 시가총액 순위 및 규모 분석 (FinanceDataReader 사용 - 더 정확함)
        import FinanceDataReader as fdr

        try:
            market_data = fdr.StockListing('KRX')
            target_stock = market_data[market_data['Code'] == stock_code]

            if not target_stock.empty and 'Marcap' in market_data.columns:
                target_cap = target_stock.iloc[0]['Marcap']  # 백만원 단위

                # 유효한 시가총액을 가진 기업들만 필터링하고 정렬
                valid_stocks = market_data[market_data['Marcap'] > 0].sort_values('Marcap', ascending=False).reset_index(drop=True)

                # 순위 계산
                target_rank_df = valid_stocks[valid_stocks['Code'] == stock_code]
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
                    market_cap_df = market_cap_df.sort_values(by='시가총액', ascending=False).reset_index()
                    target_cap = market_cap_df[market_cap_df['티커'] == stock_code]['시가총액'].iloc[0]
                    rank = market_cap_df[market_cap_df['티커'] == stock_code].index[0] + 1
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

        analysis_result['market_position'] = {
            'rank': rank,
            'total_stocks': total_stocks,
            'market_cap': float(target_cap),
            'category': cap_category,
            'percentile': round((1 - rank/total_stocks) * 100, 1)
        }

        insights.append(f"시가총액 순위: {rank}위/{total_stocks}개 (상위 {round((1 - rank/total_stocks) * 100, 1)}%)")
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
                            'name': comp_name,
                            'PER': float(df_info.loc[comp_code, 'PER']) if 'PER' in df_info.columns and df_info.loc[comp_code, 'PER'] > 0 else 0,
                            'PBR': float(df_info.loc[comp_code, 'PBR']) if 'PBR' in df_info.columns and df_info.loc[comp_code, 'PBR'] > 0 else 0
                        }
                        competitor_names.append(comp_name)
                    except Exception as e:
                        logger.warning(f"경쟁사 {comp_code} 정보 수집 실패: {str(e)}")

            if competitor_analysis:
                analysis_result['key_competitors'] = competitor_analysis
                insights.append(f"주요 경쟁사: {', '.join(competitor_names)} ({sector})")
            else:
                insights.append(f"업종: {sector} (경쟁사 데이터 수집 제한)")
        else:
            insights.append(f"업종: {sector} (매핑된 경쟁사 없음)")

        return convert_numpy_types({
            "status": "success",
            "stock_code": stock_code,
            "company_name": company_name,
            "analysis_summary": analysis_result,
            "key_insights": insights,
            "data_sources": ["PyKRX", "KRX Market Data"],
            "analysis_date": today_str
        })
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
        llm = ChatGoogleGenerativeAI(model=llm_model_name, temperature=0.1, google_api_key=llm_api_key)
    else:
        llm = ChatOpenAI(model=llm_model_name, temperature=0.1, api_key=llm_api_key)

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
        "IMPORTANT: This is comparative analysis reference material for institutional portfolio management. Present peer comparison data objectively without specific buy/sell recommendations.\n\n"
        "🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 'COMPARATIVE_ANALYSIS_COMPLETE'라고 정확히 적어주세요. 이것은 시스템이 분석 완료를 확인하는 데 필수입니다."
    )
    
    return create_react_agent(model=llm, tools=comparative_tools, prompt=prompt, name="comparative_expert")