"""
Korean Global Market Context Agent
글로벌 시장 맥락 분석 (미국 증시, 암호화폐, 시장 심리)

🆕 P1-3: 실시간 데이터 통합
- Alpha Vantage: 미국 증시 (S&P 500, NASDAQ, Dow 추종 ETF)
- CoinGecko: 암호화폐 (Bitcoin, Ethereum)
- CNN Fear & Greed Index: 시장 심리 지수

받지 못한 데이터는 수치 대신 '데이터 없음'과 사유로 LLM에 전달한다.
"""

import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from core.signals import AgentSignal
from utils.redaction import redact
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)

NO_DATA = "데이터 없음"

_INDEX_LABELS = (
    ("sp500", "S&P 500 추종 ETF(SPY)"),
    ("nasdaq", "NASDAQ-100 추종 ETF(QQQ)"),
    ("dow", "다우존스 추종 ETF(DIA)"),
)

_SOURCE_LABELS = {
    "global_markets": "미국 증시 (Alpha Vantage)",
    "crypto_markets": "암호화폐 (CoinGecko)",
    "market_sentiment": "시장 심리 지수 (CNN Fear & Greed)",
    "forex": "USD/KRW 환율 (Alpha Vantage)",
}


@tool
def analyze_global_market_context(company_name: str, stock_code: str) -> dict[str, Any]:
    """
    글로벌 시장 맥락 분석 - 한국 주식에 영향을 주는 글로벌 시장 동향

    Args:
        company_name: 기업명
        stock_code: 종목코드

    Returns:
        {
            "company_name": str,
            "stock_code": str,
            "global_markets": {...},  # 미국 증시 현황
            "crypto_markets": {...},  # 암호화폐 시장
            "market_sentiment": {...},  # Fear & Greed Index
            "forex": {...},  # 환율
            "unavailable_data": [str],  # 받지 못한 데이터와 사유
            "analysis": str,  # LLM 분석 결과
            "timestamp": str
        }
    """
    try:
        logger.info(f"🌍 글로벌 시장 맥락 분석 시작: {company_name} ({stock_code})")

        # 1. 글로벌 시장 데이터 수집
        global_markets = _fetch_global_markets()

        # 2. 암호화폐 시장 데이터 수집
        crypto_markets = _fetch_crypto_markets()

        # 3. 시장 심리 지수 수집
        market_sentiment = _fetch_market_sentiment()

        # 4. 환율 데이터 수집
        forex = _fetch_forex_data()

        sections = {
            "global_markets": global_markets,
            "crypto_markets": crypto_markets,
            "market_sentiment": market_sentiment,
            "forex": forex,
        }

        # 5. LLM 기반 분석
        analysis = _analyze_with_llm(
            company_name, stock_code, global_markets, crypto_markets, market_sentiment, forex
        )

        available_count = sum(1 for section in sections.values() if section.get("available"))
        result = {
            "status": _overall_status(available_count, len(sections)),
            "company_name": company_name,
            "stock_code": stock_code,
            **sections,
            "unavailable_data": _summarize_unavailable(sections),
            "analysis": analysis,
            "timestamp": kst_isoformat(),
        }

        logger.info("✅ 글로벌 시장 맥락 분석 완료")
        return result

    except Exception as e:
        logger.error(f"❌ 글로벌 시장 맥락 분석 실패: {redact(str(e))}")
        return _create_fallback_analysis(company_name, stock_code, redact(str(e)))


def _overall_status(available_count: int, total: int) -> str:
    """도구 출력의 status. 하나도 못 받았으면 'unavailable' — 분석 근거가 없다는 표시."""
    if available_count == 0:
        return "unavailable"
    return "success" if available_count == total else "partial"


def _summarize_unavailable(sections: dict[str, dict[str, Any]]) -> list[str]:
    """받지 못한 데이터 소스를 '소스: 사유' 목록으로. 도구 출력에서 바로 보이게 한다."""
    missing = []
    for key, section in sections.items():
        if not section.get("available"):
            missing.append(f"{_SOURCE_LABELS[key]}: {section.get('reason') or NO_DATA}")
    return missing


