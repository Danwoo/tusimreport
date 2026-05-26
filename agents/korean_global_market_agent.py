"""
Korean Global Market Context Agent
글로벌 시장 맥락 분석 (미국 증시, 암호화폐, 시장 심리)

🆕 P1-3: 실시간 데이터 통합
- Alpha Vantage: 미국 증시 (S&P 500, NASDAQ, Dow)
- CoinGecko: 암호화폐 (Bitcoin, Ethereum)
- CNN Fear & Greed Index: 시장 심리 지수
"""

import logging
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config.llm_factory import build_llm
from core.signals import AgentSignal
from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


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

        # 5. LLM 기반 분석
        analysis = _analyze_with_llm(
            company_name, stock_code, global_markets, crypto_markets, market_sentiment, forex
        )

        result = {
            "company_name": company_name,
            "stock_code": stock_code,
            "global_markets": global_markets,
            "crypto_markets": crypto_markets,
            "market_sentiment": market_sentiment,
            "forex": forex,
            "analysis": analysis,
            "timestamp": kst_isoformat(),
        }

        logger.info("✅ 글로벌 시장 맥락 분석 완료")
        return result

    except Exception as e:
        logger.error(f"❌ 글로벌 시장 맥락 분석 실패: {str(e)}")
        return _create_fallback_analysis(company_name, stock_code, str(e))


def _fetch_global_markets() -> dict[str, Any]:
    """
    글로벌 주요 지수 현황 조회 (Alpha Vantage)

    Returns:
        {
            "sp500": {"price": 450.12, "change_percent": 0.5},
            "nasdaq": {"price": 380.45, "change_percent": 0.8},
            "dow": {"price": 350.23, "change_percent": 0.3},
            "available": bool
        }
    """
    try:
        from data.alpha_vantage_client import AlphaVantageClient

        client = AlphaVantageClient()
        data = client.get_global_market_overview()

        # 데이터 사용 가능 여부 확인
        available = "note" not in data

        return {
            "sp500": data.get("sp500", {}),
            "nasdaq": data.get("nasdaq", {}),
            "dow": data.get("dow", {}),
            "available": available,
            "timestamp": data.get("timestamp", ""),
        }

    except Exception as e:
        logger.error(f"글로벌 시장 데이터 수집 실패: {str(e)}")
        return {"sp500": {}, "nasdaq": {}, "dow": {}, "available": False, "error": str(e)}


def _fetch_crypto_markets() -> dict[str, Any]:
    """
    암호화폐 시장 현황 조회 (CoinGecko)

    Returns:
        {
            "bitcoin": {
                "price_usd": 65000.0,
                "price_krw": 85800000.0,
                "change_24h": 2.5
            },
            "market_overview": {...},
            "available": bool
        }
    """
    try:
        from data.coingecko_client import CoinGeckoClient

        client = CoinGeckoClient()
        data = client.get_market_overview()

        # 데이터 사용 가능 여부 확인
        available = "note" not in data

        return {
            "bitcoin": data.get("bitcoin", {}),
            "ethereum": data.get("ethereum", {}),
            "global": data.get("global", {}),
            "available": available,
            "timestamp": data.get("timestamp", ""),
        }

    except Exception as e:
        logger.error(f"암호화폐 시장 데이터 수집 실패: {str(e)}")
        return {"bitcoin": {}, "ethereum": {}, "global": {}, "available": False, "error": str(e)}


def _fetch_market_sentiment() -> dict[str, Any]:
    """
    시장 심리 지수 조회 (Fear & Greed Index)

    Returns:
        {
            "score": 45,
            "rating": "Fear",
            "interpretation": "...",
            "trend": "improving",
            "available": bool
        }
    """
    try:
        from data.fear_greed_client import FearGreedClient

        client = FearGreedClient()
        index_data = client.get_current_index()
        trend_data = client.get_trend_analysis()

        # 데이터 사용 가능 여부 확인
        available = "note" not in index_data

        return {
            "score": index_data.get("score", 50),
            "rating": index_data.get("rating", "Neutral"),
            "interpretation": trend_data.get("interpretation_korean", ""),
            "trend": trend_data.get("trend", "stable"),
            "change_from_week": trend_data.get("change_from_week", 0),
            "available": available,
            "timestamp": index_data.get("timestamp", ""),
        }

    except Exception as e:
        logger.error(f"시장 심리 지수 수집 실패: {str(e)}")
        return {
            "score": 50,
            "rating": "Neutral",
            "interpretation": "",
            "trend": "stable",
            "available": False,
            "error": str(e),
        }


