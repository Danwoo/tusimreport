"""
Plotly 기반 인터랙티브 주식 차트 생성기

Matplotlib 정적 차트를 대체하는 Plotly 인터랙티브 차트
- 줌, 팬, 호버 기능
- 4-서브플롯 (가격 + 거래량 + RSI + MACD)
- 7가지 기간 옵션 (1W, 1M, 3M, 6M, 1Y, YTD, MAX)
- 기술적 지표 확장 (MA, BB, RSI, MACD, Stochastic)
- 모바일 반응형 디자인
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import FinanceDataReader as fdr

from data.technical_indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


def convert_period_to_days(period: str) -> int:
    """
    기간 문자열을 일수로 변환

    Args:
        period: 기간 문자열 ("1W", "1M", "3M", "6M", "1Y", "YTD", "MAX")

    Returns:
        일수 (int)
    """
    period_map = {
        "1W": 7,
        "1M": 30,
        "3M": 90,
        "6M": 180,
        "1Y": 365,
        "YTD": (datetime.now() - datetime(datetime.now().year, 1, 1)).days,
        "MAX": 1825  # 5년
    }
    days = period_map.get(period, 180)  # 기본값 6개월
    logger.info(f"기간 변환: {period} → {days}일")
    return days


def fetch_stock_data(symbol: str, period: str = "6M") -> pd.DataFrame:
    """
    주식 데이터 가져오기 (FinanceDataReader)

    Args:
        symbol: 종목 코드
        period: 기간 문자열 ("1W", "1M", "3M", "6M", "1Y", "YTD", "MAX")

    Returns:
        OHLCV 데이터프레임
    """
    try:
        days = convert_period_to_days(period)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)  # 여유분 추가 (지표 계산용)

        logger.info(f"주식 데이터 가져오는 중: {symbol} ({start_date.date()} ~ {end_date.date()})")

        df = fdr.DataReader(symbol, start_date, end_date)

        if df.empty:
            logger.error(f"주식 데이터 없음: {symbol}")
            return pd.DataFrame()

        # 최근 days 만큼만 자르기
        df = df.tail(days)

        logger.info(f"데이터 수집 완료: {len(df)}일 ({df.index[0].date()} ~ {df.index[-1].date()})")
        return df

    except Exception as e:
        logger.error(f"주식 데이터 가져오기 실패 {symbol}: {e}")
        return pd.DataFrame()


def create_interactive_chart(
    symbol: str,
    company_name: str,
    period: str = "6M",
    indicators: list = None
) -> go.Figure:
    """
    Plotly 기반 인터랙티브 차트 생성

    Args:
        symbol: 종목 코드 (예: "005930")
        company_name: 회사명 (예: "삼성전자")
        period: 기간 ("1W", "1M", "3M", "6M", "1Y", "YTD", "MAX")
        indicators: 표시할 지표 리스트
                   예: ["MA5", "MA20", "MA60", "BB", "RSI", "MACD", "Stochastic"]
                   None이면 기본 지표: ["MA5", "MA20", "MA60", "RSI", "MACD"]

    Returns:
        plotly.graph_objects.Figure (인터랙티브 차트)
    """
    try:
        logger.info(f"📊 Plotly 차트 생성 시작: {symbol} ({company_name}), 기간={period}")

        # 1. 데이터 가져오기
        df = fetch_stock_data(symbol, period)
        if df.empty:
            logger.error(f"차트 생성 실패: {symbol} 데이터 없음")
            return create_error_chart(f"{company_name} 데이터 없음")

        # 2. 기본 지표 설정
        if indicators is None:
            indicators = ["MA5", "MA20", "MA60", "RSI", "MACD"]

        # 3. 기술적 지표 계산
        logger.info(f"기술적 지표 계산 중: {indicators}")
        df = calculate_all_indicators(df, indicators=indicators)

        # 4. 서브플롯 생성 (4행 1열)
        subplot_titles = ["주가", "거래량", "RSI", "MACD"]
        row_heights = [0.5, 0.15, 0.15, 0.2]

        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=row_heights,
            subplot_titles=subplot_titles,
            specs=[
                [{"secondary_y": False}],  # 주가
                [{"secondary_y": False}],  # 거래량
                [{"secondary_y": False}],  # RSI
                [{"secondary_y": False}]   # MACD
            ]
        )

        # 5. Row 1: 캔들스틱 차트
        # Note: Candlestick은 hovertemplate를 지원하지 않음 (hoverinfo만 지원)
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='주가',
                increasing_line_color='#FF6B6B',  # 상승 (빨강)
                decreasing_line_color='#4ECDC4',  # 하락 (청록)
            ),
            row=1, col=1
        )

        # 6. Row 1: 이동평균선 (MA5, MA20, MA60)
        if 'MA5' in indicators or 'MA' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['MA5'],
                    mode='lines',
                    name='MA5',
                    line=dict(color='#FFD93D', width=1.5),
                    hovertemplate='<b>MA5</b>: %{y:,.0f}원<extra></extra>'
                ),
                row=1, col=1
            )

        if 'MA20' in indicators or 'MA' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['MA20'],
                    mode='lines',
                    name='MA20',
                    line=dict(color='#6BCB77', width=1.5),
                    hovertemplate='<b>MA20</b>: %{y:,.0f}원<extra></extra>'
                ),
                row=1, col=1
            )

        if 'MA60' in indicators or 'MA' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['MA60'],
                    mode='lines',
                    name='MA60',
                    line=dict(color='#4D96FF', width=1.5),
                    hovertemplate='<b>MA60</b>: %{y:,.0f}원<extra></extra>'
                ),
                row=1, col=1
            )

        # 7. Row 1: 볼린저밴드 (선택적)
        if 'BB' in indicators and 'BB_Upper' in df.columns:
            # 상단선
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['BB_Upper'],
                    mode='lines',
                    name='BB Upper',
                    line=dict(color='gray', width=1, dash='dash'),
                    hovertemplate='<b>BB상단</b>: %{y:,.0f}원<extra></extra>',
                    showlegend=False
                ),
                row=1, col=1
            )

            # 하단선
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['BB_Lower'],
                    mode='lines',
                    name='BB Lower',
                    line=dict(color='gray', width=1, dash='dash'),
                    fill='tonexty',  # 상단선까지 채우기
                    fillcolor='rgba(128, 128, 128, 0.1)',
                    hovertemplate='<b>BB하단</b>: %{y:,.0f}원<extra></extra>',
                    showlegend=False
                ),
                row=1, col=1
            )

        # 8. Row 2: 거래량 (색상: 종가-시가 기준)
        colors = ['#FF6B6B' if c >= o else '#4ECDC4'
                  for c, o in zip(df['Close'], df['Open'])]

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['Volume'],
                name='거래량',
                marker_color=colors,
                hovertemplate='<b>날짜</b>: %{x|%Y-%m-%d}<br>' +
                              '<b>거래량</b>: %{y:,.0f}주<br>' +
                              '<extra></extra>'
            ),
            row=2, col=1
        )

        # 9. Row 3: RSI
        if 'RSI' in indicators and 'RSI' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='purple', width=2),
                    hovertemplate='<b>RSI</b>: %{y:.2f}<extra></extra>'
                ),
                row=3, col=1
            )

            # RSI 과매수(70) / 과매도(30) 기준선
            fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="blue", opacity=0.5, row=3, col=1)

            # 과매수/과매도 영역 색칠
            fig.add_hrect(y0=70, y1=100, fillcolor="red", opacity=0.1, row=3, col=1)
            fig.add_hrect(y0=0, y1=30, fillcolor="blue", opacity=0.1, row=3, col=1)

        # 10. Row 4: MACD
        if 'MACD' in indicators and 'MACD' in df.columns:
            # MACD 선
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['MACD'],
                    mode='lines',
                    name='MACD',
                    line=dict(color='blue', width=2),
                    hovertemplate='<b>MACD</b>: %{y:.2f}<extra></extra>'
                ),
                row=4, col=1
            )

            # Signal 선
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df['MACD_Signal'],
                    mode='lines',
                    name='Signal',
                    line=dict(color='orange', width=2),
                    hovertemplate='<b>Signal</b>: %{y:.2f}<extra></extra>'
                ),
                row=4, col=1
            )

            # Histogram
            colors_hist = ['#FF6B6B' if val >= 0 else '#4ECDC4'
                           for val in df['MACD_Hist']]

            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df['MACD_Hist'],
                    name='Histogram',
                    marker_color=colors_hist,
                    hovertemplate='<b>Hist</b>: %{y:.2f}<extra></extra>'
                ),
                row=4, col=1
            )

        # 11. 레이아웃 설정
        fig.update_layout(
            title=dict(
                text=f"{company_name} ({symbol}) - {period} 차트",
                font=dict(size=20, family="Malgun Gothic, sans-serif")
            ),
            hovermode='x unified',  # 모든 서브플롯에서 동시 호버
            xaxis_rangeslider_visible=False,  # 불필요한 레인지 슬라이더 제거
            height=800,  # 전체 높이
            margin=dict(l=50, r=50, t=80, b=50),
            template="plotly_white",  # 깔끔한 흰색 배경
            showlegend=True,
            legend=dict(
                orientation="h",  # 가로 배치
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            # 모바일 최적화
            autosize=True,
            dragmode='zoom'  # 기본 동작: 줌
        )

        # 12. X축 설정 (모든 서브플롯)
        fig.update_xaxes(
            showgrid=True,
            gridwidth=1,
            gridcolor='LightGray',
            zeroline=False,
            tickformat='%m-%d'  # 월-일 형식
        )

        # 13. Y축 설정
        fig.update_yaxes(
            showgrid=True,
            gridwidth=1,
            gridcolor='LightGray',
            zeroline=False
        )

        # RSI Y축 범위 고정
        fig.update_yaxes(range=[0, 100], row=3, col=1)

        # Y축 레이블
        fig.update_yaxes(title_text="가격 (원)", row=1, col=1)
        fig.update_yaxes(title_text="거래량", row=2, col=1)
        fig.update_yaxes(title_text="RSI", row=3, col=1)
        fig.update_yaxes(title_text="MACD", row=4, col=1)

        logger.info(f"✅ Plotly 차트 생성 완료: {symbol}")
        return fig

    except Exception as e:
        logger.error(f"차트 생성 실패 {symbol}: {e}", exc_info=True)
        return create_error_chart(f"차트 생성 오류: {str(e)}")


def create_error_chart(error_message: str) -> go.Figure:
    """
    에러 발생 시 표시할 빈 차트 생성

    Args:
        error_message: 에러 메시지

    Returns:
        에러 메시지를 표시하는 Figure
    """
    fig = go.Figure()
    fig.add_annotation(
        text=f"⚠️ {error_message}",
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=20, color="red", family="Malgun Gothic, sans-serif")
    )
    fig.update_layout(
        height=400,
        margin=dict(l=50, r=50, t=50, b=50),
        template="plotly_white"
    )
    return fig


if __name__ == "__main__":
    """
    테스트 코드
    """
    logging.basicConfig(level=logging.INFO)

    # 삼성전자 6개월 차트 생성
    fig = create_interactive_chart(
        symbol="005930",
        company_name="삼성전자",
        period="6M",
        indicators=["MA5", "MA20", "MA60", "BB", "RSI", "MACD"]
    )

    # HTML로 저장 (브라우저로 확인 가능)
    fig.write_html("test_chart_samsung.html")
    print("[SUCCESS] Test chart created: test_chart_samsung.html")

    # 기아 1년 차트 생성
    fig2 = create_interactive_chart(
        symbol="000270",
        company_name="기아",
        period="1Y",
        indicators=["MA5", "MA20", "MA60", "RSI", "MACD"]
    )

    fig2.write_html("test_chart_kia.html")
    print("[SUCCESS] Test chart created: test_chart_kia.html")
