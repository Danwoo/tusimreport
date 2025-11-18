#!/usr/bin/env python3
"""
Valuation Calculator - DCF & Multiples Analysis
Phase 3: 정량 분석 강화 (전문가 87.5% 요구)
"""

import logging
from typing import Dict, Any, Optional, List
import FinanceDataReader as fdr
from pykrx import stock
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class ValuationCalculator:
    """기업 가치 평가 계산기 - DCF & Multiples"""

    def __init__(self, stock_code: str, company_name: str):
        self.stock_code = stock_code
        self.company_name = company_name

    def calculate_dcf_valuation(
        self,
        wacc: float = 0.085,  # WACC 8.5% (기본값)
        terminal_growth: float = 0.025,  # 영구 성장률 2.5%
        fcf_growth_rate: float = 0.10  # FCF 성장률 10%
    ) -> Dict[str, Any]:
        """
        DCF (Discounted Cash Flow) 밸류에이션

        Args:
            wacc: 가중평균자본비용 (WACC)
            terminal_growth: 영구 성장률
            fcf_growth_rate: FCF 성장률

        Returns:
            DCF 분석 결과 (Fair Value, Upside, etc.)
        """
        try:
            logger.info(f"DCF 밸류에이션 시작: {self.company_name} ({self.stock_code})")

            # 1. 현재가 가져오기
            current_price = self._get_current_price()
            if not current_price:
                return {"error": "현재가 데이터를 가져올 수 없습니다"}

            # 2. 재무 데이터 가져오기 (PyKRX)
            financial_data = self._get_financial_data()
            if not financial_data:
                # 재무 데이터 없으면 간소화된 DCF
                return self._simplified_dcf(current_price, wacc, terminal_growth, fcf_growth_rate)

            # 3. FCF (Free Cash Flow) 추정
            fcf_base = financial_data.get('operating_cash_flow', 0) - financial_data.get('capex', 0)
            if fcf_base <= 0:
                fcf_base = financial_data.get('net_income', 0) * 0.7  # Fallback: NI의 70%

            # 4. 5년 FCF 예측
            fcf_projections = []
            for year in range(1, 6):
                fcf = fcf_base * ((1 + fcf_growth_rate) ** year)
                fcf_projections.append(fcf)

            # 5. Terminal Value 계산
            terminal_fcf = fcf_projections[-1] * (1 + terminal_growth)
            terminal_value = terminal_fcf / (wacc - terminal_growth)

            # 6. 현재가치로 할인
            pv_fcf = []
            for i, fcf in enumerate(fcf_projections, 1):
                pv = fcf / ((1 + wacc) ** i)
                pv_fcf.append(pv)

            pv_terminal = terminal_value / ((1 + wacc) ** 5)

            # 7. Enterprise Value
            enterprise_value = sum(pv_fcf) + pv_terminal

            # 8. Equity Value (순차입금 제외)
            net_debt = financial_data.get('total_debt', 0) - financial_data.get('cash', 0)
            equity_value = enterprise_value - net_debt

            # 9. Fair Value per Share
            shares_outstanding = financial_data.get('shares_outstanding', 1)
            fair_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

            # 10. Upside/Downside 계산
            if fair_value_per_share > 0:
                upside_pct = ((fair_value_per_share / current_price) - 1) * 100
                valuation_status = "저평가" if upside_pct > 0 else "고평가"
            else:
                upside_pct = 0
                valuation_status = "분석 불가"

            logger.info(f"DCF Fair Value: {fair_value_per_share:,.0f}원 (Upside: {upside_pct:+.1f}%)")

            return {
                "method": "DCF",
                "fair_value": int(fair_value_per_share),
                "current_price": int(current_price),
                "upside_pct": round(upside_pct, 1),
                "valuation_status": valuation_status,
                "wacc": wacc,
                "terminal_growth": terminal_growth,
                "fcf_growth_rate": fcf_growth_rate,
                "fcf_projections": [int(f) for f in fcf_projections],
                "enterprise_value": int(enterprise_value),
                "equity_value": int(equity_value)
            }

        except Exception as e:
            logger.error(f"DCF 계산 오류: {str(e)}")
            return {"error": str(e)}

    def _simplified_dcf(
        self,
        current_price: float,
        wacc: float,
        terminal_growth: float,
        fcf_growth_rate: float
    ) -> Dict[str, Any]:
        """간소화된 DCF (재무 데이터 없을 때)"""
        logger.warning("재무 데이터 부족 - 간소화된 DCF 사용")

        # 현재 시가총액 기반 추정
        market_cap = self._get_market_cap()
        if not market_cap:
            return {"error": "시가총액 데이터 없음"}

        # 가정: 시가총액의 8%를 연간 FCF로 추정
        fcf_base = market_cap * 0.08

        # 5년 FCF 예측
        fcf_projections = [fcf_base * ((1 + fcf_growth_rate) ** year) for year in range(1, 6)]

        # Terminal Value
        terminal_fcf = fcf_projections[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)

        # 현재가치 할인
        pv_fcf = [fcf / ((1 + wacc) ** i) for i, fcf in enumerate(fcf_projections, 1)]
        pv_terminal = terminal_value / ((1 + wacc) ** 5)

        # Enterprise Value = 현재 시가총액 유사
        enterprise_value = sum(pv_fcf) + pv_terminal
        shares_outstanding = self._get_shares_outstanding()

        fair_value_per_share = enterprise_value / shares_outstanding if shares_outstanding > 0 else 0
        upside_pct = ((fair_value_per_share / current_price) - 1) * 100 if fair_value_per_share > 0 else 0

        return {
            "method": "DCF (Simplified)",
            "fair_value": int(fair_value_per_share),
            "current_price": int(current_price),
            "upside_pct": round(upside_pct, 1),
            "valuation_status": "저평가" if upside_pct > 0 else "고평가",
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "fcf_growth_rate": fcf_growth_rate,
            "note": "재무 데이터 부족으로 간소화된 방법 사용"
        }

    def calculate_multiples_valuation(self, sector: str = None) -> Dict[str, Any]:
        """
        멀티플 밸류에이션 (PER/PBR/PSR/EV-EBITDA)

        Args:
            sector: 업종 코드 (비교 대상)

        Returns:
            멀티플 분석 결과
        """
        try:
            logger.info(f"멀티플 밸류에이션 시작: {self.company_name}")

            # 1. 현재가 및 기본 데이터
            current_price = self._get_current_price()
            if not current_price:
                return {"error": "현재가 데이터를 가져올 수 없습니다"}

            # 2. 현재 멀티플 가져오기
            current_multiples = self._get_current_multiples()
            if not current_multiples:
                return {"error": "멀티플 데이터를 가져올 수 없습니다"}

            # 3. 업종 평균 가져오기
            sector_avg = self._get_sector_average_multiples(sector)

            # 4. Fair Value 계산 (각 멀티플별)
            fair_values = {}

            # PER 기준
            if current_multiples.get('PER') and sector_avg.get('PER'):
                eps = current_price / current_multiples['PER'] if current_multiples['PER'] > 0 else 0
                fair_values['per_based'] = eps * sector_avg['PER'] if eps > 0 else 0

            # PBR 기준
            if current_multiples.get('PBR') and sector_avg.get('PBR'):
                bps = current_price / current_multiples['PBR'] if current_multiples['PBR'] > 0 else 0
                fair_values['pbr_based'] = bps * sector_avg['PBR'] if bps > 0 else 0

            # PSR 기준 (선택)
            if current_multiples.get('PSR') and sector_avg.get('PSR'):
                sps = current_price / current_multiples['PSR'] if current_multiples['PSR'] > 0 else 0
                fair_values['psr_based'] = sps * sector_avg['PSR'] if sps > 0 else 0

            # 5. 평균 Fair Value
            valid_fvs = [v for v in fair_values.values() if v > 0]
            avg_fair_value = sum(valid_fvs) / len(valid_fvs) if valid_fvs else 0

            # 6. Upside 계산
            upside_pct = ((avg_fair_value / current_price) - 1) * 100 if avg_fair_value > 0 else 0

            logger.info(f"멀티플 Fair Value: {avg_fair_value:,.0f}원 (Upside: {upside_pct:+.1f}%)")

            return {
                "method": "Multiples",
                "current_price": int(current_price),
                "current_multiples": current_multiples,
                "sector_average": sector_avg,
                "fair_values": {k: int(v) for k, v in fair_values.items()},
                "average_fair_value": int(avg_fair_value),
                "upside_pct": round(upside_pct, 1),
                "valuation_status": "저평가" if upside_pct > 0 else "고평가"
            }

        except Exception as e:
            logger.error(f"멀티플 계산 오류: {str(e)}")
            return {"error": str(e)}

    def get_integrated_valuation(self) -> Dict[str, Any]:
        """
        통합 밸류에이션 (DCF + Multiples + AI 종합)

        Returns:
            3가지 방법 통합 결과
        """
        try:
            logger.info(f"통합 밸류에이션 시작: {self.company_name}")

            # 1. DCF 밸류에이션
            dcf_result = self.calculate_dcf_valuation()

            # 2. 멀티플 밸류에이션
            multiples_result = self.calculate_multiples_valuation()

            # 3. 현재가
            current_price = self._get_current_price()

            # 4. 각 방법별 Fair Value 수집
            valuations = []

            if "error" not in dcf_result and dcf_result.get('fair_value', 0) > 0:
                valuations.append({
                    "method": "DCF",
                    "fair_value": dcf_result['fair_value'],
                    "upside": dcf_result['upside_pct'],
                    "weight": 0.4  # DCF 40% 가중치
                })

            if "error" not in multiples_result and multiples_result.get('average_fair_value', 0) > 0:
                valuations.append({
                    "method": "Multiples",
                    "fair_value": multiples_result['average_fair_value'],
                    "upside": multiples_result['upside_pct'],
                    "weight": 0.35  # 멀티플 35% 가중치
                })

            # 5. 가중 평균 Fair Value
            if valuations:
                total_weight = sum(v['weight'] for v in valuations)
                weighted_fair_value = sum(v['fair_value'] * v['weight'] for v in valuations) / total_weight
                weighted_upside = ((weighted_fair_value / current_price) - 1) * 100
            else:
                weighted_fair_value = 0
                weighted_upside = 0

            return {
                "current_price": int(current_price),
                "valuations": valuations,
                "weighted_fair_value": int(weighted_fair_value),
                "weighted_upside": round(weighted_upside, 1),
                "valuation_status": "저평가" if weighted_upside > 0 else "고평가",
                "dcf_detail": dcf_result,
                "multiples_detail": multiples_result
            }

        except Exception as e:
            logger.error(f"통합 밸류에이션 오류: {str(e)}")
            return {"error": str(e)}

    # ============ Helper Methods ============

    def _get_current_price(self) -> Optional[float]:
        """현재가 가져오기"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

            df = fdr.DataReader(self.stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return float(df['Close'].iloc[-1])
            return None
        except Exception as e:
            logger.error(f"현재가 조회 실패: {str(e)}")
            return None

    def _get_market_cap(self) -> Optional[float]:
        """시가총액 가져오기"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_cap_by_ticker(today, market="ALL")
            if self.stock_code in df.index:
                return float(df.loc[self.stock_code, '시가총액'])
            return None
        except Exception as e:
            logger.error(f"시가총액 조회 실패: {str(e)}")
            return None

    def _get_shares_outstanding(self) -> float:
        """발행주식수 가져오기"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_cap_by_ticker(today, market="ALL")
            if self.stock_code in df.index:
                return float(df.loc[self.stock_code, '상장주식수'])
            return 1.0  # 0으로 나누기 방지
        except Exception as e:
            logger.error(f"발행주식수 조회 실패: {str(e)}")
            return 1.0

    def _get_financial_data(self) -> Optional[Dict[str, float]]:
        """재무 데이터 가져오기 (간소화)"""
        try:
            # PyKRX를 통해 기본 재무 데이터 수집
            today = datetime.now().strftime("%Y%m%d")

            # 시가총액, 발행주식수
            cap_df = stock.get_market_cap_by_ticker(today, market="ALL")
            if self.stock_code not in cap_df.index:
                return None

            shares = float(cap_df.loc[self.stock_code, '상장주식수'])
            market_cap = float(cap_df.loc[self.stock_code, '시가총액'])

            # PER, PBR 등 멀티플에서 역산
            fundamental = stock.get_market_fundamental_by_ticker(today, market="ALL")
            if self.stock_code not in fundamental.index:
                return None

            per = float(fundamental.loc[self.stock_code, 'PER'])
            pbr = float(fundamental.loc[self.stock_code, 'PBR'])

            current_price = self._get_current_price()
            if not current_price:
                return None

            # EPS, BPS 역산
            eps = current_price / per if per > 0 else 0
            bps = current_price / pbr if pbr > 0 else 0

            # 순이익 추정
            net_income = eps * shares if eps > 0 else 0

            return {
                "net_income": net_income,
                "operating_cash_flow": net_income * 1.2,  # 추정: NI의 120%
                "capex": net_income * 0.3,  # 추정: NI의 30%
                "total_debt": market_cap * 0.3,  # 추정: 시총의 30%
                "cash": market_cap * 0.15,  # 추정: 시총의 15%
                "shares_outstanding": shares
            }

        except Exception as e:
            logger.error(f"재무 데이터 조회 실패: {str(e)}")
            return None

    def _get_current_multiples(self) -> Dict[str, float]:
        """현재 멀티플 가져오기"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_fundamental_by_ticker(today, market="ALL")

            if self.stock_code not in df.index:
                return {}

            return {
                "PER": float(df.loc[self.stock_code, 'PER']),
                "PBR": float(df.loc[self.stock_code, 'PBR']),
                "PSR": float(df.loc[self.stock_code, 'PSR']) if 'PSR' in df.columns else 0,
                "DIV": float(df.loc[self.stock_code, 'DIV']) if 'DIV' in df.columns else 0
            }

        except Exception as e:
            logger.error(f"멀티플 조회 실패: {str(e)}")
            return {}

    def _get_sector_average_multiples(self, sector: str = None) -> Dict[str, float]:
        """업종 평균 멀티플 (간소화: KOSPI 평균 사용)"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            df = stock.get_market_fundamental_by_ticker(today, market="KOSPI")

            if df is None or df.empty:
                # Fallback: 기본값
                return {
                    "PER": 15.0,
                    "PBR": 1.5,
                    "PSR": 1.2,
                    "DIV": 2.0
                }

            # KOSPI 평균 계산
            return {
                "PER": float(df['PER'].median()),
                "PBR": float(df['PBR'].median()),
                "PSR": float(df['PSR'].median()) if 'PSR' in df.columns else 1.2,
                "DIV": float(df['DIV'].median()) if 'DIV' in df.columns else 2.0
            }

        except Exception as e:
            logger.error(f"업종 평균 조회 실패: {str(e)}")
            # Fallback
            return {
                "PER": 15.0,
                "PBR": 1.5,
                "PSR": 1.2,
                "DIV": 2.0
            }


# 편의 함수
def get_valuation_analysis(stock_code: str, company_name: str) -> Dict[str, Any]:
    """통합 밸류에이션 분석 실행"""
    calculator = ValuationCalculator(stock_code, company_name)
    return calculator.get_integrated_valuation()


if __name__ == "__main__":
    # 테스트
    result = get_valuation_analysis("005930", "삼성전자")

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
