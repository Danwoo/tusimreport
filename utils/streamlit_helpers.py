#!/usr/bin/env python3
"""
Streamlit 전용 헬퍼 유틸리티
UI 컴포넌트 및 상태 관리 함수들
"""

import streamlit as st
import time
from datetime import datetime
from typing import Dict, Any, Optional

def render_parallel_progress_dashboard():
    """병렬 처리 진행률 대시보드 렌더링"""

    if 'parallel_progress' not in st.session_state:
        st.info("🔄 병렬 처리가 아직 시작되지 않았습니다.")
        return

    # 제목
    st.markdown("### 🚀 병렬 에이전트 분석 진행률")

    # 전체 진행률
    total_agents = len(st.session_state.parallel_progress)
    completed_count = sum(1 for p in st.session_state.parallel_progress.values()
                         if p['status'] == 'completed')
    error_count = sum(1 for p in st.session_state.parallel_progress.values()
                     if p['status'] == 'error')
    running_count = sum(1 for p in st.session_state.parallel_progress.values()
                       if p['status'] == 'running')

    # 전체 진행률 표시
    overall_progress = completed_count / total_agents if total_agents > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("전체 진행률", f"{overall_progress*100:.0f}%", f"{completed_count}/{total_agents}")
    with col2:
        st.metric("완료", completed_count, delta_color="normal")
    with col3:
        st.metric("실행 중", running_count, delta_color="off")
    with col4:
        st.metric("오류", error_count, delta_color="inverse")

    # 전체 진행률 바
    st.progress(overall_progress, text=f"전체 진행률: {completed_count}/{total_agents} 완료")

    # 개별 에이전트 상태
    st.markdown("#### 📊 개별 에이전트 상태")

    # 2x4 그리드로 배치
    row1_cols = st.columns(4)
    row2_cols = st.columns(4)

    agent_display_info = {
        'context_expert': {'name': '🌍 시장환경', 'col': row1_cols[0]},
        'sentiment_expert': {'name': '📰 뉴스분석', 'col': row1_cols[1]},
        'financial_expert': {'name': '💰 재무분석', 'col': row1_cols[2]},
        'advanced_technical_expert': {'name': '📈 기술분석', 'col': row1_cols[3]},
        'institutional_trading_expert': {'name': '🏢 수급분석', 'col': row2_cols[0]},
        'comparative_expert': {'name': '⚖️ 상대평가', 'col': row2_cols[1]},
        'esg_expert': {'name': '🌱 ESG분석', 'col': row2_cols[2]},
        'community_expert': {'name': '💬 커뮤니티', 'col': row2_cols[3]}
    }

    for agent_name, display_info in agent_display_info.items():
        with display_info['col']:
            if agent_name in st.session_state.parallel_progress:
                progress_info = st.session_state.parallel_progress[agent_name]
                status = progress_info['status']

                # 상태별 표시
                if status == 'completed':
                    st.success(f"✅ {display_info['name']}")
                    if progress_info.get('end_time'):
                        duration = _calculate_duration(
                            progress_info.get('start_time'),
                            progress_info.get('end_time')
                        )
                        st.caption(f"완료 ({duration})")

                elif status == 'error':
                    st.error(f"❌ {display_info['name']}")
                    error_msg = progress_info.get('error', '알 수 없는 오류')
                    st.caption(f"오류: {error_msg[:50]}...")

                elif status == 'running':
                    st.warning(f"⏳ {display_info['name']}")
                    st.caption("실행 중...")

                elif status == 'starting':
                    st.info(f"🔄 {display_info['name']}")
                    st.caption("시작 중...")

                else:  # waiting
                    st.info(f"⏸️ {display_info['name']}")
                    st.caption("대기 중...")
            else:
                st.info(f"⏸️ {display_info['name']}")
                st.caption("대기 중...")

def _calculate_duration(start_time, end_time) -> str:
    """실행 시간 계산"""
    if not start_time or not end_time:
        return "시간 미측정"

    try:
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

        duration = end_time - start_time
        seconds = duration.total_seconds()

        if seconds < 60:
            return f"{seconds:.1f}초"
        else:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes:.0f}분 {remaining_seconds:.0f}초"

    except Exception:
        return "시간 미측정"

