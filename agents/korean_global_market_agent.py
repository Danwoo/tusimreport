"""
Korean Global Market Context Agent
글로벌 시장 맥락 분석 (미국 증시, 암호화폐, 환율)

- Alpha Vantage: 미국 증시 (S&P 500, NASDAQ, Dow 추종 ETF), USD/KRW 환율
- CoinGecko: 암호화폐 (Bitcoin, Ethereum)

도구는 데이터만 돌려주고 해석은 에이전트 LLM이 한다. 도구 안에서 LLM을 또 부르면
에이전트에게 보이지 않는 호출이 비용을 늘리고, 그 글이 숫자 근거 검사에서 도구
데이터로 읽힌다. 받지 못한 데이터는 수치 대신 '데이터 없음'과 사유로 전달한다.
"""

import logging
import math
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
    "forex": "USD/KRW 환율 (Alpha Vantage)",
}


@tool
def analyze_global_market_context(company_name: str, stock_code: str) -> dict[str, Any]:
    """
    글로벌 시장 맥락 데이터 수집 - 한국 주식에 영향을 주는 미국 증시·암호화폐·환율 현황.
    수치만 돌려주고 해석은 하지 않는다.

    Args:
        company_name: 기업명
        stock_code: 종목코드

    Returns:
        {
            "status": "success" | "partial" | "unavailable",
            "company_name": str,
            "stock_code": str,
            "global_markets": {...},  # 미국 증시 현황
            "crypto_markets": {...},  # 암호화폐 시장
            "forex": {...},  # 환율
            "unavailable_data": [str],  # 받지 못한 데이터와 사유
            "summary": str,  # 위 수치를 옮긴 요약. 받지 못한 항목은 '데이터 없음'과 사유
            "timestamp": str
        }
    """
    try:
        logger.info(f"🌍 글로벌 시장 맥락 데이터 수집 시작: {company_name} ({stock_code})")

        global_markets = _fetch_global_markets()
        crypto_markets = _fetch_crypto_markets()
        forex = _fetch_forex_data()

        sections = {
            "global_markets": global_markets,
            "crypto_markets": crypto_markets,
            "forex": forex,
        }

        available_count = sum(1 for section in sections.values() if section.get("available"))
        result = {
            "status": _overall_status(available_count, len(sections)),
            "company_name": company_name,
            "stock_code": stock_code,
            **sections,
            "unavailable_data": _summarize_unavailable(sections),
            "summary": _build_summary(global_markets, crypto_markets, forex),
            "timestamp": kst_isoformat(),
        }

        logger.info("✅ 글로벌 시장 맥락 데이터 수집 완료")
        return result

    except Exception as e:
        logger.error(f"❌ 글로벌 시장 맥락 데이터 수집 실패: {redact(str(e))}")
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

    받지 못했으면 코인·global 자리를 {}로 비워, 클라이언트가 남긴 값이 LLM에 가지 않게 한다.

    Returns:
        {
            "bitcoin": {"current_price_usd": 65000.0, "price_change_24h": 2.5, ...},
            "ethereum": {...},
            "global": {...},
            "available": bool,
            "reason": str  # available이 False일 때만
        }
    """
    try:
        from data.coingecko_client import CoinGeckoClient

        data = CoinGeckoClient().get_market_overview()

        if data.get("available") is not True:
            return {
                "bitcoin": {},
                "ethereum": {},
                "global": {},
                "available": False,
                "reason": data.get("reason") or "CoinGecko 응답 없음",
                "timestamp": data.get("timestamp", ""),
            }
        return {
            "bitcoin": data.get("bitcoin") or {},
            "ethereum": data.get("ethereum") or {},
            "global": data.get("global") or {},
            "available": True,
            "timestamp": data.get("timestamp", ""),
        }

    except Exception as e:
        logger.error(f"암호화폐 시장 데이터 수집 실패: {redact(str(e))}")
        return {"bitcoin": {}, "ethereum": {}, "global": {}, "available": False, "reason": redact(str(e))}


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


def _build_summary(
    global_markets: dict[str, Any], crypto_markets: dict[str, Any], forex: dict[str, Any]
) -> str:
    """도구 출력의 summary. 수집한 수치를 그대로 옮길 뿐 해석하지 않는다."""
    return "\n\n".join(
        (
            f"## 미국 증시 (지수 추종 ETF)\n{_format_global_markets(global_markets)}",
            f"## 암호화폐\n{_format_crypto_markets(crypto_markets)}",
            f"## 환율\n{_format_forex(forex)}",
        )
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _format_global_markets(data: dict[str, Any]) -> str:
    """글로벌 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return f"⚠️ 글로벌 시장 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."

    lines = []
    for key, label in _INDEX_LABELS:
        entry = data.get(key) or {}
        price = entry.get("price")
        if entry.get("available") and _is_number(price):
            change = entry.get("change_percent")
            change_text = f" ({change:+.2f}%)" if _is_number(change) else ""
            lines.append(f"- {label}: ${price:.2f}{change_text}")
        else:
            lines.append(f"- {label}: {NO_DATA} ({entry.get('reason') or '사유 미상'})")
    return "\n".join(lines)


