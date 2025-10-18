import streamlit as st
import logging
from datetime import datetime
import requests

from core.korean_supervisor_langgraph import (
    stream_korean_stock_analysis,
    generate_comprehensive_report,
    get_supervisor_llm,
)
from core.streamlit_parallel_engine import get_parallel_engine
from core.streamlit_conversation_manager import get_conversation_manager
from data.sqlite_client import get_db_client
from utils.streamlit_helpers import (
    render_parallel_progress_dashboard,
    render_parallel_results_summary,
    show_parallel_status_indicator,
)
from config.settings import settings
from utils.helpers import setup_logging
from data.plotly_chart_generator import create_interactive_chart

# 로깅 설정
logger = setup_logging(settings.log_level, enable_file_logging=True)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="📊 AI Stock Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 종목 데이터베이스
STOCK_DATABASE = {
    "대형주": {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "005380": "현대차",
        "068270": "셀트리온",
        "207940": "삼성바이오로직스",
        "005490": "POSCO홀딩스",
        "035720": "카카오",
    },
    "중견주": {
        "028260": "삼성물산",
        "000270": "기아",
        "066570": "LG전자",
        "003550": "LG",
        "017670": "SK텔레콤",
        "030200": "KT",
        "032830": "삼성생명",
    },
    "성장주": {
        "251270": "넷마블",
        "036570": "엔씨소프트",
        "259960": "크래프톤",
        "352820": "하이브",
    },
}