def _fetch_global_markets() -> dict[str, Any]:
    """
    글로벌 주요 지수 추종 ETF 현황 조회 (Alpha Vantage)

    Returns:
        {
            "sp500": {"symbol": "SPY", "price": 450.12, "change_percent": 0.5, "available": True},
            "nasdaq": {"symbol": "QQQ", "price": None, "available": False, "reason": "..."},
            "dow": {...},
            "available": bool,  # 하나라도 받았으면 True
            "reason": str  # available이 False일 때만
        }
    """
    try:
        from data.alpha_vantage_client import AlphaVantageClient

        data = AlphaVantageClient().get_global_market_overview()
        result: dict[str, Any] = {
            "sp500": data.get("sp500") or {},
            "nasdaq": data.get("nasdaq") or {},
            "dow": data.get("dow") or {},
            "available": data.get("available") is True,
            "timestamp": data.get("timestamp", ""),
        }
        if not result["available"]:
            result["reason"] = data.get("reason") or "Alpha Vantage 응답 없음"
        return result

    except Exception as e:
        logger.error(f"글로벌 시장 데이터 수집 실패: {redact(str(e))}")
        return {"sp500": {}, "nasdaq": {}, "dow": {}, "available": False, "reason": redact(str(e))}


def _fetch_crypto_markets() -> dict[str, Any]:
    """
    암호화폐 시장 현황 조회 (CoinGecko)

    Returns:
        {
            "bitcoin": {"current_price_usd": 65000.0, "price_change_24h": 2.5, ...},
            "ethereum": {...},
            "global": {...},
            "available": bool
        }
    """
    try:
        from data.coingecko_client import CoinGeckoClient

        client = CoinGeckoClient()
        data = client.get_market_overview()

        # CoinGecko 클라이언트는 실패 시 'note'가 붙은 결과를 돌려준다.
        available = "note" not in data
        result: dict[str, Any] = {
            "bitcoin": data.get("bitcoin", {}),
            "ethereum": data.get("ethereum", {}),
            "global": data.get("global", {}),
            "available": available,
            "timestamp": data.get("timestamp", ""),
        }
        if not available:
            result["reason"] = data.get("note") or "CoinGecko 응답 없음"
        return result

    except Exception as e:
        logger.error(f"암호화폐 시장 데이터 수집 실패: {redact(str(e))}")
        return {"bitcoin": {}, "ethereum": {}, "global": {}, "available": False, "reason": redact(str(e))}


def _fetch_market_sentiment() -> dict[str, Any]:
    """
    시장 심리 지수 조회 (Fear & Greed Index)

    Returns:
        {
            "score": 45,  # 받지 못했으면 None
            "rating": "Fear",
            "interpretation": "...",
            "trend": "improving",
            "available": bool,
            "reason": str  # available이 False일 때만
        }
    """
    try:
        from data.fear_greed_client import FearGreedClient

        client = FearGreedClient()
        index_data = client.get_current_index()
        trend_data = client.get_trend_analysis(index_data)

        available = index_data.get("available") is True and index_data.get("score") is not None
        result: dict[str, Any] = {
            "score": index_data.get("score") if available else None,
            "rating": index_data.get("rating") if available else None,
            "interpretation": trend_data.get("interpretation_korean", ""),
            "trend": trend_data.get("trend"),
            "change_from_week": trend_data.get("change_from_week"),
            "available": available,
            "timestamp": index_data.get("timestamp", ""),
        }
        if not available:
            result["reason"] = index_data.get("reason") or "Fear & Greed Index 응답 없음"
        return result

    except Exception as e:
        logger.error(f"시장 심리 지수 수집 실패: {redact(str(e))}")
        return {
            "score": None,
            "rating": None,
            "interpretation": "",
            "trend": None,
            "change_from_week": None,
            "available": False,
            "reason": redact(str(e)),
        }


def _fetch_forex_data() -> dict[str, Any]:
    """
    환율 데이터 조회 (Alpha Vantage)

    Returns:
        {
            "usd_krw": {"rate": 1320.50, "bid": ..., "ask": ...},  # 받지 못했으면 rate None
            "available": bool,
            "reason": str  # available이 False일 때만
        }
    """
    try:
        from data.alpha_vantage_client import AlphaVantageClient

        data = AlphaVantageClient().get_exchange_rate("USD", "KRW")
        available = data.get("available") is True and bool(data.get("rate"))
        result: dict[str, Any] = {
            "usd_krw": {
                "rate": data.get("rate") if available else None,
                "bid": data.get("bid") if available else None,
                "ask": data.get("ask") if available else None,
            },
            "available": available,
            "timestamp": data.get("timestamp", ""),
        }
        if not available:
            result["reason"] = data.get("reason") or "Alpha Vantage 환율 응답 없음"
        return result

    except Exception as e:
        logger.error(f"환율 데이터 수집 실패: {redact(str(e))}")
        return {"usd_krw": {"rate": None}, "available": False, "reason": redact(str(e))}


