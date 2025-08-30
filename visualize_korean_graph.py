from agents.korean_supervisor_langgraph import korean_supervisor_graph

def visualize_korean_graph():
    """한국 주식 분석 그래프 시각화 - Context7 방법 사용"""
    print("Korean Stock Analysis LangGraph Visualization")
    print("=" * 60)
    
    try:
        # 그래프 가져오기
        graph = korean_supervisor_graph
        
        print(f"Graph Type: {type(graph).__name__}")
        print()
        
        # 1. Mermaid 코드 생성
        print("MERMAID DIAGRAM CODE")
        print("=" * 50)
        mermaid_code = graph.get_graph().draw_mermaid()
        print(mermaid_code)
        print()
        
        # 2. PNG 파일로 저장 (Context7 방법)
        try:
            print("Generating PNG Image...")
            png_data = graph.get_graph().draw_mermaid_png()
            
            # PNG 파일로 저장
            with open("korean_supervisor_graph.png", "wb") as f:
                f.write(png_data)
                
            print("SUCCESS: Graph saved as korean_supervisor_graph.png")
            print(f"   File size: {len(png_data)} bytes")
            
        except Exception as png_error:
            print(f"PNG generation failed: {str(png_error)}")
            print("   (This is normal - requires additional dependencies)")
        
        # 3. Mermaid 코드를 파일로 저장
        with open("korean_graph_mermaid.md", "w", encoding="utf-8") as f:
            f.write("# Korean Stock Analysis System - LangGraph Architecture\n\n")
            f.write("## System Overview\n")
            f.write("한국 주식 분석을 위한 LangGraph Supervisor Pattern 구현\n\n")
            f.write("### Components:\n")
            f.write("- **Supervisor**: 전체 워크플로우 조율\n")
            f.write("- **Financial Agent**: 재무 데이터 수집 및 분석 (FinanceDataReader + PyKRX)\n")
            f.write("- **Sentiment Agent**: 뉴스 감정 분석 (Naver API + Google News RSS)\n")
            f.write("- **Report Agent**: 종합 투자 보고서 생성 (GPT-4 기반)\n\n")
            f.write("### Data Sources:\n")
            f.write("- FinanceDataReader (KRX 히스토리컬 데이터)\n")
            f.write("- PyKRX (실시간 KRX 데이터)\n")
            f.write("- Naver News API (한국 뉴스)\n")
            f.write("- Google News RSS (추가 뉴스)\n")
            f.write("- OpenAI GPT-4o (분석 및 보고서 생성)\n\n")
            f.write("## Architecture Diagram\n\n")
            f.write("```mermaid\n")
            f.write(mermaid_code)
            f.write("\n```\n\n")
            f.write("## Usage\n")
            f.write("```python\n")
            f.write('from agents.korean_supervisor_langgraph import analyze_korean_stock_with_supervisor\n\n')
            f.write('# 삼성전자 분석\n')
            f.write('result = analyze_korean_stock_with_supervisor("005930", "삼성전자")\n\n')
            f.write('# 카카오 분석\n')
            f.write('result = analyze_korean_stock_with_supervisor("035720", "카카오")\n')
            f.write("```\n")
            
        print("SUCCESS: Mermaid diagram saved to korean_graph_mermaid.md")
        
        # 4. 그래프 구조 정보
        print("\nGRAPH STRUCTURE INFO")
        print("=" * 40)
        graph_dict = graph.get_graph()
        
        if hasattr(graph_dict, 'nodes'):
            nodes = list(graph_dict.nodes.keys())
            print(f"Nodes ({len(nodes)}):")
            for i, node in enumerate(nodes, 1):
                print(f"  {i}. {node}")
        
        if hasattr(graph_dict, 'edges'):
            edges = graph_dict.edges
            print(f"\nEdges ({len(edges)}):")
            for i, edge in enumerate(edges, 1):
                print(f"  {i}. {edge}")
        
        print("\nREADY FOR PRODUCTION")
        print("=" * 30)
        print("Korean Stock Analysis System")
        print("LangGraph Supervisor Pattern")
        print("Multi-Source Data Collection")  
        print("GPT-4 Powered Analysis")
        print("Complete Workflow Visualization")
        
        return True
        
    except Exception as e:
        print(f"Visualization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    visualize_korean_graph()