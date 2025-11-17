#!/usr/bin/env python3
"""
korean_sentiment_agent.py 통합 테스트
v2.3 멀티 쿼리 전략 검증
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.korean_sentiment_agent import get_enhanced_news_sentiment

def test_sentiment_agent():
    """
    감정 분석 에이전트 통합 테스트
    """
    print("=" * 80)
    print("🧪 korean_sentiment_agent.py v2.3 통합 테스트")
    print("=" * 80)
    print()

    # 테스트 종목
    test_companies = [
        {"name": "삼성전자", "code": "005930"},
    ]

    for company in test_companies:
        print(f"📊 테스트: {company['name']} ({company['code']})")
        print("-" * 80)

        try:
            result = get_enhanced_news_sentiment(
                company_name=company['name'],
                stock_code=company['code']
            )

            if "error" in result:
                print(f"❌ 오류 발생: {result['error']}")
                print()
                continue

            # 결과 출력
            print(f"✅ 분석 완료")
            print()

            # 데이터 소스 통계
            if "data_sources" in result:
                ds = result["data_sources"]
                print(f"📰 Naver 뉴스: {ds.get('naver_news_count', 0)}개")
                print(f"🌍 Tavily 뉴스: {ds.get('tavily_news_count', 0)}개")
                print(f"🔗 총 분석: {ds.get('total_analyzed', 0)}개")
                print()

                # 목표 달성률
                total = ds.get('total_analyzed', 0)
                target = 100
                if total > 0:
                    achievement = (total / target) * 100
                    print(f"🎯 목표 달성률: {achievement:.1f}% ({total}/{target}개)")

                    if achievement >= 70:
                        print(f"✅ 성공! 목표 70% 이상 달성")
                    elif achievement >= 50:
                        print(f"⚠️  부분 성공 (50-70%)")
                    else:
                        print(f"❌ 목표 미달 (50% 미만)")
                print()

            # 감정 분석 결과
            if "sentiment_analysis" in result:
                print("💭 감정 분석 결과:")
                for key, value in result["sentiment_analysis"].items():
                    print(f"   {key}: {value}")
                print()

            # 뉴스 소스 샘플
            if "news_sources" in result:
                sources = result["news_sources"]
                print(f"📄 뉴스 소스 (총 {len(sources)}개)")
                print()

                # 네이버 샘플
                naver_sources = [s for s in sources if s.get('type') == 'naver']
                if naver_sources:
                    print(f"🇰🇷 Naver 뉴스 샘플 (상위 3개):")
                    for i, source in enumerate(naver_sources[:3], 1):
                        print(f"   {i}. {source['title']}")
                        print(f"      URL: {source['url'][:80]}...")
                    print()

                # Tavily 샘플
                tavily_sources = [s for s in sources if s.get('type') == 'tavily']
                if tavily_sources:
                    print(f"🌍 Tavily 뉴스 샘플 (상위 3개):")
                    for i, source in enumerate(tavily_sources[:3], 1):
                        print(f"   {i}. {source['title']}")
                        print(f"      Score: {source.get('score', 0):.2f}")
                        print(f"      URL: {source['url'][:80]}...")
                    print()

        except Exception as e:
            print(f"❌ 테스트 실패: {str(e)}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 80)
    print("테스트 완료")
    print("=" * 80)
    print()
    print("📝 참고:")
    print("   - API 키가 유효하지 않으면 0개 수집됩니다")
    print("   - Naver/Tavily API 키를 재발급한 후 다시 테스트하세요")
    print("   - API_KEY_RENEWAL_GUIDE.md 참조")


if __name__ == "__main__":
    test_sentiment_agent()
