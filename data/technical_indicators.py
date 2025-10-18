"""
기술적 지표 계산 모듈

모든 기술적 지표 계산을 담당합니다.
TA-Lib 기반으로 정확하고 표준화된 지표를 계산합니다.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# TA-Lib import (fallback 처리)
try:
    import talib
    TALIB_AVAILABLE = True
    logger.info("TA-Lib 사용 가능")
except ImportError:
    TALIB_AVAILABLE = False
    logger.warning("TA-Lib 없음 - 수동 계산으로 대체")


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    이동평균선 계산 (MA5, MA20, MA60)

    Args:
        df: OHLCV 데이터프레임

    Returns:
        MA5, MA20, MA60 컬럼이 추가된 데이터프레임
    """
    try:
        if TALIB_AVAILABLE:
            df['MA5'] = talib.SMA(df['Close'], timeperiod=5)
            df['MA20'] = talib.SMA(df['Close'], timeperiod=20)
            df['MA60'] = talib.SMA(df['Close'], timeperiod=60)
        else:
            # Fallback: pandas rolling
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()

        logger.info("이동평균선 계산 완료 (MA5, MA20, MA60)")
        return df
    except Exception as e:
        logger.error(f"이동평균선 계산 실패: {e}")
        return df


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """
    볼린저밴드 계산 (±2σ)

    Args:
        df: OHLCV 데이터프레임
        period: 기간 (기본 20일)
        std_dev: 표준편차 배수 (기본 2)

    Returns:
        BB_Upper, BB_Middle, BB_Lower 컬럼이 추가된 데이터프레임
    """
    try:
        if TALIB_AVAILABLE:
            upper, middle, lower = talib.BBANDS(
                df['Close'],
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev,
                matype=0
            )
            df['BB_Upper'] = upper
            df['BB_Middle'] = middle
            df['BB_Lower'] = lower
        else:
            # Fallback: pandas
            ma = df['Close'].rolling(window=period).mean()
            std = df['Close'].rolling(window=period).std()
            df['BB_Upper'] = ma + (std * std_dev)
            df['BB_Middle'] = ma
            df['BB_Lower'] = ma - (std * std_dev)

        logger.info(f"볼린저밴드 계산 완료 (period={period}, std={std_dev})")
        return df
    except Exception as e:
        logger.error(f"볼린저밴드 계산 실패: {e}")
        return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    RSI (Relative Strength Index) 계산

    Args:
        df: OHLCV 데이터프레임
        period: 기간 (기본 14일)

    Returns:
        RSI 컬럼이 추가된 데이터프레임
    """
    try:
        if TALIB_AVAILABLE:
            df['RSI'] = talib.RSI(df['Close'], timeperiod=period)
        else:
            # Fallback: 수동 계산
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

        logger.info(f"RSI 계산 완료 (period={period})")
        return df
    except Exception as e:
        logger.error(f"RSI 계산 실패: {e}")
        return df


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence) 계산

    Args:
        df: OHLCV 데이터프레임
        fast: 단기 EMA 기간 (기본 12일)
        slow: 장기 EMA 기간 (기본 26일)
        signal: 시그널선 기간 (기본 9일)

    Returns:
        MACD, MACD_Signal, MACD_Hist 컬럼이 추가된 데이터프레임
    """
    try:
        if TALIB_AVAILABLE:
            macd, signal_line, hist = talib.MACD(
                df['Close'],
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=signal
            )
            df['MACD'] = macd
            df['MACD_Signal'] = signal_line
            df['MACD_Hist'] = hist
        else:
            # Fallback: 수동 계산
            ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
            ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
            macd = ema_fast - ema_slow
            signal_line = macd.ewm(span=signal, adjust=False).mean()
            hist = macd - signal_line

            df['MACD'] = macd
            df['MACD_Signal'] = signal_line
            df['MACD_Hist'] = hist

        logger.info(f"MACD 계산 완료 (fast={fast}, slow={slow}, signal={signal})")
        return df
    except Exception as e:
        logger.error(f"MACD 계산 실패: {e}")
        return df


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    """
    Stochastic Oscillator 계산

    Args:
        df: OHLCV 데이터프레임
        k_period: %K 기간 (기본 14일)
        d_period: %D 기간 (기본 3일)

    Returns:
        Stoch_K, Stoch_D 컬럼이 추가된 데이터프레임
    """
    try:
        if TALIB_AVAILABLE:
            slowk, slowd = talib.STOCH(
                df['High'],
                df['Low'],
                df['Close'],
                fastk_period=k_period,
                slowk_period=d_period,
                slowk_matype=0,
                slowd_period=d_period,
                slowd_matype=0
            )
            df['Stoch_K'] = slowk
            df['Stoch_D'] = slowd
        else:
            # Fallback: 수동 계산
            lowest_low = df['Low'].rolling(window=k_period).min()
            highest_high = df['High'].rolling(window=k_period).max()

            k = 100 * ((df['Close'] - lowest_low) / (highest_high - lowest_low))
            df['Stoch_K'] = k.rolling(window=d_period).mean()
            df['Stoch_D'] = df['Stoch_K'].rolling(window=d_period).mean()

        logger.info(f"Stochastic 계산 완료 (K={k_period}, D={d_period})")
        return df
    except Exception as e:
        logger.error(f"Stochastic 계산 실패: {e}")
        return df


