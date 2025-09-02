#!/usr/bin/env python3
"""
한국은행(Bank of Korea) 경제통계 API 클라이언트
거시경제 지표 및 금융 데이터 수집을 위한 API 클라이언트

한국은행 경제통계시스템: https://ecos.bok.or.kr/
"""

import logging
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class BOKAPIClient:
    """한국은행 경제통계 API 클라이언트"""
    
    def __init__(self, api_key: Optional[str] = None):
        # 무료 샘플 API 키 (실제 서비스에서는 발급받은 키 사용)
        self.api_key = api_key or "sample"
        self.base_url = "https://ecos.bok.or.kr/api"
        self.session = requests.Session()
        
        # 요청 헤더 설정
        self.session.headers.update({
            'User-Agent': 'TuSimReport/1.0',
            'Accept': 'application/json'
        })
    
    def _make_request(self, service_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 실행"""
        url = f"{self.base_url}/{service_name}/{self.api_key}/json/kr"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Rate limiting
            time.sleep(0.1)
            
            return response.json()
            
        except Exception as e:
            logger.error(f"BOK API request failed: {str(e)}")
            return {"error": str(e)}
    
    def get_base_rate(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """기준금리 조회
        
        Args:
            start_date: 시작일 (YYYYMMDD), 기본값은 1년 전
            end_date: 종료일 (YYYYMMDD), 기본값은 오늘
        """
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            
            params = {
                'start_date': start_date,
                'end_date': end_date,
                'item_code1': '722Y001',  # 기준금리 코드
                'cycle_type': 'D',  # 일별
                'per_page': '1000'
            }
            
            result = self._make_request('StatisticSearch', params)
            
            if result.get('StatisticSearch') and result['StatisticSearch'].get('row'):
                rates = []
                for item in result['StatisticSearch']['row']:
                    try:
                        rates.append({
                            "date": item.get('TIME'),
                            "rate": float(item.get('DATA_VALUE', 0)),
                            "unit": item.get('UNIT_NAME', '%')
                        })
                    except (ValueError, TypeError):
                        continue
                
                return {
                    "base_rates": rates,
                    "latest_rate": rates[-1] if rates else None,
                    "data_source": "Bank of Korea",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": "No base rate data found"}
            
        except Exception as e:
            logger.error(f"Error getting base rate: {str(e)}")
            return {"error": str(e)}
    
    def get_exchange_rate(self, currency_code: str = "USD", start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """환율 조회
        
        Args:
            currency_code: 통화코드 (USD, EUR, JPY, CNY 등)
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
        """
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            
            # 통화별 아이템 코드 매핑
            currency_codes = {
                "USD": "731Y003",  # 원/달러 환율
                "EUR": "731Y009",  # 원/유로 환율
                "JPY": "731Y006",  # 원/엔 환율
                "CNY": "731Y012"   # 원/위안 환율
            }
            
            item_code = currency_codes.get(currency_code, "731Y003")  # 기본값: USD
            
            params = {
                'start_date': start_date,
                'end_date': end_date,
                'item_code1': item_code,
                'cycle_type': 'D',
                'per_page': '1000'
            }
            
            result = self._make_request('StatisticSearch', params)
            
            if result.get('StatisticSearch') and result['StatisticSearch'].get('row'):
                rates = []
                for item in result['StatisticSearch']['row']:
                    try:
                        rates.append({
                            "date": item.get('TIME'),
                            "rate": float(item.get('DATA_VALUE', 0)),
                            "currency": currency_code,
                            "unit": item.get('UNIT_NAME', '원')
                        })
                    except (ValueError, TypeError):
                        continue
                
                return {
                    "exchange_rates": rates,
                    "latest_rate": rates[-1] if rates else None,
                    "currency": currency_code,
                    "data_source": "Bank of Korea",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"No exchange rate data found for {currency_code}"}
            
        except Exception as e:
            logger.error(f"Error getting exchange rate: {str(e)}")
            return {"error": str(e)}
    
    def get_gdp_data(self, start_period: str = None, end_period: str = None) -> Dict[str, Any]:
        """GDP 데이터 조회
        
        Args:
            start_period: 시작 기간 (YYYYQQ), 기본값은 2년 전
            end_period: 종료 기간 (YYYYQQ), 기본값은 최신 분기
        """
        try:
            if not end_period:
                current_year = datetime.now().year
                current_quarter = ((datetime.now().month - 1) // 3) + 1
                end_period = f"{current_year}{current_quarter:02d}"
            
            if not start_period:
                start_year = datetime.now().year - 2
                start_period = f"{start_year}01"
            
            params = {
                'start_date': start_period,
                'end_date': end_period,
                'item_code1': '111Y003',  # 실질GDP 계절조정
                'cycle_type': 'Q',  # 분기별
                'per_page': '100'
            }
            
            result = self._make_request('StatisticSearch', params)
            
            if result.get('StatisticSearch') and result['StatisticSearch'].get('row'):
                gdp_data = []
                for item in result['StatisticSearch']['row']:
                    try:
                        gdp_data.append({
                            "period": item.get('TIME'),
                            "value": float(item.get('DATA_VALUE', 0)),
                            "unit": item.get('UNIT_NAME', '십억원')
                        })
                    except (ValueError, TypeError):
                        continue
                
                # 성장률 계산
                if len(gdp_data) > 1:
                    latest = gdp_data[-1]
                    previous = gdp_data[-2]
                    growth_rate = ((latest['value'] - previous['value']) / previous['value']) * 100
                else:
                    growth_rate = 0
                
                return {
                    "gdp_data": gdp_data,
                    "latest_gdp": gdp_data[-1] if gdp_data else None,
                    "quarterly_growth_rate": round(growth_rate, 2),
                    "data_source": "Bank of Korea",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": "No GDP data found"}
            
        except Exception as e:
            logger.error(f"Error getting GDP data: {str(e)}")
            return {"error": str(e)}
    
    def get_cpi_data(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """소비자물가지수(CPI) 조회
        
        Args:
            start_date: 시작일 (YYYYMM)
            end_date: 종료일 (YYYYMM)
        """
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m')
            
            params = {
                'start_date': start_date,
                'end_date': end_date,
                'item_code1': '901Y009',  # 소비자물가지수
                'cycle_type': 'M',  # 월별
                'per_page': '100'
            }
            
            result = self._make_request('StatisticSearch', params)
            
            if result.get('StatisticSearch') and result['StatisticSearch'].get('row'):
                cpi_data = []
                for item in result['StatisticSearch']['row']:
                    try:
                        cpi_data.append({
                            "period": item.get('TIME'),
                            "value": float(item.get('DATA_VALUE', 0)),
                            "unit": item.get('UNIT_NAME', '2020=100')
                        })
                    except (ValueError, TypeError):
                        continue
                
                # 인플레이션율 계산 (전년 동월 대비)
                inflation_rate = 0
                if len(cpi_data) >= 12:
                    current = cpi_data[-1]['value']
                    year_ago = cpi_data[-13]['value']
                    inflation_rate = ((current - year_ago) / year_ago) * 100
                
                return {
                    "cpi_data": cpi_data,
                    "latest_cpi": cpi_data[-1] if cpi_data else None,
                    "inflation_rate": round(inflation_rate, 2),
                    "data_source": "Bank of Korea",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": "No CPI data found"}
            
        except Exception as e:
            logger.error(f"Error getting CPI data: {str(e)}")
            return {"error": str(e)}

# 전역 인스턴스
bok_client = BOKAPIClient()

def get_macro_economic_indicators() -> Dict[str, Any]:
    """주요 거시경제 지표 종합 조회"""
    try:
        logger.info("Getting comprehensive macro economic indicators")
        
        # 주요 지표 병렬 조회
        base_rate = bok_client.get_base_rate()
        usd_rate = bok_client.get_exchange_rate("USD")
        gdp_data = bok_client.get_gdp_data()
        cpi_data = bok_client.get_cpi_data()
        
        return {
            "base_interest_rate": base_rate,
            "usd_exchange_rate": usd_rate,
            "gdp": gdp_data,
            "consumer_price_index": cpi_data,
            "data_source": "Bank of Korea ECOS",
            "last_updated": datetime.now().isoformat(),
            "summary": {
                "current_base_rate": base_rate.get("latest_rate", {}).get("rate") if not base_rate.get("error") else "N/A",
                "current_usd_rate": usd_rate.get("latest_rate", {}).get("rate") if not usd_rate.get("error") else "N/A",
                "gdp_growth_rate": gdp_data.get("quarterly_growth_rate") if not gdp_data.get("error") else "N/A",
                "inflation_rate": cpi_data.get("inflation_rate") if not cpi_data.get("error") else "N/A"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting macro economic indicators: {str(e)}")
        return {"error": str(e)}