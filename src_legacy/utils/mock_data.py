"""
Mock Data Generator
Generates realistic test data for development without API keys
"""

from datetime import datetime, timedelta
import random
from typing import List, Dict

class MockDataGenerator:
    """Generate mock data for testing"""
    
    MOCK_ARTICLES = [
        {
            "title": "Tesla Opens First Gigafactory in Southeast Asia",
            "source": "TechCrunch",
            "category": "tech",
            "content": """
Tesla announced the opening of its first Gigafactory in Southeast Asia, located in Indonesia.
The facility will produce batteries and electric vehicles for the Asian market, with initial
capacity of 500,000 vehicles per year. This strategic move positions Tesla to compete more
effectively with Chinese EV manufacturers in the region. Industry analysts expect this to
significantly reduce production costs and delivery times for Asian customers.
""",
            "summary": """
**핵심 요약:**
테슬라가 동남아시아 첫 기가팩토리를 인도네시아에 개소했습니다. 연간 50만 대 생산 능력을 갖추고 아시아 시장 공략을 본격화합니다.

**비즈니스 시사점:**
- 중국 EV 제조사와의 경쟁 심화
- 생산 비용 절감 및 배송 시간 단축
- 아시아 시장에서의 입지 강화

**전략적 의미:**
글로벌 기업들의 아시아 생산 거점 확대 트렌드를 보여주는 사례. 현지화 전략의 중요성 재확인.
""",
        },
        {
            "title": "EU Announces Stricter AI Regulation Framework",
            "source": "Reuters",
            "category": "regulation",
            "content": """
The European Union unveiled comprehensive AI regulations that will require companies to
disclose AI training data sources and implement strict safety measures. The new framework
classifies AI systems by risk level and imposes penalties up to 6% of global revenue for
violations. Tech giants like Google and Microsoft will need to adjust their AI products
to comply with these regulations by Q4 2026.
""",
            "summary": """
**핵심 요약:**
EU가 포괄적 AI 규제 프레임워크를 발표했습니다. AI 학습 데이터 공개 의무화와 리스크 기반 분류 체계를 도입하며, 위반 시 전 세계 매출의 6%까지 제재 가능합니다.

**비즈니스 시사점:**
- 글로벌 테크 기업들의 제품 조정 필요
- 2026년 4분기까지 컴플라이언스 확보 필수
- AI 개발 비용 증가 예상

**전략적 의미:**
규제 환경 변화에 대응하는 글로벌 전략 수립이 필수. 컴플라이언스를 경쟁 우위로 전환하는 기업이 승자가 될 것.
""",
        },
        {
            "title": "Microsoft Announces $10B Investment in African Cloud Infrastructure",
            "source": "Bloomberg",
            "category": "business",
            "content": """
Microsoft revealed plans to invest $10 billion in cloud infrastructure across Africa over
the next five years. The initiative includes building data centers in Nigeria, South Africa,
and Kenya, along with training programs for 100,000 cloud professionals. This represents
the largest tech infrastructure investment in the continent's history and signals growing
importance of African markets for global tech companies.
""",
            "summary": """
**핵심 요약:**
마이크로소프트가 향후 5년간 아프리카 클라우드 인프라에 100억 달러 투자를 발표했습니다. 나이지리아, 남아공, 케냐에 데이터센터 구축 예정입니다.

**비즈니스 시사점:**
- 아프리카 시장의 잠재력 인정
- 10만 명 클라우드 전문가 양성 계획
- 글로벌 테크 기업들의 신흥 시장 공략 가속화

**전략적 의미:**
신흥 시장에 대한 장기 투자 전략의 중요성. 단순 판매가 아닌 생태계 구축을 통한 시장 선점 전략.
""",
        },
        {
            "title": "Samsung Launches Revolutionary Solid-State Battery Technology",
            "source": "The Verge",
            "category": "tech",
            "content": """
Samsung has successfully commercialized solid-state battery technology that offers 3x longer
lifespan and 2x faster charging compared to traditional lithium-ion batteries. The company
plans to begin mass production by 2027, initially targeting premium electric vehicles and
then expanding to consumer electronics. This breakthrough could reshape the entire battery
industry and accelerate EV adoption globally.
""",
            "summary": """
**핵심 요약:**
삼성이 전고체 배터리 기술 상용화에 성공했습니다. 기존 리튬이온 대비 3배 긴 수명, 2배 빠른 충전 속도를 자랑하며 2027년 양산 예정입니다.

**비즈니스 시사점:**
- 배터리 산업 전체의 패러다임 전환 예고
- 프리미엄 전기차 시장 먼저 공략
- 글로벌 EV 채택 가속화

**전략적 의미:**
기술 혁신이 시장 판도를 바꾸는 사례. 후발 주자도 혁신 기술로 시장 리더십 확보 가능.
""",
        },
        {
            "title": "Global Supply Chain Disruption Eases as Shipping Costs Drop 40%",
            "source": "Financial Times",
            "category": "business",
            "content": """
International shipping costs have decreased by 40% from their 2025 peak as global supply
chain bottlenecks continue to ease. Container availability has improved significantly, and
port congestion has reduced by 60% compared to last year. Analysts predict continued
normalization through 2026, benefiting retailers and manufacturers worldwide.
""",
            "summary": """
**핵심 요약:**
글로벌 공급망 혼란이 완화되며 해운 비용이 2025년 대비 40% 하락했습니다. 컨테이너 가용성 개선과 항만 혼잡도 60% 감소했습니다.

**비즈니스 시사점:**
- 소매업체 및 제조사들의 마진 개선 기대
- 2026년까지 지속적 정상화 전망
- 재고 관리 전략 재조정 필요

**전략적 의미:**
공급망 안정화에 따른 운영 전략 최적화 기회. 비용 절감분을 가격 경쟁력 강화에 활용할 시점.
""",
        },
    ]
    
    @staticmethod
    def generate_articles(num_articles: int = 5) -> List[Dict]:
        """
        Generate mock articles
        
        Args:
            num_articles: Number of articles to generate
            
        Returns:
            List of mock article dictionaries
        """
        articles = []
        available_articles = MockDataGenerator.MOCK_ARTICLES[:num_articles]
        
        for i, article_template in enumerate(available_articles):
            article = {
                'title': article_template['title'],
                'url': f"https://example.com/article/{i+1}",
                'published': datetime.now() - timedelta(days=random.randint(0, 6)),
                'summary': article_template['content'].strip(),
                'content': article_template['content'].strip(),
                'source': article_template['source'],
                'category': article_template['category'],
            }
            articles.append(article)
        
        return articles
    
    @staticmethod
    def generate_summaries(articles: List[Dict]) -> List[Dict]:
        """
        Generate mock AI summaries for articles
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            List of summary dictionaries
        """
        summaries = []
        
        for i, article in enumerate(articles):
            # Find matching mock article
            mock_article = next(
                (a for a in MockDataGenerator.MOCK_ARTICLES if a['title'] == article['title']),
                MockDataGenerator.MOCK_ARTICLES[0]
            )
            
            summary = {
                'original_url': article['url'],
                'original_title': article['title'],
                'source': article['source'],
                'category': article['category'],
                'summary': mock_article['summary'].strip(),
                'generated_at': article['published'],
            }
            summaries.append(summary)
        
        return summaries
    
    @staticmethod
    def generate_newsletter_data() -> Dict:
        """
        Generate complete newsletter data
        
        Returns:
            Dictionary with newsletter content
        """
        articles = MockDataGenerator.generate_articles(5)
        summaries = MockDataGenerator.generate_summaries(articles)
        
        return {
            'newsletter_title': 'DETA Intelligence Brief',
            'tagline': '1분 안에 읽는 글로벌 시장 인텔리전스',
            'reading_time': '1',
            'main_issue_title': summaries[0]['original_title'],
            'main_issue_content': summaries[0]['summary'],
            'main_issue_source': summaries[0]['source'],
            'insights': [
                {
                    'title': summaries[i]['original_title'],
                    'content': summaries[i]['summary'],
                    'source': summaries[i]['source'],
                }
                for i in range(1, min(3, len(summaries)))
            ],
            'sample_report_url': 'https://deta.kr/sample-report',
            'consultation_url': 'https://deta.kr/consultation',
            'unsubscribe_url': 'https://deta.kr/unsubscribe',
            'manage_preferences_url': 'https://deta.kr/preferences',
        }

# Example usage
if __name__ == "__main__":
    # Generate mock articles
    articles = MockDataGenerator.generate_articles(5)
    print(f"Generated {len(articles)} mock articles")
    
    for article in articles:
        print(f"\n- {article['title']}")
        print(f"  Source: {article['source']}")
        print(f"  Category: {article['category']}")
    
    # Generate summaries
    summaries = MockDataGenerator.generate_summaries(articles)
    print(f"\n\nGenerated {len(summaries)} summaries")
    
    # Generate newsletter
    newsletter = MockDataGenerator.generate_newsletter_data()
    print(f"\n\nNewsletter: {newsletter['newsletter_title']}")
    print(f"Main issue: {newsletter['main_issue_title']}")
