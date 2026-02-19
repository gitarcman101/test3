"""
Claude AI Summarizer
Uses Claude API to generate summaries and insights
"""

from anthropic import Anthropic
from typing import Dict, List
from src.utils.logger import default_logger as logger

class ClaudeSummarizer:
    """Generate AI-powered summaries using Claude"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Claude summarizer
        
        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        
    def summarize_article(
        self, 
        article: Dict, 
        prompt_template: str,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> Dict:
        """
        Summarize a single article
        
        Args:
            article: Article dictionary with 'title', 'content', etc.
            prompt_template: Prompt template with {article_content} placeholder
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            
        Returns:
            Dictionary with 'summary' and 'insights'
        """
        try:
            # Prepare article content
            article_content = f"""
제목: {article['title']}
출처: {article['source']}
내용: {article['content'][:3000]}  # Limit to 3000 chars
"""
            
            # Format prompt
            prompt = prompt_template.format(article_content=article_content)
            
            # Call Claude API
            logger.info(f"Summarizing article: {article['title'][:50]}...")
            
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary = message.content[0].text
            
            return {
                'original_url': article['url'],
                'original_title': article['title'],
                'source': article['source'],
                'category': article.get('category', 'general'),
                'summary': summary,
                'generated_at': article.get('published'),
            }
            
        except Exception as e:
            logger.error(f"Error summarizing article: {str(e)}")
            return {
                'original_url': article['url'],
                'original_title': article['title'],
                'summary': f"요약 생성 실패: {str(e)}",
                'error': str(e)
            }
    
    def summarize_batch(
        self, 
        articles: List[Dict], 
        prompt_template: str,
        max_articles: int = 10
    ) -> List[Dict]:
        """
        Summarize multiple articles
        
        Args:
            articles: List of article dictionaries
            prompt_template: Prompt template
            max_articles: Maximum number of articles to process
            
        Returns:
            List of summary dictionaries
        """
        summaries = []
        
        for i, article in enumerate(articles[:max_articles]):
            logger.info(f"Processing article {i+1}/{min(len(articles), max_articles)}")
            summary = self.summarize_article(article, prompt_template)
            summaries.append(summary)
        
        logger.info(f"Completed summarization of {len(summaries)} articles")
        return summaries
    
    def generate_insights(
        self,
        summaries: List[Dict],
        num_insights: int = 3
    ) -> List[str]:
        """
        Generate top insights from summaries
        
        Args:
            summaries: List of article summaries
            num_insights: Number of insights to generate
            
        Returns:
            List of insight strings
        """
        try:
            # Combine all summaries
            combined = "\n\n".join([
                f"[{s['source']}] {s['original_title']}\n{s['summary']}"
                for s in summaries
            ])
            
            prompt = f"""
다음은 최근 글로벌 비즈니스 뉴스 요약들입니다.

{combined}

위 뉴스들을 분석하여 B2B 전략기획팀이 알아야 할 핵심 인사이트 {num_insights}가지를 추출해주세요.

각 인사이트는:
- 제목 (한 줄)
- 설명 (2-3문장)
- 비즈니스 시사점

형식으로 작성해주세요.
"""
            
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            insights_text = message.content[0].text
            return [insights_text]  # Can be parsed into structured format
            
        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return []

# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv("config/.env")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if api_key:
        summarizer = ClaudeSummarizer(api_key)
        
        # Test article
        test_article = {
            'title': 'AI Transforms Global Markets',
            'source': 'TechCrunch',
            'content': 'Artificial intelligence is reshaping how businesses operate...',
            'url': 'https://example.com/article'
        }
        
        prompt = "다음 기사를 간단히 요약해주세요:\n\n{article_content}"
        result = summarizer.summarize_article(test_article, prompt)
        
        print("Summary:", result['summary'])
