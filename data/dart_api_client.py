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
        self.api_key = (
            api_key or "f8b3ea29d07f35057df6de77d72e84d726357c6b"
        )  # 무료 API 키
        self.base_url = "https://opendart.fss.or.kr/api"
        self.session = requests.Session()

        # 요청 헤더 설정
        self.session.headers.update(
            {"User-Agent": "TuSimReport/1.0", "Accept": "application/json"}
        )

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 실행"""
        params["crtfc_key"] = self.api_key

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
            params = {"corp_name": corp_name}

            result = self._make_request("company.json", params)

            if result.get("status") == "000":
                return result.get("corp_code")

            return None

        except Exception as e:
            logger.error(f"Error getting corp_code for {corp_name}: {str(e)}")
            return None

    def get_company_info(self, corp_code: str) -> Dict[str, Any]:
        """기업 개요 조회"""
        try:
            params = {"corp_code": corp_code}

            result = self._make_request("company.json", params)

            if result.get("status") == "000":
                return {
                    "corp_name": result.get("corp_name"),
                    "corp_name_eng": result.get("corp_name_eng"),
                    "stock_name": result.get("stock_name"),
                    "stock_code": result.get("stock_code"),
                    "ceo_nm": result.get("ceo_nm"),
                    "corp_cls": result.get("corp_cls"),
                    "jurir_no": result.get("jurir_no"),
                    "bizr_no": result.get("bizr_no"),
                    "adres": result.get("adres"),
                    "hm_url": result.get("hm_url"),
                    "ir_url": result.get("ir_url"),
                    "phn_no": result.get("phn_no"),
                    "fax_no": result.get("fax_no"),
                    "induty_code": result.get("induty_code"),
                    "est_dt": result.get("est_dt"),
                    "acc_mt": result.get("acc_mt"),
                }

            return {
                "error": f"Company info not found: {result.get('message', 'Unknown error')}"
            }

        except Exception as e:
            logger.error(f"Error getting company info: {str(e)}")
            return {"error": str(e)}

    def get_financial_statements(
        self, corp_code: str, bsns_year: str, reprt_code: str = "11013"
    ) -> Dict[str, Any]:
        """재무제표 조회

        Args:
            corp_code: 고유번호
            bsns_year: 사업연도 (YYYY)
            reprt_code: 보고서 코드 (11013: 1분기보고서, 11012: 반기보고서, 11011: 3분기보고서, 11014: 사업보고서)
        """
        try:
            params = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
            }

            result = self._make_request("fnlttSinglAcnt.json", params)

            if result.get("status") == "000" and result.get("list"):
                financial_data = {}

                for item in result["list"]:
                    account_nm = item.get("account_nm", "")
                    thstrm_amount = item.get("thstrm_amount", "0").replace(",", "")

                    try:
                        amount = float(thstrm_amount) if thstrm_amount != "-" else 0
                        financial_data[account_nm] = amount
                    except (ValueError, TypeError):
                        financial_data[account_nm] = 0

                return {
                    "year": bsns_year,
                    "report_code": reprt_code,
                    "financial_data": financial_data,
                    "last_updated": datetime.now().isoformat(),
                }

            return {
                "error": f"Financial statements not found: {result.get('message', 'Unknown error')}"
            }

        except Exception as e:
            logger.error(f"Error getting financial statements: {str(e)}")
            return {"error": str(e)}

    def get_recent_disclosures(
        self, corp_code: str, page_count: int = 10
    ) -> List[Dict[str, Any]]:
        """최근 공시 조회"""
        try:
            end_dt = datetime.now().strftime("%Y%m%d")
            bgn_dt = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

            params = {
                "corp_code": corp_code,
                "bgn_de": bgn_dt,
                "end_de": end_dt,
                "page_count": str(page_count),
            }

            result = self._make_request("list.json", params)

            if result.get("status") == "000" and result.get("list"):
                disclosures = []

                for item in result["list"]:
                    disclosures.append(
                        {
                            "rcept_no": item.get("rcept_no"),
                            "corp_cls": item.get("corp_cls"),
                            "corp_name": item.get("corp_name"),
                            "corp_code": item.get("corp_code"),
                            "stock_code": item.get("stock_code"),
                            "report_nm": item.get("report_nm"),
                            "rcept_dt": item.get("rcept_dt"),
                            "flr_nm": item.get("flr_nm"),
                            "rm": item.get("rm"),
                        }
                    )

                return disclosures

            return []

        except Exception as e:
            logger.error(f"Error getting recent disclosures: {str(e)}")
            return []

    def get_stock_code_to_corp_code_mapping(self, stock_code: str) -> Optional[str]:
        """주식코드로 고유번호 찾기 - 실제 DART API 사용"""
        try:
            # DART corpcode.xml 다운로드 및 파싱으로 실제 매핑 찾기
            return self._fetch_corp_code_from_dart_api(stock_code)

        except Exception as e:
            logger.error(f"Error mapping stock code {stock_code}: {str(e)}")
            return None

    def _fetch_corp_code_from_dart_api(self, stock_code: str) -> Optional[str]:
        """실제 DART API에서 corp_code 조회"""
        try:
            # DART 고유번호 다운로드 API 사용
            url = f"{self.base_url}/corpCode.xml"
            params = {"crtfc_key": self.api_key}
            
            logger.info(f"Fetching corp_code for {stock_code} from DART API")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                # ZIP 파일 압축 해제
                import zipfile
                import xml.etree.ElementTree as ET
                
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                    xml_content = zip_file.read('CORPCODE.xml')
                    
                # XML 파싱하여 stock_code 매칭
                root = ET.fromstring(xml_content)
                
                for company in root.findall('.//list'):
                    stock_code_elem = company.find('stock_code')
                    corp_code_elem = company.find('corp_code')
                    
                    if (stock_code_elem is not None and 
                        corp_code_elem is not None and
                        stock_code_elem.text and
                        stock_code_elem.text.strip() == stock_code):
                        
                        corp_code = corp_code_elem.text.strip()
                        logger.info(f"Found corp_code {corp_code} for stock {stock_code}")
                        return corp_code
                
                logger.warning(f"Stock code {stock_code} not found in DART database")
                return None
            else:
                logger.error(f"Failed to download DART corp_code data: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching corp_code from DART API: {str(e)}")
            return None

    def get_major_shareholder_info(self, corp_code: str, bsns_year: str = None) -> Dict[str, Any]:
        """최대주주 및 특수관계인 정보 조회"""
        try:
            if not bsns_year:
                bsns_year = str(datetime.now().year - 1)  # 전년도 데이터
            
            params = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": "11011"  # 3분기보고서
            }
            
            result = self._make_request("hyslrSttus.json", params)
            
            if result.get("status") == "000" and result.get("list"):
                shareholders = []
                for item in result["list"]:
                    shareholders.append({
                        "nm": item.get("nm"),  # 성명(명칭)
                        "relate": item.get("relate"),  # 관계
                        "stock_knd": item.get("stock_knd"),  # 주식종류
                        "bsis_posesn_stock_co": item.get("bsis_posesn_stock_co", "0").replace(",", ""),
                        "bsis_posesn_stock_qota_rt": item.get("bsis_posesn_stock_qota_rt", "0"),
                        "trmend_posesn_stock_co": item.get("trmend_posesn_stock_co", "0").replace(",", ""),
                        "trmend_posesn_stock_qota_rt": item.get("trmend_posesn_stock_qota_rt", "0")
                    })
                
                return {
                    "year": bsns_year,
                    "major_shareholders": shareholders,
                    "data_source": "DART - Major Shareholders",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"Major shareholder info not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting major shareholder info: {str(e)}")
            return {"error": str(e)}

    def get_executive_info(self, corp_code: str, bsns_year: str = None) -> Dict[str, Any]:
        """임원 현황 조회"""
        try:
            if not bsns_year:
                bsns_year = str(datetime.now().year - 1)
            
            params = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": "11011"
            }
            
            result = self._make_request("exctvSttus.json", params)
            
            if result.get("status") == "000" and result.get("list"):
                executives = []
                for item in result["list"]:
                    executives.append({
                        "nm": item.get("nm"),  # 성명
                        "sexdstn": item.get("sexdstn"),  # 성별
                        "birth_ym": item.get("birth_ym"),  # 생년월
                        "ofcps": item.get("ofcps"),  # 직위
                        "rgist_exctv_at": item.get("rgist_exctv_at"),  # 등기임원여부
                        "tenure_bgn_dt": item.get("tenure_bgn_dt"),  # 임기시작일
                        "tenure_end_dt": item.get("tenure_end_dt"),  # 임기만료일
                        "crrs": item.get("crrs"),  # 주요경력
                        "main_career": item.get("main_career"),  # 담당업무
                        "mxmm_shrholdr_relate": item.get("mxmm_shrholdr_relate")  # 최대주주와의관계
                    })
                
                return {
                    "year": bsns_year,
                    "executives": executives,
                    "total_executives": len(executives),
                    "data_source": "DART - Executive Status",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"Executive info not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting executive info: {str(e)}")
            return {"error": str(e)}

    def get_dividend_info(self, corp_code: str, bsns_year: str = None) -> Dict[str, Any]:
        """배당 정보 조회"""
        try:
            if not bsns_year:
                bsns_year = str(datetime.now().year - 1)
            
            params = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": "11011"
            }
            
            result = self._make_request("alotMatter.json", params)
            
            if result.get("status") == "000" and result.get("list"):
                dividends = []
                for item in result["list"]:
                    dividends.append({
                        "se": item.get("se"),  # 구분
                        "stock_knd": item.get("stock_knd"),  # 주식종류
                        "thstrm": item.get("thstrm", "0").replace(",", ""),  # 당기
                        "frmtrm": item.get("frmtrm", "0").replace(",", ""),  # 전기
                        "lwfr": item.get("lwfr", "0").replace(",", "")  # 전전기
                    })
                
                return {
                    "year": bsns_year,
                    "dividend_info": dividends,
                    "data_source": "DART - Dividend Information",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"Dividend info not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting dividend info: {str(e)}")
            return {"error": str(e)}

    def get_audit_opinion(self, corp_code: str, bsns_year: str = None) -> Dict[str, Any]:
        """회계감사 의견 조회"""
        try:
            if not bsns_year:
                bsns_year = str(datetime.now().year - 1)
            
            params = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": "11011"
            }
            
            result = self._make_request("acntAudpnOp.json", params)
            
            if result.get("status") == "000" and result.get("list"):
                audit_opinions = []
                for item in result["list"]:
                    audit_opinions.append({
                        "rcept_no": item.get("rcept_no"),
                        "bsns_year": item.get("bsns_year"),
                        "corp_code": item.get("corp_code"),
                        "audpn_nm": item.get("audpn_nm"),  # 감사의견명
                        "audpn": item.get("audpn"),  # 감사의견
                        "auditor": item.get("auditor"),  # 감사인
                    })
                
                return {
                    "year": bsns_year,
                    "audit_opinions": audit_opinions,
                    "data_source": "DART - Audit Opinion",
                    "last_updated": datetime.now().isoformat()
                }
            
            return {"error": f"Audit opinion not found: {result.get('message', 'Unknown error')}"}
            
        except Exception as e:
            logger.error(f"Error getting audit opinion: {str(e)}")
            return {"error": str(e)}

    def analyze_esg_factors(self, corp_code: str, bsns_year: str = None) -> Dict[str, Any]:
        """ESG 요소 분석 (공시 데이터 기반)"""
        try:
            if not bsns_year:
                bsns_year = str(datetime.now().year - 1)
            
            # ESG 관련 데이터 수집
            esg_data = {}
            
            # Environmental (환경): 감사의견, 회계투명성
            audit_info = self.get_audit_opinion(corp_code, bsns_year)
            if not audit_info.get("error"):
                esg_data["environmental_governance"] = audit_info
            
            # Social (사회): 직원 현황, 임원 다양성
            executive_info = self.get_executive_info(corp_code, bsns_year)
            if not executive_info.get("error"):
                esg_data["executive_diversity"] = executive_info
            
            # Governance (지배구조): 주주 구성, 배당
            shareholder_info = self.get_major_shareholder_info(corp_code, bsns_year)
            if not shareholder_info.get("error"):
                esg_data["governance_structure"] = shareholder_info
            
            dividend_info = self.get_dividend_info(corp_code, bsns_year)
            if not dividend_info.get("error"):
                esg_data["shareholder_returns"] = dividend_info
            
            # ESG 점수 계산 (간단한 지표 기반)
            esg_score = self._calculate_esg_score(esg_data)
            
            return {
                "corp_code": corp_code,
                "year": bsns_year,
                "esg_analysis": esg_data,
                "esg_score": esg_score,
                "analysis_timestamp": datetime.now().isoformat(),
                "data_source": "DART - ESG Analysis"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing ESG factors: {str(e)}")
            return {"error": str(e)}

    def _calculate_esg_score(self, esg_data: Dict[str, Any]) -> Dict[str, Any]:
        """ESG 점수 계산 (기본적인 지표 기반)"""
        try:
            scores = {"E": 0, "S": 0, "G": 0, "total": 0}
            
            # Environmental Score (감사의견 기반)
            if "environmental_governance" in esg_data:
                audit_data = esg_data["environmental_governance"]
                if audit_data.get("audit_opinions"):
                    for opinion in audit_data["audit_opinions"]:
                        if "적정" in opinion.get("audpn", ""):
                            scores["E"] += 30
                        else:
                            scores["E"] += 10
            
            # Social Score (임원 다양성 기반)
            if "executive_diversity" in esg_data:
                exec_data = esg_data["executive_diversity"]
                if exec_data.get("executives"):
                    executives = exec_data["executives"]
                    gender_diversity = len(set(exec.get("sexdstn", "") for exec in executives if exec.get("sexdstn")))
                    scores["S"] += min(gender_diversity * 15, 30)
            
            # Governance Score (지배구조 기반)
            if "governance_structure" in esg_data:
                governance_data = esg_data["governance_structure"]
                if governance_data.get("major_shareholders"):
                    scores["G"] += 20
            
            if "shareholder_returns" in esg_data:
                dividend_data = esg_data["shareholder_returns"]
                if dividend_data.get("dividend_info"):
                    scores["G"] += 20
            
            # 총점 계산
            scores["total"] = scores["E"] + scores["S"] + scores["G"]
            
            return scores
            
        except Exception as e:
            logger.error(f"Error calculating ESG score: {str(e)}")
            return {"E": 0, "S": 0, "G": 0, "total": 0, "error": str(e)}


# 전역 인스턴스
dart_client = DARTAPIClient(api_key="f8b3ea29d07f35057df6de77d72e84d726357c6b")


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

        financial_current = dart_client.get_financial_statements(
            corp_code, current_year, "11014"
        )
        financial_prev = dart_client.get_financial_statements(
            corp_code, prev_year, "11014"
        )

        # 4. 최근 공시 조회
        recent_disclosures = dart_client.get_recent_disclosures(corp_code, 20)

        return {
            "stock_code": stock_code,
            "corp_code": corp_code,
            "company_info": company_info,
            "financial_statements": {
                "current_year": financial_current,
                "previous_year": financial_prev,
            },
            "recent_disclosures": recent_disclosures,
            "data_source": "DART OpenAPI",
            "last_updated": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting comprehensive company data: {str(e)}")
        return {"error": str(e)}
