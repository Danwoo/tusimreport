#!/usr/bin/env python3
"""
주식 차트 생성 API
matplotlib과 plotly를 사용한 한국 주식 차트 생성
"""

import logging
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager, rc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import base64
from pathlib import Path
import FinanceDataReader as fdr
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# 한글 폰트 설정
def setup_korean_font():
    """한글 폰트 설정"""
    try:
        # Windows 환경에서 맑은 고딕 사용
        font_path = 'C:/Windows/Fonts/malgun.ttf'
        if Path(font_path).exists():
            font_prop = font_manager.FontProperties(fname=font_path)
            plt.rcParams['font.family'] = font_prop.get_name()
        else:
            # 맑은 고딕이 없으면 시스템 기본 폰트 사용
            plt.rcParams['font.family'] = ['DejaVu Sans']

        plt.rcParams['axes.unicode_minus'] = False
        return True
    except Exception as e:
        logger.warning(f"한글 폰트 설정 실패: {e}")
        return False

def fetch_stock_data(symbol: str, period: int = 252) -> pd.DataFrame:
    """주식 데이터 가져오기 (FinanceDataReader 사용)"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period + 30)  # 여유분 추가

        # 종목 코드 정리 (앞의 0 제거하지 않음)
        if len(symbol) == 6 and symbol.isdigit():
            symbol = symbol  # 그대로 유지

        logger.info(f"주식 데이터 가져오는 중: {symbol} ({start_date.date()} ~ {end_date.date()})")

        df = fdr.DataReader(symbol, start_date, end_date)

        if df.empty:
            logger.error(f"주식 데이터가 없습니다: {symbol}")
            return pd.DataFrame()

        # 최근 period일 데이터만 유지
        df = df.tail(period)

        logger.info(f"데이터 수집 완료: {len(df)}일치 데이터")
        return df

    except Exception as e:
        logger.error(f"주식 데이터 가져오기 실패 {symbol}: {e}")
        return pd.DataFrame()

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 계산"""
    if df.empty:
        return df

    try:
        # 이동평균선
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()

        # 볼린저 밴드
        ma20 = df['Close'].rolling(window=20).mean()
        std20 = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = ma20 + (std20 * 2)
        df['BB_Lower'] = ma20 - (std20 * 2)

        # RSI 계산
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        return df

    except Exception as e:
        logger.error(f"기술적 지표 계산 실패: {e}")
        return df

