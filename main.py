import streamlit as st
import logging
from datetime import datetime
from PIL import Image

from core.korean_supervisor_langgraph import stream_korean_stock_analysis
from config.settings import settings
from utils.helpers import setup_logging

# 로깅 설정
logger = setup_logging(settings.log_level)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="🇰🇷 한국 주식 분석 AI 에이전트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 스타일 설정
st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)


def validate_korean_stock_symbol(symbol: str) -> bool:
    """한국 주식 코드 검증 (6자리 숫자)"""
    if not symbol:
        return False
    return len(symbol) == 6 and symbol.isdigit()


def display_korean_financial_results(financial_data: dict):
    """재무 분석 결과 표시"""
    st.subheader("📊 재무 분석 결과")

    if "error" in financial_data:
        st.error(f"재무 데이터 수집 실패: {financial_data['error']}")
        return

    try:
        # 메시지에서 정보 추출
        if "messages" in financial_data:
            latest_message = financial_data["messages"][-1]
            st.info(latest_message.content)

        # 차트 표시 (있다면)
        col1, col2 = st.columns([2, 1])

        with col1:
            try:
                img = Image.open("korean_stock_chart.png")
                st.image(img, caption="주가 차트", use_container_width=True)
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

    if "error" in sentiment_data:
        st.error(f"감정 분석 실패: {sentiment_data['error']}")
        return

    try:
        if "messages" in sentiment_data:
            latest_message = sentiment_data["messages"][-1]
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

    if "error" in report_data:
        st.error(f"보고서 생성 실패: {report_data['error']}")
        return

    try:
        if "messages" in report_data:
            latest_message = report_data["messages"][-1]
            st.success(latest_message.content)

        st.write("**보고서 구성**")
        st.write("- 경영진 요약 (Executive Summary)")
        st.write("- 상세 분석 보고서 (GPT-4 기반)")
        st.write("- 리스크 평가 (Risk Assessment)")
        st.write("- 투자 의견 및 추천")

    except Exception as e:
        st.error(f"보고서 표시 중 오류: {str(e)}")


def extract_news_data_from_messages(messages: list) -> list:
    """메시지에서 뉴스 데이터 추출"""
    news_data = []
    
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "collect_korean_news_official_sources":
                    # 도구 결과에서 뉴스 데이터 추출 시도
                    pass
        
        # 메시지 내용에서 뉴스 정보 파싱 (간단한 방법)
        if hasattr(msg, "content") and msg.content:
            content = msg.content
            # 여기서 뉴스 링크와 제목을 파싱할 수 있지만
            # 더 나은 방법은 분석 결과에서 직접 가져오는 것
    
    return news_data


