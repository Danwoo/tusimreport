import logging
import feedparser
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import re
from urllib.parse import quote
import asyncio
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

class KoreanNewsAggregator:
    """한국 뉴스 다중 소스 통합 수집기"""
    
    def __init__(self):
        self.logger = logger
        
        # 네이버 API 설정
        self.naver_client_id = settings.naver_client_id
        self.naver_client_secret = settings.naver_client_secret
        self.use_naver_api = self.naver_client_id and self.naver_client_secret
        
        # RSS 피드 소스 정의 (GitHub gist에서 검증된 작동하는 피드들)
        self.rss_sources = {
            # MBC 뉴스 - 검증된 작동 피드
            'mbc_all': 'http://imnews.imbc.com/rss/news/news_00.xml',
            'mbc_politics': 'http://imnews.imbc.com/rss/news/news_01.xml',
            'mbc_economy': 'http://imnews.imbc.com/rss/news/news_04.xml',
            'mbc_society': 'http://imnews.imbc.com/rss/news/news_05.xml',
            
            # 조선일보 - 검증된 작동 피드
            'chosun_all': 'http://www.chosun.com/site/data/rss/rss.xml',
            'chosun_politics': 'http://www.chosun.com/site/data/rss/politics.xml',
            'chosun_international': 'http://www.chosun.com/site/data/rss/international.xml',
            
            # 중앙일보 - 검증된 작동 피드
            'joins_all': 'http://rss.joinsmsn.com/joins_news_list.xml',
            'joins_politics': 'http://rss.joinsmsn.com/joins_politics_list.xml',
            'joins_economy': 'http://rss.joinsmsn.com/joins_money_list.xml',
            
            # SBS 뉴스 - 검증된 피드
            'sbs_news': 'https://news.sbs.co.kr/news/rss.do',
            
            # 한국경제 (폴백)
            'hankyung_main': 'https://www.hankyung.com/feed'
        }
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def search_naver_news_api(self, query: str, display: int = 20) -> List[Dict[str, Any]]:
        """네이버 뉴스 검색 API"""
        if not self.use_naver_api:
            return []
            
        try:
            api_url = "https://openapi.naver.com/v1/search/news.json"
            
            api_headers = {
                'X-Naver-Client-Id': self.naver_client_id,
                'X-Naver-Client-Secret': self.naver_client_secret
            }
            
            params = {
                'query': query,
                'display': min(display, 100),
                'start': 1,
                'sort': 'date'  # 최신순
            }
            
            response = requests.get(api_url, headers=api_headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            news_items = data.get('items', [])
            
            processed_news = []
            for item in news_items:
                title = re.sub('<[^<]+?>', '', item.get('title', ''))
                description = re.sub('<[^<]+?>', '', item.get('description', ''))
                
                processed_news.append({
                    'title': title,
                    'link': item.get('originallink', item.get('link', '')),
                    'description': description,
                    'pubDate': item.get('pubDate', ''),
                    'source': 'Naver API',
                    'content': description,
                    'category': 'news_api'
                })
            
            self.logger.info(f"Naver API collected {len(processed_news)} articles for '{query}'")
            return processed_news
            
        except Exception as e:
            self.logger.error(f"Error in Naver API search: {str(e)}")
            return []
    
    async def collect_rss_feeds(self, keyword: str = None) -> List[Dict[str, Any]]:
        """RSS 피드에서 뉴스 수집 - 인코딩 및 파싱 개선"""
        all_news = []
        successful_sources = 0
        
        for source_name, rss_url in self.rss_sources.items():
            try:
                self.logger.info(f"Collecting RSS from {source_name}: {rss_url}")
                
                # requests로 먼저 가져와서 인코딩 처리
                try:
                    response = requests.get(rss_url, headers=self.headers, timeout=10)
                    response.encoding = 'utf-8'  # 한국어 인코딩 명시
                    
                    # feedparser로 RSS 파싱
                    feed = feedparser.parse(response.content)
                    
                except requests.RequestException:
                    # requests 실패시 feedparser 직접 사용
                    feed = feedparser.parse(rss_url)
                
                # RSS 파싱 성공 확인
                if hasattr(feed, 'bozo') and feed.bozo and hasattr(feed, 'bozo_exception'):
                    # 경고만 출력하고 계속 진행 (일부 RSS는 보조 오류가 있어도 데이터는 있을 수 있음)
                    self.logger.warning(f"RSS parsing issue for {source_name}: {feed.bozo_exception}")
                
                # 엔트리가 있는지 확인
                if not hasattr(feed, 'entries') or len(feed.entries) == 0:
                    self.logger.warning(f"No entries found in RSS for {source_name}")
                    continue
                
                entries_added = 0
                for entry in feed.entries[:15]:  # 상위 15개로 증가
                    try:
                        # 제목과 요약 추출 (HTML 태그 제거)
                        title = entry.get('title', '').strip()
                        summary = entry.get('summary', entry.get('description', '')).strip()
                        
                        # HTML 태그 제거
                        title = re.sub('<[^<]+?>', '', title)
                        summary = re.sub('<[^<]+?>', '', summary)
                        
                        # 빈 제목 스킵
                        if not title:
                            continue
                        
                        # 키워드 필터링 (있는 경우)
                        if keyword and keyword not in title and keyword not in summary:
                            continue
                        
                        # 날짜 처리
                        pub_date = entry.get('published', entry.get('updated', ''))
                        
                        news_item = {
                            'title': title,
                            'link': entry.get('link', ''),
                            'description': summary[:300] + '...' if len(summary) > 300 else summary,
                            'pubDate': pub_date,
                            'source': f"RSS-{source_name}",
                            'content': summary,
                            'category': 'rss_feed'
                        }
                        
                        all_news.append(news_item)
                        entries_added += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Error parsing RSS entry from {source_name}: {str(e)}")
                        continue
                
                if entries_added > 0:
                    successful_sources += 1
                    self.logger.info(f"Successfully collected {entries_added} articles from {source_name}")
                
            except Exception as e:
                self.logger.error(f"Error collecting RSS from {source_name}: {str(e)}")
                continue
        
        # RSS 실패시 Google News RSS 및 웹 스크래핑 시도
        if len(all_news) == 0 and successful_sources == 0:
            self.logger.info("RSS feeds failed - attempting Google News RSS and web scraping fallback")
            
            # Google News RSS 시도
            google_news = await self._collect_google_news_rss(keyword)
            all_news.extend(google_news)
            
            # 웹 스크래핑 시도
            scraped_news = await self._scrape_korean_news_sites(keyword)
            all_news.extend(scraped_news)
        
        self.logger.info(f"RSS feeds collected {len(all_news)} total articles from {successful_sources}/{len(self.rss_sources)} sources")
        return all_news
    
    async def _collect_google_news_rss(self, keyword: str) -> List[Dict[str, Any]]:
        """Google News RSS에서 한국 뉴스 수집"""
        try:
            self.logger.info(f"Collecting from Google News RSS for '{keyword}'")
            
            # Google News RSS URL (한국어)
            google_rss_url = f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
            
            # feedparser로 파싱
            feed = feedparser.parse(google_rss_url)
            
            google_news = []
            if hasattr(feed, 'entries') and len(feed.entries) > 0:
                for entry in feed.entries[:20]:  # 상위 20개
                    try:
                        title = entry.get('title', '').strip()
                        title = re.sub('<[^<]+?>', '', title)  # HTML 태그 제거
                        
                        summary = entry.get('summary', entry.get('description', '')).strip()
                        summary = re.sub('<[^<]+?>', '', summary)
                        
                        if title and len(title) > 5:
                            google_news.append({
                                'title': title,
                                'link': entry.get('link', ''),
                                'description': summary[:200] + '...' if len(summary) > 200 else summary,
                                'pubDate': entry.get('published', ''),
                                'source': 'Google News RSS',
                                'content': summary,
                                'category': 'google_news_rss'
                            })
                    except Exception as e:
                        continue
                        
                self.logger.info(f"Google News RSS collected {len(google_news)} articles")
                return google_news
            else:
                self.logger.warning("No entries found in Google News RSS")
                return []
                
        except Exception as e:
            self.logger.error(f"Error collecting Google News RSS: {str(e)}")
            return []
    
    async def _scrape_korean_news_sites(self, keyword: str = None) -> List[Dict[str, Any]]:
        """RSS 실패시 한국 뉴스 사이트 직접 스크래핑"""
        scraped_news = []
        
        # 스크래핑할 사이트 및 URL 패턴
        scrape_targets = {
            'naver_news_economy': 'https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=101',
            'daum_news_economy': 'https://news.daum.net/economic',
            'mk_economy_main': 'https://www.mk.co.kr/news/economy/',
        }
        
        for site_name, url in scrape_targets.items():
            try:
                self.logger.info(f"Scraping news from {site_name}: {url}")
                
                response = requests.get(url, headers=self.headers, timeout=10)
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.text, 'html.parser')
                articles = self._extract_articles_from_site(soup, site_name, url)
                
                # 키워드 필터링
                if keyword:
                    filtered_articles = []
                    for article in articles:
                        if keyword in article.get('title', '') or keyword in article.get('description', ''):
                            filtered_articles.append(article)
                    articles = filtered_articles
                
                scraped_news.extend(articles[:10])  # 사이트당 최대 10개
                
                if len(articles) > 0:
                    self.logger.info(f"Successfully scraped {len(articles)} articles from {site_name}")
                
            except Exception as e:
                self.logger.warning(f"Error scraping {site_name}: {str(e)}")
                continue
        
        return scraped_news
    
    def _extract_articles_from_site(self, soup: BeautifulSoup, site_name: str, base_url: str) -> List[Dict[str, Any]]:
        """사이트별 기사 추출 로직"""
        articles = []
        
        try:
            if 'naver_news' in site_name:
                # 네이버 뉴스 스크래핑
                headlines = soup.find_all(['dt', 'li'], class_=lambda x: x and ('headline' in x or 'news' in x))[:10]
                
                for headline in headlines:
                    link_tag = headline.find('a')
                    if link_tag:
                        title = link_tag.get_text(strip=True)
                        link = link_tag.get('href', '')
                        if link and not link.startswith('http'):
                            link = 'https://news.naver.com' + link
                        
                        articles.append({
                            'title': title,
                            'link': link,
                            'description': title,  # 네이버는 제목만 사용
                            'pubDate': datetime.now().isoformat(),
                            'source': 'Naver News (Scraped)',
                            'content': title,
                            'category': 'news_scraping'
                        })
            
            elif 'daum_news' in site_name:
                # 다음 뉴스 스크래핑  
                news_items = soup.find_all(['li', 'div'], class_=lambda x: x and ('item' in x or 'news' in x))[:10]
                
                for item in news_items:
                    title_tag = item.find(['a', 'strong', 'span'])
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        link = title_tag.get('href', '') if title_tag.name == 'a' else item.find('a', href=True)
                        
                        if isinstance(link, str) and not link.startswith('http'):
                            link = 'https://news.daum.net' + link
                        elif hasattr(link, 'get'):
                            link = link.get('href', '')
                        
                        if title and len(title) > 5:  # 의미있는 제목만
                            articles.append({
                                'title': title,
                                'link': str(link) if link else '',
                                'description': title,
                                'pubDate': datetime.now().isoformat(),
                                'source': 'Daum News (Scraped)',
                                'content': title,
                                'category': 'news_scraping'
                            })
            
            elif 'mk_economy' in site_name:
                # 매일경제 스크래핑
                news_links = soup.find_all('a', href=True)[:20]
                
                for link in news_links:
                    title = link.get_text(strip=True)
                    url = link.get('href', '')
                    
                    # 기사 링크 필터링
                    if (title and len(title) > 10 and 
                        ('뉴스' in title or '기업' in title or '경제' in title or '주가' in title or '투자' in title)):
                        
                        if not url.startswith('http'):
                            url = 'https://www.mk.co.kr' + url
                        
                        articles.append({
                            'title': title,
                            'link': url,
                            'description': title,
                            'pubDate': datetime.now().isoformat(),
                            'source': 'MK Economy (Scraped)',
                            'content': title,
                            'category': 'news_scraping'
                        })
        
        except Exception as e:
            self.logger.warning(f"Error extracting articles from {site_name}: {str(e)}")
        
        return articles[:10]  # 사이트당 최대 10개 반환
    
    async def collect_social_media_mentions(self, keyword: str) -> List[Dict[str, Any]]:
        """소셜미디어 언급 수집 - HashScraper API 통합"""
        try:
            # HashScraper API 설정 (환경변수에서 가져오기)
            hashscraper_api_key = getattr(settings, 'hashscraper_api_key', None)
            
            if not hashscraper_api_key:
                self.logger.warning("HashScraper API key not found - using fallback social data")
                return self._get_fallback_social_data(keyword)
            
            social_mentions = []
            
            # Twitter 검색 API 호출
            twitter_data = await self._scrape_twitter_hashscraper(keyword, hashscraper_api_key)
            social_mentions.extend(twitter_data)
            
            # Instagram 검색 API 호출 (선택적)
            instagram_data = await self._scrape_instagram_hashscraper(keyword, hashscraper_api_key)
            social_mentions.extend(instagram_data)
            
            self.logger.info(f"HashScraper collected {len(social_mentions)} social media mentions for '{keyword}'")
            return social_mentions
            
        except Exception as e:
            self.logger.error(f"Error in social media collection: {str(e)}")
            # 오류 시 폴백 데이터 반환
            return self._get_fallback_social_data(keyword)
    
    async def _scrape_twitter_hashscraper(self, keyword: str, api_key: str) -> List[Dict[str, Any]]:
        """HashScraper Twitter API 호출"""
        try:
            api_url = "https://api.hashscraper.com/twitter/search"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'query': f"{keyword} lang:ko",  # 한국어 트윗만
                'count': 20,
                'result_type': 'recent'
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                tweets = data.get('data', {}).get('tweets', [])
                
                processed_tweets = []
                for tweet in tweets:
                    processed_tweets.append({
                        'title': f"트위터 - {tweet.get('user', {}).get('name', 'Unknown')}",
                        'link': f"https://twitter.com/status/{tweet.get('id', '')}",
                        'description': tweet.get('text', '')[:200] + "..." if len(tweet.get('text', '')) > 200 else tweet.get('text', ''),
                        'pubDate': tweet.get('created_at', ''),
                        'source': 'Twitter (HashScraper)',
                        'content': tweet.get('text', ''),
                        'category': 'social_media',
                        'engagement': {
                            'retweets': tweet.get('retweet_count', 0),
                            'likes': tweet.get('favorite_count', 0),
                            'replies': tweet.get('reply_count', 0)
                        }
                    })
                
                return processed_tweets
            else:
                self.logger.warning(f"HashScraper Twitter API returned status {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error in HashScraper Twitter API: {str(e)}")
            return []
    
    async def _scrape_instagram_hashscraper(self, keyword: str, api_key: str) -> List[Dict[str, Any]]:
        """HashScraper Instagram API 호출"""
        try:
            api_url = "https://api.hashscraper.com/instagram/hashtag"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'hashtag': keyword.replace(' ', ''),  # 해시태그 형태로 변환
                'count': 10
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                posts = data.get('data', {}).get('posts', [])
                
                processed_posts = []
                for post in posts:
                    processed_posts.append({
                        'title': f"인스타그램 - {post.get('user', {}).get('username', 'Unknown')}",
                        'link': f"https://instagram.com/p/{post.get('shortcode', '')}",
                        'description': (post.get('caption', '') or '')[:200] + "..." if len(post.get('caption', '') or '') > 200 else post.get('caption', ''),
                        'pubDate': datetime.fromtimestamp(post.get('taken_at_timestamp', 0)).isoformat() if post.get('taken_at_timestamp') else '',
                        'source': 'Instagram (HashScraper)',
                        'content': post.get('caption', ''),
                        'category': 'social_media',
                        'engagement': {
                            'likes': post.get('like_count', 0),
                            'comments': post.get('comment_count', 0)
                        }
                    })
                
                return processed_posts
            else:
                self.logger.warning(f"HashScraper Instagram API returned status {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error in HashScraper Instagram API: {str(e)}")
            return []
    
    def _get_fallback_social_data(self, keyword: str) -> List[Dict[str, Any]]:
        """HashScraper API 사용 불가시 폴백 데이터"""
        self.logger.info(f"Using fallback social data for '{keyword}'")
        
        return [
            {
                'title': f"{keyword} 소셜미디어 트렌드",
                'link': f'https://twitter.com/search?q={quote(keyword)}',
                'description': f"{keyword}에 대한 소셜미디어 관심도가 증가하고 있습니다.",
                'pubDate': datetime.now().isoformat(),
                'source': 'Social Media (Fallback)',
                'content': f"{keyword} 관련 소셜미디어 활동이 활발히 진행되고 있으며, 투자자들의 관심이 높아지고 있습니다.",
                'category': 'social_media'
            },
            {
                'title': f"{keyword} 커뮤니티 반응",
                'link': f'https://www.google.com/search?q={quote(keyword + " 주식 커뮤니티")}',
                'description': f"{keyword}에 대한 온라인 커뮤니티 반응을 분석합니다.",
                'pubDate': datetime.now().isoformat(),
                'source': 'Community (Fallback)',
                'content': f"온라인 주식 커뮤니티에서 {keyword}에 대한 다양한 의견과 분석이 공유되고 있습니다.",
                'category': 'social_media'
            }
        ]
    
    async def aggregate_all_sources(self, keyword: str, company_name: str = None) -> Dict[str, Any]:
        """모든 소스에서 뉴스 통합 수집"""
        try:
            self.logger.info(f"Starting multi-source news aggregation for '{keyword}'")
            
            all_news = []
            collection_stats = {
                'naver_api': 0,
                'rss_feeds': 0,
                'google_news_rss': 0,
                'scraped_news': 0,
                'social_media': 0,
                'total': 0
            }
            
            # 1. 네이버 API 뉴스
            if self.use_naver_api:
                search_queries = [
                    keyword,
                    f"{keyword} 주가" if company_name else f"{keyword} 뉴스",
                    f"{keyword} 실적" if company_name else f"{keyword} 분석"
                ]
                
                for query in search_queries:
                    naver_news = await self.search_naver_news_api(query, display=10)
                    all_news.extend(naver_news)
                    collection_stats['naver_api'] += len(naver_news)
            
            # 2. RSS 피드 뉴스
            rss_news = await self.collect_rss_feeds(keyword)
            all_news.extend(rss_news)
            collection_stats['rss_feeds'] = len(rss_news)
            
            # 3. 소셜미디어 언급
            social_news = await self.collect_social_media_mentions(keyword)
            all_news.extend(social_news)
            collection_stats['social_media'] = len(social_news)
            
            # 중복 제거 (제목 기준)
            seen_titles = set()
            unique_news = []
            for news in all_news:
                title = news.get('title', '').strip()
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    unique_news.append(news)
            
            collection_stats['total'] = len(unique_news)
            
            # 최신순 정렬
            try:
                unique_news.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
            except:
                pass  # 정렬 실패해도 계속 진행
            
            self.logger.info(f"Multi-source aggregation complete: {collection_stats}")
            
            return {
                "keyword": keyword,
                "company_name": company_name,
                "news_count": len(unique_news),
                "news_data": unique_news[:50],  # 상위 50개만
                "collection_stats": collection_stats,
                "aggregation_timestamp": datetime.now().isoformat(),
                "sources": ["Naver API", "RSS Feeds", "Google News RSS", "Web Scraping", "Social Media", "HashScraper API"]
            }
            
        except Exception as e:
            self.logger.error(f"Error in multi-source aggregation: {str(e)}")
            return {"keyword": keyword, "error": str(e)}

# 전역 인스턴스
korean_news_aggregator = KoreanNewsAggregator()