#!/usr/bin/env python3
"""
Paxnet 종목토론 크롤링 클라이언트
한국 투자 커뮤니티 감정 분석을 위한 데이터 수집
"""

import logging
import time
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    import chromedriver_autoinstaller
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium이 설치되지 않았습니다. Paxnet 크롤링을 사용할 수 없습니다.")


class PaxnetCrawlClient:
    """Paxnet 종목토론 크롤링 클라이언트"""

    def __init__(self):
        """클라이언트 초기화"""
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium이 설치되지 않았습니다. pip install selenium chromedriver-autoinstaller webdriver-manager 실행하세요.")

        self.driver = None
        self.base_url = "https://www.paxnet.co.kr"

    def setup_driver(self, headless: bool = True) -> bool:
        """Chrome 드라이버 설정"""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

            try:
                chromedriver_autoinstaller.install()
                self.driver = webdriver.Chrome(options=chrome_options)
            except Exception:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)

            logger.info("Chrome 드라이버 설정 완료")
            return True

        except Exception as e:
            logger.error(f"드라이버 설정 실패: {e}")
            return False

    def fetch_stock_discussions(self, stock_code: str, max_posts: int = 10) -> Dict[str, Any]:
        """
        종목 토론 게시글 수집

        Args:
            stock_code: 종목 코드 (예: '005930')
            max_posts: 최대 게시글 수

        Returns:
            Dict containing posts data or error information
        """
        if not self.driver:
            if not self.setup_driver():
                return {"error": "드라이버 설정에 실패했습니다."}

        url = f"https://www.paxnet.co.kr/tbbs/list?tbbsType=L&id={stock_code}"

        try:
            logger.info(f"Paxnet 종목토론 페이지 접근: {stock_code}")
            self.driver.get(url)
            time.sleep(5)

            # 게시글 수집
            posts = self._extract_posts(stock_code, max_posts)

            if posts:
                logger.info(f"게시글 수집 완료: {len(posts)}개")
                return {
                    "status": "success",
                    "stock_code": stock_code,
                    "source": "Paxnet 종목토론",
                    "url": url,
                    "timestamp": datetime.now().isoformat(),
                    "total_posts": len(posts),
                    "posts": posts
                }
            else:
                return {
                    "error": "게시글을 찾을 수 없습니다.",
                    "stock_code": stock_code,
                    "url": url
                }

        except Exception as e:
            logger.error(f"Paxnet 크롤링 오류: {e}")
            return {"error": f"크롤링 오류: {str(e)}"}

    def _extract_posts(self, stock_code: str, max_posts: int) -> List[Dict[str, Any]]:
        """게시글 목록 추출"""
        posts = []

        try:
            # 여러 시도로 안정적 데이터 수집
            for attempt in range(3):
                try:
                    title_elements = self.driver.find_elements(By.CSS_SELECTOR, "a.best-title")
                    logger.info(f"시도 {attempt + 1}: {len(title_elements)}개 게시글 발견")

                    if len(title_elements) >= max_posts:
                        break

                    time.sleep(2)

                except Exception as e:
                    logger.warning(f"시도 {attempt + 1} 실패: {e}")
                    if attempt < 2:
                        time.sleep(3)
                        continue
                    else:
                        title_elements = []

            # 게시글 정보 수집
            post_info_list = []
            for i, element in enumerate(title_elements[:max_posts]):
                try:
                    title = element.text.strip()
                    href = element.get_attribute("href")

                    # seq 번호 추출
                    seq_match = re.search(r'bbsWrtView\((\d+)\)', href)
                    seq = seq_match.group(1) if seq_match else ""

                    if title and seq:
                        post_info_list.append({
                            "title": title,
                            "seq": seq,
                            "detail_url": f"https://www.paxnet.co.kr/tbbs/view?id={stock_code}&seq={seq}"
                        })

                except Exception as e:
                    logger.warning(f"게시글 {i+1} 정보 추출 오류: {e}")
                    continue

            logger.info(f"수집 예정 게시글: {len(post_info_list)}개")

            # 각 게시글 내용 수집
            for i, post_info in enumerate(post_info_list):
                try:
                    logger.debug(f"게시글 {i+1}/{len(post_info_list)} 처리 중...")

                    content = self._get_post_content(post_info["detail_url"])

                    post_data = {
                        "title": post_info["title"],
                        "content": content,
                        "url": post_info["detail_url"]
                    }

                    posts.append(post_data)

                    # 서버 부하 방지를 위한 딜레이
                    if i < len(post_info_list) - 1:
                        time.sleep(3)

                except Exception as e:
                    logger.warning(f"게시글 {i+1} 내용 수집 오류: {e}")
                    continue

        except Exception as e:
            logger.error(f"게시글 목록 추출 오류: {e}")

        return posts

    def _get_post_content(self, detail_url: str) -> str:
        """개별 게시글 내용 추출"""
        try:
            self.driver.get(detail_url)
            time.sleep(2)

            # 다양한 셀렉터로 내용 추출 시도
            content_selectors = [
                ".view-content",
                ".content",
                ".post-content",
                "[class*='content']",
                ".article-content",
                ".detail-content"
            ]

            for selector in content_selectors:
                try:
                    content_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if content_elements:
                        content = content_elements[0].text.strip()
                        if len(content) > 20:
                            return content[:1000]  # 1000자 제한
                except:
                    continue

            # 기본 body 텍스트 추출
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines = [line.strip() for line in body_text.split('\n')
                    if len(line.strip()) > 10 and
                    not any(skip in line for skip in ['팍스넷', '로그인', '회원가입', '메뉴'])]

            return '\n'.join(lines[:10])[:1000]

        except Exception as e:
            logger.warning(f"내용 추출 실패: {str(e)}")
            return f"내용 추출 실패: {str(e)}"

    def close(self):
        """드라이버 종료"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome 드라이버 종료")
            except Exception as e:
                logger.warning(f"드라이버 종료 중 오류: {e}")

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()


# 편의 함수
def fetch_paxnet_discussions(stock_code: str, max_posts: int = 10) -> Dict[str, Any]:
    """
    Paxnet 종목토론 데이터 수집 편의 함수

    Args:
        stock_code: 종목 코드
        max_posts: 최대 게시글 수

    Returns:
        게시글 데이터 또는 오류 정보
    """
    try:
        with PaxnetCrawlClient() as client:
            return client.fetch_stock_discussions(stock_code, max_posts)
    except Exception as e:
        logger.error(f"Paxnet 데이터 수집 실패: {e}")
        return {"error": f"데이터 수집 실패: {str(e)}"}


# 테스트용 메인 함수
if __name__ == "__main__":
    import json

    # 로깅 설정
    logging.basicConfig(level=logging.INFO)

    # 삼성전자 테스트
    print("=== Paxnet 크롤링 클라이언트 테스트 ===")
    result = fetch_paxnet_discussions("005930", max_posts=5)

    if "error" not in result:
        print(f"✅ 성공: {result['total_posts']}개 게시글 수집")
        for i, post in enumerate(result['posts'][:3], 1):
            print(f"{i}. {post['title'][:50]}...")
    else:
        print(f"❌ 오류: {result['error']}")

    # 결과를 JSON 파일로 저장
    with open("paxnet_test_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("결과가 paxnet_test_result.json에 저장되었습니다.")