def _format_crypto_markets(data: dict[str, Any]) -> str:
    """암호화폐 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return (
            f"⚠️ 암호화폐 시장 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."
        )

    lines = []
    for key, label in (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum")):
        coin = data.get(key) or {}
        price = coin.get("current_price_usd")
        if not _is_number(price):
            lines.append(f"- {label}: {NO_DATA} (CoinGecko 응답에 가격 없음)")
            continue
        change = coin.get("price_change_24h")
        change_text = f" (24시간 {change:+.2f}%)" if _is_number(change) else ""
        lines.append(f"- {label}: ${price:,.2f}{change_text}")

    dominance = (data.get("global") or {}).get("bitcoin_dominance")
    lines.append(
        f"- BTC 도미넌스: {dominance:.1f}%" if _is_number(dominance) else f"- BTC 도미넌스: {NO_DATA}"
    )
    return "\n".join(lines)


def _format_forex(data: dict[str, Any]) -> str:
    """환율 데이터 포맷팅"""
    rate = (data.get("usd_krw") or {}).get("rate")
    if not data.get("available", False) or not _is_number(rate):
        return f"⚠️ 환율 데이터를 사용할 수 없습니다 ({NO_DATA}: {data.get('reason') or '사유 미상'})."

    return f"- USD/KRW: {rate:,.2f}원"


def _create_fallback_analysis(company_name: str, stock_code: str, error: str) -> dict[str, Any]:
    """
    Fallback 결과 생성

    Args:
        company_name: 기업명
        stock_code: 종목코드
        error: 에러 메시지

    Returns:
        모든 소스를 받지 못한 결과
    """
    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "global_markets": {"available": False},
        "crypto_markets": {"available": False},
        "forex": {"available": False},
        "unavailable_data": [f"{label}: {error}" for label in _SOURCE_LABELS.values()],
        "summary": f"⚠️ 글로벌 시장 데이터를 수집할 수 없습니다 ({NO_DATA}).\n\n이유: {error}\n\n해결 방법:\n1. Alpha Vantage API 키를 .env 파일에 추가하세요 (ALPHA_VANTAGE_API_KEY)\n2. 인터넷 연결을 확인하세요",
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
        "3. 환율 (USD/KRW)\n\n"
        "도구는 수치와 그 수치를 옮긴 `summary`만 돌려주고 해석은 하지 않습니다. 분석은 당신이 직접 하세요.\n"
        "데이터를 수집한 후, 다음과 같이 자연스럽게 분석해주세요:\n\n"
        "1. **글로벌 시장 현황**: 미국 증시와 암호화폐 시장이 어떻게 움직이고 있는지 요약\n"
        "2. **한국 시장 영향**: 이러한 글로벌 흐름과 환율 변동이 한국 주식시장과 이 기업(수출/수입 비중)에 "
        "어떤 영향을 줄 수 있는지 설명\n"
        "3. **리스크 환경**: 지금이 Risk-On(위험 선호) 환경인지 Risk-Off(안전 선호) 환경인지 판단\n"
        "4. **투자 전략 시사점**: 현재 글로벌 환경에서 투자자들이 주의해야 할 점\n\n"
        "⚠️ 주의사항:\n"
        "- 도구 결과에 있는 수치만 근거로 사용하세요\n"
        "- 도구 결과에서 available이 false이거나 값이 null인 항목, `unavailable_data`에 적힌 항목, "
        f"`summary`에 '{NO_DATA}'으로 표시된 항목은 '{NO_DATA}'이라고 밝히고, "
        "수치를 추정하거나 만들어내지 말고 사용 가능한 데이터만으로 분석하세요\n"
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

    print("\n=== 글로벌 시장 맥락 데이터 ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
