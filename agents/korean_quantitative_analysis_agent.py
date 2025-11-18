#!/usr/bin/env python3
"""
Korean Quantitative Analysis Agent - Phase 3
정량 분석 강화: DCF + Multiples + 재무 비율 심화
전문가 87.5% 요구 기능
"""

import logging
from typing import Dict, Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import get_llm_model
from data.valuation_calculator import ValuationCalculator

logger = logging.getLogger(__name__)


@tool
def analyze_quantitative_valuation(company_name: str, stock_code: str) -> Dict[str, Any]:
    """
    정량 분석: DCF + 멀티플 밸류에이션 + 재무 비율

    Args:
        company_name: 회사명
        stock_code: 종목코드

    Returns:
        정량 분석 결과 (Fair Value, Multiples, 재무 비율 등)
    """
    try:
        logger.info(f"정량 분석 시작: {company_name} ({stock_code})")

        # 1. Valuation Calculator 초기화
        calculator = ValuationCalculator(stock_code, company_name)

        # 2. DCF 밸류에이션
        dcf_result = calculator.calculate_dcf_valuation(
            wacc=0.085,  # WACC 8.5%
            terminal_growth=0.025,  # 영구 성장률 2.5%
            fcf_growth_rate=0.10  # FCF 성장률 10%
        )

        # 3. 멀티플 밸류에이션
        multiples_result = calculator.calculate_multiples_valuation()

        # 4. 통합 밸류에이션
        integrated = calculator.get_integrated_valuation()

        # 5. LLM 분석을 위한 요약 생성
        summary = _generate_valuation_summary(
            company_name,
            stock_code,
            dcf_result,
            multiples_result,
            integrated
        )

        return {
            "status": "success",
            "company_name": company_name,
            "stock_code": stock_code,
            "dcf_valuation": dcf_result,
            "multiples_valuation": multiples_result,
            "integrated_valuation": integrated,
            "quantitative_summary": summary,
            "completion_signal": "QUANTITATIVE_ANALYSIS_COMPLETE"
        }

    except Exception as e:
        logger.error(f"정량 분석 오류: {str(e)}")
        return {"error": str(e)}


