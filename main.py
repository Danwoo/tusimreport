import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import streamlit as st

from agents.korean_investment_opinion_agent import generate_investment_opinion, opinion_sections
from config.settings import check_minimum_requirements, get_api_key_status, resolve_llm_config, settings
from core.chat_session import create_chat_session
from core.korean_supervisor_langgraph import stream_korean_stock_analysis
from core.signals import AGENT_TO_SIGNAL, MIN_AGENTS_FOR_REPORT
from data.chart_generator import create_stock_chart
from data.naver_api_client import fetch_naver_news_for_display
from ui.cards import create_investment_opinion_card, create_result_card, escape_html, get_agent_config
from ui.stock_database import STOCK_DATABASE
from ui.styles import PAGE_CSS
from utils.agent_helpers import validate_stock_code
from utils.helpers import setup_logging
from utils.logging_context import bind_session, configure_logging

# 로깅: 표준 핸들러는 utils.logging_context가 부착(세션/종목 contextvars 주입).
# 기존 setup_logging도 파일 로깅용으로 유지 (구조화 포맷은 stream만 일단 우선).
configure_logging(level=settings.log_level)
logger = setup_logging(settings.log_level, enable_file_logging=True)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="📊 AI Stock Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 페이지 스타일 (ui/styles.py)
st.markdown(PAGE_CSS, unsafe_allow_html=True)


AGENT_NAMES = list(AGENT_TO_SIGNAL.keys())

# 투자 의견·채팅은 엔진의 보고서 기준과 같은 수의 근거 있는 분석이 있을 때만 연다.
MIN_AGENTS_FOR_OPINION = MIN_AGENTS_FOR_REPORT

# 한 번의 분석이 남기는 session_state 키. 새 분석을 시작하면 모두 비운다.
_ANALYSIS_STATE_KEYS = (
    "chat_session",
    "chat_history",
    "analysis_completed",
    "final_report",
    "investment_opinion",
    "analysis_agents",
    "analysis_excluded",
    "analysis_agent_statuses",
)

_STATE_REASONS = {"no_data": "근거 데이터 없음", "failed": "실행 실패"}


@dataclass
class StreamOutcome:
    """분석 스트림을 끝까지 읽은 결과."""

    completed: int = 0
    final_report: str = ""
    report_error: str | None = None
    incomplete: bool = False
    excluded: dict[str, str] = field(default_factory=dict)
    agent_statuses: dict[str, Any] = field(default_factory=dict)


def _reset_analysis_state() -> None:
    """새 분석 시작 전 이전 분석의 보고서·투자 의견·채팅 상태를 비운다."""
    for key in _ANALYSIS_STATE_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def _prefetch_news_and_chart(symbol: str, company_name: str) -> None:
    """뉴스/차트를 분석 시작 전에 미리 가져와 session_state에 캐싱."""
    with st.spinner("📰 뉴스 데이터 수집 중..."):
        st.session_state[f"news_sources_{symbol}"] = fetch_naver_news_for_display(company_name)
    with st.spinner("📈 차트 생성 중..."):
        chart_base64 = create_stock_chart(symbol, company_name, period=120, chart_type="candle")
        if chart_base64:
            st.session_state[f"chart_{symbol}"] = chart_base64


def _render_analysis_header(symbol: str, company_name: str) -> None:
    """결과 섹션 헤더와 미리 생성된 차트를 렌더링."""
    st.markdown(
        f'<div class="results-section"><h2 style="color: #334155; margin: 0 0 1rem 0; font-size: 1.5rem;">📊 {escape_html(symbol)} {escape_html(company_name)} 분석 결과</h2></div>',
        unsafe_allow_html=True,
    )
    chart = st.session_state.get(f"chart_{symbol}")
    if chart:
        st.markdown("### 📈 기술적 차트 분석")
        st.markdown(
            f'<img src="data:image/png;base64,{chart}" style="width: 100%; max-width: 800px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">',
            unsafe_allow_html=True,
        )
        st.markdown("---")


