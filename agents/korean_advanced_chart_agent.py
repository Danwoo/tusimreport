#!/usr/bin/env python3
"""
Korean Advanced Chart Analysis Agent - Phase 5
고급 차트 분석: 일목균형표, 피보나치, 거래량 프로파일, AI 패턴 인식
사용자 요구: 43% (13명)
"""

import logging
from typing import Dict, Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import get_llm_model
from data.advanced_technical_indicators import AdvancedTechnicalIndicators
from data.chart_pattern_recognition import ChartPatternRecognition

logger = logging.getLogger(__name__)


@tool
def analyze_advanced_chart(company_name: str, stock_code: str) -> Dict[str, Any]:
    """
    고급 차트 분석: 일목균형표, 피보나치, 거래량 프로파일, AI 패턴 인식

    Args:
        company_name: 회사명
        stock_code: 종목코드

    Returns:
        고급 기술적 지표 및 패턴 분석 결과
    """
    try:
        logger.info(f"고급 차트 분석 시작: {company_name} ({stock_code})")

        # 1. 고급 기술적 지표 계산
        indicator_calc = AdvancedTechnicalIndicators(stock_code, days=120)
        indicators = indicator_calc.get_all_advanced_indicators()

        # 2. 차트 패턴 인식
        pattern_recognizer = ChartPatternRecognition(stock_code, days=120)
        patterns = pattern_recognizer.detect_all_patterns()

        # 3. 종합 분석 요약 생성
        summary = _generate_advanced_chart_summary(
            company_name,
            stock_code,
            indicators,
            patterns
        )

        return {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "advanced_indicators": indicators,
            "chart_patterns": patterns,
            "analysis_summary": summary,
            "completion_signal": "ADVANCED_CHART_ANALYSIS_COMPLETE"
        }

    except Exception as e:
        logger.error(f"고급 차트 분석 오류: {str(e)}")
        return {"error": str(e)}