def _generate_valuation_summary(
    company_name: str,
    stock_code: str,
    dcf_result: Dict[str, Any],
    multiples_result: Dict[str, Any],
    integrated: Dict[str, Any]
) -> str:
    """밸류에이션 결과 요약 텍스트 생성"""

    summary_parts = []

    # 헤더
    summary_parts.append(f"# 📊 {company_name} ({stock_code}) 정량 분석")
    summary_parts.append("")

    # 1. 통합 밸류에이션 결과
    if "error" not in integrated:
        weighted_fv = integrated.get('weighted_fair_value', 0)
        weighted_upside = integrated.get('weighted_upside', 0)
        current_price = integrated.get('current_price', 0)
        status = integrated.get('valuation_status', 'N/A')

        summary_parts.append("## 🎯 통합 밸류에이션 결론")
        summary_parts.append(f"- **현재가**: {current_price:,}원")
        summary_parts.append(f"- **적정가치 (가중평균)**: {weighted_fv:,}원")
        summary_parts.append(f"- **Upside/Downside**: {weighted_upside:+.1f}%")
        summary_parts.append(f"- **평가**: {status}")
        summary_parts.append("")

    # 2. DCF 밸류에이션
    if "error" not in dcf_result:
        dcf_fv = dcf_result.get('fair_value', 0)
        dcf_upside = dcf_result.get('upside_pct', 0)
        wacc = dcf_result.get('wacc', 0) * 100
        terminal_growth = dcf_result.get('terminal_growth', 0) * 100
        fcf_growth = dcf_result.get('fcf_growth_rate', 0) * 100

        summary_parts.append("## 💰 DCF (현금흐름할인) 분석")
        summary_parts.append(f"- **Fair Value**: {dcf_fv:,}원 ({dcf_upside:+.1f}%)")
        summary_parts.append(f"- **WACC**: {wacc:.1f}%")
        summary_parts.append(f"- **영구 성장률**: {terminal_growth:.1f}%")
        summary_parts.append(f"- **FCF 성장률**: {fcf_growth:.1f}%")

        if 'note' in dcf_result:
            summary_parts.append(f"- ⚠️ {dcf_result['note']}")

        summary_parts.append("")

    # 3. 멀티플 밸류에이션
    if "error" not in multiples_result:
        avg_fv = multiples_result.get('average_fair_value', 0)
        multiples_upside = multiples_result.get('upside_pct', 0)
        current = multiples_result.get('current_multiples', {})
        sector_avg = multiples_result.get('sector_average', {})
        fair_values = multiples_result.get('fair_values', {})

        summary_parts.append("## 📈 멀티플 (상대가치) 분석")
        summary_parts.append(f"- **평균 Fair Value**: {avg_fv:,}원 ({multiples_upside:+.1f}%)")
        summary_parts.append("")

        summary_parts.append("### 현재 vs 업종 평균")
        if current.get('PER') and sector_avg.get('PER'):
            per_status = "저평가" if current['PER'] < sector_avg['PER'] else "고평가"
            summary_parts.append(f"- **PER**: {current['PER']:.1f}배 (업종 {sector_avg['PER']:.1f}배) → {per_status}")

        if current.get('PBR') and sector_avg.get('PBR'):
            pbr_status = "저평가" if current['PBR'] < sector_avg['PBR'] else "고평가"
            summary_parts.append(f"- **PBR**: {current['PBR']:.2f}배 (업종 {sector_avg['PBR']:.2f}배) → {pbr_status}")

        if current.get('PSR') and sector_avg.get('PSR'):
            psr_status = "저평가" if current['PSR'] < sector_avg['PSR'] else "고평가"
            summary_parts.append(f"- **PSR**: {current['PSR']:.2f}배 (업종 {sector_avg['PSR']:.2f}배) → {psr_status}")

        summary_parts.append("")

        summary_parts.append("### 멀티플별 Fair Value")
        if fair_values.get('per_based'):
            summary_parts.append(f"- **PER 기준**: {fair_values['per_based']:,}원")
        if fair_values.get('pbr_based'):
            summary_parts.append(f"- **PBR 기준**: {fair_values['pbr_based']:,}원")
        if fair_values.get('psr_based'):
            summary_parts.append(f"- **PSR 기준**: {fair_values['psr_based']:,}원")

        summary_parts.append("")

    # 4. 투자 시사점
    summary_parts.append("## 💡 정량 분석 시사점")

    if "error" not in integrated:
        upside = integrated.get('weighted_upside', 0)

        if upside > 20:
            summary_parts.append("- **강력 저평가**: 현재가 대비 20% 이상 상승 여력")
            summary_parts.append("- DCF와 멀티플 분석 모두 매력적인 진입 구간 시사")
        elif upside > 10:
            summary_parts.append("- **적정 저평가**: 현재가 대비 10-20% 상승 여력")
            summary_parts.append("- 중장기 관점에서 긍정적 리스크/보상 비율")
        elif upside > 0:
            summary_parts.append("- **소폭 저평가**: 현재가 대비 0-10% 상승 여력")
            summary_parts.append("- 추가 모멘텀 발생 시 매력적")
        elif upside > -10:
            summary_parts.append("- **소폭 고평가**: 현재가 대비 0-10% 과대평가")
            summary_parts.append("- 조정 가능성 존재, 신중한 접근 필요")
        else:
            summary_parts.append("- **고평가**: 현재가 대비 10% 이상 과대평가")
            summary_parts.append("- 밸류에이션 부담, 매수 보류 권고")

    summary_parts.append("")
    summary_parts.append("---")
    summary_parts.append("*정량 분석은 과거 데이터 기반 추정치이며, 실제 결과와 차이가 있을 수 있습니다.*")

    return "\n".join(summary_parts)


# 에이전트 생성 함수
def create_quantitative_analysis_agent():
    """Quantitative Analysis Agent 생성"""
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

    prompt = """당신은 정량 분석 전문가입니다.

DCF (현금흐름할인) 밸류에이션과 멀티플 (PER/PBR/PSR) 분석을 통해 기업의 적정 가치를 평가합니다.

핵심 역할:
1. DCF 모델로 기업의 내재가치 산출
2. 멀티플 분석으로 상대가치 평가
3. 업종 평균 대비 저평가/고평가 판단
4. 정량적 근거 기반 투자 시사점 제공

분석 원칙:
- 객관적 수치 기반 분석
- 보수적 가정 적용
- 다양한 방법론 통합
- 명확한 투자 시사점 도출

전문가 87.5%가 요구한 핵심 기능입니다.
"""

    return create_react_agent(
        model=llm,
        tools=[analyze_quantitative_valuation],
        prompt=prompt,
        name="quantitative_analysis_expert"
    )


if __name__ == "__main__":
    # 테스트
    result = analyze_quantitative_valuation(
        company_name="삼성전자",
        stock_code="005930"
    )

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