def fetch_news_for_display(company_name):
    try:
        client_id = settings.naver_client_id
        client_secret = settings.naver_client_secret
        if not client_id or not client_secret:
            return []
        search_query = (
            f"{company_name} 주식"
            if company_name == "KT"
            else (
                f"{company_name} 그룹"
                if company_name in ["LG", "SK"]
                else (
                    f"{company_name} 자동차"
                    if company_name == "현대차"
                    else f"{company_name} 주식"
                )
            )
        )
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {"query": search_query, "display": 10, "sort": "sim"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        news_data = response.json()
        return [
            {
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "url": item.get("link", ""),
                "pub_date": item.get("pubDate", "")[:16],
            }
            for item in news_data.get("items", [])
        ]
    except Exception as e:
        logger.error(f"뉴스 데이터 가져오기 실패: {str(e)}")
        return []


def get_agent_config(agent_name):
    configs = {
        "context_expert": ("🌍", "시장 환경 분석", "거시경제 및 시장 동향"),
        "sentiment_expert": ("📰", "뉴스 여론 분석", "뉴스 감정 및 시장 심리"),
        "financial_expert": ("💰", "재무 상태 분석", "재무제표 및 기업 건전성"),
        "advanced_technical_expert": ("📈", "기술적 분석", "차트 패턴 및 기술 지표"),
        "institutional_trading_expert": (
            "🏦",
            "기관 수급 분석",
            "기관투자자 매매 동향",
        ),
        "comparative_expert": ("⚖️", "상대 가치 분석", "동종업계 비교 평가"),
        "esg_expert": ("🌱", "ESG 분석", "지속가능경영 평가"),
        "community_expert": ("💬", "커뮤니티 여론 분석", "실제 투자자 의견 및 심리"),
    }
    return configs.get(agent_name, ("🤖", agent_name, "AI 분석"))


def render_result_card(agent_name, status="waiting", content="", news_sources=None):
    config = get_agent_config(agent_name)
    status_text = {"waiting": "대기 중", "running": "분석 중", "completed": "완료"}
    status_state = {"waiting": "running", "running": "running", "completed": "complete"}
    with st.container():
        st.subheader(f"{config[0]} {config[1]}")
        st.caption(config[2])
        with st.status(status_text[status], state=status_state[status]):
            if not content and status == "waiting":
                st.write(f"{config[1]}을 준비하고 있습니다...")
            else:
                st.write(content)
            if (
                agent_name in ["sentiment_expert", "community_expert"]
                and news_sources
                and status == "completed"
            ):
                with st.expander(
                    f"{'📰' if agent_name == 'sentiment_expert' else '💬'} 분석된 {'뉴스' if agent_name == 'sentiment_expert' else '커뮤니티 게시글'} (상위 5개)"
                ):
                    for i, item in enumerate(news_sources[:5], 1):
                        title = item.get("title", "").strip()
                        url = item.get("url", "")
                        if title:
                            st.link_button(f"{i}. {title}", url)


def run_analysis(symbol, company_name):
    st.session_state.current_analysis_type = "sequential"
    with st.spinner("📰 뉴스 데이터 수집 중..."):
        st.session_state[f"news_sources_{symbol}"] = fetch_news_for_display(
            company_name
        )
    with st.spinner("📈 인터랙티브 차트 생성 중..."):
        # 차트 설정 가져오기 (기본값: 6개월, 기본 지표)
        chart_period = st.session_state.get("chart_period", "6M")
        chart_indicators = st.session_state.get("chart_indicators", ["MA5", "MA20", "MA60", "RSI", "MACD"])

        chart_fig = create_interactive_chart(
            symbol=symbol,
            company_name=company_name,
            period=chart_period,
            indicators=chart_indicators
        )
        st.session_state[f"chart_{symbol}"] = chart_fig if chart_fig else None
        if not chart_fig:
            st.warning("차트 생성 실패: 데이터 없음")
            logger.warning(f"차트 생성 실패: {symbol}")
    st.header(f"📊 {symbol} {company_name} 분석 결과")
    if f"chart_{symbol}" in st.session_state and st.session_state[f"chart_{symbol}"]:
        st.subheader("📈 인터랙티브 차트 분석")
        try:
            st.plotly_chart(
                st.session_state[f"chart_{symbol}"],
                use_container_width=True,
                key=f"chart_plotly_{symbol}_main"
            )
        except Exception as e:
            st.error(f"차트 표시 오류: {e}")
            logger.error(f"차트 표시 오류: {str(e)}", exc_info=True)
        st.divider()
    progress_container = st.empty()
    agent_names = [
        "context_expert",
        "sentiment_expert",
        "financial_expert",
        "advanced_technical_expert",
        "institutional_trading_expert",
        "comparative_expert",
        "esg_expert",
        "community_expert",
    ]
    result_containers = {name: st.empty() for name in agent_names}
    agent_states = {name: {"status": "waiting", "content": ""} for name in agent_names}
    completed_count, final_report = 0, ""

    def update_progress(completed, total, current_agent=""):
        progress_pct = (completed / total) * 100
        status_text = f"{completed}/{total} 분석 완료" + (
            f" • 현재: {get_agent_config(current_agent)[1]}" if current_agent else ""
        )
        with progress_container.container():
            st.subheader("분석 진행 상황")
            st.progress(progress_pct / 100)
            st.metric("진행률", f"{progress_pct:.0f}%")
            st.text(status_text)

    try:
        logger.info(f"주식 분석 시작: {symbol} {company_name} at {datetime.now()}")
        for chunk_data in stream_korean_stock_analysis(symbol, company_name):
            if "error" in chunk_data:
                st.error(f"분석 중 오류: {chunk_data['error']}")
                return
            supervisor_data = chunk_data.get("supervisor", {})
            if supervisor_data:
                messages = supervisor_data.get("messages", [])
                current_stage = supervisor_data.get("current_stage", "")
                if "분석 시작" in current_stage:
                    for agent_name in agent_names:
                        if agent_name in current_stage:
                            agent_states[agent_name]["status"] = "running"
                            with result_containers[agent_name]:
                                render_result_card(agent_name, "running")
                            update_progress(
                                completed_count, len(agent_names), agent_name
                            )
                            break
                if supervisor_data.get("final_report_generated"):
                    for msg in messages:
                        msg_content = (
                            msg.get("content", "")
                            if isinstance(msg, dict)
                            else getattr(msg, "content", str(msg))
                        )
                        if (
                            supervisor_data.get("progressive_mode")
                            and len(msg_content) > 100
                        ):
                            final_report = msg_content.strip()
                            break
                    continue
                completion_signals = {
                    "context_expert": "MARKET_CONTEXT_ANALYSIS_COMPLETE",
                    "sentiment_expert": "SENTIMENT_ANALYSIS_COMPLETE",
                    "financial_expert": "FINANCIAL_ANALYSIS_COMPLETE",
                    "advanced_technical_expert": "ADVANCED_TECHNICAL_ANALYSIS_COMPLETE",
                    "institutional_trading_expert": "INSTITUTIONAL_TRADING_ANALYSIS_COMPLETE",
                    "comparative_expert": "COMPARATIVE_ANALYSIS_COMPLETE",
                    "esg_expert": "ESG_ANALYSIS_COMPLETE",
                    "community_expert": "COMMUNITY_ANALYSIS_COMPLETE",
                }
                for msg in messages:
                    msg_content = (
                        msg.get("content", "")
                        if isinstance(msg, dict)
                        else getattr(msg, "content", str(msg))
                    )
                    for agent_name, signal in completion_signals.items():
                        if (
                            signal in msg_content
                            and agent_states[agent_name]["status"] != "completed"
                        ):
                            content = msg_content.replace(signal, "").strip()
                            if len(content) > 100:
                                agent_states[agent_name]["status"] = "completed"
                                agent_states[agent_name]["content"] = content
                                completed_count += 1
                                card_news_sources = (
                                    st.session_state.get(f"news_sources_{symbol}", [])
                                    if agent_name == "sentiment_expert"
                                    else st.session_state.get(
                                        f"community_sources_{symbol}", []
                                    )
                                )
                                with result_containers[agent_name]:
                                    render_result_card(
                                        agent_name,
                                        "completed",
                                        content,
                                        card_news_sources,
                                    )
                                update_progress(completed_count, len(agent_names))
        if final_report and completed_count >= 5:
            # ✅ 세션 상태에만 저장 (렌더링은 main()에서 수행)
            agent_summaries_dict = {
                name: state["content"]
                for name, state in agent_states.items()
                if state["content"]
            }

            st.session_state.final_report = final_report
            st.session_state.agent_summaries = agent_summaries_dict
            st.session_state.stock_code = symbol
            st.session_state.company_name = company_name

            # ✅ NEW: DB에 보고서 저장
            try:
                db = get_db_client()
                report_id = db.save_analysis_report(
                    stock_code=symbol,
                    company_name=company_name,
                    analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    analysis_method="순차 처리",
                    final_report=final_report,
                    agent_summaries=agent_summaries_dict,
                    news_sources=st.session_state.get(f"news_sources_{symbol}", []),
                    community_sources=st.session_state.get(f"community_sources_{symbol}", []),
                    chart_image=None  # 차트는 세션에서 관리
                )
                st.session_state.current_report_id = report_id
                logger.info(f"✅ 분석 보고서 DB 저장 완료: report_id={report_id}")
            except Exception as e:
                logger.error(f"DB 저장 실패 (계속 진행): {str(e)}")
                st.session_state.current_report_id = None

            # ✅ 분석 완료 후 페이지 새로고침하여 보고서 렌더링 모드로 전환
            st.success("✅ 분석 완료! 보고서를 표시합니다...")
            st.rerun()
        elif completed_count < 7:
            st.warning(f"⚠️ 일부 분석 미완료 ({completed_count}/7)")
        update_progress(completed_count, len(agent_names))
    except Exception as e:
        logger.error(f"분석 오류: {str(e)}", exc_info=True)
        st.error(f"분석 오류: {e}")


def run_parallel_analysis(symbol, company_name):
    try:
        logger.info(f"병렬 분석 시작: {symbol} {company_name} at {datetime.now()}")
        parallel_engine = get_parallel_engine()
        show_parallel_status_indicator()
        st.session_state[f"news_sources_{symbol}"] = fetch_news_for_display(
            company_name or ""
        )
        st.session_state[f"community_sources_{symbol}"] = []
        st.session_state.current_analysis_type = "parallel"
        st.subheader("🚀 병렬 AI 분석 진행 중")
        st.info("8개 에이전트 동시 분석 (1-2분 소요)")
        with st.spinner("분석 중... (실패시 순차 전환)"):
            success = parallel_engine.execute_agents_parallel(symbol, company_name)
            if not success or len(parallel_engine.get_analysis_results()) < 3:
                logger.warning("병렬 실패 - 순차 전환")
                st.warning("병렬 실패 - 순차 전환")
                run_analysis(symbol, company_name)
                return
        analysis_results = parallel_engine.get_analysis_results()
        if len(analysis_results) >= 5:
            st.success(f"완료! {len(analysis_results)}/8 성공")
            supervisor_llm = get_supervisor_llm()
            final_report = generate_comprehensive_report(
                supervisor_llm, analysis_results, symbol, company_name
            )
            if final_report:
                # ✅ 세션 상태에만 저장 (렌더링은 main()에서 수행)
                st.session_state.final_report = final_report
                st.session_state.agent_summaries = analysis_results
                st.session_state.stock_code = symbol
                st.session_state.company_name = company_name

                # ✅ NEW: DB에 보고서 저장
                try:
                    db = get_db_client()
                    report_id = db.save_analysis_report(
                        stock_code=symbol,
                        company_name=company_name,
                        analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        analysis_method="병렬 처리",
                        final_report=final_report,
                        agent_summaries=analysis_results,
                        news_sources=st.session_state.get(f"news_sources_{symbol}", []),
                        community_sources=st.session_state.get(f"community_sources_{symbol}", []),
                        chart_image=None  # 차트는 세션에서 관리
                    )
                    st.session_state.current_report_id = report_id
                    logger.info(f"✅ 분석 보고서 DB 저장 완료: report_id={report_id}")
                except Exception as e:
                    logger.error(f"DB 저장 실패 (계속 진행): {str(e)}")
                    st.session_state.current_report_id = None

                # ✅ 분석 완료 후 페이지 새로고침
                st.success("✅ 병렬 분석 완료! 보고서를 표시합니다...")
                st.rerun()
            else:
                st.error("보고서 생성 실패")
            with st.expander("📊 상세 결과"):
                render_parallel_results_summary()
        else:
            st.error(f"실패: {len(analysis_results)}/8 성공")
            if analysis_results:
                with st.expander("📊 부분 결과"):
                    render_parallel_results_summary()
    except Exception as e:
        logger.error(f"병렬 오류: {str(e)}", exc_info=True)
        st.error(f"병렬 오류: {e}")


def execute_analysis_based_on_method(symbol, company_name, analysis_method):
    if analysis_method == "🚀 병렬 처리 (빠름)":
        run_parallel_analysis(symbol, company_name)
    else:
        run_analysis(symbol, company_name)


def load_saved_report(report_id: int):
    """
    저장된 보고서를 DB에서 로드하여 세션 상태에 복원

    Args:
        report_id: 보고서 ID
    """
    try:
        db = get_db_client()
        report_data = db.load_full_report(report_id)

        if not report_data:
            st.error(f"보고서를 찾을 수 없습니다 (ID: {report_id})")
            return

        # 세션 상태 초기화
        for key in list(st.session_state.keys()):
            del st.session_state[key]

        # 보고서 메타데이터 복원
        st.session_state.stock_code = report_data["stock_code"]
        st.session_state.company_name = report_data["company_name"]
        st.session_state.final_report = report_data["final_report"]
        st.session_state.agent_summaries = report_data.get("agent_summaries", {})
        st.session_state.current_report_id = report_id

        # 뉴스 소스 복원
        symbol = report_data["stock_code"]
        st.session_state[f"news_sources_{symbol}"] = report_data.get("news_sources", [])
        st.session_state[f"community_sources_{symbol}"] = report_data.get("community_sources", [])

        # 대화 히스토리 복원
        st.session_state.chat_messages = report_data.get("conversation_history", [])
        st.session_state.conversation_started = len(st.session_state.chat_messages) > 0

        logger.info(f"✅ 보고서 로드 완료: {report_data['company_name']} ({report_data['analysis_date']})")
        st.success(f"✅ 보고서 로드 완료: {report_data['company_name']} ({report_data['analysis_date']})")
        st.rerun()

    except Exception as e:
        logger.error(f"보고서 로드 실패: {str(e)}")
        st.error(f"보고서 로드 실패: {str(e)}")


def render_conversation_sidebar_status():
    conversation_manager = get_conversation_manager()
    with st.sidebar:
        st.subheader("💬 대화형 Q&A")
        if conversation_manager.is_conversation_available():
            stats = conversation_manager.get_conversation_stats()
            if stats["conversation_started"]:
                st.success("✅ 대화 활성")
                # ✅ 통계 제거: 히스토리는 세션에 저장되고, 초기화 버튼만 제공
                if st.button("🗑️ 대화 초기화", use_container_width=True):
                    st.session_state.chat_messages = []
                    st.session_state.conversation_started = False
                    st.success("대화 내역이 초기화되었습니다")
                    st.rerun()
            else:
                st.info("💬 준비됨")
                st.caption("보고서 하단에서 대화")
        else:
            st.warning("⏳ 대기")
            st.caption("분석 후 가능")

        st.divider()

        # ✅ NEW: 이전 보고서 조회
        with st.expander("📂 이전 보고서", expanded=False):
            try:
                db = get_db_client()
                recent_reports = db.get_recent_reports(limit=15)

                if not recent_reports:
                    st.info("저장된 보고서가 없습니다")
                else:
                    st.caption(f"총 {len(recent_reports)}개 저장됨")

                    # 보고서 목록 표시
                    for report in recent_reports:
                        report_id = report["id"]
                        stock_code = report["stock_code"]
                        company_name = report["company_name"]
                        analysis_date = report["analysis_date"]
                        analysis_method = report.get("analysis_method", "분석")

                        # 날짜 포맷팅 (YYYY-MM-DD HH:MM:SS → MM/DD HH:MM)
                        try:
                            date_obj = datetime.strptime(analysis_date, "%Y-%m-%d %H:%M:%S")
                            date_str = date_obj.strftime("%m/%d %H:%M")
                        except:
                            date_str = analysis_date[:16]

                        # 현재 보고서 강조
                        current_report_id = st.session_state.get("current_report_id")
                        is_current = (report_id == current_report_id)
                        button_label = f"{'▶️ ' if is_current else ''}{company_name} ({stock_code})"

                        if st.button(
                            button_label,
                            key=f"load_report_{report_id}",
                            use_container_width=True,
                            help=f"{date_str} | {analysis_method}",
                            disabled=is_current
                        ):
                            load_saved_report(report_id)

                # DB 통계 표시
                st.caption("---")
                db_stats = db.get_db_stats()
                if db_stats:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("보고서", db_stats.get("total_reports", 0))
                    with col2:
                        st.metric("대화", db_stats.get("total_conversations", 0))

            except Exception as e:
                logger.error(f"이전 보고서 조회 실패: {str(e)}")
                st.error("보고서 조회 실패")


def render_persistent_report():
    """분석 보고서를 session_state 기반으로 지속적으로 렌더링"""
    if not st.session_state.get("final_report"):
        return

    # 보고서 메타데이터
    symbol = st.session_state.get("stock_code", "")
    company_name = st.session_state.get("company_name", "")

    # 차트 표시 (있는 경우)
    if f"chart_{symbol}" in st.session_state and st.session_state[f"chart_{symbol}"]:
        st.subheader("📈 인터랙티브 차트 분석")
        try:
            st.plotly_chart(
                st.session_state[f"chart_{symbol}"],
                use_container_width=True,
                key=f"chart_plotly_{symbol}_report"
            )
        except Exception as e:
            logger.error(f"차트 표시 오류: {str(e)}")
        st.divider()

    # ✅ NEW: 8명 전문가 개별 보고서 표시
    agent_summaries = st.session_state.get("agent_summaries", {})
    if agent_summaries:
        st.header("📊 전문가 분석 상세 보고서")
        st.caption("각 전문가의 상세 분석 내용을 확인하세요 (대화 시 참고 자료)")

        # 에이전트 순서 정의
        agent_order = [
            "context_expert",
            "sentiment_expert",
            "financial_expert",
            "advanced_technical_expert",
            "institutional_trading_expert",
            "comparative_expert",
            "esg_expert",
            "community_expert",
        ]

        # 각 에이전트 보고서 표시
        for agent_name in agent_order:
            if agent_name in agent_summaries:
                content = agent_summaries[agent_name]

                # 뉴스/커뮤니티 소스 가져오기
                news_sources = None
                if agent_name == "sentiment_expert":
                    news_sources = st.session_state.get(f"news_sources_{symbol}", [])
                elif agent_name == "community_expert":
                    news_sources = st.session_state.get(f"community_sources_{symbol}", [])

                # 카드 렌더링
                render_result_card(agent_name, "completed", content, news_sources)

        st.divider()

    # 종합 보고서 표시
    with st.container():
        st.header("🎯 종합 투자 분석 보고서")
        st.markdown(st.session_state.final_report)
        st.download_button(
            "📋 보고서 다운로드",
            data=st.session_state.final_report,
            file_name=f"{symbol}_{company_name}_analysis_report.txt",
            mime="text/plain",
            use_container_width=True,
        )


def main():
    st.title("📊 AI Stock Analyzer")
    st.caption("AI 전문가 7인의 종합 주식 분석")

    # ✅ NEW: 분석 완료 상태인 경우, 보고서를 먼저 렌더링
    if st.session_state.get("final_report"):
        render_persistent_report()
        st.divider()

        # 대화형 인터페이스 렌더링
        conversation_manager = get_conversation_manager()
        if conversation_manager.is_conversation_available():
            conversation_manager.render_conversation_interface()

        # 사이드바에 대화 상태 표시
        render_conversation_sidebar_status()

        # 새 분석 시작 버튼 (하단)
        st.divider()
        if st.button("🔄 새로운 종목 분석하기", type="secondary"):
            # 세션 상태 초기화
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        return  # ✅ 보고서가 있으면 여기서 종료

    # ✅ 기존: 분석 전 상태 - 종목 선택 UI
    with st.container():
        st.subheader("📈 종목 선택")
        input_method = st.radio(
            "입력 방식:",
            ["드롭다운", "직접 입력"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if input_method == "드롭다운":
            category = st.selectbox("카테고리", list(STOCK_DATABASE.keys()))
            stock_options = STOCK_DATABASE[category]
            selected_stock = st.selectbox(
                "종목",
                list(stock_options.keys()),
                format_func=lambda x: f"{stock_options[x]} ({x})",
            )
            symbol = selected_stock
            company_name = stock_options[selected_stock]
        else:
            symbol = st.text_input(
                "종목코드", "005930", placeholder="005930, 000660 등"
            )
            company_name = st.text_input(
                "회사명 (선택)", "삼성전자", placeholder="삼성전자 등"
            )

        # ✅ NEW: 차트 설정 UI
        with st.expander("⚙️ 차트 설정 (선택)", expanded=False):
            st.markdown("**📅 차트 기간 선택**")
            col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

            # 기본값: 6M
            if "chart_period" not in st.session_state:
                st.session_state.chart_period = "6M"

            period_buttons = {
                "1W": (col1, "1주일"),
                "1M": (col2, "1개월"),
                "3M": (col3, "3개월"),
                "6M": (col4, "6개월"),
                "1Y": (col5, "1년"),
                "YTD": (col6, "올해"),
                "MAX": (col7, "전체")
            }

            for period_code, (col, period_label) in period_buttons.items():
                with col:
                    button_type = "primary" if st.session_state.chart_period == period_code else "secondary"
                    if st.button(period_label, key=f"period_btn_{period_code}", type=button_type, use_container_width=True):
                        st.session_state.chart_period = period_code

            st.markdown("**📊 기술적 지표 선택**")

            # 기본값: MA5, MA20, MA60, RSI, MACD
            if "chart_indicators" not in st.session_state:
                st.session_state.chart_indicators = ["MA5", "MA20", "MA60", "RSI", "MACD"]

            available_indicators = {
                "MA5": "이동평균선 5일",
                "MA20": "이동평균선 20일",
                "MA60": "이동평균선 60일",
                "BB": "볼린저밴드",
                "RSI": "RSI (14)",
                "MACD": "MACD",
                "Stochastic": "스토캐스틱"
            }

            selected_indicators = st.multiselect(
                "표시할 지표를 선택하세요",
                options=list(available_indicators.keys()),
                default=st.session_state.chart_indicators,
                format_func=lambda x: available_indicators[x],
                key="indicator_multiselect"
            )

            # multiselect 변경 시 session_state 업데이트
            if selected_indicators != st.session_state.chart_indicators:
                st.session_state.chart_indicators = selected_indicators

            st.caption(f"현재 설정: {st.session_state.chart_period} 기간, {len(st.session_state.chart_indicators)}개 지표")

        analysis_method = st.radio(
            "분석 방법:",
            ["🔄 순차 (안정)", "🚀 병렬 (빠름)"],
            help="순차: 3-5분\n병렬: 1-2분 (Rate Limit 위험)",
            horizontal=True,
        )
        if analysis_method == "🔄 순차 (안정)":
            st.info("순차: 실시간 진행 확인 (권장)")
        else:
            st.warning("병렬: 동시 분석, Rate Limit 위험")
        button_text = "🔄 순차 시작" if "순차" in analysis_method else "🚀 병렬 시작"
        if st.button(button_text, type="primary", use_container_width=True) and symbol:
            execute_analysis_based_on_method(
                symbol.strip(), company_name.strip() or None, analysis_method
            )
        else:
            if not symbol:
                st.error("종목코드 입력")
    with st.expander("ℹ️ 시스템 정보"):
        st.markdown(
            "**🤖 AI 전문가:** 🌍 시장환경 📰 뉴스여론 💰 재무 📈 기술 🏦 기관 ⚖️ 상대 🌱 ESG\n**📊 데이터:** FinanceDataReader • PyKRX 등\n**💬 Q&A:** 분석 후 대화 가능"
        )

    render_conversation_sidebar_status()


if __name__ == "__main__":
    main()