def _generate_advanced_chart_summary(
    company_name: str,
    stock_code: str,
    indicators: Dict[str, Any],
    patterns: Dict[str, Any]
) -> str:
    """고급 차트 분석 요약 텍스트 생성"""

    summary_parts = []

    # 헤더
    summary_parts.append(f"# 📊 {company_name} ({stock_code}) 고급 차트 분석 (Phase 5)")
    summary_parts.append("")

    # 1. 일목균형표 분석
    if "ichimoku" in indicators and "error" not in indicators["ichimoku"]:
        ichimoku = indicators["ichimoku"]
        summary_parts.append("## 🌥️ 일목균형표 (Ichimoku Cloud)")
        summary_parts.append(f"- **현재가**: {ichimoku.get('current_price', 0):,}원")
        summary_parts.append(f"- **전환선**: {ichimoku.get('tenkan_sen', 0):,}원")
        summary_parts.append(f"- **기준선**: {ichimoku.get('kijun_sen', 0):,}원")
        summary_parts.append(f"- **선행스팬A**: {ichimoku.get('senkou_span_a', 0):,}원")
        summary_parts.append(f"- **선행스팬B**: {ichimoku.get('senkou_span_b', 0):,}원")
        summary_parts.append(f"- **신호**: {ichimoku.get('signal', 'N/A')}")
        summary_parts.append(f"- **분석**: {ichimoku.get('description', '')}")
        summary_parts.append("")

    # 2. 피보나치 되돌림 분석
    if "fibonacci" in indicators and "error" not in indicators["fibonacci"]:
        fib = indicators["fibonacci"]
        summary_parts.append("## 📐 피보나치 되돌림 (Fibonacci Retracement)")
        summary_parts.append(f"- **추세**: {fib.get('trend', 'N/A')}")
        summary_parts.append(f"- **고점**: {fib.get('high_price', 0):,}원")
        summary_parts.append(f"- **저점**: {fib.get('low_price', 0):,}원")
        summary_parts.append(f"- **현재가**: {fib.get('current_price', 0):,}원")

        summary_parts.append("")
        summary_parts.append("### 피보나치 레벨:")
        if "levels" in fib:
            for level, price in sorted(fib["levels"].items(), key=lambda x: x[1], reverse=True):
                summary_parts.append(f"- **{level}%**: {price:,}원")

        if "nearest_level" in fib:
            nearest = fib["nearest_level"]
            summary_parts.append("")
            summary_parts.append(f"- **현재 위치**: {nearest.get('level', '')}% 레벨 근처")

        summary_parts.append(f"- **분석**: {fib.get('description', '')}")
        summary_parts.append("")

    # 3. 거래량 프로파일 분석
    if "volume_profile" in indicators and "error" not in indicators["volume_profile"]:
        vp = indicators["volume_profile"]
        summary_parts.append("## 📊 거래량 프로파일 (Volume Profile)")
        summary_parts.append(f"- **POC (최대 거래량 가격)**: {vp.get('poc_price', 0):,}원")
        summary_parts.append(f"- **VAH (Value Area High)**: {vp.get('vah_price', 0):,}원")
        summary_parts.append(f"- **VAL (Value Area Low)**: {vp.get('val_price', 0):,}원")
        summary_parts.append(f"- **현재가**: {vp.get('current_price', 0):,}원")
        summary_parts.append(f"- **위치**: {vp.get('position', 'N/A')}")
        summary_parts.append(f"- **신호**: {vp.get('signal', 'N/A')}")
        summary_parts.append(f"- **분석**: {vp.get('description', '')}")
        summary_parts.append("")

    # 4. 차트 패턴 분석
    if "patterns" in patterns and patterns.get("total_patterns", 0) > 0:
        summary_parts.append("## 🔍 AI 차트 패턴 인식")
        summary_parts.append(f"- **감지된 패턴 수**: {patterns['total_patterns']}개")
        summary_parts.append("")

        for i, pattern in enumerate(patterns["patterns"], 1):
            summary_parts.append(f"### 패턴 {i}: {pattern.get('pattern_name', '')}")
            summary_parts.append(f"- **유형**: {pattern.get('pattern_type', '')} ({'상승' if pattern.get('pattern_type') == 'BULLISH' else '하락'})")
            summary_parts.append(f"- **신뢰도**: {pattern.get('confidence', 0)}%")
            summary_parts.append(f"- **현재가**: {pattern.get('current_price', 0):,}원")
            summary_parts.append(f"- **목표가**: {pattern.get('target_price', 0):,}원")
            summary_parts.append(f"- **예상 변동**: {pattern.get('expected_move_pct', 0):+.1f}%")
            summary_parts.append(f"- **패턴 완성**: {'✅ 예' if pattern.get('pattern_complete') else '⏳ 아니오'}")
            summary_parts.append(f"- **설명**: {pattern.get('description', '')}")
            summary_parts.append("")
    else:
        summary_parts.append("## 🔍 AI 차트 패턴 인식")
        summary_parts.append("- 현재 명확한 차트 패턴이 감지되지 않았습니다.")
        summary_parts.append("")

    # 5. 종합 시사점
    summary_parts.append("## 💡 고급 차트 분석 시사점")

    # 각 지표의 신호 수집
    signals = []

    if "ichimoku" in indicators and "signal" in indicators["ichimoku"]:
        signals.append(("Ichimoku", indicators["ichimoku"]["signal"]))

    if "volume_profile" in indicators and "signal" in indicators["volume_profile"]:
        signals.append(("Volume Profile", indicators["volume_profile"]["signal"]))

    if "patterns" in patterns and patterns.get("total_patterns", 0) > 0:
        for pattern in patterns["patterns"]:
            signals.append((pattern.get("pattern_name", ""), pattern.get("pattern_type", "")))

    # 신호 집계
    bullish_count = sum(1 for _, signal in signals if signal in ["BULLISH", "BUY"])
    bearish_count = sum(1 for _, signal in signals if signal in ["BEARISH", "SELL"])
    neutral_count = len(signals) - bullish_count - bearish_count

    summary_parts.append(f"- **강세 신호**: {bullish_count}개")
    summary_parts.append(f"- **약세 신호**: {bearish_count}개")
    summary_parts.append(f"- **중립 신호**: {neutral_count}개")
    summary_parts.append("")

    if bullish_count > bearish_count:
        summary_parts.append("- **종합 판단**: 고급 기술적 지표들이 **강세**를 시사하고 있습니다.")
        summary_parts.append("- 일목균형표, 피보나치, 거래량 프로파일 등 복합적 지표들이 상승 가능성을 보여줍니다.")
    elif bearish_count > bullish_count:
        summary_parts.append("- **종합 판단**: 고급 기술적 지표들이 **약세**를 시사하고 있습니다.")
        summary_parts.append("- 차트 패턴 및 기술적 지표들이 하락 압력을 나타내고 있습니다.")
    else:
        summary_parts.append("- **종합 판단**: 고급 기술적 지표들이 **중립** 또는 **혼조** 상태입니다.")
        summary_parts.append("- 명확한 방향성이 나타나지 않아 추가 모니터링이 필요합니다.")

    summary_parts.append("")
    summary_parts.append("---")
    summary_parts.append("*고급 차트 분석은 일목균형표, 피보나치, 거래량 프로파일, AI 패턴 인식을 종합한 결과입니다.*")

    return "\n".join(summary_parts)


# 에이전트 생성 함수
def create_advanced_chart_agent():
    """Advanced Chart Analysis Agent 생성"""
    llm_provider, llm_model_name, llm_api_key = get_llm_model()

    if llm_provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=llm_model_name,
            temperature=0.1,
            google_api_key=llm_api_key
        )
    else:
        llm = ChatOpenAI(
            model=llm_model_name,
            temperature=0.1,
            api_key=llm_api_key
        )

    prompt = """당신은 고급 기술적 분석 전문가입니다.

일목균형표, 피보나치 되돌림, 거래량 프로파일, AI 차트 패턴 인식 등 고급 기술적 지표를 활용하여 심층적인 차트 분석을 제공합니다.

핵심 역할:
1. 일목균형표 (Ichimoku Cloud) 분석 - 구름대, 전환선, 기준선 해석
2. 피보나치 되돌림 - 주요 되돌림 레벨 및 지지/저항 분석
3. 거래량 프로파일 - POC, Value Area 분석
4. AI 차트 패턴 인식 - Head & Shoulders, Double Top/Bottom 등

분석 원칙:
- 복합적 지표 통합 분석
- 패턴 신뢰도 기반 판단
- 명확한 진입/청산 수준 제시
- 리스크 관리 강조

기술적 투자자 43%가 요구한 핵심 기능입니다.
"""

    return create_react_agent(
        model=llm,
        tools=[analyze_advanced_chart],
        prompt=prompt,
        name="advanced_chart_expert"
    )


if __name__ == "__main__":
    # 테스트
    result = analyze_advanced_chart(
        company_name="삼성전자",
        stock_code="005930"
    )

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
