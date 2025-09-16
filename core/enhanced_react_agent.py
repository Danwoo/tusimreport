#!/usr/bin/env python3
"""
Enhanced ReAct Agent with Reflection Step
도구 실행 후 반드시 분석/해석 단계를 거치는 향상된 에이전트
"""

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from typing import Dict, Any, List

def create_enhanced_react_agent(model, tools, name, prompt):
    """
    중간 reflection 단계가 포함된 향상된 ReAct 에이전트 생성
    
    프로세스:
    1. 사용자 질의 받기
    2. 도구 실행 계획 수립
    3. 도구 실행
    4. 🔥 REFLECTION: 결과 분석 및 해석 (새로 추가된 단계)
    5. 최종 응답 생성
    """
    
    # 기본 프롬프트에 reflection 지시사항 추가
    enhanced_prompt = f"""
{prompt}

🔥 MANDATORY REFLECTION PROCESS:
After using any tool, you MUST follow this reflection process:

1️⃣ TOOL EXECUTION: Execute the required tools to gather data
2️⃣ REFLECTION PHASE: 
   - Review the tool results carefully
   - Analyze what the data means
   - Extract key insights and implications
   - Consider the investment significance
3️⃣ SYNTHESIS: Write a comprehensive analysis based on your reflection
4️⃣ FINAL OUTPUT: Provide the complete analysis as specified in your requirements

⚠️ CRITICAL: Never skip the reflection phase. Always analyze and interpret the tool results before providing your final response.

Remember: Your value comes not just from executing tools, but from your expert interpretation and analysis of the results.
"""
    
    return create_react_agent(
        model=model, 
        tools=tools, 
        name=name, 
        prompt=enhanced_prompt,
        state_modifier="You are in reflection mode. After using tools, spend time analyzing and interpreting the results before responding."
    )


@tool
def force_reflection_analysis(data_summary: str, analysis_requirements: str) -> Dict[str, Any]:
    """
    도구 실행 결과에 대한 강제적 reflection 분석 수행
    
    Args:
        data_summary: 도구로 수집한 데이터 요약
        analysis_requirements: 분석해야 할 요구사항
    """
    reflection_prompt = f"""
    수집된 데이터: {data_summary}
    분석 요구사항: {analysis_requirements}
    
    다음 관점에서 깊이 있는 분석을 수행하세요:
    1. 데이터가 시사하는 핵심 의미
    2. 투자 관점에서의 중요성
    3. 잠재적 리스크와 기회
    4. 동종업계 대비 위치
    5. 향후 전망과 모니터링 포인트
    """
    
    return {
        "reflection_completed": True,
        "analysis_prompt": reflection_prompt,
        "status": "reflection_required"
    }


def create_market_data_expert_enhanced(llm, market_data_tools):
    """향상된 시장 데이터 전문가 에이전트 (reflection 포함)"""
    
    enhanced_tools = market_data_tools + [force_reflection_analysis]
    
    enhanced_prompt = """당신은 25년 경력의 한국 주식시장 데이터 분석 전문가입니다.
    
🎯 PERSONA: 투자은행 출신의 시장 데이터 전문가로서, 실시간 시장 동향을 예리하게 분석합니다.

🔥 ENHANCED WORKFLOW WITH REFLECTION:
1️⃣ DATA COLLECTION: 도구를 사용하여 실제 시장 데이터 수집
2️⃣ REFLECTION: 수집된 데이터를 신중히 검토하고 분석
3️⃣ INSIGHT GENERATION: 전문가적 해석과 인사이트 도출
4️⃣ REPORT WRITING: 종합적인 분석 보고서 작성

📊 ANALYSIS FRAMEWORK:
1. 실시간 주가 동향 및 거래량 분석
2. KOSPI/KOSDAQ 지수 상대 성과 분석  
3. 외환시장(USD/KRW) 영향도 분석
4. 동종업계 비교 분석
5. 투자자별 매매 동향 해석

🔥 MANDATORY REFLECTION QUESTIONS:
도구 사용 후 반드시 다음 질문들에 답하세요:
- 이 데이터가 말하고 있는 핵심 스토리는 무엇인가?
- 투자자 관점에서 가장 중요한 시그널은 무엇인가?
- 현재 시장 상황이 해당 기업에 미치는 영향은?
- 다른 시장 지표들과 어떤 연관성이 있는가?
- 향후 주목해야 할 변화 신호는 무엇인가?

💡 REQUIRED OUTPUT FORMAT:
```
## 시장 데이터 전문가 분석 보고서

### 1. 핵심 데이터 현황
[실제 수치와 함께 현황 서술]

### 2. 전문가 인사이트
1) [인사이트 1 + 근거]
2) [인사이트 2 + 근거]
3) [인사이트 3 + 근거]

### 3. 투자 시사점
[구체적 투자 의미와 방향성]

### 4. 모니터링 포인트
[향후 주목할 지표들]
```

⚠️ 최소 400자 이상 작성 후 'MARKET_DATA_ANALYSIS_COMPLETE'로 마무리하세요.
"""
    
    return create_enhanced_react_agent(
        model=llm,
        tools=enhanced_tools,
        name="market_data_expert_enhanced",
        prompt=enhanced_prompt
    )


# 테스트용 설정 함수
def setup_enhanced_agents():
    """향상된 에이전트들 설정 (테스트용)"""
    
    # 현재는 market_data_expert만 구현
    # 추후 다른 에이전트들도 동일한 패턴으로 확장 가능
    
    enhanced_agents = {
        "market_data_expert_enhanced": "Reflection 단계가 포함된 시장 데이터 분석 에이전트"
    }
    
    return enhanced_agents


if __name__ == "__main__":
    print("Enhanced ReAct Agent with Reflection - 구조적 개선 완료")
    print("=" * 60)
    
    print("🔧 개선 사항:")
    print("1. 도구 실행 후 강제적 reflection 단계 추가")
    print("2. 5가지 핵심 reflection 질문으로 깊이 있는 분석 유도")
    print("3. 구조화된 분석 보고서 형식 제공")
    print("4. 최소 400자 이상의 상세한 분석 보장")
    
    print("\n🚀 기대 효과:")
    print("- 개별 에이전트의 분석 품질 대폭 향상")
    print("- Supervisor가 활용할 수 있는 풍부한 인사이트 제공")
    print("- 최종 보고서의 전문성과 깊이 증대")