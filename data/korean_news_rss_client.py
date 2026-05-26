"""
Korean News RSS Client
주요 경제지 RSS 실시간 수집

소스: Google News RSS만 유효 (그 외 국내 매체는 봇 차단으로 비활성).

⚠️ SSL 검증: 일부 한국 RSS 서버가 SAN 누락/체인 깨진 인증서를 쓰는 경우가
있어 verify=False가 필요했다. 그러나 MITM 위험을 줄이기 위해
`_ALLOWED_HOSTS` 화이트리스트에 등록된 도메인에 대해서만 verify=False를
허용하고, 그 외 도메인은 항상 verify=True로 요청한다.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3

from utils.time import kst_isoformat

# SSL 검증을 끄지 않는 게 원칙이지만, 일부 한국 매체 RSS는 인증서 체인이
# 깨져 있어 우회가 필요. 화이트리스트에 명시된 호스트에만 한해 허용한다.
_ALLOWED_INSECURE_HOSTS: frozenset[str] = frozenset(
    {
        # 현재 활성 소스: Google News. 정상 인증서. verify=True로 충분.
        # 아래는 향후 우회가 필요할 때 명시적으로 추가할 자리:
        # "rss.hankyung.com",
        # "rss.mk.co.kr",
    }
)

# verify=False가 들어가는 경우에만 인증서 경고를 끈다. 화이트리스트가 비면
# 사실상 호출되지 않지만 import 시점 안전 가드로 남겨 둔다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def _should_verify_tls(url: str) -> bool:
    """URL의 호스트가 insecure 허용 목록에 있으면 False, 아니면 True."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return True
    return host not in _ALLOWED_INSECURE_HOSTS


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
        return "".join(self.text)


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
        # 🎯 Option A: Google News RSS (봇 친화적, 무료)
        # Note: Google News는 검색 쿼리 기반이므로 동적 URL 생성 필요
        self.rss_feeds = {
            # Google News (봇 친화적!)
            "google_news": {
                "url_template": "https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko",
                "name": "Google News",
                "tested": False,
                "dynamic": True,  # 키워드 기반 동적 URL
            },
        }

        # ❌ 실패한 RSS 피드들 (참고용, 비활성화)
        self.failed_feeds = {
            "yonhap": "403 Forbidden",
            "edaily": "403 Forbidden",
            "newspim": "403 Forbidden",
            "newsis": "403 Forbidden",
            "hankyung": "403 Forbidden",
            "maeil": "403 Forbidden",
            "seoul": "403 Forbidden",
            "moneytoday": "403 Forbidden",
        }

    def test_rss_feed(self, feed_key: str, test_keyword: str = "삼성전자") -> bool:
        """
        RSS 피드 테스트 (실제 접속 가능한지 확인)

        Args:
            feed_key: rss_feeds의 키 (예: "google_news")
            test_keyword: 테스트용 키워드 (동적 URL용)

        Returns:
            성공 시 True, 실패 시 False
        """
        try:
            feed_info = self.rss_feeds.get(feed_key)
            if not feed_info:
                logger.error(f"❌ 알 수 없는 피드: {feed_key}")
                return False

            # 동적 URL 생성 (Google News 등)
            if feed_info.get("dynamic", False):
                url = feed_info["url_template"].format(keyword=test_keyword)
                logger.info(f"🧪 테스트 시작: {feed_info['name']} (키워드: {test_keyword})")
                logger.info(f"   URL: {url}")
            else:
                url = feed_info["url"]
                logger.info(f"🧪 테스트 시작: {feed_info['name']} ({url})")

            # RSS 피드 다운로드 (User-Agent 추가 - 봇 차단 우회)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10, verify=_should_verify_tls(url))
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)

            # RSS 또는 Atom 포맷 감지
            if root.tag == "rss":
                # RSS 2.0
                items = root.findall(".//item")
                logger.info("✅ RSS 2.0 포맷 감지")
            elif root.tag.endswith("feed"):
                # Atom
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
                logger.info("✅ Atom 포맷 감지")
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
            title_elem = first_item.find("title") or first_item.find("{http://www.w3.org/2005/Atom}title")
            title = title_elem.text if title_elem is not None else "N/A"

            logger.info(f"✅ RSS 피드 작동: {feed_info['name']}")
            logger.info(f"   - 총 기사 수: {entry_count}개")
            logger.info(f"   - 첫 번째 기사: {title[:50]}...")

            # 테스트 완료 표시
            self.rss_feeds[feed_key]["tested"] = True
            return True

        except Exception as e:
            logger.error(f"❌ RSS 테스트 실패 ({feed_key}): {str(e)}")
            return False

    def test_all_feeds(self) -> dict[str, bool]:
        """
        모든 RSS 피드 테스트

        Returns:
            각 피드의 테스트 결과 (True/False)
        """
        results = {}
        for feed_key in self.rss_feeds:
            results[feed_key] = self.test_rss_feed(feed_key)

        # 요약 출력
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        logger.info(f"\n📊 RSS 피드 테스트 결과: {success_count}/{total_count} 성공")

        return results

    def fetch_news_from_feed(self, feed_key: str, keyword: str, days: int = 7) -> list[dict[str, Any]]:
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

            # 동적 URL 생성 (Google News 등)
            if feed_info.get("dynamic", False):
                url = feed_info["url_template"].format(keyword=keyword)
            else:
                url = feed_info["url"]

            # RSS 피드 다운로드 (User-Agent 추가)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10, verify=_should_verify_tls(url))
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)

            # RSS 또는 Atom 포맷 감지
            if root.tag == "rss":
                items = root.findall(".//item")
            elif root.tag.endswith("feed"):
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            else:
                logger.error("❌ 알 수 없는 RSS 포맷")
                return []

            # 날짜 필터링은 추후 pubDate 파싱 개선과 함께 적용 (현재는 미사용)
            _ = days

            news_list = []
            for item in items:
                # 제목 추출
                title_elem = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                title = title_elem.text if title_elem is not None else ""

                # 요약/설명 추출
                desc_elem = (
                    item.find("description")
                    or item.find("summary")
                    or item.find("{http://www.w3.org/2005/Atom}summary")
                )
                description = desc_elem.text if desc_elem is not None else ""

                # 키워드 필터링
                if keyword.lower() not in title.lower() and keyword.lower() not in description.lower():
                    continue

                # URL 추출
                link_elem = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
                if link_elem is not None:
                    if link_elem.text:
                        url = link_elem.text
                    else:
                        url = link_elem.get("href", "")
                else:
                    url = ""

                # 발행일은 추후 pubDate/Atom published 파싱 추가 예정 — 지금은 현재 시간 사용
                published_at = kst_isoformat()

                # 본문 추출
                content = strip_html_tags(description) if description else ""

                news_item = {
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": feed_info["name"],
                    "published_at": published_at,
                    "summary": content[:200] if content else "",
                }

                news_list.append(news_item)

            logger.info(f"✅ {feed_info['name']}: {len(news_list)}개 뉴스 수집 완료")
            return news_list

        except Exception as e:
            logger.error(f"❌ 뉴스 수집 실패 ({feed_key}): {str(e)}")
            return []

    def fetch_all_news(self, keyword: str, days: int = 7, only_tested: bool = True) -> list[dict[str, Any]]:
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
            if only_tested and not feed_info.get("tested", False):
                logger.warning(f"⏭️ 건너뜀 (테스트 안 함): {feed_info['name']}")
                continue

            news_list = self.fetch_news_from_feed(feed_key, keyword, days)
            all_news.extend(news_list)

        # 중복 제거 (URL 기준)
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news["url"] not in seen_urls:
                seen_urls.add(news["url"])
                unique_news.append(news)

        # 최신순 정렬
        unique_news.sort(key=lambda x: x["published_at"], reverse=True)

        logger.info(f"📊 총 {len(unique_news)}개 뉴스 수집 완료 (중복 제거 후)")

        return unique_news


# 테스트 코드
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    client = KoreanNewsRSSClient()

    # Step 1: 모든 RSS 피드 테스트
    print("\n" + "=" * 80)
    print("🧪 Step 1: 모든 RSS 피드 테스트")
    print("=" * 80)
    test_results = client.test_all_feeds()

    # Step 2: 성공한 피드로 실제 뉴스 수집 테스트
    print("\n" + "=" * 80)
    print("📰 Step 2: 실제 뉴스 수집 테스트 (삼성전자)")
    print("=" * 80)
    news_list = client.fetch_all_news(
        keyword="삼성전자",
        days=7,
        only_tested=True,  # 테스트 통과한 피드만 사용
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