def _initialize_agent_cards() -> dict:
    """에이전트마다 대기 상태의 빈 카드를 만들고 컨테이너 핸들을 반환."""
    containers = {}
    for name in AGENT_NAMES:
        cfg = get_agent_config(name)
        containers[name] = st.empty()
        containers[name].markdown(create_result_card(name, cfg, "waiting"), unsafe_allow_html=True)
    return containers


def _make_progress_renderer(progress_container, total: int):
    """progress bar를 갱신하는 콜백 클로저."""

    def render(completed: int, current_agent: str = "") -> None:
        pct = (completed / total) * 100
        status_text = f"{completed}/{total} 분석 완료"
        if current_agent:
            status_text += f" • 현재: {get_agent_config(current_agent)['name']}"
        progress_container.markdown(
            f'<div class="progress-section"><div class="progress-header">'
            f'<h3 class="progress-title">분석 진행 상황</h3>'
            f'<span class="progress-percentage">{pct:.0f}%</span></div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width: {pct}%;"></div></div>'
            f'<p class="progress-status">{status_text}</p></div>',
            unsafe_allow_html=True,
        )

    return render


def _extract_message_content(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("content", "")
    return msg.content if hasattr(msg, "content") else str(msg)


def _handle_running_signal(
    running_agent: str, agent_states: dict, containers: dict, render_progress, completed: int
) -> None:
    """supervisor가 표시한 `running_agent` 키를 보고 해당 카드를 running으로 갱신.

    이전 버전은 한글 stage_name(예: '시장/경제 분석')에서 영문 에이전트 키
    ('context_expert')를 substring 매칭으로 찾으려 했는데, 두 문자열에는
    공통 부분이 없어 결과적으로 카드를 한 번도 running으로 못 바꾸는
    dead code였다. 이제 supervisor가 명시적 'running_agent' 키를 보내고,
    UI는 그 키만 본다.
    """
    if not running_agent or running_agent not in agent_states:
        return
    if agent_states[running_agent]["status"] != "waiting":
        return
    agent_states[running_agent]["status"] = "running"
    containers[running_agent].markdown(
        create_result_card(running_agent, get_agent_config(running_agent), "running"),
        unsafe_allow_html=True,
    )
    render_progress(completed, running_agent)


def _extract_final_report(messages, progressive_mode: bool) -> str:
    """progressive 모드에서 100자 이상 메시지를 최종 보고서로 채택."""
    if not progressive_mode:
        return ""
    for msg in messages:
        content = _extract_message_content(msg)
        if len(content) > 100:
            return content.strip()
    return ""


def _process_completion_signals(
    messages,
    symbol: str,
    agent_states: dict,
    containers: dict,
    render_progress,
    completed: int,
) -> int:
    """완료 신호가 포함된 메시지를 처리하고 새 completed count를 반환."""
    completion_signals = {name: sig.value for name, sig in AGENT_TO_SIGNAL.items()}

    for msg in messages:
        content = _extract_message_content(msg)
        for agent_name, signal in completion_signals.items():
            if (
                signal in content
                and agent_name in agent_states
                and agent_states[agent_name]["status"] != "completed"
            ):
                analysis_text = content.replace(signal, "").strip()
                if len(analysis_text) <= 100:
                    continue
                agent_states[agent_name]["status"] = "completed"
                agent_states[agent_name]["content"] = analysis_text
                completed += 1

                # 카드 업데이트 — sentiment/community엔 출처 노출
                card_sources = None
                if agent_name == "sentiment_expert":
                    card_sources = st.session_state.get(f"news_sources_{symbol}", [])
                elif agent_name == "community_expert":
                    card_sources = st.session_state.get(f"community_sources_{symbol}", [])

                cfg = get_agent_config(agent_name)
                containers[agent_name].markdown(
                    create_result_card(agent_name, cfg, "completed", analysis_text, card_sources),
                    unsafe_allow_html=True,
                )
                render_progress(completed)
                logger.info(f"===== {cfg['name']} ({agent_name}) 분석 완료 =====")
    return completed


def _consume_analysis_stream(
    symbol: str,
    company_name: str,
    agent_states: dict,
    containers: dict,
    render_progress,
) -> StreamOutcome:
    """supervisor 스트림을 소비하며 카드/진행률을 실시간 갱신.

    이 함수 안에서 발생하는 모든 로그는 `[s=<session> c=<symbol>]` 접두사를
    얻는다 (bind_session으로 contextvar에 주입). 동시 사용자 두 명이 같은
    프로세스 안에서 분석을 돌려도 로그가 서로 섞이지 않는다.

    Returns: 완료 수, 최종 보고서 또는 보고서를 못 만든 사유, 제외 영역
    """
    with bind_session(stock_code=symbol):
        return _consume_inner(symbol, company_name, agent_states, containers, render_progress)


def _mark_agent(
    agent_name: str,
    status: str,
    content: str,
    symbol: str,
    agent_states: dict,
    containers: dict,
) -> None:
    """엔진이 이름을 명시한 에이전트의 카드를 갱신한다."""
    agent_states[agent_name]["status"] = status
    agent_states[agent_name]["content"] = content
    card_sources = None
    if status == "completed" and agent_name == "sentiment_expert":
        card_sources = st.session_state.get(f"news_sources_{symbol}", [])
    elif status == "completed" and agent_name == "community_expert":
        card_sources = st.session_state.get(f"community_sources_{symbol}", [])
    containers[agent_name].markdown(
        create_result_card(agent_name, get_agent_config(agent_name), status, content, card_sources),
        unsafe_allow_html=True,
    )


def _show_exclusions(excluded: dict) -> None:
    if not excluded:
        return
    lines = "\n".join(f"- {get_agent_config(name)['name']}: {reason}" for name, reason in excluded.items())
    st.warning(f"다음 영역은 종합 보고서에 반영되지 않았습니다.\n\n{lines}")


def _error_reason(error: Any) -> str:
    """스트림 오류 chunk의 사유. supervisor는 {"error": {"error": 사유, ...}} 모양으로 보낸다."""
    if isinstance(error, dict):
        error = error.get("error")
    return str(error) if error else "알 수 없는 오류"


def _grounded_results(agent_states: dict) -> dict[str, str]:
    """근거 데이터가 있는 분석 텍스트. 투자 의견·채팅의 입력이고, 그 수로 둘을 열지 정한다."""
    return opinion_sections(
        {name: state["content"] for name, state in agent_states.items() if state["status"] == "completed"}
    )


def _exclusions(excluded: dict[str, str], agent_states: dict, grounded: dict[str, str]) -> dict[str, str]:
    """보고서·대화에서 빠진 영역과 사유. 엔진이 준 사유를 쓰고, 없으면 카드 상태로 적는다."""
    return {
        name: excluded.get(name)
        or _STATE_REASONS.get(agent_states.get(name, {}).get("status", ""), "결과 없음")
        for name in AGENT_NAMES
        if name not in grounded or name in excluded
    }


def _consume_inner(
    symbol: str,
    company_name: str,
    agent_states: dict,
    containers: dict,
    render_progress,
) -> StreamOutcome:
    outcome = StreamOutcome()
    for chunk in stream_korean_stock_analysis(symbol, company_name):
        if "error" in chunk:
            # report_error와 system_error가 모두 이 모양으로 온다. 보고서 텍스트는 오지 않았다.
            outcome.report_error = _error_reason(chunk["error"])
            st.error(f"종합 보고서를 만들지 못했습니다: {outcome.report_error}")
            break

        supervisor_data = chunk.get("supervisor", {})
        if not supervisor_data:
            continue

        messages = supervisor_data.get("messages", [])
        _handle_running_signal(
            supervisor_data.get("running_agent", ""),
            agent_states,
            containers,
            render_progress,
            outcome.completed,
        )

        agent_error = supervisor_data.get("agent_error")
        if agent_error and agent_error.get("agent") in agent_states:
            _mark_agent(
                agent_error["agent"],
                "failed",
                f"분석 실패: {agent_error.get('error', '')}",
                symbol,
                agent_states,
                containers,
            )
            render_progress(outcome.completed)
            continue

        if supervisor_data.get("incomplete"):
            outcome.incomplete = True
            outcome.excluded = supervisor_data.get("excluded", {})
            outcome.agent_statuses = supervisor_data.get("agent_statuses", {})
            st.warning(f"종합 보고서를 만들지 않았습니다: {supervisor_data.get('current_stage', '')}")
            _show_exclusions(outcome.excluded)
            continue

        if supervisor_data.get("final_report_generated"):
            outcome.final_report = _extract_final_report(
                messages, supervisor_data.get("progressive_mode", False)
            )
            outcome.excluded = supervisor_data.get("excluded", {})
            outcome.agent_statuses = supervisor_data.get("agent_statuses", {})
            _show_exclusions(outcome.excluded)
            continue

        completed_agent = supervisor_data.get("completed_agent")
        if completed_agent in agent_states and agent_states[completed_agent]["status"] != "completed":
            content = _extract_message_content(messages[0]) if messages else ""
            signal = AGENT_TO_SIGNAL[completed_agent].value
            grounded = supervisor_data.get("agent_status", {}).get("data_status", "none") != "none"
            _mark_agent(
                completed_agent,
                "completed" if grounded else "no_data",
                content.replace(signal, "").strip(),
                symbol,
                agent_states,
                containers,
            )
            if grounded:
                outcome.completed += 1
            render_progress(outcome.completed)
            logger.info(f"===== {completed_agent} 분석 완료 (근거 데이터: {grounded}) =====")
            continue

        outcome.completed = _process_completion_signals(
            messages, symbol, agent_states, containers, render_progress, outcome.completed
        )
    return outcome


def _render_investment_opinion(symbol: str, company_name: str, sections: dict[str, str]) -> None:
    """근거 있는 분석만 모아 종합 투자 의견 카드를 그린다."""
    logger.info("===== AI 투자 의견 생성 시작 =====")
    with st.spinner("🤖 AI가 투자 의견을 생성하고 있습니다..."):
        try:
            opinion_data = generate_investment_opinion.invoke(
                {
                    "company_name": company_name,
                    "stock_code": symbol,
                    "agent_results": sections,
                }
            )
            if opinion_data and not opinion_data.get("error"):
                st.markdown(create_investment_opinion_card(opinion_data), unsafe_allow_html=True)
                logger.info(
                    f"투자 의견 생성 완료: {opinion_data.get('opinion')} "
                    f"(신뢰도: {opinion_data.get('confidence')}%)"
                )
                st.session_state["investment_opinion"] = opinion_data
            else:
                logger.warning("투자 의견 생성 실패 또는 에러 발생")
                st.warning("⚠️ AI 투자 의견 생성 중 오류가 발생했습니다. 전문 분석 결과를 참고해주세요.")
        except Exception as e:
            logger.error(f"투자 의견 생성 중 오류: {str(e)}", exc_info=True)
            st.error(f"💡 투자 의견 생성 오류: {str(e)}")


def _finalize_analysis(
    symbol: str,
    company_name: str,
    agent_states: dict,
    outcome: StreamOutcome,
    grounded: dict[str, str],
) -> None:
    """보고서·제외 영역·카드 상태를 session_state에 저장하고, 근거 있는 분석만으로
    채팅 세션을 만든 뒤 rerun한다. rerun 뒤 결과 탭은 session_state만 보고 그린다."""
    excluded = _exclusions(outcome.excluded, agent_states, grounded)
    st.session_state["final_report"] = outcome.final_report
    st.session_state["analysis_completed"] = True
    st.session_state["analysis_symbol"] = symbol
    st.session_state["analysis_company"] = company_name
    st.session_state["analysis_agents"] = agent_states
    st.session_state["analysis_excluded"] = excluded
    st.session_state["analysis_agent_statuses"] = outcome.agent_statuses
    st.session_state["analysis_timestamp"] = datetime.now().isoformat()

    chat_session = create_chat_session(
        symbol, company_name, {name: agent_states[name] for name in grounded}, excluded=excluded
    )
    if chat_session:
        st.session_state["chat_session"] = chat_session
        logger.info("Chat session created successfully")

    st.success("✅ 분석이 완료되었습니다! 탭에서 결과를 확인하세요.")
    time.sleep(1)
    st.rerun()


def _conclude(symbol: str, company_name: str, agent_states: dict, outcome: StreamOutcome) -> None:
    """보고서가 나왔고 근거 있는 분석이 기준 이상일 때만 투자 의견·채팅을 연다."""
    grounded = _grounded_results(agent_states)
    if outcome.report_error is not None:
        logger.warning(f"종합 보고서 실패 — 투자 의견·대화를 만들지 않음: {outcome.report_error}")
        return
    if not outcome.final_report:
        if not outcome.incomplete:
            st.warning("⚠️ 종합 보고서를 받지 못했습니다. 위 카드의 개별 분석만 참고해주세요.")
        return
    if len(grounded) < MIN_AGENTS_FOR_OPINION:
        st.warning(
            f"⚠️ 근거 있는 분석이 {len(grounded)}개로 기준({MIN_AGENTS_FOR_OPINION}개)에 못 미쳐 "
            "투자 의견과 AI 대화를 열지 않습니다."
        )
        return
    _render_investment_opinion(symbol, company_name, grounded)
    _finalize_analysis(symbol, company_name, agent_states, outcome, grounded)


def run_analysis(symbol: str, company_name: str) -> None:
    """분석 실행 — 단계별 helper에 위임하는 얇은 컨트롤러."""
    _reset_analysis_state()
    _prefetch_news_and_chart(symbol, company_name)
    _render_analysis_header(symbol, company_name)

    progress_container = st.empty()
    containers = _initialize_agent_cards()
    agent_states = {name: {"status": "waiting", "content": ""} for name in AGENT_NAMES}
    render_progress = _make_progress_renderer(progress_container, total=len(AGENT_NAMES))

    try:
        logger.info("================== 주식 분석 시작 ==================")
        logger.info(f"종목코드: {symbol} | 회사명: {company_name}")
        logger.info(f"분석 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        outcome = _consume_analysis_stream(symbol, company_name, agent_states, containers, render_progress)
        render_progress(outcome.completed)

        logger.info(f"완료된 전문가 수: {outcome.completed}/{len(AGENT_NAMES)}")
        logger.info(f"최종 보고서 생성: {'예' if outcome.final_report else '아니오'}")
        logger.info("================== 주식 분석 완료 ==================")

        _conclude(symbol, company_name, agent_states, outcome)

    except Exception as e:
        logger.error(f"분석 실행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        st.error(f"분석 프로세스 오류: {e}")


def main():
    # 메인 헤더
    st.markdown(
        f"""
    <div class="main-header">
        <h1 class="main-title">📊 AI Stock Analyzer</h1>
        <p class="main-subtitle">AI 전문가 {len(AGENT_NAMES)}인의 종합 주식 분석</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # API 키 상태 사이드바
    with st.sidebar:
        st.subheader("🔑 API 키 상태")
        api_status = get_api_key_status()
        for _key, msg in api_status.items():
            st.write(msg)

        st.divider()
        st.caption("💡 API 키 설정: docs/API_KEYS.md")

    # API 키 최소 요구사항 확인
    has_llm, warnings = check_minimum_requirements()

    if not has_llm:
        _, llm_problem = resolve_llm_config()
        st.error(
            "**LLM 설정이 필요합니다**\n\n"
            + (llm_problem or "").replace("\n", "  \n")
            + "\n\n설정 안내: docs/API_KEYS.md"
        )

    # 입력 섹션
    st.markdown(
        """
    <div class="input-section">
        <h3 class="input-header">📈 분석할 종목 선택</h3>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # 메인 입력 구역
    col1, col2 = st.columns([3, 1])

    with col1:
        # 종목 선택 - 드롭다운 + 직접 입력
        input_method = st.radio(
            "입력 방식 선택:",
            ["드롭다운에서 선택", "직접 입력"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if input_method == "드롭다운에서 선택":
            category = st.selectbox("카테고리 선택", list(STOCK_DATABASE.keys()))
            stock_options = STOCK_DATABASE[category]
            selected_stock = st.selectbox(
                "종목 선택", list(stock_options.keys()), format_func=lambda x: f"{stock_options[x]} ({x})"
            )
            symbol = selected_stock
            company_name = stock_options[selected_stock]
        else:
            symbol = st.text_input("종목코드", value="005930", placeholder="예: 005930, 000660, 035420")
            company_name = st.text_input(
                "회사명 (선택)", value="삼성전자", placeholder="예: 삼성전자, SK하이닉스"
            )

        # 분석 시작 버튼
        if st.button("🚀 AI 분석 시작", type="primary", use_container_width=True):
            if not symbol:
                st.error("❌ 종목코드를 입력해주세요!")
            else:
                # 종목 코드 검증
                is_valid, validation_msg = validate_stock_code(symbol.strip())
                if not is_valid:
                    st.error(validation_msg)
                else:
                    run_analysis(symbol.strip(), company_name.strip() if company_name else None)

    with col2:
        # 인기 종목 (오른쪽 사이드)
        st.markdown(
            '<div class="popular-stocks"><p class="popular-title">🔥 인기 종목</p></div>',
            unsafe_allow_html=True,
        )
        popular_stocks = [
            ("005930", "삼성전자"),
            ("000660", "SK하이닉스"),
            ("035420", "NAVER"),
            ("005380", "현대차"),
        ]
        for code, name in popular_stocks:
            if st.button(f"{name}\n{code}", key=f"popular_{code}", use_container_width=True):
                run_analysis(code, name)

    # 시스템 정보
    with st.expander("ℹ️ 시스템 정보"):
        experts = " ".join(f"{cfg['icon']} {cfg['name']}" for cfg in map(get_agent_config, AGENT_NAMES))
        st.markdown(
            f"**🤖 AI 전문가 구성 ({len(AGENT_NAMES)}인):**\n{experts}\n\n**📊 데이터:** FinanceDataReader • PyKRX • 한국은행 ECOS • OpenDART • Tavily • Alpha Vantage • CoinGecko • Paxnet(선택)"
        )

    # 탭: 분석 결과 / AI 대화
    if st.session_state.get("analysis_completed") and st.session_state.get("chat_session"):
        st.markdown("---")

        # 종목 정보
        symbol = st.session_state.get("analysis_symbol", "")
        company_name = st.session_state.get("analysis_company", "종목")

        # Tab 헤더
        st.markdown(
            f"<h2 style='color: #334155; text-align: center; margin: 1rem 0;'>📊 {escape_html(symbol)} {escape_html(company_name)} - 분석 결과</h2>",
            unsafe_allow_html=True,
        )

        # Tab 생성
        tab1, tab2 = st.tabs(["📊 분석 결과", "💬 AI 대화"])

        # Tab 1: 분석 결과
        with tab1:
            agent_states = st.session_state.get("analysis_agents", {})

            # 차트 표시
            if f"chart_{symbol}" in st.session_state:
                st.markdown("### 📈 기술적 차트 분석")
                chart_html = f'<img src="data:image/png;base64,{st.session_state[f"chart_{symbol}"]}" style="width: 100%; max-width: 800px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
                st.markdown(chart_html, unsafe_allow_html=True)
                st.markdown("---")

            # 근거 있는 에이전트 결과 카드 — 빠진 영역은 아래 제외 목록에 사유와 함께 남는다
            for agent_name in AGENT_NAMES:
                if agent_name in agent_states and agent_states[agent_name]["status"] == "completed":
                    config = get_agent_config(agent_name)
                    content = agent_states[agent_name]["content"]

                    # 뉴스/커뮤니티 소스
                    card_news_sources = None
                    if agent_name == "sentiment_expert":
                        card_news_sources = st.session_state.get(f"news_sources_{symbol}", [])
                    elif agent_name == "community_expert":
                        card_news_sources = st.session_state.get(f"community_sources_{symbol}", [])

                    st.markdown(
                        create_result_card(agent_name, config, "completed", content, card_news_sources),
                        unsafe_allow_html=True,
                    )

            _show_exclusions(st.session_state.get("analysis_excluded", {}))

            # 투자 의견 카드
            if "investment_opinion" in st.session_state:
                opinion_data = st.session_state["investment_opinion"]
                st.markdown(create_investment_opinion_card(opinion_data), unsafe_allow_html=True)

            # 최종 보고서
            if "final_report" in st.session_state:
                final_report = st.session_state["final_report"]
                # LLM 출력이므로 escape + 줄바꿈만 <br>로 보존
                safe_report = escape_html(final_report).replace("\n", "<br>")
                st.markdown(
                    f"""
                <div class="final-report">
                    <h2 class="report-title">🎯 종합 투자 분석 보고서</h2>
                    <div class="report-content">{safe_report}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # 다운로드
                st.download_button(
                    label="📋 보고서 다운로드",
                    data=final_report,
                    file_name=f"{symbol}_{company_name}_analysis_report.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

        # Tab 2: AI 대화
        with tab2:
            st.markdown("### 💬 AI와 대화하기")
            st.info(f"✨ **{company_name}** 분석 결과에 대해 궁금한 점을 물어보세요!")

            # 예시 질문 버튼
            st.markdown("**💡 빠른 질문:**")
            col1, col2, col3, col4 = st.columns(4)
            example_questions = [
                "재무 상태가 괜찮아?",
                "지금 사도 될까?",
                "가장 큰 리스크는 뭐야?",
                "긍정적인 요인은?",
            ]

            # 예시 질문 클릭 시 처리를 위한 session_state
            if "pending_question" not in st.session_state:
                st.session_state["pending_question"] = None

            with col1:
                if st.button(example_questions[0], key="q1", use_container_width=True):
                    st.session_state["pending_question"] = example_questions[0]
                    st.rerun()
            with col2:
                if st.button(example_questions[1], key="q2", use_container_width=True):
                    st.session_state["pending_question"] = example_questions[1]
                    st.rerun()
            with col3:
                if st.button(example_questions[2], key="q3", use_container_width=True):
                    st.session_state["pending_question"] = example_questions[2]
                    st.rerun()
            with col4:
                if st.button(example_questions[3], key="q4", use_container_width=True):
                    st.session_state["pending_question"] = example_questions[3]
                    st.rerun()

            chat_session = st.session_state["chat_session"]

            # 대화 히스토리 초기화 (세션 상태에 저장)
            if "chat_history" not in st.session_state:
                st.session_state["chat_history"] = []

            # 기존 대화 표시
            for message in st.session_state["chat_history"]:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # 예시 질문 버튼 클릭 시 처리
            if st.session_state["pending_question"]:
                prompt = st.session_state["pending_question"]
                st.session_state["pending_question"] = None  # 초기화

                # 사용자 메시지 표시 및 저장
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state["chat_history"].append({"role": "user", "content": prompt})

                # AI 응답 생성
                with st.chat_message("assistant"), st.spinner("🤔 생각 중..."):
                    response = chat_session.ask(prompt)
                    st.markdown(response)

                st.session_state["chat_history"].append({"role": "assistant", "content": response})

            # 채팅 입력
            if prompt := st.chat_input("질문을 입력하세요...", key="chat_input_tab2"):
                # 사용자 메시지 표시 및 저장
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state["chat_history"].append({"role": "user", "content": prompt})

                # AI 응답 생성
                with st.chat_message("assistant"), st.spinner("🤔 생각 중..."):
                    response = chat_session.ask(prompt)
                    st.markdown(response)

                st.session_state["chat_history"].append({"role": "assistant", "content": response})
                st.rerun()

            # 대화 초기화 버튼
            col_clear, col_space = st.columns([1, 3])
            with col_clear:
                if st.button("🔄 대화 내역 지우기", key="clear_chat", use_container_width=True):
                    st.session_state["chat_history"] = []
                    chat_session.clear_history()
                    st.rerun()


if __name__ == "__main__":
    main()
