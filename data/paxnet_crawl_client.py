#!/usr/bin/env python3
"""
Paxnet 종목토론 크롤링 클라이언트
한국 투자 커뮤니티 감정 분석을 위한 데이터 수집
"""

import logging
import time
import re
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 🔧 전역 드라이버 관리를 위한 락
_driver_lock = threading.Lock()
_active_drivers = set()
_max_concurrent_drivers = 2  # 최대 동시 실행 드라이버 수

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
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
        """Chrome 드라이버 설정 - 동시 실행 제한"""
        global _driver_lock, _active_drivers, _max_concurrent_drivers

        with _driver_lock:
            # 이미 최대 드라이버 수에 도달한 경우 대기 또는 실패
            if len(_active_drivers) >= _max_concurrent_drivers:
                logger.warning(f"최대 드라이버 수({_max_concurrent_drivers})에 도달. 크롤링 대기 중...")
                return False

        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless=new")  # New headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)

            # 실제 브라우저처럼 보이도록 User-Agent 설정
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            # 🚀 빠른 로딩을 위한 최적화 옵션 (JavaScript는 필수 - AJAX 콘텐츠 로딩)
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--disable-features=TranslateUI")
            chrome_options.add_argument("--disable-ipc-flooding-protection")
            chrome_options.add_argument("--disable-images")  # 이미지 로딩 비활성화
            # JavaScript는 활성화 필요 - Paxnet은 AJAX로 게시글 로딩
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 이미지 완전 차단

            try:
                chromedriver_autoinstaller.install()
                self.driver = webdriver.Chrome(options=chrome_options)
            except Exception:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)

            # 🚀 Paxnet AJAX 콘텐츠 로딩을 위한 타임아웃 설정
            self.driver.implicitly_wait(10)  # 10초 implicit wait (AJAX 대기)
            self.driver.set_page_load_timeout(30)  # 30초 페이지 로드 timeout
            self.driver.set_script_timeout(20)  # 20초 스크립트 timeout (AJAX 실행)

            # 🔧 활성 드라이버 목록에 추가
            with _driver_lock:
                _active_drivers.add(id(self.driver))

            logger.info("Chrome 드라이버 설정 완료")
            return True

        except Exception as e:
            logger.error(f"드라이버 설정 실패: {e}")
            return False

    def fetch_stock_discussions(self, stock_code: str, max_posts: int = 10, fetch_content: bool = False) -> Dict[str, Any]:
        """
        종목 토론 게시글 수집

        Args:
            stock_code: 종목 코드 (예: '005930')
            max_posts: 최대 게시글 수
            fetch_content: 개별 게시글 내용 수집 여부 (False면 제목만, 빠름)

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

            # AJAX 콘텐츠 로딩 대기 - 명시적 대기 사용
            try:
                wait = WebDriverWait(self.driver, 15)
                # .best-title 또는 .board-col 요소가 로드될 때까지 대기
                wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".best-title, .board-col"))
                )
                logger.info("AJAX 콘텐츠 로딩 완료")
                time.sleep(2)  # 추가 안정화 대기
            except Exception as e:
                logger.warning(f"AJAX 대기 중 경고: {e}, 계속 진행...")
                time.sleep(5)  # Fallback 대기

            # 게시글 수집
            posts = self._extract_posts(stock_code, max_posts, fetch_content)

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

    def _extract_posts(self, stock_code: str, max_posts: int, fetch_content: bool = False) -> List[Dict[str, Any]]:
        """게시글 목록 추출"""
        posts = []

        try:
            # 여러 CSS 선택자로 안정적 데이터 수집
            title_elements = []
            selectors_to_try = [
                "a.best-title",  # 베스트 게시글
                "p.tit a",  # 일반 게시글 제목
                ".board-col a[href*='bbsWrtView']",  # 게시글 링크
                ".tit a"  # 제목 링크
            ]

            for attempt in range(3):
                try:
                    for selector in selectors_to_try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and len(elements) > len(title_elements):
                            title_elements = elements
                            logger.info(f"시도 {attempt + 1}, 선택자 '{selector}': {len(title_elements)}개 게시글 발견")

                    if len(title_elements) >= max_posts:
                        break

                    if attempt < 2:
                        time.sleep(2)

                except Exception as e:
                    logger.warning(f"시도 {attempt + 1} 실패: {e}")
                    if attempt < 2:
                        time.sleep(3)
                        continue

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
                    # fetch_content=True인 경우에만 개별 페이지 접근
                    if fetch_content:
                        logger.debug(f"게시글 {i+1}/{len(post_info_list)} 내용 수집 중...")
                        content = self._get_post_content(post_info["detail_url"])
                    else:
                        # 제목만 사용 (빠른 수집)
                        content = post_info["title"]  # 감정 분석은 제목만으로도 가능

                    post_data = {
                        "title": post_info["title"],
                        "content": content,
                        "url": post_info["detail_url"]
                    }

                    posts.append(post_data)

                    # 서버 부하 방지를 위한 짧은 딜레이 (내용 수집시만)
                    if fetch_content and i < len(post_info_list) - 1:
                        time.sleep(1)

                except Exception as e:
                    logger.warning(f"내용 추출 실패: {e}")
                    # Timeout 발생시 제목만으로 데이터 생성 (fallback)
                    post_data = {
                        "title": post_info["title"],
                        "content": post_info["title"],  # 제목을 내용으로 대체
                        "url": post_info["detail_url"]
                    }
                    posts.append(post_data)
                    continue

        except Exception as e:
            logger.error(f"게시글 목록 추출 오류: {e}")

        return posts

    def _get_post_content(self, detail_url: str) -> str:
        """개별 게시글 내용 추출"""
        try:
            # 15초 타임아웃으로 빠른 페이지 로드 (AJAX는 이미 로드됨)
            self.driver.set_page_load_timeout(15)
            self.driver.get(detail_url)

            # AJAX 콘텐츠 대기
            try:
                wait = WebDriverWait(self.driver, 5)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".view-content, .content, body")))
            except:
                pass

            time.sleep(1)  # 안정화 대기 감소

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
            error_msg = str(e)
            if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                logger.warning(f"Timeout으로 인한 내용 추출 실패: {error_msg}")
                return "[Timeout으로 내용 추출 실패 - 제목 기반 분석 진행]"
            else:
                logger.warning(f"내용 추출 실패: {error_msg}")
                return f"[내용 추출 실패: {error_msg}]"

    def close(self):
        """드라이버 종료"""
        if self.driver:
            try:
                driver_id = id(self.driver)
                self.driver.quit()

                # 🔧 활성 드라이버 목록에서 제거
                with _driver_lock:
                    _active_drivers.discard(driver_id)

                logger.info("Chrome 드라이버 종료")
            except Exception as e:
                logger.warning(f"드라이버 종료 중 오류: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()


# 편의 함수
def fetch_paxnet_discussions(stock_code: str, max_posts: int = 10, fetch_content: bool = False) -> Dict[str, Any]:
    """
    Paxnet 종목토론 데이터 수집 편의 함수

    Args:
        stock_code: 종목 코드
        max_posts: 최대 게시글 수
        fetch_content: 개별 게시글 내용 수집 여부 (기본값 False - 제목만, 빠름)

    Returns:
        게시글 데이터 또는 오류 정보
    """
    try:
        with PaxnetCrawlClient() as client:
            # 🔧 드라이버 생성 실패시 즉시 fallback 반환
            if not client.setup_driver():
                logger.warning("Paxnet 크롤링 드라이버 생성 실패 - 리소스 부족")
                return {
                    "error": "시스템 리소스 부족으로 크롤링 대기 중",
                    "posts": [],
                    "post_count": 0,
                    "data_source": "Paxnet (실패)",
                    "last_updated": datetime.now().isoformat()
                }

            return client.fetch_stock_discussions(stock_code, max_posts, fetch_content)
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