def display_news_links_section(analysis_result: dict, stock_symbol: str = None, company_name: str = None):
    """뉴스 링크 섹션 표시 - 실시간 뉴스 수집"""
    try:
        st.markdown("---")
        st.subheader("📰 수집된 뉴스 목록")
        st.caption("클릭하면 원문 기사로 이동합니다")
        
        # 실시간으로 뉴스 데이터 수집 (하드코딩 제거)
        news_data = []
        
        if stock_symbol or company_name:
            try:
                # 뉴스 수집 도구 직접 호출
                from agents.korean_sentiment_react_agent import collect_korean_news_official_sources
                
                search_keyword = company_name if company_name else stock_symbol
                
                with st.spinner(f"'{search_keyword}' 관련 뉴스를 수집하고 있습니다..."):
                    news_result = collect_korean_news_official_sources.invoke({
                        'keyword': search_keyword,
                        'company_name': company_name
                    })
                
                news_data = news_result.get('news_data', [])
                news_count = news_result.get('news_count', 0)
                
                st.success(f"✅ {news_count}개의 최신 뉴스를 수집했습니다!")
                
            except Exception as collect_error:
                st.error(f"뉴스 수집 실패: {str(collect_error)}")
                news_data = []
        
        if news_data:
            for i, news in enumerate(news_data[:15], 1):  # 상위 15개만 표시
                title = news.get('title', '제목 없음')
                url = news.get('link', '#')
                source = news.get('source', '출처 미상')
                description = news.get('description') or news.get('content', '')
                pub_date = news.get('pubDate', '')
                
                # HTML 태그 제거
                import re
                title = re.sub('<[^<]+?>', '', title)
                description = re.sub('<[^<]+?>', '', description)
                
                with st.expander(f"{i}. {title[:60]}..." if len(title) > 60 else f"{i}. {title}"):
                    col1, col2 = st.columns([4, 1])
                    
                    with col1:
                        # 클릭 가능한 링크 - target="_blank"로 새 탭에서 열기
                        if url != '#' and url:
                            st.markdown(f'<a href="{url}" target="_blank" style="color: #1f77b4; font-weight: bold;">📰 원문 보기</a>', unsafe_allow_html=True)
                        else:
                            st.write("**링크 없음**")
                        
                        st.write(f"**출처:** {source}")
                        
                        if pub_date:
                            st.write(f"**발행일:** {pub_date}")
                        
                        if description:
                            truncated_desc = description[:250] + "..." if len(description) > 250 else description
                            st.write(f"**요약:** {truncated_desc}")
                    
                    with col2:
                        if url != '#' and url:
                            # URL 텍스트 박스로 복사 편의성 제공
                            st.text_area("URL", url, height=80, key=f"url_{i}", help="URL을 복사할 수 있습니다")
                        
            # 통계 정보
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("수집된 뉴스", len(news_data))
            with col_stat2:
                sources = list(set([news.get('source', '미상') for news in news_data]))
                st.metric("뉴스 출처", len(sources))
            with col_stat3:
                st.metric("표시된 뉴스", min(len(news_data), 15))
                
        else:
            st.info("💡 수집된 뉴스가 없습니다. 종목코드나 회사명을 확인해주세요.")
        
    except Exception as e:
        st.error(f"뉴스 링크 표시 중 오류: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


def display_supervisor_results(analysis_result: dict):
    """새로운 supervisor 결과를 Streamlit에 표시"""
    try:
        messages = analysis_result.get("messages", [])

        st.subheader("🤖 AI 분석 과정")

        # 에이전트별 결과 분류 (개선된 로직)
        financial_messages = []
        sentiment_messages = []
        report_messages = []
        supervisor_messages = []
        debug_info = {"total_messages": len(messages), "agent_breakdown": {}}

        for msg in messages:
            msg_name = getattr(msg, "name", None)
            msg_type = getattr(msg, "type", None)
            msg_content = getattr(msg, "content", "")
            
            # 디버깅 정보 수집
            key = msg_name or msg_type or "unknown"
            debug_info["agent_breakdown"][key] = debug_info["agent_breakdown"].get(key, 0) + 1
            
            # 에이전트별 분류 (더 유연한 방식)
            if msg_name:
                if "financial" in msg_name.lower():
                    financial_messages.append(msg)
                elif "sentiment" in msg_name.lower():
                    sentiment_messages.append(msg)
                elif "report" in msg_name.lower():
                    report_messages.append(msg)
                elif "supervisor" in msg_name.lower():
                    supervisor_messages.append(msg)
            
            # 메시지 내용 기반 분류 (백업)
            elif msg_content:
                content_lower = msg_content.lower()
                if "financial_analysis_complete" in content_lower or "차트" in content_lower:
                    financial_messages.append(msg)
                elif "sentiment_analysis_complete" in content_lower or "뉴스" in content_lower:
                    sentiment_messages.append(msg)
                elif "report_generation_complete" in content_lower or "투자 보고서" in content_lower:
                    report_messages.append(msg)
                elif "분석이 완료되었습니다" in content_lower:
                    supervisor_messages.append(msg)
        
        # 디버깅 정보 표시
        with st.expander("🔧 디버깅 정보 (개발용)", expanded=False):
            st.json(debug_info)
            st.write(f"**에이전트별 메시지 수:**")
            st.write(f"- 📊 재무분석: {len(financial_messages)}개")
            st.write(f"- 📰 뉴스감정: {len(sentiment_messages)}개") 
            st.write(f"- 📋 투자보고서: {len(report_messages)}개")
            st.write(f"- 🎯 종합분석: {len(supervisor_messages)}개")

        # 탭으로 결과 구성
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 재무분석", "📰 뉴스감정", "📋 투자보고서", "🎯 종합분석"]
        )

        with tab1:
            st.subheader("📊 재무 분석 결과")
            if financial_messages:
                for msg in financial_messages:
                    if hasattr(msg, "content") and msg.content:
                        st.markdown(msg.content)
            else:
                st.warning("📊 재무 분석 결과가 없습니다.")
                st.info("💡 **가능한 원인**: Financial Expert 에이전트가 실행되지 않았거나 API 오류로 중단되었을 수 있습니다.")

            # 차트 표시 시도
            try:
                img = Image.open("korean_stock_chart.png")
                st.image(img, caption="주가 차트", use_container_width=True)
            except FileNotFoundError:
                st.info("차트 이미지를 찾을 수 없습니다.")

        with tab2:
            st.subheader("📰 뉴스 감정 분석")
            if sentiment_messages:
                for msg in sentiment_messages:
                    if hasattr(msg, "content") and msg.content:
                        if msg.content.strip():  # 빈 내용 제외
                            st.markdown(msg.content)
                        else:
                            st.warning("감정 분석이 완료되지 않았습니다.")
                            
                # 뉴스 링크 리스트 표시 (실시간 수집)
                # 세션 상태에서 현재 분석 중인 종목 정보 가져오기
                current_symbol = st.session_state.get('current_stock_symbol', None)
                current_company = st.session_state.get('current_company_name', None)
                display_news_links_section(analysis_result, current_symbol, current_company)
            else:
                st.warning("📰 감정 분석 결과가 없습니다.")
                st.info("💡 **가능한 원인**: Sentiment Expert 에이전트가 호출되지 않았습니다. 이는 이전 단계(재무분석)에서 오류가 발생했거나 API 할당량이 초과되었을 가능성이 있습니다.")
                st.markdown("**🔧 해결 방법**: API 할당량을 확인하거나 잠시 후 다시 시도해주세요.")

        with tab3:
            st.subheader("📋 투자 보고서")
            if report_messages:
                for msg in report_messages:
                    if hasattr(msg, "content") and msg.content:
                        st.markdown(msg.content)
            else:
                st.warning("📋 투자 보고서 결과가 없습니다.")
                st.info("💡 **가능한 원인**: Report Expert 에이전트가 호출되지 않았습니다. 이는 재무분석 또는 감정분석 단계에서 오류가 발생했을 가능성이 있습니다.")
                st.markdown("**📋 Report Expert 실행 조건**: 재무분석 + 감정분석이 모두 완료되어야 실행됩니다.")

        with tab4:
            st.subheader("🎯 AI Supervisor 종합 분석")
            if supervisor_messages:
                # 마지막 supervisor 메시지(종합 분석)를 우선 표시
                for msg in reversed(supervisor_messages):
                    if hasattr(msg, "content") and msg.content:
                        if "분석이 완료되었습니다" in msg.content:
                            st.success("✅ 분석 완료")
                            st.markdown(msg.content)
                            break
            else:
                st.warning("🎯 종합 분석 결과가 없습니다.")
                st.info("💡 **가능한 원인**: Supervisor가 최종 종합 분석을 수행하지 못했습니다. 이는 모든 전문 에이전트(재무+감정+보고서)가 완료되지 않았기 때문일 가능성이 높습니다.")
                st.markdown("**🎯 Supervisor 실행 조건**: 3개 전문 에이전트가 모두 완료되어야 최종 종합 분석을 수행합니다.")
                
                # 추가 도움말
                with st.expander("📚 LangGraph Supervisor 워크플로우 설명"):
                    st.markdown("""
                    **순차 실행 구조:**
                    1. 🎯 Supervisor → 📊 Financial Expert (재무 분석)
                    2. 📊 Financial Expert → 🎯 Supervisor 
                    3. 🎯 Supervisor → 📰 Sentiment Expert (감정 분석)
                    4. 📰 Sentiment Expert → 🎯 Supervisor
                    5. 🎯 Supervisor → 📋 Report Expert (투자 보고서)
                    6. 📋 Report Expert → 🎯 Supervisor
                    7. 🎯 Supervisor → **최종 종합 분석** ✨
                    
                    현재는 단계 1-2에서 중단된 상태로 보입니다.
                    """)

    except Exception as e:
        st.error(f"결과 표시 중 오류: {str(e)}")
        logger.error(f"Display error: {e}")


