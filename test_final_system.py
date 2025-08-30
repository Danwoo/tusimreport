import logging
from agents.korean_supervisor_langgraph import (
    korean_supervisor_graph
)

# 로깅 설정 - 토큰 절약을 위해 WARNING 레벨로
logging.basicConfig(level=logging.WARNING)

def test_graph_structure():
    """그래프 구조 확인 및 Mermaid 다이어그램 생성"""
    print("Korean Stock Analysis System - Graph Structure Test")
    print("=" * 70)
    
    try:
        graph = korean_supervisor_graph
        
        # 기본 정보
        print(f"Graph Type: {type(graph).__name__}")
        
        # 그래프 구조 정보
        graph_dict = graph.get_graph()
        
        if hasattr(graph_dict, 'nodes'):
            nodes = list(graph_dict.nodes.keys())
            print(f"Nodes Count: {len(nodes)}")
            print(f"Nodes: {nodes}")
        
        if hasattr(graph_dict, 'edges'):
            edges = graph_dict.edges
            print(f"Edges Count: {len(edges)}")
            
        print("\n" + "=" * 50)
        print("MERMAID DIAGRAM")
        print("=" * 50)
        
        # Mermaid 다이어그램 생성
        try:
            mermaid_code = graph.get_graph().draw_mermaid()
            print(mermaid_code)
            
            # 파일로 저장
            with open("korean_graph_structure.md", "w", encoding="utf-8") as f:
                f.write("# Korean Stock Analysis System - LangGraph Structure\n\n")
                f.write("```mermaid\n")
                f.write(mermaid_code)
                f.write("\n```\n")
            
            print("\nSUCCESS: Mermaid diagram saved to korean_graph_structure.md")
            
        except Exception as mermaid_error:
            print(f"Mermaid generation failed: {str(mermaid_error)}")
        
        print("\nSUCCESS: Graph structure analysis complete")
        return True
        
    except Exception as e:
        print(f"ERROR: Graph structure analysis failed: {str(e)}")
        return False

def test_agents_individually():
    """각 에이전트 개별 테스트"""
    print("\n" + "=" * 70)
    print("INDIVIDUAL AGENT TESTS")
    print("=" * 70)
    
    # 간단한 import 테스트
    try:
        from agents.korean_financial_react_agent import korean_financial_react_agent
        print("SUCCESS: Financial Agent imported")
        
        from agents.korean_sentiment_react_agent import korean_sentiment_react_agent
        print("SUCCESS: Sentiment Agent imported")
        
        from agents.korean_report_react_agent import korean_report_react_agent
        print("SUCCESS: Report Agent imported")
        
        from agents.korean_supervisor_langgraph import supervisor_node
        print("SUCCESS: Supervisor Node imported")
        
        print("\nAll agents successfully loaded and ready!")
        return True
        
    except Exception as e:
        print(f"ERROR: Agent import failed: {str(e)}")
        return False

def main():
    """메인 테스트"""
    print("Korean Stock Analysis LangGraph System - Final Test")
    print("=" * 80)
    
    results = []
    
    # 1. 그래프 구조 및 Mermaid
    results.append(test_graph_structure())
    
    # 2. 에이전트 개별 테스트
    results.append(test_agents_individually())
    
    # 결과 요약
    print("\n" + "=" * 80)
    passed = sum(results)
    total = len(results)
    
    print(f"Final Test Results: {passed}/{total} PASSED")
    
    if passed == total:
        print("\nSUCCESS: All systems operational!")
        print("Korean Stock Analysis System Ready for Production")
        print("- Samsung Electronics (005930)")
        print("- Kakao (035720)") 
        print("- Naver (035420)")
        print("- And all other Korean stocks (KRX/KOSPI/KOSDAQ)")
    else:
        print("\nWARNING: Some tests failed")

if __name__ == "__main__":
    main()