def _fetch_forex_data() -> dict[str, Any]:
    """
    환율 데이터 조회 (Alpha Vantage)

    Returns:
        {
            "usd_krw": {
                "rate": 1320.50,
                "change": "..."
            },
            "available": bool
        }
    """
    try:
        from data.alpha_vantage_client import AlphaVantageClient

        client = AlphaVantageClient()
        data = client.get_exchange_rate("USD", "KRW")

        # 데이터 사용 가능 여부 확인
        available = "note" not in data

        return {
            "usd_krw": {
                "rate": data.get("rate", 0.0),
                "bid": data.get("bid", 0.0),
                "ask": data.get("ask", 0.0),
            },
            "available": available,
            "timestamp": data.get("timestamp", ""),
        }

    except Exception as e:
        logger.error(f"환율 데이터 수집 실패: {str(e)}")
        return {"usd_krw": {}, "available": False, "error": str(e)}


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

        # 프롬프트 구성
        prompt = f"""당신은 글로벌 시장 전문 애널리스트입니다.
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
- 구체적인 수치와 근거 제시
"""

        # LLM 호출
        response = llm.invoke(prompt)
        return response.content

    except Exception as e:
        logger.error(f"LLM 분석 실패: {str(e)}")
        return f"⚠️ 자동 분석 중 오류가 발생했습니다: {str(e)}"


def _format_global_markets(data: dict[str, Any]) -> str:
    """글로벌 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return "⚠️ 글로벌 시장 데이터를 사용할 수 없습니다."

    sp500 = data.get("sp500", {})
    nasdaq = data.get("nasdaq", {})
    dow = data.get("dow", {})

    return f"""
- S&P 500: {sp500.get("price", 0):.2f} ({sp500.get("change_percent", 0):+.2f}%)
- NASDAQ: {nasdaq.get("price", 0):.2f} ({nasdaq.get("change_percent", 0):+.2f}%)
- Dow Jones: {dow.get("price", 0):.2f} ({dow.get("change_percent", 0):+.2f}%)
"""


def _format_crypto_markets(data: dict[str, Any]) -> str:
    """암호화폐 시장 데이터 포맷팅"""
    if not data.get("available", False):
        return "⚠️ 암호화폐 시장 데이터를 사용할 수 없습니다."

    btc = data.get("bitcoin", {})
    eth = data.get("ethereum", {})
    global_data = data.get("global", {})

    btc_dominance = global_data.get("bitcoin_dominance", 0)

    return f"""
- Bitcoin: ${btc.get("current_price_usd", 0):,.2f} ({btc.get("price_change_24h", 0):+.2f}%)
- Ethereum: ${eth.get("current_price_usd", 0):,.2f} ({eth.get("price_change_24h", 0):+.2f}%)
- BTC 도미넌스: {btc_dominance:.1f}%
"""


def _format_market_sentiment(data: dict[str, Any]) -> str:
    """시장 심리 데이터 포맷팅"""
    if not data.get("available", False):
        return "⚠️ 시장 심리 데이터를 사용할 수 없습니다."

    score = data.get("score", 50)
    rating = data.get("rating", "Neutral")
    interpretation = data.get("interpretation", "")
    trend = data.get("trend", "stable")

    return f"""
- 현재 지수: {score}/100 ({rating})
- 해석: {interpretation}
- 추세: {trend}
"""


def _format_forex(data: dict[str, Any]) -> str:
    """환율 데이터 포맷팅"""
    if not data.get("available", False):
        return "⚠️ 환율 데이터를 사용할 수 없습니다."

    usd_krw = data.get("usd_krw", {})
    rate = usd_krw.get("rate", 0)

    return f"""
- USD/KRW: {rate:,.2f}원
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
        "1. 미국 주요 지수 (S&P 500, NASDAQ, Dow Jones)\n"
        "2. 암호화폐 시장 (Bitcoin, Ethereum)\n"
        "3. 시장 심리 지수 (Fear & Greed Index)\n"
        "4. 환율 (USD/KRW)\n\n"
        "데이터를 수집한 후, 다음과 같이 자연스럽게 분석해주세요:\n\n"
        "1. **글로벌 시장 현황**: 미국 증시와 암호화폐 시장이 어떻게 움직이고 있는지 요약\n"
        "2. **한국 시장 영향**: 이러한 글로벌 흐름이 한국 주식시장에 어떤 영향을 줄 수 있는지 설명\n"
        "3. **리스크 환경**: 지금이 Risk-On(위험 선호) 환경인지 Risk-Off(안전 선호) 환경인지 판단\n"
        "4. **투자 전략 시사점**: 현재 글로벌 환경에서 투자자들이 주의해야 할 점\n\n"
        "⚠️ 주의사항:\n"
        "- API 데이터가 없을 경우(available: false), 그 사실을 명시하고 사용 가능한 데이터만으로 분석하세요\n"
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
