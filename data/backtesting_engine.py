#!/usr/bin/env python3
"""
Backtesting Engine
투자 의견의 역사적 정확도를 검증하는 백테스팅 시스템

핵심 기능:
1. 분석 결과 저장 (투자 의견 + 목표가)
2. 3개월 후 실제 결과 검증
3. 승률 및 평균 수익률 계산
4. DCF Fair Value 정확도 검증
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)


class BacktestingEngine:
    """
    백테스팅 엔진 - 투자 의견의 역사적 정확도 검증

    데이터 구조:
    {
        "stock_code": "005930",
        "company_name": "삼성전자",
        "analysis_date": "2025-11-18",
        "investment_opinion": {
            "decision": "BUY",
            "confidence": 78,
            "current_price": 70000,
            "target_price_3m": 80500,
            "target_percentage": 15.0
        },
        "actual_result": {
            "verification_date": "2026-02-18",
            "actual_price": 82000,
            "actual_return": 17.1,
            "prediction_correct": true
        }
    }
    """

    def __init__(self, history_dir: str = None):
        """백테스팅 엔진 초기화

        Args:
            history_dir: 분석 결과 저장 디렉토리 (기본: data/backtest_history)
        """
        if history_dir is None:
            # 프로젝트 루트 기준 경로
            project_root = Path(__file__).parent.parent
            history_dir = project_root / "data" / "backtest_history"

        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"BacktestingEngine initialized. History dir: {self.history_dir}")

    def save_analysis_result(
        self,
        stock_code: str,
        company_name: str,
        investment_opinion: Dict[str, Any],
        current_price: float,
        target_prices: Dict[str, Any]
    ) -> bool:
        """분석 결과를 백테스팅용으로 저장

        Args:
            stock_code: 종목 코드
            company_name: 회사명
            investment_opinion: 투자 의견 (decision, confidence, key_reasons)
            current_price: 현재 주가
            target_prices: 목표가 (3_months, 6_months, 12_months)

        Returns:
            bool: 저장 성공 여부
        """
        try:
            analysis_date = datetime.now()

            # 백테스팅 레코드 생성
            record = {
                "stock_code": stock_code,
                "company_name": company_name,
                "analysis_date": analysis_date.isoformat(),
                "investment_opinion": {
                    "decision": investment_opinion.get('decision', 'N/A'),
                    "confidence": investment_opinion.get('confidence', 0),
                    "current_price": current_price,
                    "target_price_3m": target_prices.get('3_months', {}).get('price', 0),
                    "target_percentage_3m": target_prices.get('3_months', {}).get('percentage', 0),
                    "key_reasons": investment_opinion.get('key_reasons', [])
                },
                "actual_result": None  # 3개월 후 검증 시 업데이트
            }

            # 파일명: {종목코드}_{날짜}.json
            filename = f"{stock_code}_{analysis_date.strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self.history_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved backtesting record: {filename}")
            return True

        except Exception as e:
            logger.error(f"Error saving backtesting record: {str(e)}")
            return False

    def verify_old_predictions(self) -> List[Dict[str, Any]]:
        """3개월 이상 경과한 예측들을 검증

        Returns:
            List[Dict]: 검증된 예측 결과 목록
        """
        verified_records = []

        try:
            # 3개월 전 날짜
            three_months_ago = datetime.now() - timedelta(days=90)

            # 모든 백테스팅 레코드 로드
            for filepath in self.history_dir.glob("*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        record = json.load(f)

                    # 이미 검증된 레코드는 스킵
                    if record.get('actual_result') is not None:
                        continue

                    # 분석 날짜 파싱
                    analysis_date = datetime.fromisoformat(record['analysis_date'])

                    # 3개월 이상 경과했는지 확인
                    if analysis_date >= three_months_ago:
                        continue

                    # 실제 주가 데이터 가져오기
                    stock_code = record['stock_code']
                    verification_date = analysis_date + timedelta(days=90)

                    actual_price = self._get_stock_price_at_date(
                        stock_code,
                        verification_date
                    )

                    if actual_price is None:
                        logger.warning(f"Could not get price for {stock_code} at {verification_date}")
                        continue

                    # 실제 수익률 계산
                    original_price = record['investment_opinion']['current_price']
                    actual_return = ((actual_price - original_price) / original_price) * 100

                    # 예측이 맞았는지 판단
                    decision = record['investment_opinion']['decision']
                    prediction_correct = self._is_prediction_correct(
                        decision,
                        actual_return
                    )

                    # 실제 결과 업데이트
                    record['actual_result'] = {
                        "verification_date": verification_date.isoformat(),
                        "actual_price": actual_price,
                        "actual_return": round(actual_return, 2),
                        "prediction_correct": prediction_correct
                    }

                    # 파일 업데이트
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(record, f, ensure_ascii=False, indent=2)

                    verified_records.append(record)
                    logger.info(f"Verified prediction: {stock_code} - {prediction_correct}")

                except Exception as e:
                    logger.error(f"Error verifying record {filepath}: {str(e)}")
                    continue

            return verified_records

        except Exception as e:
            logger.error(f"Error in verify_old_predictions: {str(e)}")
            return []

    def _get_stock_price_at_date(self, stock_code: str, date: datetime) -> Optional[float]:
        """특정 날짜의 주가 가져오기

        Args:
            stock_code: 종목 코드
            date: 조회 날짜

        Returns:
            float: 종가 (실패 시 None)
        """
        try:
            # 날짜 전후 7일 데이터 가져오기 (휴일 대비)
            start_date = date - timedelta(days=7)
            end_date = date + timedelta(days=7)

            df = fdr.DataReader(stock_code, start_date, end_date)

            if df is None or df.empty:
                return None

            # 목표 날짜에 가장 가까운 거래일 찾기
            df['date_diff'] = abs((df.index - date).days)
            closest_row = df.loc[df['date_diff'].idxmin()]

            return float(closest_row['Close'])

        except Exception as e:
            logger.error(f"Error getting stock price for {stock_code} at {date}: {str(e)}")
            return None

    def _is_prediction_correct(self, decision: str, actual_return: float) -> bool:
        """예측이 맞았는지 판단

        Args:
            decision: 투자 의견 (BUY/HOLD/SELL)
            actual_return: 실제 수익률 (%)

        Returns:
            bool: 예측 정확도
        """
        if decision == "BUY":
            # BUY는 +5% 이상 상승 시 성공
            return actual_return >= 5.0
        elif decision == "SELL":
            # SELL은 -5% 이상 하락 시 성공
            return actual_return <= -5.0
        else:  # HOLD
            # HOLD는 -5% ~ +5% 범위 시 성공
            return -5.0 <= actual_return <= 5.0

    def get_backtesting_statistics(self) -> Dict[str, Any]:
        """백테스팅 통계 생성

        Returns:
            Dict: 승률, 평균 수익률 등 통계
        """
        try:
            # 모든 검증된 레코드 로드
            verified_records = []

            for filepath in self.history_dir.glob("*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        record = json.load(f)

                    # 검증된 레코드만
                    if record.get('actual_result') is not None:
                        verified_records.append(record)

                except Exception as e:
                    logger.error(f"Error loading record {filepath}: {str(e)}")
                    continue

            if not verified_records:
                return {
                    "total_predictions": 0,
                    "verified_predictions": 0,
                    "message": "백테스팅 데이터가 아직 충분하지 않습니다. 3개월 후 결과를 확인할 수 있습니다."
                }

            # 의견별 통계
            buy_records = [r for r in verified_records if r['investment_opinion']['decision'] == 'BUY']
            hold_records = [r for r in verified_records if r['investment_opinion']['decision'] == 'HOLD']
            sell_records = [r for r in verified_records if r['investment_opinion']['decision'] == 'SELL']

            # 승률 계산
            buy_win_rate = self._calculate_win_rate(buy_records) if buy_records else 0
            hold_win_rate = self._calculate_win_rate(hold_records) if hold_records else 0
            sell_win_rate = self._calculate_win_rate(sell_records) if sell_records else 0

            # 평균 수익률 계산
            buy_avg_return = self._calculate_avg_return(buy_records) if buy_records else 0
            hold_avg_return = self._calculate_avg_return(hold_records) if hold_records else 0
            sell_avg_return = self._calculate_avg_return(sell_records) if sell_records else 0

            # 전체 승률
            total_correct = sum(1 for r in verified_records if r['actual_result']['prediction_correct'])
            total_win_rate = (total_correct / len(verified_records)) * 100 if verified_records else 0

            return {
                "total_predictions": len(verified_records),
                "verified_predictions": len(verified_records),
                "overall_win_rate": round(total_win_rate, 1),
                "by_decision": {
                    "BUY": {
                        "count": len(buy_records),
                        "win_rate": round(buy_win_rate, 1),
                        "avg_return": round(buy_avg_return, 2)
                    },
                    "HOLD": {
                        "count": len(hold_records),
                        "win_rate": round(hold_win_rate, 1),
                        "avg_return": round(hold_avg_return, 2)
                    },
                    "SELL": {
                        "count": len(sell_records),
                        "win_rate": round(sell_win_rate, 1),
                        "avg_return": round(sell_avg_return, 2)
                    }
                },
                "message": f"지난 3개월 이상 경과한 {len(verified_records)}개 예측 검증 완료"
            }

        except Exception as e:
            logger.error(f"Error calculating backtesting statistics: {str(e)}")
            return {
                "total_predictions": 0,
                "verified_predictions": 0,
                "error": str(e)
            }

    def _calculate_win_rate(self, records: List[Dict[str, Any]]) -> float:
        """승률 계산

        Args:
            records: 검증된 레코드 목록

        Returns:
            float: 승률 (%)
        """
        if not records:
            return 0.0

        correct_count = sum(1 for r in records if r['actual_result']['prediction_correct'])
        return (correct_count / len(records)) * 100

    def _calculate_avg_return(self, records: List[Dict[str, Any]]) -> float:
        """평균 수익률 계산

        Args:
            records: 검증된 레코드 목록

        Returns:
            float: 평균 수익률 (%)
        """
        if not records:
            return 0.0

        total_return = sum(r['actual_result']['actual_return'] for r in records)
        return total_return / len(records)


# 전역 백테스팅 엔진 인스턴스
_backtesting_engine_instance = None


def get_backtesting_engine() -> BacktestingEngine:
    """전역 BacktestingEngine 인스턴스 반환 (싱글톤)"""
    global _backtesting_engine_instance
    if _backtesting_engine_instance is None:
        _backtesting_engine_instance = BacktestingEngine()
    return _backtesting_engine_instance
