import streamlit as st
import logging
from datetime import datetime
from PIL import Image
import time
import requests

from core.korean_supervisor_langgraph import stream_korean_stock_analysis
from core.chat_session import create_chat_session
from config.settings import settings, get_api_key_status, check_minimum_requirements
from utils.helpers import setup_logging
from data.chart_generator import create_stock_chart
from utils.agent_helpers import validate_stock_code

# 로깅 설정 - 파일 로깅 활성화
logger = setup_logging(settings.log_level, enable_file_logging=True)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="📊 AI Stock Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 간소화된 스타일
st.markdown("""
<style>
    .main > div { padding-top: 0.5rem; max-width: 1200px; margin: 0 auto; }
    .main-header { text-align: center; padding: 1rem 0 0.5rem 0; border-bottom: 1px solid #f1f5f9; margin-bottom: 1rem; }
    .main-title { font-size: 2rem; font-weight: 700; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .main-subtitle { font-size: 1rem; color: #64748b; margin: 0.3rem 0 0 0; }
    .input-section { background: white; padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0;
                     margin-bottom: 1rem; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
    .input-header { font-size: 1.1rem; font-weight: 600; color: #334155; margin: 0 0 1rem 0; }
    .popular-stocks { background: #f8fafc; padding: 0.8rem; border-radius: 6px; border: 1px solid #e2e8f0; }
    .popular-title { font-size: 0.85rem; font-weight: 600; color: #475569; margin: 0 0 0.5rem 0; text-align: center; }
    .stock-btn { display: block; width: 100%; padding: 0.4rem; margin: 0.2rem 0; background: white;
                 border: 1px solid #e2e8f0; border-radius: 4px; color: #334155; font-size: 0.75rem;
                 text-align: center; transition: all 0.15s ease; cursor: pointer; }
    .stock-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }
    .progress-section { background: white; padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0;
                        margin: 0.8rem 0; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
    .progress-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem; }
    .progress-title { font-size: 1rem; font-weight: 600; color: #334155; margin: 0; }
    .progress-percentage { font-size: 1rem; font-weight: 600; color: #667eea; }
    .progress-bar { width: 100%; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; margin: 0.3rem 0; }
    .progress-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 3px; transition: width 0.3s ease; }
    .progress-status { font-size: 0.85rem; color: #64748b; margin: 0.3rem 0 0 0; }
    .results-section { margin-top: 1rem; }
    .result-card { background: white; border-radius: 8px; padding: 1rem; margin: 0.8rem 0; border: 1px solid #e2e8f0;
                   box-shadow: 0 1px 4px rgba(0,0,0,0.04); border-left: 3px solid var(--accent-color); }
    .result-header { display: flex; align-items: center; margin-bottom: 0.8rem; padding-bottom: 0.8rem; border-bottom: 1px solid #f1f5f9; }
    .result-icon { font-size: 1.2rem; margin-right: 0.8rem; width: 32px; height: 32px; border-radius: 6px;
                   display: flex; align-items: center; justify-content: center; background: var(--bg-color); }
    .result-title { flex: 1; }
    .result-name { font-size: 1rem; font-weight: 600; color: var(--accent-color); margin: 0; }
    .result-desc { font-size: 0.8rem; color: #64748b; margin: 0.2rem 0 0 0; }
    .result-status { padding: 0.25rem 0.6rem; border-radius: 8px; font-size: 0.7rem; font-weight: 500; text-transform: uppercase; }
    .status-waiting { background: #f1f5f9; color: #64748b; }
    .status-running { background: #fef3c7; color: #92400e; animation: pulse 2s infinite; }
    .status-completed { background: #dcfce7; color: #166534; }
    .result-content { line-height: 1.5; color: #374151; font-size: 0.9rem; white-space: pre-wrap; }
    .final-report { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
                    padding: 1.5rem; border-radius: 8px; margin: 1.5rem 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .report-title { font-size: 1.3rem; font-weight: 700; margin: 0 0 0.8rem 0; }
    .report-content { background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 6px;
                      backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); line-height: 1.5;
                      white-space: pre-wrap; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    @media (max-width: 768px) { .main-title { font-size: 1.8rem; } .input-section { padding: 0.8rem; } }
</style>
""", unsafe_allow_html=True)

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
        "035720": "카카오"
    },
    "중견주": {
        "028260": "삼성물산",
        "000270": "기아",
        "066570": "LG전자",
        "003550": "LG",
        "017670": "SK텔레콤",
        "030200": "KT",
        "032830": "삼성생명"
    },
    "성장주": {
        "251270": "넷마블",
        "036570": "엔씨소프트",
        "259960": "크래프톤",
        "352820": "하이브"
    }
}

