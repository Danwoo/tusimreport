import streamlit as st
import logging
from datetime import datetime
from PIL import Image

from agents.korean_supervisor_langgraph import stream_korean_stock_analysis
from config.settings import settings
from utils.helpers import setup_logging

# 로깅 설정
logger = setup_logging(settings.log_level)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="🇰🇷 한국 주식 분석 AI 에이전트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 스타일 설정
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin-bottom: 1rem;
    }
    .status-success { color: #28a745; font-weight: bold; }
    .status-warning { color: #ffc107; font-weight: bold; }
    .status-danger { color: #dc3545; font-weight: bold; }
    .buy { background-color: #d4edda; color: #155724; }
    .hold { background-color: #fff3cd; color: #856404; }
    .sell { background-color: #f8d7da; color: #721c24; }
</style>
""", unsafe_allow_html=True)

def validate_korean_stock_symbol(symbol: str) -> bool:
    """한국 주식 코드 검증 (6자리 숫자)"""
    if not symbol:
        return False
    return len(symbol) == 6 and symbol.isdigit()

def display_korean_financial_results(financial_data: dict):
    """재무 분석 결과 표시"""
    st.subheader("📊 재무 분석 결과")
    
    if 'error' in financial_data:
        st.error(f"재무 데이터 수집 실패: {financial_data['error']}")
        return
    
    try:
        # 메시지에서 정보 추출
        if 'messages' in financial_data:
            latest_message = financial_data['messages'][-1]
            st.info(latest_message.content)
        
        # 차트 표시 (있다면)
        col1, col2 = st.columns([2, 1])
        
        with col1:
            try:
                img = Image.open("korean_stock_chart.png")
                st.image(img, caption="주가 차트", use_column_width=True)
            except FileNotFoundError:
                st.info("차트 이미지를 생성하지 못했습니다.")
        
        with col2:
            st.write("**분석 요약**")
            st.write("- FinanceDataReader 데이터 수집 완료")
            st.write("- PyKRX 시장 데이터 연동")
            st.write("- 기술적 분석 수행")
            
    except Exception as e:
        st.error(f"재무 결과 표시 중 오류: {str(e)}")

def display_korean_sentiment_results(sentiment_data: dict):
    """감정 분석 결과 표시"""
    st.subheader("📰 뉴스 감정 분석")
    
    if 'error' in sentiment_data:
        st.error(f"감정 분석 실패: {sentiment_data['error']}")
        return
    
    try:
        if 'messages' in sentiment_data:
            latest_message = sentiment_data['messages'][-1]
            st.info(latest_message.content)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.write("**뉴스 소스**")
            st.write("- 네이버 뉴스 API")
            st.write("- 구글 뉴스 RSS")
            st.write("- 다음 뉴스")
            
        with col2:
            st.write("**분석 방식**")
            st.write("- GPT-4 한국어 감정 분석")
            st.write("- 뉴스 키워드 추출")
            st.write("- 시장 센티먼트 평가")
            
    except Exception as e:
        st.error(f"감정 결과 표시 중 오류: {str(e)}")

def display_korean_report_results(report_data: dict):
    """투자 보고서 결과 표시"""
    st.subheader("📋 종합 투자 보고서")
    
    if 'error' in report_data:
        st.error(f"보고서 생성 실패: {report_data['error']}")
        return
    
    try:
        if 'messages' in report_data:
            latest_message = report_data['messages'][-1]
            st.success(latest_message.content)
        
        st.write("**보고서 구성**")
        st.write("- 경영진 요약 (Executive Summary)")
        st.write("- 상세 분석 보고서 (GPT-4 기반)")
        st.write("- 리스크 평가 (Risk Assessment)")
        st.write("- 투자 의견 및 추천")
        
    except Exception as e:
        st.error(f"보고서 표시 중 오류: {str(e)}")

def run_korean_analysis(symbol: str, company_name: str = None):
    """한국 주식 분석을 LangGraph로 실행"""
    
    st.info(f"🔄 {symbol} ({company_name or '회사명 미상'}) 분석을 시작합니다...")
    
    # 진행 상황 컨테이너
    progress_container = st.empty()
    results_container = st.empty()
    
    try:
        # LangGraph 실행 (스트리밍)
        final_results = None
        
        for chunk in stream_korean_stock_analysis(symbol, company_name):
            # chunk는 {node_name: state} 형태
            for node_name, state in chunk.items():
                current_stage = state.get("current_stage", "unknown")
                progress = state.get("progress", 0.0)
                
                # 진행 상황 업데이트
                with progress_container.container():
                    st.progress(progress)
                    st.write(f"**현재 단계**: {current_stage}")
                    st.write(f"**처리 중**: {node_name}")
                
                # 최종 결과 저장
                final_results = state
        
        # 최종 결과 표시
        if final_results:
            with results_container.container():
                if final_results.get("financial_data"):
                    display_korean_financial_results(final_results["financial_data"])
                    
                if final_results.get("sentiment_data"):
                    display_korean_sentiment_results(final_results["sentiment_data"])
                    
                if final_results.get("report_data"):
                    display_korean_report_results(final_results["report_data"])
        
        st.success("✅ 분석이 완료되었습니다!")
        return final_results
        
    except Exception as e:
        logger.error(f"분석 중 오류 발생: {str(e)}")
        st.error(f"분석 중 오류가 발생했습니다: {str(e)}")
        return None

def main():
    """메인 애플리케이션"""
    st.markdown('<h1 class="main-header">🇰🇷 한국 주식 분석 AI 에이전트</h1>', unsafe_allow_html=True)
    st.markdown("**LangGraph Supervisor Pattern** 기반 멀티 에이전트 시스템")
    
    # 사이드바
    with st.sidebar:
        st.header("📈 주식 분석")
        
        # 인기 종목
        st.subheader("인기 종목")
        popular_stocks = {
            "005930": "삼성전자",
            "035720": "카카오", 
            "035420": "네이버",
            "000660": "SK하이닉스",
            "005380": "현대차",
            "051910": "LG화학",
            "006400": "삼성SDI",
            "207940": "삼성바이오로직스"
        }
        
        selected_popular = st.selectbox(
            "인기 종목에서 선택:",
            options=list(popular_stocks.keys()),
            format_func=lambda x: f"{x} ({popular_stocks[x]})",
            index=0
        )
        
        # 또는 직접 입력
        st.subheader("직접 입력")
        stock_symbol = st.text_input(
            "한국 종목코드 (6자리):",
            value=selected_popular,
            help="예: 005930 (삼성전자)"
        )
        
        company_name = st.text_input(
            "회사명 (선택사항):",
            value=popular_stocks.get(stock_symbol, ""),
            help="예: 삼성전자"
        )
        
        analyze_button = st.button("🔍 분석 시작", type="primary")
    
    # 메인 컨테이너
    if analyze_button:
        if not validate_korean_stock_symbol(stock_symbol):
            st.error("❌ 올바른 한국 종목코드를 입력하세요 (6자리 숫자)")
        else:
            # 분석 실행
            results = run_korean_analysis(stock_symbol, company_name)
            
            # 결과가 있으면 다운로드 버튼 제공
            if results:
                st.download_button(
                    label="📊 분석 결과 다운로드 (JSON)",
                    data=str(results),
                    file_name=f"korean_stock_analysis_{stock_symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    else:
        # 초기 화면
        st.markdown("### 🎯 시스템 특징")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **📊 재무 분석**
            - FinanceDataReader
            - PyKRX 데이터
            - 기술적 분석
            """)
        
        with col2:
            st.markdown("""
            **📰 감정 분석**
            - 네이버 뉴스 API
            - 구글 뉴스 RSS
            - GPT-4 감정 분석
            """)
        
        with col3:
            st.markdown("""
            **📋 투자 보고서**
            - 경영진 요약
            - 상세 분석
            - 리스크 평가
            """)
        
        st.markdown("### 🔧 기술 스택")
        st.markdown("""
        - **LangGraph**: Supervisor Pattern Multi-Agent System
        - **OpenAI GPT-4**: 한국어 분석 및 보고서 생성
        - **한국 데이터**: FinanceDataReader, PyKRX, 네이버 API
        - **실시간 UI**: Streamlit 스트리밍
        """)

if __name__ == "__main__":
    main()