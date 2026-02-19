"""
RSS Feed Collector
Collects articles from configured RSS feeds
"""

import feedparser
from typing import List, Dict
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from src.utils.logger import default_logger as logger

class RSSCollector:
    """Collect and parse RSS feeds"""
    
    def __init__(self, feeds: List[Dict[str, str]], keywords: List[str] = None):
        """
        Initialize RSS collector
        
        Args:
            feeds: List of feed dictionaries with 'name', 'url', and 'category'
            keywords: Optional list of keywords to filter articles
        """
        self.feeds = feeds
        self.keywords = keywords or []
        
    def collect_recent_articles(self, days: int = 7) -> List[Dict]:
        """
        Collect articles from the last N days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of article dictionaries
        """
        articles = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        logger.info(f"Collecting articles from {len(self.feeds)} RSS feeds")
        
        for feed_info in self.feeds:
            try:
                feed = feedparser.parse(feed_info['url'])
                logger.info(f"Processing feed: {feed_info['name']} ({len(feed.entries)} entries)")
                
                for entry in feed.entries:
                    # Parse publish date
                    published = self._parse_date(entry)
                    
                    # Filter by date
                    if published and published < cutoff_date:
                        continue
                    
                    # Extract article content
                    article = {
                        'title': entry.get('title', ''),
                        'url': entry.get('link', ''),
                        'published': published,
                        'summary': self._clean_html(entry.get('summary', '')),
                        'content': self._extract_content(entry),
                        'source': feed_info['name'],
                        'category': feed_info.get('category', 'general'),
                    }
                    
                    # Filter by keywords if specified
                    if self._matches_keywords(article):
                        articles.append(article)
                        
            except Exception as e:
                logger.error(f"Error processing feed {feed_info['name']}: {str(e)}")
        
        logger.info(f"Collected {len(articles)} articles")
        return articles
    
    def _parse_date(self, entry) -> datetime:
        """Parse entry publish date"""
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6])
        return datetime.now()
    
    def _clean_html(self, html: str) -> str:
        """Remove HTML tags from text"""
        if not html:
            return ""
        soup = BeautifulSoup(html, 'html.parser')
        return soup.get_text(strip=True)
    
    def _extract_content(self, entry) -> str:
        """Extract full content from entry"""
        # Try content field first
        if hasattr(entry, 'content') and entry.content:
            return self._clean_html(entry.content[0].value)
        # Fall back to summary
        elif hasattr(entry, 'summary'):
            return self._clean_html(entry.summary)
        return ""
    
    def _matches_keywords(self, article: Dict) -> bool:
        """Check if article matches any keywords"""
        if not self.keywords:
            return True
        
        text = f"{article['title']} {article['summary']} {article['content']}".lower()
        return any(keyword.lower() in text for keyword in self.keywords)

# Example usage
if __name__ == "__main__":
    # Test with sample feeds
    test_feeds = [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "tech"}
    ]
    
    collector = RSSCollector(test_feeds, keywords=["AI", "market"])
    articles = collector.collect_recent_articles(days=1)
    
    print(f"Found {len(articles)} articles")
    for article in articles[:3]:
        print(f"\n- {article['title']}")
        print(f"  Source: {article['source']}")
        print(f"  Published: {article['published']}")