def fetch_news_for_display(company_name):
    """UI 표시용 뉴스 데이터 가져오기"""
    try:
        client_id = settings.naver_client_id
        client_secret = settings.naver_client_secret

        if not client_id or not client_secret:
            return []

        # 🔧 최적화된 검색어 (감정 분석과 동일한 로직)
        if company_name == "KT":
            search_query = f"{company_name} 주식"
        elif company_name in ["LG", "SK"]:
            search_query = f"{company_name} 그룹"
        elif company_name in ["현대차"]:
            search_query = f"{company_name} 자동차"
        else:
            search_query = f"{company_name} 주식"

        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {
            "query": search_query,
            "display": 10,
            "sort": "sim",
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        news_data = response.json()

        # 뉴스 데이터 정제
        news_sources = []
        for item in news_data.get("items", []):
            news_sources.append({
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "url": item.get("link", ""),
                "pub_date": item.get("pubDate", "")[:16]  # 날짜만 간단히
            })

        return news_sources

    except Exception as e:
        logger.error(f"뉴스 데이터 가져오기 실패: {str(e)}")
        return []

def get_agent_config(agent_name):
    """에이전트별 설정"""
    configs = {
        "context_expert": ("🌍", "시장 환경 분석", "#3b82f6", "#dbeafe", "거시경제 및 시장 동향"),
        "sentiment_expert": ("📰", "뉴스 여론 분석", "#8b5cf6", "#ede9fe", "뉴스 감정 및 시장 심리"),
        "financial_expert": ("💰", "재무 상태 분석", "#f59e0b", "#fef3c7", "재무제표 및 기업 건전성"),
        "advanced_technical_expert": ("📈", "기술적 분석", "#ef4444", "#fee2e2", "차트 패턴 및 기술 지표"),
        "institutional_trading_expert": ("🏦", "기관 수급 분석", "#06b6d4", "#cffafe", "기관투자자 매매 동향"),
        "comparative_expert": ("⚖️", "상대 가치 분석", "#10b981", "#d1fae5", "동종업계 비교 평가"),
        "esg_expert": ("🌱", "ESG 분석", "#84cc16", "#ecfccb", "지속가능경영 평가"),
        "community_expert": ("💬", "커뮤니티 여론 분석", "#f97316", "#fed7aa", "실제 투자자 의견 및 심리")
    }
    if agent_name in configs:
        icon, name, color, bg, desc = configs[agent_name]
        return {"icon": icon, "name": name, "color": color, "bg": bg, "desc": desc}
    return {"icon": "🤖", "name": agent_name, "color": "#6b7280", "bg": "#f9fafb", "desc": "AI 분석"}

def create_result_card(agent_name, config, status="waiting", content="", news_sources=None):
    """결과 카드 생성 (뉴스 소스 정보 포함)"""
    status_text = {"waiting": "대기 중", "running": "분석 중", "completed": "완료"}
    if not content and status == "waiting":
        content = f"<em style='color: #9ca3af;'>{config['name']}을 준비하고 있습니다...</em>"

    # 🔧 뉴스 감정 분석과 커뮤니티 분석의 경우 데이터 소스 추가
    news_section = ""
    if agent_name == "sentiment_expert" and news_sources and status == "completed":
        news_section = "<div style='margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #f1f5f9;'>"
        news_section += "<h4 style='font-size: 0.9rem; color: #64748b; margin: 0 0 0.5rem 0;'>📰 분석된 뉴스 (상위 5개)</h4>"
        for i, news in enumerate(news_sources[:5], 1):
            title = news.get('title', '').strip()
            url = news.get('url', '')
            if title:
                news_section += f"<div style='margin: 0.3rem 0; font-size: 0.8rem;'>"
                news_section += f"<a href='{url}' target='_blank' style='color: #667eea; text-decoration: none;'>{i}. {title}</a>"
                news_section += "</div>"
        news_section += "</div>"
    elif agent_name == "community_expert" and news_sources and status == "completed":
        news_section = "<div style='margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #f1f5f9;'>"
        news_section += "<h4 style='font-size: 0.9rem; color: #64748b; margin: 0 0 0.5rem 0;'>💬 분석된 커뮤니티 게시글 (상위 5개)</h4>"
        for i, post in enumerate(news_sources[:5], 1):
            title = post.get('title', '').strip()
            url = post.get('url', '')
            if title:
                news_section += f"<div style='margin: 0.3rem 0; font-size: 0.8rem;'>"
                news_section += f"<a href='{url}' target='_blank' style='color: #f97316; text-decoration: none;'>{i}. {title}</a>"
                news_section += "</div>"
        news_section += "</div>"

    return f"""<div class="result-card" style="--accent-color: {config['color']}; --bg-color: {config['bg']};">
        <div class="result-header">
            <div class="result-icon">{config['icon']}</div>
            <div class="result-title">
                <h3 class="result-name">{config['name']}</h3>
                <p class="result-desc">{config['desc']}</p>
            </div>
            <span class="result-status status-{status}">{status_text[status]}</span>
        </div>
        <div class="result-content">{content}{news_section}</div>
    </div>"""

def run_analysis(symbol, company_name):
    """분석 실행"""

    # 🔧 Phase 4.1: 새 분석 시 이전 채팅 세션 초기화
    if 'chat_session' in st.session_state:
        del st.session_state['chat_session']
    if 'chat_history' in st.session_state:
        del st.session_state['chat_history']
    if 'analysis_completed' in st.session_state:
        st.session_state['analysis_completed'] = False

    # 뉴스 데이터 및 차트 미리 생성
    with st.spinner("📰 뉴스 데이터 수집 중..."):
        news_sources = fetch_news_for_display(company_name)
        st.session_state[f"news_sources_{symbol}"] = news_sources

    with st.spinner("📈 차트 생성 중..."):
        chart_base64 = create_stock_chart(symbol, company_name, period=120, chart_type="candle")
        if chart_base64:
            st.session_state[f"chart_{symbol}"] = chart_base64

    # 결과 섹션 시작
    st.markdown(f'<div class="results-section"><h2 style="color: #334155; margin: 0 0 1rem 0; font-size: 1.5rem;">📊 {symbol} {company_name} 분석 결과</h2></div>', unsafe_allow_html=True)

    # 차트 표시
    if f"chart_{symbol}" in st.session_state:
        st.markdown("### 📈 기술적 차트 분석")
        chart_html = f'<img src="data:image/png;base64,{st.session_state[f"chart_{symbol}"]}" style="width: 100%; max-width: 800px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
        st.markdown(chart_html, unsafe_allow_html=True)
        st.markdown("---")
    progress_container = st.empty()

    # 에이전트 설정
    agent_names = ["context_expert", "sentiment_expert", "financial_expert", "advanced_technical_expert", "institutional_trading_expert", "comparative_expert", "esg_expert", "community_expert"]
    result_containers = {}
    for agent_name in agent_names:
        config = get_agent_config(agent_name)
        result_containers[agent_name] = st.empty()
        result_containers[agent_name].markdown(create_result_card(agent_name, config, "waiting"), unsafe_allow_html=True)

    # 상태 변수
    agent_states = {name: {"status": "waiting", "content": ""} for name in agent_names}
    completed_count, final_report = 0, ""

    def update_progress(completed, total, current_agent=""):
        progress_pct = (completed / total) * 100
        status_text = f"{completed}/{total} 분석 완료"
        if current_agent:
            config = get_agent_config(current_agent)
            status_text += f" • 현재: {config['name']}"
        progress_container.markdown(f'<div class="progress-section"><div class="progress-header"><h3 class="progress-title">분석 진행 상황</h3><span class="progress-percentage">{progress_pct:.0f}%</span></div><div class="progress-bar"><div class="progress-fill" style="width: {progress_pct}%;"></div></div><p class="progress-status">{status_text}</p></div>', unsafe_allow_html=True)

    try:
        # 로깅
        logger.info(f"================== 주식 분석 시작 ==================")
        logger.info(f"종목코드: {symbol}")
        logger.info(f"회사명: {company_name}")
        logger.info(f"분석 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"====================================================")

        # 분석 실행
        for chunk_data in stream_korean_stock_analysis(symbol, company_name):
            if "error" in chunk_data:
                st.error(f"분석 중 오류 발생: {chunk_data['error']}")
                return

            supervisor_data = chunk_data.get("supervisor", {})
            if supervisor_data:
                messages = supervisor_data.get("messages", [])
                current_stage = supervisor_data.get("current_stage", "")

                # 진행 중 상태 업데이트
                if "분석 시작" in current_stage:
                    for agent_name in agent_names:
                        if agent_name in current_stage:
                            agent_states[agent_name]["status"] = "running"
                            config = get_agent_config(agent_name)
                            result_containers[agent_name].markdown(
                                create_result_card(agent_name, config, "running"),
                                unsafe_allow_html=True
                            )
                            update_progress(completed_count, len(agent_names), agent_name)
                            break

                # 최종 보고서 처리
                if supervisor_data.get("final_report_generated"):
                    for msg in messages:
                        if isinstance(msg, dict):
                            msg_content = msg.get("content", "")
                        else:
                            msg_content = msg.content if hasattr(msg, "content") else str(msg)

                        if supervisor_data.get("progressive_mode") and len(msg_content) > 100:
                            final_report = msg_content.strip()
                            break
                    continue

                # 에이전트 완료 처리
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
                    if isinstance(msg, dict):
                        msg_content = msg.get("content", "")
                    else:
                        msg_content = msg.content if hasattr(msg, "content") else str(msg)

                    for agent_name, signal in completion_signals.items():
                        if (signal in msg_content and
                            agent_states[agent_name]["status"] != "completed"):

                            content = msg_content.replace(signal, "").strip()
                            if len(content) > 100:
                                agent_states[agent_name]["status"] = "completed"
                                agent_states[agent_name]["content"] = content
                                completed_count += 1

                                # 카드 업데이트
                                config = get_agent_config(agent_name)
                                # 감정 분석과 커뮤니티 분석의 경우 데이터 소스 추가
                                card_news_sources = None
                                if agent_name == "sentiment_expert":
                                    card_news_sources = st.session_state.get(f"news_sources_{symbol}", [])
                                elif agent_name == "community_expert":
                                    card_news_sources = st.session_state.get(f"community_sources_{symbol}", [])

                                result_containers[agent_name].markdown(
                                    create_result_card(agent_name, config, "completed", content, card_news_sources),
                                    unsafe_allow_html=True
                                )

                                update_progress(completed_count, len(agent_names))
                                logger.info(f"===== {config['name']} ({agent_name}) 분석 완료 =====")

        # 최종 보고서 표시
        if final_report and completed_count >= 5:  # 5개 이상 완료시
            st.markdown(f"""
            <div class="final-report">
                <h2 class="report-title">🎯 종합 투자 분석 보고서</h2>
                <div class="report-content">{final_report}</div>
            </div>
            """, unsafe_allow_html=True)

            # 다운로드
            st.download_button(
                label="📋 보고서 다운로드",
                data=final_report,
                file_name=f"{symbol}_{company_name}_analysis_report.txt",
                mime="text/plain",
                use_container_width=True
            )
        elif completed_count < 7:
            st.warning(f"⚠️ 일부 분석이 완료되지 않았습니다 ({completed_count}/7)")

        # 최종 진행률
        update_progress(completed_count, len(agent_names))

        # 🔧 Phase 4: 분석 결과 저장 (채팅용)
        if completed_count >= 5:  # 5개 이상 완료 시
            st.session_state['analysis_completed'] = True
            st.session_state['analysis_symbol'] = symbol
            st.session_state['analysis_company'] = company_name
            st.session_state['analysis_agents'] = agent_states
            st.session_state['analysis_timestamp'] = datetime.now().isoformat()

            # 채팅 세션 생성
            chat_session = create_chat_session(symbol, company_name, agent_states)
            if chat_session:
                st.session_state['chat_session'] = chat_session
                logger.info("Chat session created successfully")

        # 로깅
        logger.info(f"================== 주식 분석 완료 ==================")
        logger.info(f"완료된 전문가 수: {completed_count}/{len(agent_names)}")
        logger.info(f"최종 보고서 생성: {'예' if final_report else '아니오'}")
        logger.info(f"분석 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"====================================================")

    except Exception as e:
        logger.error(f"분석 실행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        st.error(f"분석 프로세스 오류: {e}")

def main():
    # 메인 헤더
    st.markdown("""
    <div class="main-header">
        <h1 class="main-title">📊 AI Stock Analyzer</h1>
        <p class="main-subtitle">AI 전문가 8인의 종합 주식 분석</p>
    </div>
    """, unsafe_allow_html=True)

    # 🔧 Phase 3 개선: API 키 상태 사이드바
    with st.sidebar:
        st.subheader("🔑 API 키 상태")
        api_status = get_api_key_status()
        for key, msg in api_status.items():
            st.write(msg)

        st.divider()
        st.caption("💡 API 키 설정: .env 파일 참고")

    # 🔧 Phase 3 개선: API 키 최소 요구사항 확인
    has_llm, warnings = check_minimum_requirements()

    if not has_llm:
        st.error("❌ **LLM API 키가 필요합니다**\n\n시스템을 사용하려면 다음 중 하나의 API 키를 설정해주세요:\n- Google Gemini API\n- OpenAI API\n\n.env 파일을 확인하고 API 키를 설정해주세요.")

    # 입력 섹션
    st.markdown("""
    <div class="input-section">
        <h3 class="input-header">📈 분석할 종목 선택</h3>
    </div>
    """, unsafe_allow_html=True)

    # 메인 입력 구역
    col1, col2 = st.columns([3, 1])

    with col1:
        # 종목 선택 - 드롭다운 + 직접 입력
        input_method = st.radio(
            "입력 방식 선택:",
            ["드롭다운에서 선택", "직접 입력"],
            horizontal=True,
            label_visibility="collapsed"
        )

        if input_method == "드롭다운에서 선택":
            category = st.selectbox("카테고리 선택", list(STOCK_DATABASE.keys()))
            stock_options = STOCK_DATABASE[category]
            selected_stock = st.selectbox(
                "종목 선택",
                list(stock_options.keys()),
                format_func=lambda x: f"{stock_options[x]} ({x})"
            )
            symbol = selected_stock
            company_name = stock_options[selected_stock]
        else:
            symbol = st.text_input(
                "종목코드",
                value="005930",
                placeholder="예: 005930, 000660, 035420"
            )
            company_name = st.text_input(
                "회사명 (선택)",
                value="삼성전자",
                placeholder="예: 삼성전자, SK하이닉스"
            )

        # 분석 시작 버튼
        if st.button("🚀 AI 분석 시작", type="primary", use_container_width=True):
            if not symbol:
                st.error("❌ 종목코드를 입력해주세요!")
            else:
                # 🔧 Phase 3 개선: 종목 코드 검증
                is_valid, validation_msg = validate_stock_code(symbol.strip())
                if not is_valid:
                    st.error(validation_msg)
                else:
                    run_analysis(symbol.strip(), company_name.strip() if company_name else None)

    with col2:
        # 인기 종목 (오른쪽 사이드)
        st.markdown('<div class="popular-stocks"><p class="popular-title">🔥 인기 종목</p></div>', unsafe_allow_html=True)
        popular_stocks = [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("035420", "NAVER"), ("005380", "현대차")]
        for code, name in popular_stocks:
            if st.button(f"{name}\n{code}", key=f"popular_{code}", use_container_width=True):
                run_analysis(code, name)

    # 시스템 정보
    with st.expander("ℹ️ 시스템 정보"):
        st.markdown("**🤖 AI 전문가 구성 (8인):**\n🌍 시장환경 📰 뉴스여론 💰 재무상태 📈 기술분석 🏦 기관수급 ⚖️ 상대가치 🌱 ESG분석 💬 커뮤니티분석\n\n**📊 데이터:** FinanceDataReader • PyKRX • BOK ECOS • DART • Naver News • Paxnet")

    # 🔧 Phase 4: 대화형 AI 채팅 인터페이스
    if st.session_state.get('analysis_completed') and st.session_state.get('chat_session'):
        st.markdown("---")
        st.markdown("## 💬 AI와 대화하기")

        analysis_company = st.session_state.get('analysis_company', '종목')
        st.info(f"✨ **{analysis_company}** 분석 결과에 대해 궁금한 점을 물어보세요!")

        # 🔧 Phase 4.1: 예시 질문 버튼
        st.markdown("**💡 빠른 질문:**")
        col1, col2, col3, col4 = st.columns(4)
        example_questions = [
            "재무 상태가 괜찮아?",
            "지금 사도 될까?",
            "가장 큰 리스크는 뭐야?",
            "긍정적인 요인은?"
        ]

        # 예시 질문 클릭 시 처리를 위한 session_state
        if 'pending_question' not in st.session_state:
            st.session_state['pending_question'] = None

        with col1:
            if st.button(example_questions[0], key="q1", use_container_width=True):
                st.session_state['pending_question'] = example_questions[0]
        with col2:
            if st.button(example_questions[1], key="q2", use_container_width=True):
                st.session_state['pending_question'] = example_questions[1]
        with col3:
            if st.button(example_questions[2], key="q3", use_container_width=True):
                st.session_state['pending_question'] = example_questions[2]
        with col4:
            if st.button(example_questions[3], key="q4", use_container_width=True):
                st.session_state['pending_question'] = example_questions[3]

        chat_session = st.session_state['chat_session']

        # 대화 히스토리 초기화 (세션 상태에 저장)
        if 'chat_history' not in st.session_state:
            st.session_state['chat_history'] = []

        # 기존 대화 표시
        for message in st.session_state['chat_history']:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # 🔧 Phase 4.1: 예시 질문 버튼 클릭 시 처리
        if st.session_state['pending_question']:
            prompt = st.session_state['pending_question']
            st.session_state['pending_question'] = None  # 초기화

            # 사용자 메시지 표시 및 저장
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state['chat_history'].append({"role": "user", "content": prompt})

            # AI 응답 생성
            with st.chat_message("assistant"):
                with st.spinner("🤔 생각 중..."):
                    response = chat_session.ask(prompt)
                    st.markdown(response)

            st.session_state['chat_history'].append({"role": "assistant", "content": response})

        # 채팅 입력
        if prompt := st.chat_input("질문을 입력하세요..."):
            # 사용자 메시지 표시 및 저장
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state['chat_history'].append({"role": "user", "content": prompt})

            # AI 응답 생성
            with st.chat_message("assistant"):
                with st.spinner("🤔 생각 중..."):
                    response = chat_session.ask(prompt)
                    st.markdown(response)

            st.session_state['chat_history'].append({"role": "assistant", "content": response})

        # 대화 초기화 버튼
        col_clear, col_space = st.columns([1, 3])
        with col_clear:
            if st.button("🔄 대화 내역 지우기", key="clear_chat", use_container_width=True):
                st.session_state['chat_history'] = []
                chat_session.clear_history()
                st.success("✅ 대화 내역이 초기화되었습니다!")

if __name__ == "__main__":
    main()