def run_korean_analysis(symbol: str, company_name: str = None):
    """한국 주식 분석을 새로운 LangGraph Supervisor로 실행"""

    # 세션 상태에 현재 분석 종목 저장
    st.session_state['current_stock_symbol'] = symbol
    st.session_state['current_company_name'] = company_name

    st.info(f"🔄 {symbol} ({company_name or '회사명 미상'}) 분석을 시작합니다...")

    # 진행 상황 컨테이너
    progress_container = st.empty()
    results_container = st.empty()

    try:
        # LangGraph Supervisor 실행 (스트리밍)
        all_chunks = []
        current_progress = 0.0

        for chunk_data in stream_korean_stock_analysis(symbol, company_name):
            all_chunks.append(chunk_data)

            # 진행 상황 업데이트
            if isinstance(chunk_data, dict) and "supervisor" in chunk_data:
                supervisor_data = chunk_data["supervisor"]
                current_progress = supervisor_data.get("progress", current_progress)
                current_stage = supervisor_data.get("current_stage", "processing")

                with progress_container.container():
                    st.progress(min(current_progress, 1.0))
                    st.write(f"**현재 단계**: {current_stage}")

                    # 실시간 메시지 미리보기
                    chunk_info = supervisor_data.get("chunk", {})
                    if isinstance(chunk_info, dict) and "supervisor" in chunk_info:
                        messages = chunk_info["supervisor"].get("messages", [])
                        if messages:
                            latest_msg = messages[-1]
                            if hasattr(latest_msg, "content") and latest_msg.content:
                                with st.expander(
                                    f"최신 업데이트 (길이: {len(latest_msg.content)} 문자)"
                                ):
                                    st.text(
                                        latest_msg.content[:200] + "..."
                                        if len(latest_msg.content) > 200
                                        else latest_msg.content
                                    )

        # 최종 결과 표시
        if all_chunks:
            with results_container.container():
                # 마지막 chunk에서 전체 결과 추출
                final_chunk = all_chunks[-1]
                if isinstance(final_chunk, dict) and "supervisor" in final_chunk:
                    supervisor_data = final_chunk["supervisor"]
                    chunk_info = supervisor_data.get("chunk", {})

                    if isinstance(chunk_info, dict) and "supervisor" in chunk_info:
                        analysis_result = chunk_info["supervisor"]
                        display_supervisor_results(analysis_result)
                    else:
                        st.warning("분석 결과 구조를 인식할 수 없습니다.")
                        st.json(final_chunk)  # 디버깅용

        st.success("✅ 분석이 완료되었습니다!")
        return all_chunks

    except Exception as e:
        logger.error(f"분석 중 오류 발생: {str(e)}")
        st.error(f"분석 중 오류가 발생했습니다: {str(e)}")
        import traceback

        st.error(traceback.format_exc())
        return None


