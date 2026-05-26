"""
DCInside Stock Gallery Crawler
디시인사이드 주식 갤러리 크롤링

🆕 P2-1-C: 커뮤니티 차별화 전략 (Option C)
- 실제 투자자 의견 수집
- 로그인 불필요 공개 게시판
- BeautifulSoup + requests 기반
"""

import logging
import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from utils.time import kst_isoformat

logger = logging.getLogger(__name__)


class DCInsideCrawler:
    """디시인사이드 주식 갤러리 크롤러"""

    def __init__(self):
        """크롤러 초기화"""
        self.base_url = "https://gall.dcinside.com"
        self.gallery_id = "stock"  # 주식 갤러리

        # User-Agent (봇 차단 우회)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/",
        }

    def test_connection(self) -> bool:
        """
        디시인사이드 접속 테스트

        Returns:
            성공 시 True, 실패 시 False
        """
        try:
            url = f"{self.base_url}/board/lists/?id={self.gallery_id}"
            logger.info(f"🧪 디시인사이드 접속 테스트: {url}")

            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            # HTML 파싱 테스트
            soup = BeautifulSoup(response.content, "html.parser")

            # 갤러리 제목 확인
            title_elem = soup.find("div", class_="box_head")
            if title_elem:
                logger.info("✅ 디시인사이드 접속 성공!")
                logger.info(f"   - 페이지 크기: {len(response.content)} bytes")
                return True
            else:
                logger.warning("⚠️ 페이지 구조가 예상과 다름")
                return False

        except Exception as e:
            logger.error(f"❌ 디시인사이드 접속 실패: {str(e)}")
            return False

    def crawl_posts(self, stock_code: str, keyword: str, pages: int = 3) -> list[dict[str, Any]]:
        """
        주식 갤러리에서 특정 키워드 포함 게시글 수집

        Args:
            stock_code: 종목 코드 (예: "005930")
            keyword: 검색 키워드 (예: "삼성전자")
            pages: 크롤링할 페이지 수 (default: 3)

        Returns:
            게시글 리스트
        """
        try:
            logger.info(f"📰 디시인사이드 크롤링 시작 (키워드: {keyword}, 페이지: {pages})")

            all_posts = []

            for page in range(1, pages + 1):
                logger.info(f"   - {page}/{pages} 페이지 크롤링 중...")

                # URL 생성 (검색 쿼리 포함)
                url = f"{self.base_url}/board/lists/"
                params = {
                    "id": self.gallery_id,
                    "s_type": "search_subject_memo",  # 제목+내용 검색
                    "s_keyword": keyword,
                    "page": page,
                }

                # 요청
                response = requests.get(url, params=params, headers=self.headers, timeout=10)
                response.raise_for_status()

                # HTML 파싱
                soup = BeautifulSoup(response.content, "html.parser")

                # 게시글 목록 추출 (실제 HTML 구조 확인 필요)
                posts = self._parse_posts(soup, keyword)
                all_posts.extend(posts)

                # 예의 있게 크롤링 (1초 대기)
                time.sleep(1)

            logger.info(f"✅ 디시인사이드: {len(all_posts)}개 게시글 수집 완료")
            return all_posts

        except Exception as e:
            logger.error(f"❌ 디시인사이드 크롤링 실패: {str(e)}")
            return []

    def _parse_posts(self, soup: BeautifulSoup, keyword: str) -> list[dict[str, Any]]:
        """
        HTML에서 게시글 파싱

        Args:
            soup: BeautifulSoup 객체
            keyword: 검색 키워드

        Returns:
            게시글 리스트
        """
        posts = []

        try:
            # 디시인사이드 게시글 목록 선택자 (실제 테스트 필요)
            # Note: 실제 HTML 구조 확인 후 수정 필요
            post_list = soup.find("tbody", class_="list")

            if not post_list:
                logger.warning("⚠️ 게시글 목록을 찾을 수 없음 (HTML 구조 확인 필요)")
                return []

            for row in post_list.find_all("tr", class_=["ub-content", "us-post"]):
                try:
                    # 제목 추출
                    title_elem = row.find("td", class_="gall_tit")
                    if not title_elem:
                        continue

                    title_link = title_elem.find("a")
                    if not title_link:
                        continue

                    title = title_link.get_text(strip=True)
                    post_url = self.base_url + title_link.get("href", "")

                    # 작성자 추출
                    author_elem = row.find("td", class_="gall_writer")
                    author = author_elem.get_text(strip=True) if author_elem else "Unknown"

                    # 날짜 추출
                    date_elem = row.find("td", class_="gall_date")
                    date_str = date_elem.get_text(strip=True) if date_elem else ""

                    # 조회수 추출
                    view_elem = row.find("td", class_="gall_count")
                    views = view_elem.get_text(strip=True) if view_elem else "0"

                    # 추천수 추출
                    recommend_elem = row.find("td", class_="gall_recommend")
                    recommends = recommend_elem.get_text(strip=True) if recommend_elem else "0"

                    post_item = {
                        "title": title,
                        "url": post_url,
                        "author": author,
                        "posted_at": self._parse_date(date_str),
                        "views": self._parse_number(views),
                        "recommends": self._parse_number(recommends),
                        "source": "디시인사이드 주식 갤러리",
                        "content": "",  # 본문은 별도 크롤링 필요
                    }

                    posts.append(post_item)

                except Exception as e:
                    logger.debug(f"게시글 파싱 에러: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"HTML 파싱 에러: {str(e)}")

        return posts

    def _parse_date(self, date_str: str) -> str:
        """
        날짜 문자열 파싱

        Args:
            date_str: 날짜 문자열 (예: "2025.11.17", "11:30")

        Returns:
            ISO 형식 날짜
        """
        try:
            # "11:30" 형식 (오늘)
            if ":" in date_str:
                now = datetime.now()
                return f"{now.year}-{now.month:02d}-{now.day:02d}T{date_str}:00"

            # "2025.11.17" 형식
            if "." in date_str:
                parts = date_str.split(".")
                if len(parts) == 3:
                    return f"{parts[0]}-{parts[1]}-{parts[2]}T00:00:00"

            return kst_isoformat()

        except Exception as e:
            logger.debug(f"날짜 파싱 실패 ({date_str!r}): {e}")
            return kst_isoformat()

    def _parse_number(self, num_str: str) -> int:
        """
        숫자 문자열 파싱

        Args:
            num_str: 숫자 문자열 (예: "123", "1.2k")

        Returns:
            정수
        """
        try:
            # "1.2k" → 1200
            if "k" in num_str.lower():
                return int(float(num_str.lower().replace("k", "")) * 1000)

            # 쉼표 제거
            return int(num_str.replace(",", ""))

        except (ValueError, AttributeError) as e:
            logger.debug(f"숫자 파싱 실패 ({num_str!r}): {e}")
            return 0


# 테스트 코드
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    crawler = DCInsideCrawler()

    # Step 1: 접속 테스트
    print("\n" + "=" * 80)
    print("🧪 Step 1: 디시인사이드 접속 테스트")
    print("=" * 80)
    success = crawler.test_connection()

    if success:
        # Step 2: 실제 크롤링 테스트
        print("\n" + "=" * 80)
        print("📰 Step 2: 실제 게시글 크롤링 테스트 (삼성전자)")
        print("=" * 80)
        posts = crawler.crawl_posts(
            stock_code="005930",
            keyword="삼성전자",
            pages=1,  # 1페이지만 테스트
        )

        print(f"\n✅ 총 {len(posts)}개 게시글 수집 완료")
        if posts:
            print("\n📄 첫 3개 게시글 샘플:")
            for i, post in enumerate(posts[:3], 1):
                print(f"\n[{i}] {post['title'][:50]}...")
                print(f"    URL: {post['url']}")
                print(f"    작성자: {post['author']}")
                print(f"    날짜: {post['posted_at']}")
                print(f"    조회수: {post['views']} / 추천: {post['recommends']}")
    else:
        print("\n❌ 접속 테스트 실패. HTML 구조 확인 필요.")
