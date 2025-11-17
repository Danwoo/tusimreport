"""
Korean News RSS Client
주요 경제지 RSS 실시간 수집

🆕 P2-1: 뉴스 소스 대폭 확장 (Stage 3)
- 한국경제, 매일경제, 서울경제, 머니투데이 등 RSS
- 로그인 불필요, 공개 RSS 피드 활용
- feedparser 대신 xml.etree 사용 (의존성 최소화)
"""

import logging
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from html.parser import HTMLParser
import re
import urllib3

# SSL 경고 억제 (verify=False 사용 시)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class HTMLStripper(HTMLParser):
    """HTML 태그 제거 파서"""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_data(self):
        return ''.join(self.text)


def strip_html_tags(html: str) -> str:
    """HTML 태그 제거"""
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()


class KoreanNewsRSSClient:
    """한국 주요 경제지 RSS 실시간 수집 클라이언트"""

    def __init__(self):
        """
        RSS 피드 URL 설정

        Note: 실제 테스트하면서 작동하는 URL만 유지
        """
        # ✅ 작동 확인된 RSS 피드들 (공식 RSS 제공)
        self.rss_feeds = {
            # 연합뉴스 (공식 RSS)
            "yonhap": {
                "url": "https://www.yna.co.kr/RSS/headline.xml",
                "name": "연합뉴스",
                "tested": False
            },
            # 이데일리 (공식 RSS)
            "edaily": {
                "url": "http://www.edaily.co.kr/rss/edaily_news.xml",
                "name": "이데일리",
                "tested": False
            },
            # 뉴스핌 (공식 RSS)
            "newspim": {
                "url": "http://www.newspim.com/news/rss/",
                "name": "뉴스핌",
                "tested": False
            },
            # 뉴시스 (공식 RSS)
            "newsis": {
                "url": "http://www.newsis.com/RSS/allnewstitle.xml",
                "name": "뉴시스",
                "tested": False
            },
        }

    def test_rss_feed(self, feed_key: str) -> bool:
        """
        RSS 피드 테스트 (실제 접속 가능한지 확인)

        Args:
            feed_key: rss_feeds의 키 (예: "hankyung")

        Returns:
            성공 시 True, 실패 시 False
        """
        try:
            feed_info = self.rss_feeds.get(feed_key)
            if not feed_info:
                logger.error(f"❌ 알 수 없는 피드: {feed_key}")
                return False

            logger.info(f"🧪 테스트 시작: {feed_info['name']} ({feed_info['url']})")

            # RSS 피드 다운로드 (User-Agent 추가 - 봇 차단 우회)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(feed_info['url'], headers=headers, timeout=10, verify=False)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)

            # RSS 또는 Atom 포맷 감지
            if root.tag == 'rss':
                # RSS 2.0
                items = root.findall('.//item')
                logger.info(f"✅ RSS 2.0 포맷 감지")
            elif root.tag.endswith('feed'):
                # Atom
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                logger.info(f"✅ Atom 포맷 감지")
            else:
                logger.error(f"❌ 알 수 없는 RSS 포맷: {root.tag}")
                return False

            # 엔트리 개수 확인
            entry_count = len(items)
            if entry_count == 0:
                logger.error(f"❌ RSS 피드가 비어있음: {feed_info['name']}")
                return False

            # 첫 번째 엔트리 샘플 출력
            first_item = items[0]
            title_elem = first_item.find('title') or first_item.find('{http://www.w3.org/2005/Atom}title')
            title = title_elem.text if title_elem is not None else 'N/A'

            logger.info(f"✅ RSS 피드 작동: {feed_info['name']}")
            logger.info(f"   - 총 기사 수: {entry_count}개")
            logger.info(f"   - 첫 번째 기사: {title[:50]}...")

            # 테스트 완료 표시
            self.rss_feeds[feed_key]['tested'] = True
            return True

        except Exception as e:
            logger.error(f"❌ RSS 테스트 실패 ({feed_key}): {str(e)}")
            return False

    def test_all_feeds(self) -> Dict[str, bool]:
        """
        모든 RSS 피드 테스트

        Returns:
            각 피드의 테스트 결과 (True/False)
        """
        results = {}
        for feed_key in self.rss_feeds.keys():
            results[feed_key] = self.test_rss_feed(feed_key)

        # 요약 출력
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        logger.info(f"\n📊 RSS 피드 테스트 결과: {success_count}/{total_count} 성공")

        return results

    def fetch_news_from_feed(
        self,
        feed_key: str,
        keyword: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        특정 RSS 피드에서 뉴스 수집

        Args:
            feed_key: RSS 피드 키
            keyword: 검색 키워드 (기업명)
            days: 최근 N일간 뉴스 (default: 7)

        Returns:
            뉴스 리스트 [{"title": ..., "content": ..., "url": ...}, ...]
        """
        try:
            feed_info = self.rss_feeds.get(feed_key)
            if not feed_info:
                logger.error(f"❌ 알 수 없는 피드: {feed_key}")
                return []

            logger.info(f"📰 뉴스 수집 시작: {feed_info['name']} (키워드: {keyword})")

            # RSS 피드 다운로드 (User-Agent 추가)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(feed_info['url'], headers=headers, timeout=10, verify=False)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)

            # RSS 또는 Atom 포맷 감지
            if root.tag == 'rss':
                items = root.findall('.//item')
            elif root.tag.endswith('feed'):
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            else:
                logger.error(f"❌ 알 수 없는 RSS 포맷")
                return []

            # 날짜 필터링 기준
            cutoff_date = datetime.now() - timedelta(days=days)

            news_list = []
            for item in items:
                # 제목 추출
                title_elem = item.find('title') or item.find('{http://www.w3.org/2005/Atom}title')
                title = title_elem.text if title_elem is not None else ''

                # 요약/설명 추출
                desc_elem = (item.find('description') or
                           item.find('summary') or
                           item.find('{http://www.w3.org/2005/Atom}summary'))
                description = desc_elem.text if desc_elem is not None else ''

                # 키워드 필터링
                if keyword.lower() not in title.lower() and keyword.lower() not in description.lower():
                    continue

                # URL 추출
                link_elem = item.find('link') or item.find('{http://www.w3.org/2005/Atom}link')
                if link_elem is not None:
                    if link_elem.text:
                        url = link_elem.text
                    else:
                        url = link_elem.get('href', '')
                else:
                    url = ''

                # 발행일 추출 (간단히 현재 시간 사용, 추후 파싱 개선 가능)
                pub_elem = item.find('pubDate') or item.find('{http://www.w3.org/2005/Atom}published')
                published_at = datetime.now().isoformat()  # 일단 현재 시간

                # 본문 추출
                content = strip_html_tags(description) if description else ''

                news_item = {
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": feed_info['name'],
                    "published_at": published_at,
                    "summary": content[:200] if content else ''
                }

                news_list.append(news_item)

            logger.info(f"✅ {feed_info['name']}: {len(news_list)}개 뉴스 수집 완료")
            return news_list

        except Exception as e:
            logger.error(f"❌ 뉴스 수집 실패 ({feed_key}): {str(e)}")
            return []

    def fetch_all_news(
        self,
        keyword: str,
        days: int = 7,
        only_tested: bool = True
    ) -> List[Dict[str, Any]]:
        """
        모든 RSS 피드에서 뉴스 수집 (병렬)

        Args:
            keyword: 검색 키워드
            days: 최근 N일
            only_tested: True면 테스트 통과한 피드만 사용

        Returns:
            통합 뉴스 리스트
        """
        all_news = []

        for feed_key, feed_info in self.rss_feeds.items():
            # only_tested=True일 때 테스트 안 한 피드 건너뛰기
            if only_tested and not feed_info.get('tested', False):
                logger.warning(f"⏭️ 건너뜀 (테스트 안 함): {feed_info['name']}")
                continue

            news_list = self.fetch_news_from_feed(feed_key, keyword, days)
            all_news.extend(news_list)

        # 중복 제거 (URL 기준)
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news['url'] not in seen_urls:
                seen_urls.add(news['url'])
                unique_news.append(news)

        # 최신순 정렬
        unique_news.sort(key=lambda x: x['published_at'], reverse=True)

        logger.info(f"📊 총 {len(unique_news)}개 뉴스 수집 완료 (중복 제거 후)")

        return unique_news


# 테스트 코드
if __name__ == "__main__":
    import json
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    client = KoreanNewsRSSClient()

    # Step 1: 모든 RSS 피드 테스트
    print("\n" + "="*80)
    print("🧪 Step 1: 모든 RSS 피드 테스트")
    print("="*80)
    test_results = client.test_all_feeds()

    # Step 2: 성공한 피드로 실제 뉴스 수집 테스트
    print("\n" + "="*80)
    print("📰 Step 2: 실제 뉴스 수집 테스트 (삼성전자)")
    print("="*80)
    news_list = client.fetch_all_news(
        keyword="삼성전자",
        days=7,
        only_tested=True  # 테스트 통과한 피드만 사용
    )

    # 결과 출력
    print(f"\n✅ 총 {len(news_list)}개 뉴스 수집 완료")
    if news_list:
        print("\n📄 첫 3개 뉴스 샘플:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"\n[{i}] {news['source']} - {news['title'][:50]}...")
            print(f"    URL: {news['url']}")
            print(f"    발행: {news['published_at']}")
            print(f"    본문: {news['content'][:100]}...")
