#!/usr/bin/env python3
"""
Chart Pattern Recognition - Phase 5
AI 차트 패턴 인식: Head & Shoulders, Double Top/Bottom 등
사용자 요구: Phase 5 핵심 기능
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


class ChartPatternRecognition:
    """차트 패턴 인식"""

    def __init__(self, stock_code: str, days: int = 120):
        """
        Args:
            stock_code: 종목코드
            days: 분석 기간 (일)
        """
        self.stock_code = stock_code
        self.days = days
        self.df = self._fetch_data()
        self.peaks = []
        self.troughs = []

    def _fetch_data(self) -> Optional[pd.DataFrame]:
        """주가 데이터 가져오기"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.days + 30)

            df = fdr.DataReader(self.stock_code, start_date, end_date)
            if df is None or df.empty:
                logger.error(f"데이터 없음: {self.stock_code}")
                return None

            return df

        except Exception as e:
            logger.error(f"데이터 조회 실패 ({self.stock_code}): {str(e)}")
            return None

    def _find_peaks_and_troughs(self, order: int = 5):
        """고점과 저점 찾기"""
        try:
            if self.df is None or self.df.empty:
                return

            # 고점 (peaks)
            high_peaks = argrelextrema(self.df['High'].values, np.greater, order=order)[0]
            self.peaks = [(self.df.index[i], self.df['High'].iloc[i]) for i in high_peaks]

            # 저점 (troughs)
            low_troughs = argrelextrema(self.df['Low'].values, np.less, order=order)[0]
            self.troughs = [(self.df.index[i], self.df['Low'].iloc[i]) for i in low_troughs]

            logger.info(f"고점 {len(self.peaks)}개, 저점 {len(self.troughs)}개 발견")

        except Exception as e:
            logger.error(f"고점/저점 탐색 실패: {str(e)}")

    def detect_head_and_shoulders(self) -> Dict[str, Any]:
        """
        헤드앤숄더 (Head and Shoulders) 패턴 인식

        패턴 구조:
        - 왼쪽 어깨 (Left Shoulder)
        - 머리 (Head) - 가장 높은 고점
        - 오른쪽 어깨 (Right Shoulder)
        - 넥라인 (Neckline)

        Returns:
            패턴 감지 결과 및 목표가
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            self._find_peaks_and_troughs()

            if len(self.peaks) < 3:
                return {"pattern_detected": False, "reason": "고점 부족 (3개 이상 필요)"}

            # 최근 고점 3개 검토
            recent_peaks = self.peaks[-3:]

            # 머리가 가장 높아야 함
            heights = [peak[1] for peak in recent_peaks]
            head_idx = heights.index(max(heights))

            # 헤드앤숄더는 가운데가 머리여야 함
            if head_idx != 1:
                return {"pattern_detected": False, "reason": "헤드앤숄더 패턴 아님 (가운데가 최고점 아님)"}

            left_shoulder = recent_peaks[0]
            head = recent_peaks[1]
            right_shoulder = recent_peaks[2]

            # 어깨들이 비슷한 높이여야 함 (±5% 이내)
            shoulder_diff = abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1]
            if shoulder_diff > 0.05:
                return {"pattern_detected": False, "reason": "어깨 높이 차이 과다"}

            # 넥라인 찾기 (어깨 사이의 저점들)
            neckline_troughs = [t for t in self.troughs if left_shoulder[0] < t[0] < right_shoulder[0]]

            if len(neckline_troughs) < 2:
                return {"pattern_detected": False, "reason": "넥라인 형성 부족"}

            neckline_level = np.mean([t[1] for t in neckline_troughs])

            # 현재가
            current_price = float(self.df['Close'].iloc[-1])

            # 패턴 완성 여부 (현재가가 넥라인 이탈)
            pattern_complete = current_price < neckline_level

            # 목표가 계산 (머리부터 넥라인까지 거리만큼 하락)
            distance = head[1] - neckline_level
            target_price = neckline_level - distance

            # 신뢰도 계산
            confidence = self._calculate_pattern_confidence(
                "HEAD_AND_SHOULDERS",
                shoulder_diff,
                pattern_complete
            )

            return {
                "pattern_detected": True,
                "pattern_name": "Head and Shoulders (헤드앤숄더)",
                "pattern_type": "BEARISH",
                "confidence": confidence,
                "left_shoulder": {"date": str(left_shoulder[0].date()), "price": int(left_shoulder[1])},
                "head": {"date": str(head[0].date()), "price": int(head[1])},
                "right_shoulder": {"date": str(right_shoulder[0].date()), "price": int(right_shoulder[1])},
                "neckline_level": int(neckline_level),
                "current_price": int(current_price),
                "target_price": int(target_price),
                "pattern_complete": pattern_complete,
                "expected_move": int(target_price - current_price),
                "expected_move_pct": round((target_price / current_price - 1) * 100, 1),
                "description": f"헤드앤숄더 패턴 (신뢰도 {confidence}%) - 하락 목표가 {int(target_price):,}원"
            }

        except Exception as e:
            logger.error(f"헤드앤숄더 패턴 인식 실패: {str(e)}")
            return {"error": str(e)}

    def detect_double_top(self) -> Dict[str, Any]:
        """
        더블탑 (Double Top) 패턴 인식

        패턴 구조:
        - 첫 번째 고점
        - 중간 저점
        - 두 번째 고점 (첫 번째와 비슷한 높이)
        - 넥라인 (중간 저점 수준)

        Returns:
            패턴 감지 결과
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            self._find_peaks_and_troughs()

            if len(self.peaks) < 2:
                return {"pattern_detected": False, "reason": "고점 부족"}

            # 최근 고점 2개
            recent_peaks = self.peaks[-2:]

            first_top = recent_peaks[0]
            second_top = recent_peaks[1]

            # 두 고점이 비슷한 높이여야 함 (±3% 이내)
            height_diff = abs(first_top[1] - second_top[1]) / first_top[1]

            if height_diff > 0.03:
                return {"pattern_detected": False, "reason": "고점 높이 차이 과다"}

            # 중간 저점 찾기
            middle_troughs = [t for t in self.troughs if first_top[0] < t[0] < second_top[0]]

            if not middle_troughs:
                return {"pattern_detected": False, "reason": "중간 저점 없음"}

            neckline = min(middle_troughs, key=lambda x: x[1])
            neckline_level = neckline[1]

            # 현재가
            current_price = float(self.df['Close'].iloc[-1])

            # 패턴 완성 여부
            pattern_complete = current_price < neckline_level

            # 목표가 계산
            distance = first_top[1] - neckline_level
            target_price = neckline_level - distance

            # 신뢰도
            confidence = self._calculate_pattern_confidence(
                "DOUBLE_TOP",
                height_diff,
                pattern_complete
            )

            return {
                "pattern_detected": True,
                "pattern_name": "Double Top (더블탑)",
                "pattern_type": "BEARISH",
                "confidence": confidence,
                "first_top": {"date": str(first_top[0].date()), "price": int(first_top[1])},
                "second_top": {"date": str(second_top[0].date()), "price": int(second_top[1])},
                "neckline_level": int(neckline_level),
                "current_price": int(current_price),
                "target_price": int(target_price),
                "pattern_complete": pattern_complete,
                "expected_move": int(target_price - current_price),
                "expected_move_pct": round((target_price / current_price - 1) * 100, 1),
                "description": f"더블탑 패턴 (신뢰도 {confidence}%) - 하락 목표가 {int(target_price):,}원"
            }

        except Exception as e:
            logger.error(f"더블탑 패턴 인식 실패: {str(e)}")
            return {"error": str(e)}

    def detect_double_bottom(self) -> Dict[str, Any]:
        """
        더블바텀 (Double Bottom) 패턴 인식

        패턴 구조:
        - 첫 번째 저점
        - 중간 고점
        - 두 번째 저점 (첫 번째와 비슷한 높이)
        - 넥라인 (중간 고점 수준)

        Returns:
            패턴 감지 결과
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            self._find_peaks_and_troughs()

            if len(self.troughs) < 2:
                return {"pattern_detected": False, "reason": "저점 부족"}

            # 최근 저점 2개
            recent_troughs = self.troughs[-2:]

            first_bottom = recent_troughs[0]
            second_bottom = recent_troughs[1]

            # 두 저점이 비슷한 높이여야 함
            height_diff = abs(first_bottom[1] - second_bottom[1]) / first_bottom[1]

            if height_diff > 0.03:
                return {"pattern_detected": False, "reason": "저점 높이 차이 과다"}

            # 중간 고점 찾기
            middle_peaks = [p for p in self.peaks if first_bottom[0] < p[0] < second_bottom[0]]

            if not middle_peaks:
                return {"pattern_detected": False, "reason": "중간 고점 없음"}

            neckline = max(middle_peaks, key=lambda x: x[1])
            neckline_level = neckline[1]

            # 현재가
            current_price = float(self.df['Close').iloc[-1])

            # 패턴 완성 여부
            pattern_complete = current_price > neckline_level

            # 목표가 계산
            distance = neckline_level - first_bottom[1]
            target_price = neckline_level + distance

            # 신뢰도
            confidence = self._calculate_pattern_confidence(
                "DOUBLE_BOTTOM",
                height_diff,
                pattern_complete
            )

            return {
                "pattern_detected": True,
                "pattern_name": "Double Bottom (더블바텀)",
                "pattern_type": "BULLISH",
                "confidence": confidence,
                "first_bottom": {"date": str(first_bottom[0].date()), "price": int(first_bottom[1])},
                "second_bottom": {"date": str(second_bottom[0].date()), "price": int(second_bottom[1])},
                "neckline_level": int(neckline_level),
                "current_price": int(current_price),
                "target_price": int(target_price),
                "pattern_complete": pattern_complete,
                "expected_move": int(target_price - current_price),
                "expected_move_pct": round((target_price / current_price - 1) * 100, 1),
                "description": f"더블바텀 패턴 (신뢰도 {confidence}%) - 상승 목표가 {int(target_price):,}원"
            }

        except Exception as e:
            logger.error(f"더블바텀 패턴 인식 실패: {str(e)}")
            return {"error": str(e)}

    def _calculate_pattern_confidence(
        self,
        pattern_type: str,
        height_diff: float,
        pattern_complete: bool
    ) -> int:
        """패턴 신뢰도 계산 (0-100)"""
        base_confidence = 60

        # 높이 차이가 작을수록 높은 신뢰도
        if height_diff < 0.01:
            height_score = 30
        elif height_diff < 0.02:
            height_score = 20
        elif height_diff < 0.03:
            height_score = 10
        else:
            height_score = 0

        # 패턴 완성 여부
        complete_score = 10 if pattern_complete else 0

        confidence = base_confidence + height_score + complete_score
        return min(confidence, 95)  # 최대 95%

    def detect_all_patterns(self) -> Dict[str, Any]:
        """모든 차트 패턴 감지"""
        try:
            head_and_shoulders = self.detect_head_and_shoulders()
            double_top = self.detect_double_top()
            double_bottom = self.detect_double_bottom()

            detected_patterns = []

            if head_and_shoulders.get("pattern_detected"):
                detected_patterns.append(head_and_shoulders)

            if double_top.get("pattern_detected"):
                detected_patterns.append(double_top)

            if double_bottom.get("pattern_detected"):
                detected_patterns.append(double_bottom)

            # 신뢰도 순으로 정렬
            detected_patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)

            return {
                "stock_code": self.stock_code,
                "total_patterns": len(detected_patterns),
                "patterns": detected_patterns,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"패턴 인식 실패: {str(e)}")
            return {"error": str(e)}


# 편의 함수
def recognize_chart_patterns(stock_code: str, days: int = 120) -> Dict[str, Any]:
    """차트 패턴 인식"""
    recognizer = ChartPatternRecognition(stock_code, days)
    return recognizer.detect_all_patterns()


if __name__ == "__main__":
    # 테스트
    import json

    result = recognize_chart_patterns("005930")
    print(json.dumps(result, indent=2, ensure_ascii=False))