def _analyze_with_llm(
    company_name: str,
    stock_code: str,
    global_markets: dict[str, Any],
    crypto_markets: dict[str, Any],
    market_sentiment: dict[str, Any],
    forex: dict[str, Any],
) -> str:
    """
    LLM 기반 글로벌 시장 맥락 분석

    Args:
        company_name: 기업명
        stock_code: 종목코드
        global_markets: 글로벌 시장 데이터
        crypto_markets: 암호화폐 시장 데이터
        market_sentiment: 시장 심리 데이터
        forex: 환율 데이터

    Returns:
        분석 결과 텍스트
    """
    try:
        llm = build_llm(temperature=0.3, raise_on_missing=False)
        if llm is None:
            return "⚠️ LLM API 키가 설정되지 않아 자동 분석을 수행할 수 없습니다."

        response = llm.invoke(
            _build_analysis_prompt(
                company_name, stock_code, global_markets, crypto_markets, market_sentiment, forex
            )
        )
        return response.content

    except Exception as e:
        logger.error(f"LLM 분석 실패: {redact(str(e))}")
        return f"⚠️ 자동 분석 중 오류가 발생했습니다: {redact(str(e))}"


def _build_analysis_prompt(
    company_name: str,
    stock_code: str,
    global_markets: dict[str, Any],
    crypto_markets: dict[str, Any],
    market_sentiment: dict[str, Any],
    forex: dict[str, Any],
) -> str:
    return f"""당신은 글로벌 시장 전문 애널리스트입니다.
한국 주식 '{company_name}({stock_code})'에 대한 투자 분석을 위해 글로벌 시장 맥락을 분석하세요.

## 글로벌 시장 현황
{_format_global_markets(global_markets)}

## 암호화폐 시장 현황
{_format_crypto_markets(crypto_markets)}

## 시장 심리 지수 (Fear & Greed Index)
{_format_market_sentiment(market_sentiment)}

## 환율
{_format_forex(forex)}

## 분석 요청
위 글로벌 시장 데이터를 바탕으로 '{company_name}'에 대한 투자 환경을 분석하세요.

**분석 포인트:**
1. 글로벌 시장 동향이 한국 증시에 미치는 영향
2. 리스크 온/오프 환경 판단
3. 환율 변동이 기업에 미치는 영향 (수출/수입 비중 고려)
4. 암호화폐 시장과의 상관관계 (있을 경우)
5. 종합적인 투자 환경 평가

**응답 형식:**
- 2-3 문단으로 간결하게 작성
- 투자 초보자도 이해할 수 있도록 쉽게 설명
- 위에 제시된 수치만 근거로 사용
- '{NO_DATA}'으로 표시된 항목은 수치를 추정하거나 만들어내지 말고, 데이터가 없다고 밝히세요
"""


def _fmt_number(value: Any, spec: str) -> str:
    if value is None:
        return NO_DATA
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return NO_DATA


