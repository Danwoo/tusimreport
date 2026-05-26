"""에이전트 결과 카드와 투자 의견 카드의 HTML 빌더.

main.py에 박혀있던 ~210줄의 카드 빌더를 분리.
순수 문자열 생성 함수만 모이도록 해서 Streamlit 의존성 없이 테스트 가능하다.

XSS 방어:
- 외부에서 들어오는 모든 문자열(LLM 출력, 뉴스 제목/URL, 사용자 입력)은
  반드시 html.escape() 또는 _safe_url()을 거쳐 HTML에 삽입한다.
- AGENT_CONFIGS의 값처럼 우리가 정의한 상수만 raw로 박는다.
"""

from __future__ import annotations

import html
from collections.abc import Iterable
from typing import Any

_SAFE_URL_SCHEMES = ("http://", "https://")


def _safe_url(url: str) -> str:
    """javascript:/data: 등 위험한 스킴을 차단한 후 attribute-safe escape."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url.startswith(_SAFE_URL_SCHEMES):
        return ""
    return html.escape(url, quote=True)


def escape_html(value: Any) -> str:
    """LLM 출력/외부 API/사용자 입력 문자열을 HTML 컨텐츠로 안전하게 변환.

    `unsafe_allow_html=True`로 렌더링되는 모든 st.markdown 호출 자리에서
    외부 데이터를 박을 때 이 함수를 거치게 한다.
    """
    return html.escape("" if value is None else str(value))


# 내부 사용 alias (cards.py 안에서 짧게 쓰기 위함)
_esc = escape_html


AGENT_CONFIGS: dict[str, tuple[str, str, str, str, str]] = {
    "context_expert": ("🌍", "시장 환경 분석", "#3b82f6", "#dbeafe", "거시경제 및 시장 동향"),
    "sentiment_expert": ("📰", "뉴스 여론 분석", "#8b5cf6", "#ede9fe", "뉴스 감정 및 시장 심리"),
    "financial_expert": ("💰", "재무 상태 분석", "#f59e0b", "#fef3c7", "재무제표 및 기업 건전성"),
    "advanced_technical_expert": ("📈", "기술적 분석", "#ef4444", "#fee2e2", "차트 패턴 및 기술 지표"),
    "institutional_trading_expert": ("🏦", "기관 수급 분석", "#06b6d4", "#cffafe", "기관투자자 매매 동향"),
    "comparative_expert": ("⚖️", "상대 가치 분석", "#10b981", "#d1fae5", "동종업계 비교 평가"),
    "esg_expert": ("🌱", "ESG 분석", "#84cc16", "#ecfccb", "지속가능경영 평가"),
    "community_expert": ("💬", "커뮤니티 여론 분석", "#f97316", "#fed7aa", "실제 투자자 의견 및 심리"),
    "global_market_expert": ("🌐", "글로벌 시장 분석", "#6366f1", "#e0e7ff", "미국 증시 및 환율 동향"),
}


def get_agent_config(agent_name: str) -> dict[str, str]:
    """에이전트별 아이콘/이름/색상 메타데이터를 반환."""
    if agent_name in AGENT_CONFIGS:
        icon, name, color, bg, desc = AGENT_CONFIGS[agent_name]
        return {"icon": icon, "name": name, "color": color, "bg": bg, "desc": desc}
    return {"icon": "🤖", "name": agent_name, "color": "#6b7280", "bg": "#f9fafb", "desc": "AI 분석"}


_STATUS_TEXT = {"waiting": "대기 중", "running": "분석 중", "completed": "완료"}


def _render_news_sources(agent_name: str, sources: Iterable[dict] | None) -> str:
    """sentiment/community 에이전트 카드 하단의 분석 출처 섹션 HTML."""
    if not sources:
        return ""
    if agent_name == "sentiment_expert":
        title = "📰 분석된 뉴스 (상위 5개)"
        link_color = "#667eea"
    elif agent_name == "community_expert":
        title = "💬 분석된 커뮤니티 게시글 (상위 5개)"
        link_color = "#f97316"
    else:
        return ""

    parts = [
        "<div style='margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #f1f5f9;'>",
        f"<h4 style='font-size: 0.9rem; color: #64748b; margin: 0 0 0.5rem 0;'>{title}</h4>",
    ]
    for i, item in enumerate(list(sources)[:5], 1):
        title_text = (item.get("title") or "").strip()
        url = _safe_url(item.get("url", ""))
        if not title_text:
            continue
        safe_title = _esc(title_text)
        if url:
            parts.append(
                "<div style='margin: 0.3rem 0; font-size: 0.8rem;'>"
                f"<a href=\"{url}\" target='_blank' rel='noopener noreferrer' style='color: {link_color}; text-decoration: none;'>"
                f"{i}. {safe_title}</a></div>"
            )
        else:
            parts.append(
                f"<div style='margin: 0.3rem 0; font-size: 0.8rem; color: {link_color};'>"
                f"{i}. {safe_title}</div>"
            )
    parts.append("</div>")
    return "".join(parts)


def create_result_card(
    agent_name: str,
    config: dict[str, str],
    status: str = "waiting",
    content: str = "",
    news_sources: Iterable[dict] | None = None,
) -> str:
    """단일 에이전트의 결과 카드 HTML.

    content는 LLM 출력이므로 HTML로 그대로 박지 않고 escape 처리한다.
    줄바꿈은 <br>로 보존한다.
    """
    if not content and status == "waiting":
        safe_content = f"<em style='color: #9ca3af;'>{_esc(config['name'])}을 준비하고 있습니다...</em>"
    else:
        safe_content = _esc(content).replace("\n", "<br>")

    news_section = _render_news_sources(agent_name, news_sources) if status == "completed" else ""

    return f"""<div class="result-card" style="--accent-color: {config["color"]}; --bg-color: {config["bg"]};">
        <div class="result-header">
            <div class="result-icon">{config["icon"]}</div>
            <div class="result-title">
                <h3 class="result-name">{config["name"]}</h3>
                <p class="result-desc">{config["desc"]}</p>
            </div>
            <span class="result-status status-{status}">{_STATUS_TEXT[status]}</span>
        </div>
        <div class="result-content">{safe_content}{news_section}</div>
    </div>"""


def _confidence_class(confidence: int) -> str:
    if confidence >= 80:
        return "confidence-high"
    if confidence >= 60:
        return "confidence-medium"
    if confidence >= 40:
        return "confidence-low"
    return "confidence-very-low"


def _rr_label(ratio: float) -> str:
    if ratio >= 2.0:
        return "Very Good"
    if ratio >= 1.5:
        return "Good"
    if ratio >= 1.0:
        return "Fair"
    return "Risky"


def create_investment_opinion_card(opinion_data: dict[str, Any]) -> str:
    """Level 3 투자 의견 카드 HTML (목표가/손절가/R&R/분할매수 포함)."""
    opinion = opinion_data.get("opinion", "HOLD")
    # opinion은 BUY/HOLD/SELL 화이트리스트로만 매핑되므로 raw 사용 안전
    if opinion not in ("BUY", "HOLD", "SELL"):
        opinion = "HOLD"

    try:
        confidence = int(opinion_data.get("confidence", 50))
    except (TypeError, ValueError):
        confidence = 50
    confidence = max(0, min(100, confidence))

    reasoning = opinion_data.get("reasoning", "")
    key_positives = opinion_data.get("key_positives", []) or []
    key_risks = opinion_data.get("key_risks", []) or []
    timeframe = opinion_data.get("timeframe", "중기(3-6개월)")

    current_price = opinion_data.get("current_price", 0) or 0
    target_price = opinion_data.get("target_price", 0) or 0
    stop_loss = opinion_data.get("stop_loss", 0) or 0
    risk_reward_ratio = opinion_data.get("risk_reward_ratio", 0) or 0
    split_buy_strategy = opinion_data.get("split_buy_strategy", []) or []

    opinion_config = {
        "BUY": {"text": "BUY", "class": "opinion-buy"},
        "HOLD": {"text": "HOLD", "class": "opinion-hold"},
        "SELL": {"text": "SELL", "class": "opinion-sell"},
    }
    cfg = opinion_config[opinion]
    confidence_class = _confidence_class(confidence)

    positives_html = "".join(
        f'<div class="factor-item factor-positive"><span class="factor-text">{_esc(p)}</span></div>'
        for p in key_positives[:3]
    )
    risks_html = "".join(
        f'<div class="factor-item factor-risk"><span class="factor-text">{_esc(r)}</span></div>'
        for r in key_risks[:3]
    )

    upside_pct = ((target_price - current_price) / current_price * 100) if current_price else 0
    downside_pct = ((stop_loss - current_price) / current_price * 100) if current_price else 0

    split_rows = "".join(
        f"""
            <tr>
                <td style="font-weight: 600;">{_esc(item.get("order", ""))}</td>
                <td>{_esc(item.get("price_range", ""))}원</td>
                <td style="font-weight: 600; color: #2563eb;">{_esc(item.get("weight", ""))}</td>
                <td>{_esc(item.get("timing", ""))}</td>
            </tr>
        """
        for item in split_buy_strategy
    )

    safe_reasoning = _esc(reasoning).replace("\n", "<br>")
    safe_timeframe = _esc(timeframe)

    return f"""
    <div class="investment-opinion-card">
        <div class="opinion-header">
            <h2 class="opinion-title">AI Investment Opinion</h2>
            <div class="opinion-main {cfg["class"]}">
                {cfg["text"]}
            </div>
            <div class="confidence-section">
                <div class="confidence-label">
                    <span>Confidence Score</span>
                    <span style="font-weight: 700; color: #334155;">{confidence}%</span>
                </div>
                <div class="confidence-bar">
                    <div class="confidence-fill {confidence_class}" style="width: {confidence}%;">
                        {confidence}%
                    </div>
                </div>
            </div>
            <span class="timeframe-badge">Timeframe: {safe_timeframe}</span>
        </div>

        <div class="opinion-section">
            <h3 class="section-title">Investment Rationale</h3>
            <div class="reasoning-text">{safe_reasoning}</div>
        </div>

        <div class="opinion-section">
            <h3 class="section-title">Key Positives</h3>
            <div class="factor-list">
                {positives_html if positives_html else '<p style="color: #9ca3af; font-size: 0.9rem; margin: 0;">No positive factors identified.</p>'}
            </div>
        </div>

        <div class="opinion-section">
            <h3 class="section-title">Key Risks</h3>
            <div class="factor-list">
                {risks_html if risks_html else '<p style="color: #9ca3af; font-size: 0.9rem; margin: 0;">No risks identified.</p>'}
            </div>
        </div>

        <div class="opinion-section">
            <h3 class="section-title">Price Targets & Risk Management</h3>
            <div class="price-grid">
                <div class="price-item">
                    <div class="price-label">Current Price</div>
                    <div class="price-value">{current_price:,.0f}원</div>
                </div>
                <div class="price-item">
                    <div class="price-label">Target Price</div>
                    <div class="price-value target">{target_price:,.0f}원</div>
                    <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.3rem;">
                        +{upside_pct:.1f}% upside
                    </div>
                </div>
                <div class="price-item">
                    <div class="price-label">Stop Loss</div>
                    <div class="price-value stop">{stop_loss:,.0f}원</div>
                    <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.3rem;">
                        {downside_pct:.1f}% downside
                    </div>
                </div>
                <div class="price-item">
                    <div class="price-label">Risk/Reward Ratio</div>
                    <div class="price-value ratio">{risk_reward_ratio:.1f}</div>
                    <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.3rem;">
                        {_rr_label(risk_reward_ratio)}
                    </div>
                </div>
            </div>
        </div>

        <div class="opinion-section">
            <h3 class="section-title">Split Buy Strategy</h3>
            <table class="split-buy-table">
                <thead>
                    <tr>
                        <th>Order</th>
                        <th>Price Range</th>
                        <th>Weight</th>
                        <th>Timing</th>
                    </tr>
                </thead>
                <tbody>{split_rows}</tbody>
            </table>
        </div>

        <div style="margin-top: 1.5rem; padding: 1rem; background: #fef3c7; border-radius: 8px; border-left: 4px solid #f59e0b;">
            <p style="margin: 0; color: #92400e; font-size: 0.85rem; line-height: 1.5;">
                <strong>Disclaimer:</strong> This opinion is generated by AI based on 8 expert agent analyses and is for reference only,
                not investment advice. Final investment decisions should be made at your own discretion and responsibility.
            </p>
        </div>
    </div>
    """
