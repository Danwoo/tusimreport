#!/usr/bin/env python3
"""
P2-1-B Option B 통합 테스트: Multi-Query Naver + Tavily Strategy
목표: 20개 → 100개 뉴스 수집 검증
"""

import os
import sys
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 현재 디렉토리를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.multi_query_naver_client import MultiQueryNaverClient
from data.multi_query_tavily_client import MultiQueryTavilyClient


def test_multi_query_integration():
    """
    통합 테스트: Naver + Tavily 멀티 쿼리 전략
    """
    print("=" * 80)
    print("P2-1-B Option B: Multi-Query Strategy Integration Test")
    print("=" * 80)
    print()

    # ============================================
    # Step 1: 환경 변수 확인
    # ============================================
    print("📋 Step 1: 환경 변수 확인")
    print("-" * 80)

    naver_client_id = os.getenv("NAVER_CLIENT_ID")
    naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")
    tavily_api_key = os.getenv("TAVILY_API_KEY")

    env_check = {
        "NAVER_CLIENT_ID": "✅" if naver_client_id else "❌",
        "NAVER_CLIENT_SECRET": "✅" if naver_client_secret else "❌",
        "TAVILY_API_KEY": "✅" if tavily_api_key else "❌",
    }

    for key, status in env_check.items():
        print(f"{status} {key}")

    if not all([naver_client_id, naver_client_secret, tavily_api_key]):
        print("\n❌ 필수 API 키가 설정되지 않았습니다.")
        print("   .env 파일을 확인하세요.")
        return

    print("\n✅ 모든 API 키 설정 완료")
    print()

    # ============================================
    # Step 2: 클라이언트 초기화
    # ============================================
    print("🔧 Step 2: 클라이언트 초기화")
    print("-" * 80)

    try:
        naver_client = MultiQueryNaverClient(naver_client_id, naver_client_secret)
        print("✅ MultiQueryNaverClient 초기화 성공")

        tavily_client = MultiQueryTavilyClient(tavily_api_key)
        print("✅ MultiQueryTavilyClient 초기화 성공")
    except Exception as e:
        print(f"❌ 클라이언트 초기화 실패: {e}")
        return

    print()

    # ============================================
    # Step 3: 삼성전자 뉴스 수집 테스트
    # ============================================
    print("📰 Step 3: 삼성전자 뉴스 수집 테스트")
    print("-" * 80)

    company_name = "삼성전자"
    stock_code = "005930"
    target_per_source = 50

    # Naver 뉴스 수집
    print(f"\n🇰🇷 Naver 뉴스 수집 (목표: {target_per_source}개)")
    print("   " + "-" * 76)
    try:
        naver_news = naver_client.fetch_multi_query(
            company_name=company_name,
            stock_code=stock_code,
            target_count=target_per_source
        )
        print(f"   ✅ Naver 수집 완료: {len(naver_news)}개")
    except Exception as e:
        print(f"   ❌ Naver 수집 실패: {e}")
        naver_news = []

    # Tavily 뉴스 수집
    print(f"\n🌍 Tavily 뉴스 수집 (목표: {target_per_source}개)")
    print("   " + "-" * 76)
    try:
        tavily_news = tavily_client.fetch_multi_query(
            company_name=company_name,
            stock_code=stock_code,
            target_count=target_per_source
        )
        print(f"   ✅ Tavily 수집 완료: {len(tavily_news)}개")
    except Exception as e:
        print(f"   ❌ Tavily 수집 실패: {e}")
        tavily_news = []

    print()

    # ============================================
    # Step 4: 통합 결과 분석
    # ============================================
    print("📊 Step 4: 통합 결과 분석")
    print("-" * 80)

    total_collected = len(naver_news) + len(tavily_news)
    target_total = 100
    achievement_rate = (total_collected / target_total) * 100 if target_total > 0 else 0

    print(f"\n📰 Naver 뉴스: {len(naver_news)}개")
    print(f"🌍 Tavily 뉴스: {len(tavily_news)}개")
    print(f"🔗 총 수집: {total_collected}개")
    print(f"🎯 목표: {target_total}개")
    print(f"📈 달성률: {achievement_rate:.1f}%")

    # 결과 판정
    print()
    if achievement_rate >= 70:
        print("✅ 테스트 성공! 목표 달성률 70% 이상")
    elif achievement_rate >= 50:
        print("⚠️  테스트 부분 성공. 목표 달성률 50-70%")
    else:
        print("❌ 테스트 실패. 목표 달성률 50% 미만")

    print()

    # ============================================
    # Step 5: 샘플 뉴스 출력
    # ============================================
    print("📄 Step 5: 샘플 뉴스 출력")
    print("-" * 80)

    if naver_news:
        print("\n🇰🇷 Naver 샘플 (최신 3개):")
        for i, news in enumerate(naver_news[:3], 1):
            print(f"\n   {i}. {news['title']}")
            print(f"      URL: {news['url'][:80]}...")

    if tavily_news:
        print("\n🌍 Tavily 샘플 (최고 점수 3개):")
        for i, news in enumerate(tavily_news[:3], 1):
            print(f"\n   {i}. [{news.get('category', 'N/A')}] {news['title']}")
            print(f"      Score: {news.get('score', 0):.2f}")
            print(f"      Source: {news.get('source', 'unknown')}")
            print(f"      URL: {news['url'][:80]}...")

    print()
    print("=" * 80)
    print("테스트 완료")
    print("=" * 80)


if __name__ == "__main__":
    test_multi_query_integration()
