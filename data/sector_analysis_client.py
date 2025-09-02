#!/usr/bin/env python3
"""
업종별 상대 평가 시스템
동일 업종 내 기업들의 상대적 위치 및 성과 비교 분석

PyKRX와 FinanceDataReader를 활용한 업종 분석
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import FinanceDataReader as fdr
import pykrx.stock as stock

logger = logging.getLogger(__name__)

class SectorAnalysisClient:
    """업종별 상대 평가 클라이언트"""
    
    def __init__(self):
        self.sector_mapping = self._load_sector_mapping()
    
    def _load_sector_mapping(self) -> Dict[str, Dict[str, Any]]:
        """주요 업종 및 대표 종목 매핑"""
        return {
            "반도체": {
                "companies": ["005930", "000660", "042700", "006400"],  # 삼성전자, SK하이닉스, 한미반도체, 삼성SDI
                "sector_code": "IT하드웨어",
                "description": "메모리반도체, 시스템반도체 등"
            },
            "인터넷": {
                "companies": ["035420", "035720", "376300", "181710"],  # 네이버, 카카오, 카카오뱅크, NHN
                "sector_code": "IT서비스",
                "description": "온라인 플랫폼, 게임, 핀테크"
            },
            "자동차": {
                "companies": ["005380", "012330", "000270", "161890"],  # 현대차, 현대모비스, 기아, 한국카본
                "sector_code": "자동차",
                "description": "완성차, 부품, 전기차"
            },
            "화학": {
                "companies": ["051910", "009830", "011170", "010950"],  # LG화학, 한화솔루션, 롯데케미칼, S-Oil
                "sector_code": "화학",
                "description": "정유, 석유화학, 이차전지소재"
            },
            "바이오": {
                "companies": ["207940", "068270", "326030", "196170"],  # 삼성바이오로직스, 셀트리온, SK바이오팜, 밀테크
                "sector_code": "바이오",
                "description": "바이오의약품, 제약, 의료기기"
            },
            "금융": {
                "companies": ["055550", "316140", "024110", "138930"],  # 신한지주, 우리금융지주, 기업은행, BNK금융지주
                "sector_code": "은행",
                "description": "은행, 증권, 보험"
            },
            "에너지": {
                "companies": ["015760", "034730", "000660", "017670"],  # 한국전력, SK, SK하이닉스, SK텔레콤
                "sector_code": "전력가스업",
                "description": "발전, 신재생에너지, 유틸리티"
            }
        }
    
    def get_sector_companies(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """종목코드로 업종 정보 조회"""
        try:
            for sector_name, sector_info in self.sector_mapping.items():
                if stock_code in sector_info["companies"]:
                    return {
                        "sector": sector_name,
                        "sector_code": sector_info["sector_code"],
                        "description": sector_info["description"],
                        "peer_companies": [code for code in sector_info["companies"] if code != stock_code]
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting sector for {stock_code}: {str(e)}")
            return None
    
    def get_sector_performance(self, sector_name: str, period_days: int = 90) -> Dict[str, Any]:
        """업종 전체 성과 분석"""
        try:
            if sector_name not in self.sector_mapping:
                return {"error": f"Sector {sector_name} not found"}
            
            companies = self.sector_mapping[sector_name]["companies"]
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            sector_data = []
            
            for stock_code in companies:
                try:
                    # FinanceDataReader로 개별 종목 데이터 조회
                    df = fdr.DataReader(stock_code, start_date.strftime('%Y-%m-%d'))
                    
                    if df.empty:
                        continue
                    
                    # 기본 성과 지표 계산
                    start_price = float(df.iloc[0]['Close'])
                    end_price = float(df.iloc[-1]['Close'])
                    return_pct = ((end_price - start_price) / start_price) * 100
                    
                    # 변동성 계산
                    daily_returns = df['Close'].pct_change().dropna()
                    volatility = float(daily_returns.std() * np.sqrt(252) * 100)  # 연환산 변동성
                    
                    # 거래량 분석
                    avg_volume = float(df['Volume'].mean())
                    
                    sector_data.append({
                        "stock_code": stock_code,
                        "start_price": start_price,
                        "end_price": end_price,
                        "return_percent": return_pct,
                        "volatility": volatility,
                        "avg_volume": avg_volume,
                        "market_cap": self._estimate_market_cap(stock_code, end_price)
                    })
                    
                except Exception as stock_error:
                    logger.warning(f"Error processing {stock_code}: {str(stock_error)}")
                    continue
            
            if not sector_data:
                return {"error": "No valid sector data found"}
            
            # 업종 통계 계산
            returns = [item["return_percent"] for item in sector_data]
            sector_avg_return = np.mean(returns)
            sector_median_return = np.median(returns)
            sector_std_return = np.std(returns)
            
            # 개별 종목의 상대적 위치 계산
            for item in sector_data:
                item["relative_performance"] = "outperform" if item["return_percent"] > sector_avg_return else "underperform"
                item["percentile_rank"] = sum(1 for r in returns if r < item["return_percent"]) / len(returns) * 100
            
            return {
                "sector": sector_name,
                "period_days": period_days,
                "companies_analyzed": len(sector_data),
                "sector_statistics": {
                    "average_return": sector_avg_return,
                    "median_return": sector_median_return,
                    "return_std": sector_std_return,
                    "best_performer": max(sector_data, key=lambda x: x["return_percent"]),
                    "worst_performer": min(sector_data, key=lambda x: x["return_percent"])
                },
                "company_details": sector_data,
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting sector performance: {str(e)}")
            return {"error": str(e)}
    
    def _estimate_market_cap(self, stock_code: str, current_price: float) -> Optional[float]:
        """시가총액 추정 (간단한 추정치)"""
        try:
            # 주식 수 정보 (실제로는 더 정확한 데이터 소스 필요)
            shares_mapping = {
                "005930": 5969782550,  # 삼성전자 (보통주)
                "000660": 728002365,   # SK하이닉스
                "035420": 161856878,   # 네이버
                "035720": 422776728,   # 카카오
                "005380": 1407177781,  # 현대차
            }
            
            shares = shares_mapping.get(stock_code, 1000000)  # 기본값
            market_cap = current_price * shares / 100000000  # 억원 단위
            
            return market_cap
            
        except Exception:
            return None
    
    def get_peer_comparison(self, stock_code: str, period_days: int = 90) -> Dict[str, Any]:
        """동종업계 비교 분석"""
        try:
            # 업종 정보 조회
            sector_info = self.get_sector_companies(stock_code)
            
            if not sector_info:
                return {"error": f"Sector information not found for {stock_code}"}
            
            # 업종 성과 분석
            sector_performance = self.get_sector_performance(sector_info["sector"], period_days)
            
            if sector_performance.get("error"):
                return sector_performance
            
            # 타겟 종목의 상대적 위치 찾기
            target_performance = None
            for company in sector_performance["company_details"]:
                if company["stock_code"] == stock_code:
                    target_performance = company
                    break
            
            if not target_performance:
                return {"error": f"Performance data not found for {stock_code}"}
            
            # 동종업계 순위 및 비교 정보
            sorted_companies = sorted(
                sector_performance["company_details"], 
                key=lambda x: x["return_percent"], 
                reverse=True
            )
            
            target_rank = next(
                (i + 1 for i, company in enumerate(sorted_companies) if company["stock_code"] == stock_code), 
                None
            )
            
            return {
                "target_stock": stock_code,
                "sector_info": sector_info,
                "target_performance": target_performance,
                "sector_rank": f"{target_rank}/{len(sorted_companies)}",
                "percentile_rank": target_performance["percentile_rank"],
                "sector_benchmark": {
                    "average_return": sector_performance["sector_statistics"]["average_return"],
                    "best_performer": sector_performance["sector_statistics"]["best_performer"]["stock_code"],
                    "worst_performer": sector_performance["sector_statistics"]["worst_performer"]["stock_code"]
                },
                "peer_comparison": [
                    {
                        "stock_code": company["stock_code"],
                        "return_percent": company["return_percent"],
                        "relative_to_target": company["return_percent"] - target_performance["return_percent"]
                    }
                    for company in sorted_companies if company["stock_code"] != stock_code
                ],
                "analysis_period": period_days,
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in peer comparison: {str(e)}")
            return {"error": str(e)}

# 전역 인스턴스
sector_analyzer = SectorAnalysisClient()

def analyze_sector_relative_performance(stock_code: str) -> Dict[str, Any]:
    """종목의 업종 상대 성과 분석"""
    try:
        logger.info(f"Analyzing sector relative performance for {stock_code}")
        
        return sector_analyzer.get_peer_comparison(stock_code, period_days=90)
        
    except Exception as e:
        logger.error(f"Error analyzing sector performance: {str(e)}")
        return {"error": str(e)}