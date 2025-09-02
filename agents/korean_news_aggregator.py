import logging
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
import re
import asyncio

from config.settings import settings

logger = logging.getLogger(__name__)

class KoreanNewsAggregator:
    """한국 뉴스 공식 API 통합 수집기 - 신뢰할 수 있는 소스만 사용"""
    
    def __init__(self):
        self.logger = logger
        
        # 네이버 API 설정 (공식 API)
        self.naver_client_id = settings.naver_client_id
        self.naver_client_secret = settings.naver_client_secret
        self.use_naver_api = self.naver_client_id and self.naver_client_secret
        
        # HashScraper API 설정 (공식 소셜미디어 API)
        self.hashscraper_api_key = getattr(settings, 'hashscraper_api_key', None)
        self.use_hashscraper_api = bool(self.hashscraper_api_key)
        
        # 공통 헤더
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def search_naver_news_api(self, query: str, display: int = 20) -> List[Dict[str, Any]]:
        """네이버 뉴스 검색 API - 공식 소스"""
        if not self.use_naver_api:
            self.logger.warning("Naver API credentials not configured")
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
                'sort': 'date'
            }
            
            response = requests.get(api_url, headers=api_headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            news_items = data.get('items', [])
            
            processed_news = []
            for item in news_items:
                # HTML 태그 제거
                title = re.sub('<[^<]+?>', '', item.get('title', ''))
                description = re.sub('<[^<]+?>', '', item.get('description', ''))
                
                processed_news.append({
                    'title': title,
                    'link': item.get('originallink', item.get('link', '')),
                    'description': description,
                    'pubDate': item.get('pubDate', ''),
                    'source': 'Naver API',
                    'content': description,
                    'category': 'official_news_api'
                })
            
            self.logger.info(f"Naver API collected {len(processed_news)} articles for '{query}'")
            return processed_news
            
        except Exception as e:
            self.logger.error(f"Error in Naver API search: {str(e)}")
            return []
    
    async def collect_social_media_mentions(self, keyword: str) -> List[Dict[str, Any]]:
        """소셜미디어 언급 수집 - HashScraper API 공식 소스만 사용"""
        if not self.use_hashscraper_api:
            self.logger.warning("HashScraper API key not configured")
            return []
            
        try:
            social_mentions = []
            
            # Twitter 검색 API 호출
            twitter_data = await self._scrape_twitter_hashscraper(keyword)
            social_mentions.extend(twitter_data)
            
            # Instagram 검색 API 호출
            instagram_data = await self._scrape_instagram_hashscraper(keyword)
            social_mentions.extend(instagram_data)
            
            self.logger.info(f"HashScraper collected {len(social_mentions)} social media mentions for '{keyword}'")
            return social_mentions
            
        except Exception as e:
            self.logger.error(f"Error in social media collection: {str(e)}")
            return []
    
    async def _scrape_twitter_hashscraper(self, keyword: str) -> List[Dict[str, Any]]:
        """HashScraper Twitter API 호출"""
        try:
            api_url = "https://api.hashscraper.com/twitter/search"
            
            headers = {
                'Authorization': f'Bearer {self.hashscraper_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'query': f"{keyword} lang:ko",
                'count': 20,
                'result_type': 'recent'
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                tweets = data.get('data', {}).get('tweets', [])
                
                processed_tweets = []
                for tweet in tweets:
                    text = tweet.get('text', '')
                    processed_tweets.append({
                        'title': f"트위터 - {tweet.get('user', {}).get('name', 'Unknown')}",
                        'link': f"https://twitter.com/status/{tweet.get('id', '')}",
                        'description': text[:200] + "..." if len(text) > 200 else text,
                        'pubDate': tweet.get('created_at', ''),
                        'source': 'Twitter (HashScraper)',
                        'content': text,
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
    
    async def _scrape_instagram_hashscraper(self, keyword: str) -> List[Dict[str, Any]]:
        """HashScraper Instagram API 호출"""
        try:
            api_url = "https://api.hashscraper.com/instagram/hashtag"
            
            headers = {
                'Authorization': f'Bearer {self.hashscraper_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'hashtag': keyword.replace(' ', ''),
                'count': 10
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                posts = data.get('data', {}).get('posts', [])
                
                processed_posts = []
                for post in posts:
                    caption = post.get('caption', '') or ''
                    processed_posts.append({
                        'title': f"인스타그램 - {post.get('user', {}).get('username', 'Unknown')}",
                        'link': f"https://instagram.com/p/{post.get('shortcode', '')}",
                        'description': caption[:200] + "..." if len(caption) > 200 else caption,
                        'pubDate': datetime.fromtimestamp(post.get('taken_at_timestamp', 0)).isoformat() if post.get('taken_at_timestamp') else '',
                        'source': 'Instagram (HashScraper)',
                        'content': caption,
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
    
    async def aggregate_all_sources(self, keyword: str, company_name: str = None) -> Dict[str, Any]:
        """모든 공식 소스에서 뉴스 통합 수집 - 신뢰할 수 있는 API만 사용"""
        try:
            self.logger.info(f"Starting official API news aggregation for '{keyword}'")
            
            all_news = []
            collection_stats = {
                'naver_api': 0,
                'social_media': 0,
                'total': 0
            }
            
            # 1. 네이버 API 뉴스 (공식 소스)
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
            
            # 2. 소셜미디어 언급 (HashScraper API)
            if self.use_hashscraper_api:
                social_news = await self.collect_social_media_mentions(keyword)
                all_news.extend(social_news)
                collection_stats['social_media'] = len(social_news)
            
            # 중복 제거 (제목 기준)
            unique_news = self._remove_duplicates(all_news)
            collection_stats['total'] = len(unique_news)
            
            # 최신순 정렬
            unique_news = self._sort_by_date(unique_news)
            
            self.logger.info(f"Official API aggregation complete: {collection_stats}")
            
            return {
                "keyword": keyword,
                "company_name": company_name,
                "news_count": len(unique_news),
                "news_data": unique_news[:50],  # 상위 50개만
                "collection_stats": collection_stats,
                "aggregation_timestamp": datetime.now().isoformat(),
                "sources": self._get_active_sources()
            }
            
        except Exception as e:
            self.logger.error(f"Error in official API aggregation: {str(e)}")
            return {
                "keyword": keyword, 
                "error": str(e),
                "news_count": 0,
                "collection_stats": {"error": True}
            }
    
    def _remove_duplicates(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """중복 뉴스 제거 (제목 기준)"""
        seen_titles = set()
        unique_news = []
        
        for news in news_list:
            title = news.get('title', '').strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        return unique_news
    
    def _sort_by_date(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """날짜순 정렬 (최신순)"""
        try:
            return sorted(news_list, key=lambda x: x.get('pubDate', ''), reverse=True)
        except Exception as e:
            self.logger.warning(f"Date sorting failed: {str(e)}")
            return news_list
    
    def _get_active_sources(self) -> List[str]:
        """활성화된 데이터 소스 목록 반환"""
        sources = []
        if self.use_naver_api:
            sources.append("Naver API")
        if self.use_hashscraper_api:
            sources.append("HashScraper API")
        return sources if sources else ["No API configured"]

# 전역 인스턴스
korean_news_aggregator = KoreanNewsAggregator()