#!/usr/bin/env python3
"""
P2-1-B Option B 통합 테스트 스크립트
Naver + Tavily 멀티 쿼리 전략 실전 테스트

🎯 목표: 20개 → 100개 뉴스 확장 검증

사용법:
    python3 test_p2_1_b_option_b.py

필수 환경 변수:
    NAVER_CLIENT_ID
    NAVER_CLIENT_SECRET
    TAVILY_API_KEY
"""

import logging
import os
import sys
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.multi_query_naver_client import MultiQueryNaverClient
from data.multi_query_tavily_client import MultiQueryTavilyClient

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_env_vars():
    """환경 변수 로드"""
    # .env 파일 직접 읽기
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_vars = {}

    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    # 환경 변수와 병합
    for key in ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "TAVILY_API_KEY"]:
        if key not in env_vars:
            env_vars[key] = os.environ.get(key)

    return env_vars


def test_naver_multi_query(client, company_name, stock_code):
    """Naver 멀티 쿼리 테스트"""
    print("\n" + "=" * 80)
    print("📰 STEP 1: Naver News API 멀티 쿼리 테스트")
    print("=" * 80)

    try:
        news_list = client.fetch_multi_query(
            company_name=company_name, stock_code=stock_code, target_count=50
        )

        print(f"\n✅ Naver 뉴스 수집 완료: {len(news_list)}개")

        if news_list:
            print("\n🔍 상위 5개 뉴스 샘플:")
            for i, news in enumerate(news_list[:5], 1):
                print(f"\n[{i}] [{news['query']}]")
                print(f"    제목: {news['title'][:60]}...")
                print(f"    URL: {news['url']}")

        return news_list

    except Exception as e:
        logger.error(f"Naver 테스트 실패: {str(e)}")
        return []


def test_tavily_multi_query(client, company_name, stock_code):
    """Tavily 멀티 쿼리 테스트"""
    print("\n" + "=" * 80)
    print("🌍 STEP 2: Tavily Search API 멀티 쿼리 테스트")
    print("=" * 80)

    try:
        news_list = client.fetch_multi_query(
            company_name=company_name, stock_code=stock_code, target_count=50
        )

        print(f"\n✅ Tavily 뉴스 수집 완료: {len(news_list)}개")

        if news_list:
            print("\n🔍 상위 5개 뉴스 샘플:")
            for i, news in enumerate(news_list[:5], 1):
                print(f"\n[{i}] [{news['category']}] (Score: {news['score']:.2f})")
                print(f"    제목: {news['title'][:60]}...")
                print(f"    출처: {news['source']}")

        return news_list

    except Exception as e:
        logger.error(f"Tavily 테스트 실패: {str(e)}")
        return []


def integrate_results(naver_news, tavily_news):
    """두 소스 통합 및 중복 제거"""
    print("\n" + "=" * 80)
    print("🔗 STEP 3: 결과 통합 및 중복 제거")
    print("=" * 80)

    all_news = []
    seen_urls = set()

    # Naver 뉴스 추가
    for news in naver_news:
        url = news.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_news.append({**news, "api_source": "Naver"})

    # Tavily 뉴스 추가 (중복 제거)
    duplicate_count = 0
    for news in tavily_news:
        url = news.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_news.append({**news, "api_source": "Tavily"})
        else:
            duplicate_count += 1

    print("\n📊 통합 결과:")
    print(f"   Naver: {len(naver_news)}개")
    print(f"   Tavily: {len(tavily_news)}개 (중복 제거: {duplicate_count}개)")
    print(f"   총합: {len(all_news)}개 (순수 유니크)")

    return all_news


def print_final_report(all_news):
    """최종 보고서 출력"""
    print("\n" + "=" * 80)
    print("📊 최종 결과 보고서")
    print("=" * 80)

    print(f"\n✅ 총 수집 뉴스: {len(all_news)}개")

    # 소스별 분포
    naver_count = sum(1 for n in all_news if n.get("api_source") == "Naver")
    tavily_count = sum(1 for n in all_news if n.get("api_source") == "Tavily")

    print("\n📰 소스별 분포:")
    print(f"   Naver API: {naver_count}개 ({naver_count / len(all_news) * 100:.1f}%)")
    print(f"   Tavily API: {tavily_count}개 ({tavily_count / len(all_news) * 100:.1f}%)")

    # 목표 달성 여부
    target = 100
    achievement_rate = len(all_news) / target * 100

    print(f"\n🎯 목표 달성률: {achievement_rate:.1f}% (목표: {target}개)")

    if len(all_news) >= target:
        print(f"   ✅ 목표 달성! {len(all_news) - target}개 초과 수집")
    else:
        print(f"   ⚠️ 목표 미달: {target - len(all_news)}개 부족")

    # 상위 10개 통합 뉴스
    print("\n🔍 통합 뉴스 상위 10개:")
    for i, news in enumerate(all_news[:10], 1):
        source_tag = f"[{news['api_source']}]"
        print(f"\n[{i}] {source_tag}")
        print(f"    제목: {news['title'][:60]}...")
        print(f"    URL: {news['url']}")


def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("🧪 P2-1-B Option B 통합 테스트")
    print("   Naver + Tavily 멀티 쿼리 전략 (20개 → 100개)")
    print("=" * 80)

    # 1. 환경 변수 로드
    env_vars = load_env_vars()

    naver_id = env_vars.get("NAVER_CLIENT_ID")
    naver_secret = env_vars.get("NAVER_CLIENT_SECRET")
    tavily_key = env_vars.get("TAVILY_API_KEY")

    # 2. API 키 검증
    missing_keys = []
    if not naver_id or not naver_secret:
        missing_keys.append("Naver API")
    if not tavily_key:
        missing_keys.append("Tavily API")

    if missing_keys:
        print(f"\n❌ 다음 API 키가 설정되지 않았습니다: {', '.join(missing_keys)}")
        print("\n💡 .env 파일에 다음을 추가하세요:")
        if "Naver API" in missing_keys:
            print("   NAVER_CLIENT_ID=your_client_id")
            print("   NAVER_CLIENT_SECRET=your_client_secret")
        if "Tavily API" in missing_keys:
            print("   TAVILY_API_KEY=your_api_key")
        return 1

    # 3. 클라이언트 생성
    naver_client = MultiQueryNaverClient(naver_id, naver_secret)
    tavily_client = MultiQueryTavilyClient(tavily_key)

    # 4. 테스트 대상
    company_name = "삼성전자"
    stock_code = "005930"

    print(f"\n🎯 테스트 대상: {company_name} ({stock_code})")
    print(f"⏰ 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 5. Naver 멀티 쿼리 테스트
    naver_news = test_naver_multi_query(naver_client, company_name, stock_code)

    # 6. Tavily 멀티 쿼리 테스트
    tavily_news = test_tavily_multi_query(tavily_client, company_name, stock_code)

    # 7. 결과 통합
    all_news = integrate_results(naver_news, tavily_news)

    # 8. 최종 보고서
    print_final_report(all_news)

    # 9. 완료
    print(f"\n⏰ 종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("✅ 테스트 완료")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
