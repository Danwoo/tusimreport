#!/usr/bin/env python3
"""
DART (전자공시) API 클라이언트
한국 상장기업의 공시 데이터 수집을 위한 API 클라이언트

DART OpenAPI: https://opendart.fss.or.kr/
"""

import logging
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
import zipfile
import io

logger = logging.getLogger(__name__)

class DARTAPIClient:
    """DART OpenAPI 클라이언트"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # 무료 API 키
        self.base_url = "https://opendart.fss.or.kr/api"
        self.session = requests.Session()
        
        # 요청 헤더 설정
        self.session.headers.update({
            'User-Agent': 'TuSimReport/1.0',
            'Accept': 'application/json'
        })
    
    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 실행"""
        params['crtfc_key'] = self.api_key
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Rate limiting
            time.sleep(0.1)
            
            return response.json()
            
        except Exception as e:
            logger.error(f"DART API request failed: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_corp_code(self, corp_name: str) -> Optional[str]:
        """기업명으로 고유번호(corp_code) 조회"""
        try:
            # 기업 개요 조회
            params = {
                'corp_name': corp_name
            }
            
            result = self._make_request('company.json', params)
            
            if result.get('status') == '000':
                return result.get('corp_code')
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting corp_code for {corp_name}: {str(e)}")
            return None
    
    def get_company_info(self, corp_code: str) -> Dict[str, Any]:
        """기업 개요 조회"""
        try:
            params = {
                'corp_code': corp_code
            }
            
            result = self._make_request('company.json', params)
            
            if result.get('status') == '000':
                return {
                    "corp_name": result.get('corp_name'),
                    "corp_name_eng": result.get('corp_name_eng'),
                    "stock_name": result.get('stock_name'),
                    "stock_code": result.get('stock_code'),
                    "ceo_nm": result.get('ceo_nm'),
                    "corp_cls": result.get('corp_cls'),
                    "jurir_no": result.get('jurir_no'),
                    "bizr_no": result.get('bizr_no'),
                    "adres": result.get('adres'),
                    "hm_url": result.get('hm_url'),
                    "ir_url": result.get('ir_url'),
                    "phn_no": result.get('phn_no'),
                    "fax_no": result.get('fax_no'),
                    "induty_code": result.get('induty_code'),
                    "est_dt": result.get('est_dt'),
                    "acc_mt": result.get('acc_mt')
                }
            
            return {"error": f"Company info not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting company info: {str(e)}")
            return {"error": str(e)}
    
    def get_financial_statements(self, corp_code: str, bsns_year: str, reprt_code: str = "11013") -> Dict[str, Any]:
        """재무제표 조회
        
        Args:
            corp_code: 고유번호
            bsns_year: 사업연도 (YYYY)
            reprt_code: 보고서 코드 (11013: 1분기보고서, 11012: 반기보고서, 11011: 3분기보고서, 11014: 사업보고서)
        """
        try:
            params = {
                'corp_code': corp_code,
                'bsns_year': bsns_year,
                'reprt_code': reprt_code
            }
            
            result = self._make_request('fnlttSinglAcnt.json', params)
            
            if result.get('status') == '000' and result.get('list'):
                financial_data = {}
                
                for item in result['list']:
                    account_nm = item.get('account_nm', '')
                    thstrm_amount = item.get('thstrm_amount', '0').replace(',', '')
                    
                    try:
                        amount = float(thstrm_amount) if thstrm_amount != '-' else 0
                        financial_data[account_nm] = amount
                    except (ValueError, TypeError):
                        financial_data[account_nm] = 0
                
                return {
                    "year": bsns_year,
                    "report_code": reprt_code,
                    "financial_data": financial_data,
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"Financial statements not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting financial statements: {str(e)}")
            return {"error": str(e)}
    
    def get_recent_disclosures(self, corp_code: str, page_count: int = 10) -> List[Dict[str, Any]]:
        """최근 공시 조회"""
        try:
            end_dt = datetime.now().strftime('%Y%m%d')
            bgn_dt = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            
            params = {
                'corp_code': corp_code,
                'bgn_de': bgn_dt,
                'end_de': end_dt,
                'page_count': str(page_count)
            }
            
            result = self._make_request('list.json', params)
            
            if result.get('status') == '000' and result.get('list'):
                disclosures = []
                
                for item in result['list']:
                    disclosures.append({
                        "rcept_no": item.get('rcept_no'),
                        "corp_cls": item.get('corp_cls'),
                        "corp_name": item.get('corp_name'),
                        "corp_code": item.get('corp_code'),
                        "stock_code": item.get('stock_code'),
                        "report_nm": item.get('report_nm'),
                        "rcept_dt": item.get('rcept_dt'),
                        "flr_nm": item.get('flr_nm'),
                        "rm": item.get('rm')
                    })
                
                return disclosures
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting recent disclosures: {str(e)}")
            return []
    
    def get_stock_code_to_corp_code_mapping(self, stock_code: str) -> Optional[str]:
        """주식코드로 고유번호 찾기 (기업개요에서 역조회)"""
        try:
            # 기업들의 목록에서 주식코드로 찾기 (실제로는 DB나 캐시 필요)
            # 여기서는 일반적인 대기업들의 매핑을 하드코딩
            stock_to_corp_mapping = {
                "005930": "00126380",  # 삼성전자
                "000660": "00164779",  # SK하이닉스
                "035420": "00234006",  # 네이버
                "035720": "00159764",  # 카카오
                "005380": "00126626",  # 현대차
                "051910": "00227007",  # LG화학
                "006400": "00139507",  # 삼성SDI
                "207940": "01020055",  # 삼성바이오로직스
            }
            
            return stock_to_corp_mapping.get(stock_code)
            
        except Exception as e:
            logger.error(f"Error mapping stock code {stock_code}: {str(e)}")
            return None

# 전역 인스턴스
dart_client = DARTAPIClient()

def get_comprehensive_company_data(stock_code: str) -> Dict[str, Any]:
    """주식코드로 종합 기업 데이터 조회"""
    try:
        logger.info(f"Getting comprehensive DART data for {stock_code}")
        
        # 1. 주식코드 -> 고유번호 매핑
        corp_code = dart_client.get_stock_code_to_corp_code_mapping(stock_code)
        
        if not corp_code:
            return {"error": f"Corp code not found for stock {stock_code}"}
        
        # 2. 기업 개요 조회
        company_info = dart_client.get_company_info(corp_code)
        
        if company_info.get("error"):
            return {"error": f"Company info error: {company_info['error']}"}
        
        # 3. 최근 재무제표 조회 (최근 연도)
        current_year = str(datetime.now().year)
        prev_year = str(datetime.now().year - 1)
        
        financial_current = dart_client.get_financial_statements(corp_code, current_year, "11014")
        financial_prev = dart_client.get_financial_statements(corp_code, prev_year, "11014")
        
        # 4. 최근 공시 조회
        recent_disclosures = dart_client.get_recent_disclosures(corp_code, 20)
        
        return {
            "stock_code": stock_code,
            "corp_code": corp_code,
            "company_info": company_info,
            "financial_statements": {
                "current_year": financial_current,
                "previous_year": financial_prev
            },
            "recent_disclosures": recent_disclosures,
            "data_source": "DART OpenAPI",
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting comprehensive company data: {str(e)}")
        return {"error": str(e)}