def _format_global_markets(data: dict[str, Any]) -> str:
    """글로벌 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return f"⚠️ 글로벌 시장 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."

    lines = []
    for key, label in _INDEX_LABELS:
        entry = data.get(key) or {}
        if entry.get("available") and entry.get("price"):
            change = entry.get("change_percent")
            change_text = f" ({_fmt_number(change, '+.2f')}%)" if change is not None else ""
            lines.append(f"- {label}: ${_fmt_number(entry['price'], '.2f')}{change_text}")
        else:
            lines.append(f"- {label}: {NO_DATA} ({entry.get('reason') or '사유 미상'})")
    return "\n" + "\n".join(lines) + "\n"


def _format_crypto_markets(data: dict[str, Any]) -> str:
    """암호화폐 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return f"⚠️ 암호화폐 시장 데이터를 사용할 수 없습니다 ({NO_DATA})."

    lines = []
    for key, label in (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum")):
        coin = data.get(key) or {}
        price = coin.get("current_price_usd")
        if price:
            change = coin.get("price_change_24h")
            change_text = f" ({_fmt_number(change, '+.2f')}%)" if change is not None else ""
            lines.append(f"- {label}: ${_fmt_number(price, ',.2f')}{change_text}")
        else:
            lines.append(f"- {label}: {NO_DATA}")

    dominance = (data.get("global") or {}).get("bitcoin_dominance")
    lines.append(
        f"- BTC 도미넌스: {_fmt_number(dominance, '.1f')}%" if dominance else f"- BTC 도미넌스: {NO_DATA}"
    )
    return "\n" + "\n".join(lines) + "\n"


def _format_market_sentiment(data: dict[str, Any]) -> str:
    """시장 심리 데이터 포맷팅"""
    if not data.get("available", False) or data.get("score") is None:
        return f"⚠️ 시장 심리 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."

    rating = data.get("rating") or NO_DATA
    interpretation = data.get("interpretation") or NO_DATA
    trend = data.get("trend") or NO_DATA

    return f"""
- 현재 지수: {data["score"]}/100 ({rating})
- 해석: {interpretation}
- 추세: {trend}
"""


def _format_forex(data: dict[str, Any]) -> str:
    """환율 데이터 포맷팅"""
    rate = (data.get("usd_krw") or {}).get("rate")
    if not data.get("available", False) or not rate:
        return f"⚠️ 환율 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."

    return f"""
- USD/KRW: {_fmt_number(rate, ",.2f")}원
"""


def _create_fallback_analysis(company_name: str, stock_code: str, error: str) -> dict[str, Any]:
    """
    Fallback 분석 결과 생성

    Args:
        company_name: 기업명
        stock_code: 종목코드
        error: 에러 메시지

    Returns:
        기본 분석 결과
    """
    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "global_markets": {"available": False},
        "crypto_markets": {"available": False},
        "market_sentiment": {"available": False},
        "forex": {"available": False},
        "unavailable_data": [f"{label}: {error}" for label in _SOURCE_LABELS.values()],
        "analysis": f"⚠️ 글로벌 시장 데이터를 수집할 수 없습니다.\n\n이유: {error}\n\n해결 방법:\n1. Alpha Vantage API 키를 .env 파일에 추가하세요 (ALPHA_VANTAGE_API_KEY)\n2. 인터넷 연결을 확인하세요",
        "timestamp": kst_isoformat(),
        "error": error,
    }


# 도구 목록
global_market_tools = [analyze_global_market_context]


def create_global_market_agent():
    """
    Global Market Context Agent 생성 함수

    Returns:
        LangGraph ReAct Agent
    """
    llm = build_llm(temperature=0.3)

    prompt = (
        "당신은 글로벌 시장과 한국 주식시장의 상관관계를 분석하는 전문가입니다. "
        "투자자들이 글로벌 시장 환경을 이해하고 한국 주식 투자 결정에 활용할 수 있도록 도와주세요.\n\n"
        "먼저 `analyze_global_market_context` 도구를 사용해서 다음 데이터를 수집하세요:\n"
        "1. 미국 주요 지수 추종 ETF (SPY, QQQ, DIA)\n"
        "2. 암호화폐 시장 (Bitcoin, Ethereum)\n"
        "3. 시장 심리 지수 (Fear & Greed Index)\n"
        "4. 환율 (USD/KRW)\n\n"
        "데이터를 수집한 후, 다음과 같이 자연스럽게 분석해주세요:\n\n"
        "1. **글로벌 시장 현황**: 미국 증시와 암호화폐 시장이 어떻게 움직이고 있는지 요약\n"
        "2. **한국 시장 영향**: 이러한 글로벌 흐름이 한국 주식시장에 어떤 영향을 줄 수 있는지 설명\n"
        "3. **리스크 환경**: 지금이 Risk-On(위험 선호) 환경인지 Risk-Off(안전 선호) 환경인지 판단\n"
        "4. **투자 전략 시사점**: 현재 글로벌 환경에서 투자자들이 주의해야 할 점\n\n"
        "⚠️ 주의사항:\n"
        "- 도구 결과에서 available이 false이거나 값이 null인 항목, `unavailable_data`에 적힌 항목은 "
        "데이터가 없다고 명시하고, 수치를 추정하거나 만들어내지 말고 사용 가능한 데이터만으로 분석하세요\n"
        "- 전문 용어를 사용할 때는 간단한 설명을 함께 제공하세요\n"
        "- 투자 초보자도 이해할 수 있도록 쉽게 설명하세요\n\n"
        "참고: 이 분석은 투자 참고자료이며 투자 추천이 아닙니다.\n\n"
        f"🚨 중요: 분석을 모두 마친 후 반드시 마지막 줄에 '{AgentSignal.GLOBAL_MARKET.value}'라고 정확히 적어주세요."
    )

    return create_react_agent(
        model=llm, tools=global_market_tools, prompt=prompt, name="global_market_expert"
    )


# 테스트 코드
if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)

    result = analyze_global_market_context.invoke({"company_name": "삼성전자", "stock_code": "005930"})

    print("\n=== 글로벌 시장 맥락 분석 결과 ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
