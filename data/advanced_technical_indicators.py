#!/usr/bin/env python3
"""
Advanced Technical Indicators - Phase 5
고급 기술적 지표: Ichimoku, Fibonacci, Volume Profile 등
사용자 요구: 43% (13명)
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AdvancedTechnicalIndicators:
    """고급 기술적 지표 계산"""

    def __init__(self, stock_code: str, days: int = 120):
        """
        Args:
            stock_code: 종목코드
            days: 분석 기간 (일)
        """
        self.stock_code = stock_code
        self.days = days
        self.df = self._fetch_data()

    def _fetch_data(self) -> Optional[pd.DataFrame]:
        """주가 데이터 가져오기"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.days + 60)  # 여유분 추가

            df = fdr.DataReader(self.stock_code, start_date, end_date)
            if df is None or df.empty:
                logger.error(f"데이터 없음: {self.stock_code}")
                return None

            return df

        except Exception as e:
            logger.error(f"데이터 조회 실패 ({self.stock_code}): {str(e)}")
            return None

    def calculate_ichimoku(self) -> Dict[str, Any]:
        """
        일목균형표 (Ichimoku Cloud) 계산

        Returns:
            전환선, 기준선, 선행스팬1, 선행스팬2, 후행스팬
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            df = self.df.copy()

            # 전환선 (Tenkan-sen): 9일 고가+저가 평균
            high_9 = df['High'].rolling(window=9).max()
            low_9 = df['Low'].rolling(window=9).min()
            tenkan_sen = (high_9 + low_9) / 2

            # 기준선 (Kijun-sen): 26일 고가+저가 평균
            high_26 = df['High'].rolling(window=26).max()
            low_26 = df['Low'].rolling(window=26).min()
            kijun_sen = (high_26 + low_26) / 2

            # 선행스팬1 (Senkou Span A): (전환선 + 기준선) / 2, 26일 선행
            senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

            # 선행스팬2 (Senkou Span B): 52일 고가+저가 평균, 26일 선행
            high_52 = df['High'].rolling(window=52).max()
            low_52 = df['Low'].rolling(window=52).min()
            senkou_span_b = ((high_52 + low_52) / 2).shift(26)

            # 후행스팬 (Chikou Span): 종가, 26일 후행
            chikou_span = df['Close'].shift(-26)

            # 현재 값
            current_price = float(df['Close'].iloc[-1])
            current_tenkan = float(tenkan_sen.iloc[-1]) if not pd.isna(tenkan_sen.iloc[-1]) else 0
            current_kijun = float(kijun_sen.iloc[-1]) if not pd.isna(kijun_sen.iloc[-1]) else 0
            current_span_a = float(senkou_span_a.iloc[-1]) if not pd.isna(senkou_span_a.iloc[-1]) else 0
            current_span_b = float(senkou_span_b.iloc[-1]) if not pd.isna(senkou_span_b.iloc[-1]) else 0

            # 구름대 상태 분석
            cloud_status = self._analyze_ichimoku_cloud(
                current_price,
                current_span_a,
                current_span_b,
                current_tenkan,
                current_kijun
            )

            return {
                "tenkan_sen": int(current_tenkan),
                "kijun_sen": int(current_kijun),
                "senkou_span_a": int(current_span_a),
                "senkou_span_b": int(current_span_b),
                "current_price": int(current_price),
                "cloud_status": cloud_status,
                "signal": cloud_status["signal"],
                "description": cloud_status["description"]
            }

        except Exception as e:
            logger.error(f"일목균형표 계산 실패: {str(e)}")
            return {"error": str(e)}

    def _analyze_ichimoku_cloud(
        self,
        price: float,
        span_a: float,
        span_b: float,
        tenkan: float,
        kijun: float
    ) -> Dict[str, Any]:
        """일목균형표 구름대 분석"""
        cloud_top = max(span_a, span_b)
        cloud_bottom = min(span_a, span_b)

        # 구름대 색상
        cloud_color = "BULLISH" if span_a > span_b else "BEARISH"

        # 가격 위치
        if price > cloud_top:
            position = "ABOVE_CLOUD"
            signal = "BULLISH"
            description = "구름대 위 (강한 상승 추세)"
        elif price < cloud_bottom:
            position = "BELOW_CLOUD"
            signal = "BEARISH"
            description = "구름대 아래 (강한 하락 추세)"
        else:
            position = "INSIDE_CLOUD"
            signal = "NEUTRAL"
            description = "구름대 내부 (방향성 불명확)"

        # 전환선/기준선 교차 확인
        if tenkan > kijun:
            tk_cross = "GOLDEN_CROSS"
            description += " • 전환선 상향 돌파 (매수 신호)"
        elif tenkan < kijun:
            tk_cross = "DEAD_CROSS"
            description += " • 전환선 하향 돌파 (매도 신호)"
        else:
            tk_cross = "NEUTRAL"

        return {
            "signal": signal,
            "position": position,
            "cloud_color": cloud_color,
            "tk_cross": tk_cross,
            "description": description
        }

    def calculate_fibonacci_retracement(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        피보나치 되돌림 (Fibonacci Retracement) 계산

        Args:
            lookback_days: 고점/저점 탐색 기간

        Returns:
            피보나치 레벨별 가격
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            df = self.df.tail(lookback_days).copy()

            # 최고점, 최저점 찾기
            high_price = df['High'].max()
            low_price = df['Low'].min()
            diff = high_price - low_price

            # 현재 추세 판단 (상승/하락)
            current_price = float(df['Close'].iloc[-1])
            trend = "UPTREND" if current_price > (high_price + low_price) / 2 else "DOWNTREND"

            # 피보나치 레벨 (0%, 23.6%, 38.2%, 50%, 61.8%, 100%)
            if trend == "UPTREND":
                # 상승 추세: 고점에서 되돌림
                levels = {
                    "0.0": high_price,
                    "23.6": high_price - (diff * 0.236),
                    "38.2": high_price - (diff * 0.382),
                    "50.0": high_price - (diff * 0.50),
                    "61.8": high_price - (diff * 0.618),
                    "100.0": low_price
                }
            else:
                # 하락 추세: 저점에서 반등
                levels = {
                    "0.0": low_price,
                    "23.6": low_price + (diff * 0.236),
                    "38.2": low_price + (diff * 0.382),
                    "50.0": low_price + (diff * 0.50),
                    "61.8": low_price + (diff * 0.618),
                    "100.0": high_price
                }

            # 현재 가격이 어느 레벨에 위치하는지
            nearest_level = self._find_nearest_fib_level(current_price, levels)

            return {
                "trend": trend,
                "high_price": int(high_price),
                "low_price": int(low_price),
                "current_price": int(current_price),
                "levels": {k: int(v) for k, v in levels.items()},
                "nearest_level": nearest_level,
                "description": f"{trend} 추세에서 {nearest_level['level']}% 레벨 근처 ({nearest_level['distance']:+.1f}%)"
            }

        except Exception as e:
            logger.error(f"피보나치 되돌림 계산 실패: {str(e)}")
            return {"error": str(e)}

    def _find_nearest_fib_level(self, price: float, levels: Dict[str, float]) -> Dict[str, Any]:
        """현재 가격에서 가장 가까운 피보나치 레벨 찾기"""
        min_distance = float('inf')
        nearest = None

        for level_name, level_price in levels.items():
            distance = abs(price - level_price)
            if distance < min_distance:
                min_distance = distance
                nearest = {
                    "level": level_name,
                    "price": int(level_price),
                    "distance": (price / level_price - 1) * 100
                }

        return nearest

    def calculate_volume_profile(self, bins: int = 20) -> Dict[str, Any]:
        """
        거래량 프로파일 (Volume Profile) 계산

        Args:
            bins: 가격대 구간 수

        Returns:
            가격대별 거래량 분포, POC, VAH, VAL
        """
        try:
            if self.df is None or self.df.empty:
                return {"error": "데이터 없음"}

            df = self.df.copy()

            # 가격 범위
            price_min = df['Low'].min()
            price_max = df['High'].max()

            # 가격대 구간 생성
            price_bins = np.linspace(price_min, price_max, bins + 1)
            df['price_bin'] = pd.cut(df['Close'], bins=price_bins, labels=False, include_lowest=True)

            # 가격대별 거래량 집계
            volume_profile = df.groupby('price_bin')['Volume'].sum()

            # POC (Point of Control): 거래량이 가장 많은 가격대
            poc_bin = volume_profile.idxmax()
            poc_price = (price_bins[poc_bin] + price_bins[poc_bin + 1]) / 2

            # Value Area (거래량의 70%가 집중된 구간)
            total_volume = volume_profile.sum()
            target_volume = total_volume * 0.70

            # POC부터 위아래로 확장하며 70% 찾기
            sorted_indices = volume_profile.sort_values(ascending=False).index
            cumulative_volume = 0
            value_area_bins = []

            for idx in sorted_indices:
                cumulative_volume += volume_profile[idx]
                value_area_bins.append(idx)
                if cumulative_volume >= target_volume:
                    break

            # VAH (Value Area High), VAL (Value Area Low)
            vah_bin = max(value_area_bins)
            val_bin = min(value_area_bins)
            vah_price = price_bins[vah_bin + 1]
            val_price = price_bins[val_bin]

            # 현재가 위치 분석
            current_price = float(df['Close'].iloc[-1])
            position_analysis = self._analyze_volume_profile_position(
                current_price,
                poc_price,
                vah_price,
                val_price
            )

            return {
                "poc_price": int(poc_price),
                "vah_price": int(vah_price),
                "val_price": int(val_price),
                "current_price": int(current_price),
                "position": position_analysis["position"],
                "signal": position_analysis["signal"],
                "description": position_analysis["description"]
            }

        except Exception as e:
            logger.error(f"거래량 프로파일 계산 실패: {str(e)}")
            return {"error": str(e)}

    def _analyze_volume_profile_position(
        self,
        price: float,
        poc: float,
        vah: float,
        val: float
    ) -> Dict[str, Any]:
        """거래량 프로파일 기반 가격 위치 분석"""
        if price > vah:
            return {
                "position": "ABOVE_VA",
                "signal": "BULLISH",
                "description": f"Value Area 상단 돌파 (VAH: {int(vah):,}원) - 강세"
            }
        elif price < val:
            return {
                "position": "BELOW_VA",
                "signal": "BEARISH",
                "description": f"Value Area 하단 이탈 (VAL: {int(val):,}원) - 약세"
            }
        elif abs(price - poc) / poc < 0.02:  # POC ±2% 이내
            return {
                "position": "AT_POC",
                "signal": "NEUTRAL",
                "description": f"POC 근처 (POC: {int(poc):,}원) - 균형 상태"
            }
        else:
            return {
                "position": "WITHIN_VA",
                "signal": "NEUTRAL",
                "description": f"Value Area 내부 (VAL: {int(val):,}원 ~ VAH: {int(vah):,}원)"
            }

    def get_all_advanced_indicators(self) -> Dict[str, Any]:
        """모든 고급 지표 계산"""
        try:
            ichimoku = self.calculate_ichimoku()
            fibonacci = self.calculate_fibonacci_retracement()
            volume_profile = self.calculate_volume_profile()

            return {
                "stock_code": self.stock_code,
                "ichimoku": ichimoku,
                "fibonacci": fibonacci,
                "volume_profile": volume_profile,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"고급 지표 계산 실패: {str(e)}")
            return {"error": str(e)}


# 편의 함수
def calculate_advanced_indicators(stock_code: str, days: int = 120) -> Dict[str, Any]:
    """고급 기술적 지표 계산"""
    calculator = AdvancedTechnicalIndicators(stock_code, days)
    return calculator.get_all_advanced_indicators()


if __name__ == "__main__":
    # 테스트
    import json

    result = calculate_advanced_indicators("005930")
    print(json.dumps(result, indent=2, ensure_ascii=False))