def render_parallel_execution_controls(stock_code: str, company_name: str):
    """병렬 실행 제어 UI"""

    # 실행 버튼
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        button_disabled = st.session_state.get('parallel_execution_started', False)

        start_parallel = st.button(
            "🚀 병렬 분석 시작",
            type="primary",
            disabled=button_disabled,
            help="8개 에이전트를 동시에 실행하여 빠른 분석을 수행합니다"
        )

        # 디버깅용 정보 표시
        if button_disabled:
            st.warning("⚠️ 분석이 이미 진행 중입니다. 아래 '초기화' 버튼을 눌러주세요.")

        # 강제 초기화 버튼 (디버깅용)
        if st.button("🔄 상태 초기화", help="병렬 실행 상태를 강제로 초기화합니다"):
            _reset_parallel_execution()
            st.success("상태가 초기화되었습니다.")
            st.rerun()

    with col2:
        if st.session_state.get('parallel_execution_started', False):
            if st.button("🔄 진행률 새로고침"):
                st.rerun()

    with col3:
        if st.session_state.get('parallel_execution_completed', False):
            if st.button("🔄 다시 분석"):
                _reset_parallel_execution()
                st.rerun()

    return start_parallel

def _reset_parallel_execution():
    """병렬 실행 상태 초기화"""
    keys_to_reset = [
        'parallel_results', 'parallel_progress', 'parallel_errors',
        'parallel_execution_started', 'parallel_execution_completed'
    ]

    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

def render_parallel_results_summary():
    """병렬 처리 결과 요약"""

    if 'parallel_results' not in st.session_state or not st.session_state.parallel_results:
        return

    st.markdown("### 📋 분석 결과 요약")

    results = st.session_state.parallel_results

    # 탭으로 분류
    tabs = st.tabs([
        "📊 전체 요약", "🌍 시장환경", "📰 뉴스분석", "💰 재무분석",
        "📈 기술분석", "🏢 수급분석", "⚖️ 상대평가", "🌱 ESG분석", "💬 커뮤니티"
    ])

    agent_tab_mapping = {
        'context_expert': 1,
        'sentiment_expert': 2,
        'financial_expert': 3,
        'advanced_technical_expert': 4,
        'institutional_trading_expert': 5,
        'comparative_expert': 6,
        'esg_expert': 7,
        'community_expert': 8
    }

    # 전체 요약 탭
    with tabs[0]:
        col1, col2 = st.columns(2)

        with col1:
            st.metric("완료된 분석", len(results), f"총 8개 중")

        with col2:
            total_content_length = sum(len(str(result.get('content', ''))) for result in results.values())
            st.metric("총 분석 내용", f"{total_content_length:,}자", "품질 확인")

        st.markdown("#### 📈 에이전트별 실행 결과")
        for agent_name, result in results.items():
            if isinstance(result, dict):
                content_length = len(str(result.get('content', '')))
                execution_time = result.get('execution_time', '시간 미측정')
                st.write(f"- **{agent_name}**: {content_length:,}자 (완료: {execution_time})")

    # 개별 에이전트 결과 탭
    for agent_name, result in results.items():
        if agent_name in agent_tab_mapping:
            tab_index = agent_tab_mapping[agent_name]
            with tabs[tab_index]:
                if isinstance(result, dict) and 'content' in result:
                    content = result['content']
                    st.markdown(f"**분석 길이**: {len(content):,}자")
                    st.markdown("---")
                    st.markdown(content[:2000] + "..." if len(content) > 2000 else content)
                else:
                    st.write(str(result)[:2000] + "..." if len(str(result)) > 2000 else str(result))

def show_parallel_status_indicator():
    """병렬 처리 상태 인디케이터 (사이드바용)"""

    if 'parallel_execution_started' not in st.session_state:
        return

    with st.sidebar:
        st.markdown("### 🔄 분석 상태")

        if st.session_state.get('parallel_execution_completed', False):
            st.success("✅ 분석 완료")

            if 'parallel_results' in st.session_state:
                completed_agents = len(st.session_state.parallel_results)
                st.write(f"완료된 에이전트: {completed_agents}/8")

        elif st.session_state.get('parallel_execution_started', False):
            st.warning("⏳ 분석 진행 중")

            if 'parallel_progress' in st.session_state:
                completed = sum(1 for p in st.session_state.parallel_progress.values()
                              if p['status'] == 'completed')
                total = len(st.session_state.parallel_progress)
                progress = completed / total if total > 0 else 0
                st.progress(progress, text=f"{completed}/{total}")
        else:
            st.info("⏸️ 분석 대기 중")

def auto_refresh_during_parallel_execution():
    """병렬 실행 중 자동 새로고침 (개선된 버전)"""

    if not st.session_state.get('parallel_execution_started', False):
        return

    if st.session_state.get('parallel_execution_completed', False):
        return

    # 주의: 무한 루프 방지를 위해 조건부 새로고침만 수행
    # 실제 새로고침은 main.py에서 별도 로직으로 처리
    pass