def create_stock_chart(symbol: str, company_name: str, period: int = 252, chart_type: str = "candle") -> str:
    """
    주식 차트 생성 및 Base64 인코딩된 이미지 반환

    Args:
        symbol: 종목 코드
        company_name: 회사명
        period: 조회 기간 (일)
        chart_type: 차트 유형 ("candle", "line", "ohlc")

    Returns:
        Base64 인코딩된 PNG 이미지 문자열
    """
    try:
        # 한글 폰트 설정
        setup_korean_font()

        # 데이터 가져오기
        df = fetch_stock_data(symbol, period)
        if df.empty:
            return ""

        # 기술적 지표 계산
        df = calculate_technical_indicators(df)

        # 차트 생성
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10),
                                            gridspec_kw={'height_ratios': [3, 1, 1]})

        # 메인 차트 (가격)
        if chart_type == "candle":
            # 캔들스틱 차트
            for i, (date, row) in enumerate(df.iterrows()):
                color = 'red' if row['Close'] >= row['Open'] else 'blue'
                # 몸통
                height = abs(row['Close'] - row['Open'])
                bottom = min(row['Open'], row['Close'])
                ax1.bar(date, height, bottom=bottom, color=color, alpha=0.8, width=0.8)
                # 꼬리
                ax1.plot([date, date], [row['Low'], row['High']], color=color, linewidth=1)

        elif chart_type == "line":
            ax1.plot(df.index, df['Close'], color='blue', linewidth=2, label='종가')

        # 이동평균선
        ax1.plot(df.index, df['MA5'], color='red', linewidth=1, label='MA5', alpha=0.8)
        ax1.plot(df.index, df['MA20'], color='orange', linewidth=1, label='MA20', alpha=0.8)
        ax1.plot(df.index, df['MA60'], color='green', linewidth=1, label='MA60', alpha=0.8)

        # 볼린저 밴드
        ax1.plot(df.index, df['BB_Upper'], color='gray', linewidth=1, linestyle='--', alpha=0.5)
        ax1.plot(df.index, df['BB_Lower'], color='gray', linewidth=1, linestyle='--', alpha=0.5)
        ax1.fill_between(df.index, df['BB_Upper'], df['BB_Lower'], alpha=0.1, color='gray')

        ax1.set_title(f'{company_name} ({symbol}) 주가 차트', fontsize=16, fontweight='bold')
        ax1.set_ylabel('가격 (원)', fontsize=12)
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)

        # 거래량 차트
        colors = ['red' if close >= open_price else 'blue'
                 for close, open_price in zip(df['Close'], df['Open'])]
        ax2.bar(df.index, df['Volume'], color=colors, alpha=0.7)
        ax2.set_ylabel('거래량', fontsize=12)
        ax2.grid(True, alpha=0.3)

        # RSI 차트
        ax3.plot(df.index, df['RSI'], color='purple', linewidth=2, label='RSI')
        ax3.axhline(y=70, color='red', linestyle='--', alpha=0.7, label='과매수(70)')
        ax3.axhline(y=30, color='blue', linestyle='--', alpha=0.7, label='과매도(30)')
        ax3.fill_between(df.index, 70, 100, alpha=0.1, color='red')
        ax3.fill_between(df.index, 0, 30, alpha=0.1, color='blue')
        ax3.set_ylabel('RSI', fontsize=12)
        ax3.set_xlabel('날짜', fontsize=12)
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        ax3.set_ylim(0, 100)

        # X축 날짜 포맷팅
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()

        # 이미지를 Base64로 인코딩
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        # 파일로도 저장 (선택사항)
        chart_filename = f"korean_stock_chart.png"
        plt.figure(figsize=(12, 10))
        # 위 코드 반복하여 파일 저장...

        logger.info(f"차트 생성 완료: {symbol}")
        return image_base64

    except Exception as e:
        logger.error(f"차트 생성 실패 {symbol}: {e}")
        return ""

def create_comparison_chart(symbols: list, company_names: list, period: int = 252) -> str:
    """여러 종목 비교 차트 생성"""
    try:
        setup_korean_font()

        fig, ax = plt.subplots(figsize=(12, 8))

        colors = ['blue', 'red', 'green', 'orange', 'purple']

        for i, (symbol, name) in enumerate(zip(symbols, company_names)):
            df = fetch_stock_data(symbol, period)
            if not df.empty:
                # 정규화 (첫날 대비 수익률)
                normalized = (df['Close'] / df['Close'].iloc[0] - 1) * 100
                ax.plot(df.index, normalized,
                       color=colors[i % len(colors)],
                       linewidth=2,
                       label=f'{name} ({symbol})')

        ax.set_title('종목별 수익률 비교', fontsize=16, fontweight='bold')
        ax.set_ylabel('수익률 (%)', fontsize=12)
        ax.set_xlabel('날짜', fontsize=12)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)

        # 날짜 포맷팅
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()

        # Base64 인코딩
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        logger.info(f"비교 차트 생성 완료: {symbols}")
        return image_base64

    except Exception as e:
        logger.error(f"비교 차트 생성 실패: {e}")
        return ""

# 테스트용
if __name__ == "__main__":
    # 테스트
    setup_korean_font()
    chart_data = create_stock_chart("005930", "삼성전자", 120, "candle")
    print(f"차트 생성 {'성공' if chart_data else '실패'}")