def calculate_volume_profile(df: pd.DataFrame, bins: int = 20) -> pd.Series:
    """
    Volume Profile 계산 (간소화 버전)

    가격 범위를 bins 개로 나누고, 각 구간의 거래량을 집계합니다.

    Args:
        df: OHLCV 데이터프레임
        bins: 가격 구간 수 (기본 20개)

    Returns:
        가격 구간별 거래량 Series
    """
    try:
        if df.empty or 'Close' not in df or 'Volume' not in df:
            logger.warning("Volume Profile 계산 불가: 데이터 없음")
            return pd.Series()

        # 가격 범위를 bins 개 구간으로 나눔
        df_copy = df.copy()
        df_copy['Price_Bin'] = pd.cut(df_copy['Close'], bins=bins)

        # 각 구간별 거래량 합계
        volume_profile = df_copy.groupby('Price_Bin', observed=False)['Volume'].sum()

        logger.info(f"Volume Profile 계산 완료 (bins={bins})")
        return volume_profile
    except Exception as e:
        logger.error(f"Volume Profile 계산 실패: {e}")
        return pd.Series()


def calculate_all_indicators(df: pd.DataFrame, indicators: list = None) -> pd.DataFrame:
    """
    모든 기술적 지표를 한 번에 계산

    Args:
        df: OHLCV 데이터프레임
        indicators: 계산할 지표 리스트 (None이면 전체)
                   예: ['MA', 'BB', 'RSI', 'MACD', 'Stochastic']

    Returns:
        모든 지표가 추가된 데이터프레임
    """
    if df.empty:
        logger.warning("빈 데이터프레임 - 지표 계산 불가")
        return df

    # indicators가 None이면 기본 지표만 계산
    if indicators is None:
        indicators = ['MA', 'BB', 'RSI', 'MACD']

    try:
        logger.info(f"기술적 지표 계산 시작: {indicators}")

        # 이동평균선 (항상 계산)
        if 'MA' in indicators or 'MA5' in indicators or 'MA20' in indicators or 'MA60' in indicators:
            df = calculate_moving_averages(df)

        # 볼린저밴드
        if 'BB' in indicators or 'Bollinger' in indicators:
            df = calculate_bollinger_bands(df)

        # RSI
        if 'RSI' in indicators:
            df = calculate_rsi(df)

        # MACD
        if 'MACD' in indicators:
            df = calculate_macd(df)

        # Stochastic
        if 'Stochastic' in indicators:
            df = calculate_stochastic(df)

        logger.info(f"✅ 기술적 지표 계산 완료: {len(indicators)}개")
        return df

    except Exception as e:
        logger.error(f"기술적 지표 계산 중 오류 발생: {e}", exc_info=True)
        return df


if __name__ == "__main__":
    """
    테스트 코드
    """
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta

    # 로깅 설정
    logging.basicConfig(level=logging.INFO)

    # 삼성전자 데이터 가져오기
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    df = fdr.DataReader('005930', start_date, end_date)

    print(f"원본 데이터: {len(df)}행")
    print(df.head())

    # 모든 지표 계산
    df = calculate_all_indicators(df, indicators=['MA', 'BB', 'RSI', 'MACD', 'Stochastic'])

    print("\n지표 계산 후:")
    print(df.columns.tolist())
    print(df.tail())

    # Volume Profile 계산
    vol_profile = calculate_volume_profile(df)
    print("\nVolume Profile:")
    print(vol_profile)