def main():
    """메인 애플리케이션"""
    st.markdown(
        '<h1 class="main-header">🇰🇷 한국 주식 분석 AI 에이전트</h1>',
        unsafe_allow_html=True,
    )
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
            "207940": "삼성바이오로직스",
        }

        selected_popular = st.selectbox(
            "인기 종목에서 선택:",
            options=list(popular_stocks.keys()),
            format_func=lambda x: f"{x} ({popular_stocks[x]})",
            index=0,
        )

        # 또는 직접 입력
        st.subheader("직접 입력")
        stock_symbol = st.text_input(
            "한국 종목코드 (6자리):",
            value=selected_popular,
            help="예: 005930 (삼성전자)",
        )

        company_name = st.text_input(
            "회사명 (선택사항):",
            value=popular_stocks.get(stock_symbol, ""),
            help="예: 삼성전자",
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
                    mime="application/json",
                )

    else:
        # 초기 화면 - 시스템 현황 요약
        st.markdown("### 📈 시스템 현황")
        
        col_info1, col_info2, col_info3 = st.columns(3)
        
        with col_info1:
            st.metric(
                label="지원 데이터 소스", 
                value="5개", 
                delta="공식 API 전용"
            )
            
        with col_info2:
            st.metric(
                label="AI 에이전트", 
                value="3개", 
                delta="전문화된 분석"
            )
            
        with col_info3:
            st.metric(
                label="지원 시장", 
                value="KRX", 
                delta="KOSPI/KOSDAQ 전체"
            )

        st.markdown("### 🎯 시스템 특징")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                """
            **📊 재무 분석**
            - 주가 데이터 수집 (FinanceDataReader, PyKRX)
            - DART 공시 정보 및 재무제표
            - 업종 및 경제 지표 분석
            - 한국어 라벨 차트 생성
            """
            )

        with col2:
            st.markdown(
                """
            **📰 감정 분석**
            - 네이버 뉴스 API (공식)
            - AI 기반 한국어 감정 분석
            - 시장 센티먼트 평가
            - 뉴스 임팩트 예측
            """
            )

        with col3:
            st.markdown(
                """
            **📋 투자 보고서**
            - 기관급 투자 보고서 생성
            - BUY/HOLD/SELL 추천
            - 목표가 및 리스크 평가
            - 3M/6M/12M 전망
            """
            )

        st.markdown("### 🔧 기술 스택")
        
        tech_col1, tech_col2 = st.columns(2)
        
        with tech_col1:
            st.markdown(
                """
            **🤖 AI & ML**
            - LangGraph Supervisor Pattern
            - Google Gemini 2.5 Flash
            - ReAct Agent 아키텍처
            """
            )
            
        with tech_col2:
            st.markdown(
                """
            **📊 데이터 소스**
            - FinanceDataReader (KRX 주가)
            - PyKRX (HTS 데이터)
            - DART (공시정보)
            - 한은 API (경제지표)
            - 네이버 뉴스 API
            """
            )


if __name__ == "__main__":
    main()
