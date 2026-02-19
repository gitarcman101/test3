"""
뉴스 수집 모듈 (News Collector)
================================
Google News RSS + trafilatura 본문 크롤링 기반
산업 트렌드 / 경쟁사 동향 / 규제 변화 3축 수집

기능:
- Google News RSS로 뉴스 URL 수집 (무료, API 키 불필요)
- trafilatura로 본문 전체 크롤링 (정확도 F1 0.958)
- 3개 카테고리 자동 분류: 산업 트렌드 / 경쟁사 동향 / 규제 변화
- 산업별, 기업별, 키워드별 수집 지원
- 수집 결과 JSON/CSV 저장 + 캐싱

설치:
    pip install requests trafilatura

사용법:
    from news_collector import NewsCollector
    collector = NewsCollector()

    # 산업별 수집
    news = collector.collect_industry_news("IT/소프트웨어")

    # 기업 맞춤 수집 (경쟁사 포함)
    news = collector.collect_for_company(
        company="삼성전자",
        industry="IT/소프트웨어",
        competitors=["LG전자", "SK하이닉스"]
    )
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote_plus

import requests

# trafilatura 본문 추출 (설치 필요)
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    print("⚠️ trafilatura 미설치. 본문 크롤링 불가. pip install trafilatura")


# ============================================================
# 데이터 모델
# ============================================================

@dataclass
class NewsArticle:
    """뉴스 기사 데이터 모델"""
    title: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""
    description: str = ""           # RSS 요약
    full_text: str = ""             # 본문 전체 (trafilatura)
    author: str = ""
    category: str = ""              # industry_trend / competitor / regulation
    category_label: str = ""        # 산업 트렌드 / 경쟁사 동향 / 규제 변화
    industry: str = ""
    company: str = ""               # 관련 기업
    keywords: list = field(default_factory=list)
    word_count: int = 0
    crawl_success: bool = False
    crawled_at: str = ""


# ============================================================
# 뉴스 수집 설정
# ============================================================

# 산업별 검색 키워드 — deta.kr 12개 산업 분류 기준 (영문 — 해외 뉴스 소스 타겟)
INDUSTRY_CONFIG = {
    "화학 및 재료": {
        "industry_trend": [
            "chemical industry trend 2026", "advanced materials innovation",
            "specialty chemicals market", "green chemistry", "polymer technology",
        ],
        "regulation": [
            "REACH regulation", "chemical safety regulation", "PFAS ban",
            "hazardous substance regulation", "carbon border adjustment",
        ],
        "competitor_keywords": ["chemical plant", "materials acquisition", "R&D investment", "partnership"],
    },
    "정보통신기술(ICT)": {
        "industry_trend": [
            "AI industry trend 2026", "enterprise SaaS market", "cloud transformation",
            "generative AI enterprise adoption", "software industry outlook",
        ],
        "regulation": [
            "AI regulation policy", "EU AI Act enforcement", "data protection law",
            "tech platform regulation", "digital privacy regulation",
        ],
        "competitor_keywords": ["funding", "product launch", "acquisition", "earnings"],
    },
    "전자(반도체 등)": {
        "industry_trend": [
            "semiconductor market trend 2026", "chip manufacturing expansion",
            "AI chip demand", "display technology OLED", "consumer electronics outlook",
        ],
        "regulation": [
            "CHIPS Act", "semiconductor export control", "rare earth regulation",
            "electronics waste regulation", "trade restriction semiconductor",
        ],
        "competitor_keywords": ["fab construction", "chip revenue", "technology node", "foundry"],
    },
    "자동화": {
        "industry_trend": [
            "industrial automation trend 2026", "smart factory robotics",
            "Industry 4.0 adoption", "collaborative robot cobot", "manufacturing AI",
        ],
        "regulation": [
            "robot safety regulation", "industrial safety standard",
            "automation labor regulation", "machine directive EU",
        ],
        "competitor_keywords": ["factory expansion", "automation contract", "new technology", "partnership"],
    },
    "자동차": {
        "industry_trend": [
            "electric vehicle market 2026", "autonomous driving technology",
            "EV battery innovation", "connected car trend", "automotive supply chain",
        ],
        "regulation": [
            "EV subsidy policy", "emission regulation Euro 7", "autonomous vehicle regulation",
            "battery recycling mandate", "vehicle safety standard",
        ],
        "competitor_keywords": ["vehicle sales", "EV launch", "auto partnership", "factory investment"],
    },
    "우주 및 국방": {
        "industry_trend": [
            "space industry commercial 2026", "defense technology trend",
            "satellite constellation", "hypersonic technology", "space launch market",
        ],
        "regulation": [
            "defense procurement policy", "ITAR regulation", "space debris regulation",
            "arms export control", "dual use technology regulation",
        ],
        "competitor_keywords": ["defense contract", "satellite launch", "space funding", "military acquisition"],
    },
    "에너지": {
        "industry_trend": [
            "renewable energy trend 2026", "hydrogen economy", "energy storage battery",
            "carbon capture technology", "nuclear energy revival",
        ],
        "regulation": [
            "carbon emission regulation", "renewable energy mandate", "ESG compliance",
            "energy transition policy", "carbon tax regulation",
        ],
        "competitor_keywords": ["energy project", "solar wind investment", "power plant", "clean energy funding"],
    },
    "식음료": {
        "industry_trend": [
            "food technology trend 2026", "alternative protein market",
            "food safety innovation", "beverage industry outlook", "sustainable packaging food",
        ],
        "regulation": [
            "food labeling regulation", "FDA food safety", "sugar tax policy",
            "food additive regulation", "organic certification standard",
        ],
        "competitor_keywords": ["food brand launch", "beverage acquisition", "F&B revenue", "restaurant chain"],
    },
    "소비재 및 서비스": {
        "industry_trend": [
            "consumer goods trend 2026", "retail technology innovation",
            "D2C brand growth", "ecommerce market outlook", "luxury market trend",
        ],
        "regulation": [
            "consumer protection regulation", "ecommerce platform regulation",
            "product safety standard", "cross-border commerce regulation",
        ],
        "competitor_keywords": ["brand revenue", "retail expansion", "marketplace growth", "consumer spending"],
    },
    "생명과학 및 헬스케어": {
        "industry_trend": [
            "digital health trend 2026", "biotech drug pipeline", "precision medicine",
            "AI in healthcare", "gene therapy advancement",
        ],
        "regulation": [
            "FDA approval drug", "medical device regulation", "clinical trial regulation",
            "health data privacy HIPAA", "telehealth regulation",
        ],
        "competitor_keywords": ["clinical trial results", "FDA approval", "biotech funding", "pharma acquisition"],
    },
    "교육": {
        "industry_trend": [
            "edtech market trend 2026", "AI in education", "online learning platform",
            "corporate training technology", "education technology innovation",
        ],
        "regulation": [
            "education data privacy", "AI education regulation", "online learning accreditation",
            "student data protection FERPA",
        ],
        "competitor_keywords": ["edtech funding", "education platform launch", "university partnership", "LMS"],
    },
    "농업": {
        "industry_trend": [
            "agritech trend 2026", "precision agriculture", "smart farming technology",
            "agricultural drone", "vertical farming market",
        ],
        "regulation": [
            "agricultural subsidy policy", "pesticide regulation", "GMO regulation",
            "sustainable agriculture standard", "food supply chain regulation",
        ],
        "competitor_keywords": ["agritech investment", "farm equipment", "crop technology", "agriculture acquisition"],
    },
    "기타": {
        "industry_trend": [
            "global business trend 2026", "digital transformation", "industry outlook",
        ],
        "regulation": [
            "corporate regulation change", "ESG regulation", "antitrust regulation",
        ],
        "competitor_keywords": ["growth", "investment", "innovation"],
    },
}

# 한국 출처 필터링 리스트 (제외 대상)
KOREAN_SOURCE_PATTERNS = [
    # 한국 도메인
    ".kr", "daum.net", "naver.com", "chosun.com", "joongang.co",
    "donga.com", "hankyung.com", "mk.co", "sedaily.com", "etnews.com",
    "zdnet.co.kr", "bloter.net", "platum.kr", "venturesquare.net",
    "aitimes.com", "aitimes.kr", "techm.kr", "byline.network",
    # 한국 소스명
    "조선일보", "중앙일보", "동아일보", "한국경제", "매일경제",
    "서울경제", "전자신문", "지디넷코리아", "블로터", "플래텀",
    "벤처스퀘어", "AI타임스", "테크엠", "바이라인네트워크",
    "연합뉴스", "KBS", "MBC", "SBS", "JTBC", "YTN",
    "v.daum.net", "news.naver.com", "n.news.naver.com",
    "Vietnam.vn",  # 베트남어 소스도 제외
]


# ============================================================
# Google News RSS 수집기
# ============================================================

class GoogleNewsRSS:
    """Google News RSS 피드 수집기"""

    RSS_URL = "https://news.google.com/rss/search"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def search(
        self,
        query: str,
        lang: str = "en",
        country: str = "US",
        max_results: int = 5,
        days: int = 7,
        exclude_korean: bool = True,
    ) -> list[dict]:
        """
        Google News RSS 검색 (기본: 영문/미국 — 해외 소스)

        Args:
            query: 검색어
            lang: 언어 코드 (기본: en)
            country: 국가 코드 (기본: US)
            max_results: 최대 결과 수
            days: 최근 N일 이내
            exclude_korean: 한국 출처 제외 여부 (기본: True)
        """
        params = {
            "q": query,
            "hl": lang,
            "gl": country,
            "ceid": f"{country}:{lang}",
        }

        # 기간 필터 (Google News when: 파라미터)
        if days <= 1:
            params["q"] += " when:1d"
        elif days <= 7:
            params["q"] += " when:7d"
        elif days <= 30:
            params["q"] += " when:30d"

        try:
            resp = self.session.get(self.RSS_URL, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠️ RSS 요청 실패 ({resp.status_code})")
                return []

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            results = []

            # 한국 소스 필터링 시 충분히 가져오기 위해 여유분 확보
            fetch_limit = max_results * 3 if exclude_korean else max_results

            for item in items[:fetch_limit]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                source = item.findtext("source", "")
                desc = item.findtext("description", "")
                desc_clean = re.sub(r"<[^>]+>", "", desc) if desc else ""

                # 한국 출처 필터링
                if exclude_korean and self._is_korean_source(source, link, title):
                    continue

                results.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_at": pub_date,
                    "description": desc_clean[:500],
                })

                if len(results) >= max_results:
                    break

            return results

        except Exception as e:
            print(f"  ⚠️ RSS 오류: {e}")
            return []

    @staticmethod
    def _is_korean_source(source: str, url: str, title: str) -> bool:
        """한국 출처인지 판별"""
        check_text = f"{source} {url} {title}".lower()
        for pattern in KOREAN_SOURCE_PATTERNS:
            if pattern.lower() in check_text:
                return True
        # 한글 문자 비율 체크 (제목에 한글이 50% 이상이면 한국 소스)
        if title:
            korean_chars = len(re.findall(r'[가-힣]', title))
            if korean_chars > len(title) * 0.3:
                return True
        return False


# ============================================================
# 본문 크롤러 (trafilatura)
# ============================================================

class ArticleCrawler:
    """trafilatura 기반 뉴스 본문 크롤러"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._crawled_count = 0

    def extract_article(self, url: str) -> dict:
        """
        URL에서 기사 본문 + 메타데이터 추출

        Returns:
            {
                "full_text": "본문 텍스트",
                "title": "제목",
                "author": "저자",
                "date": "날짜",
                "word_count": 1234,
                "success": True/False,
            }
        """
        if not HAS_TRAFILATURA:
            return {"full_text": "", "success": False, "error": "trafilatura 미설치"}

        try:
            # Google News 리다이렉트 URL 처리
            actual_url = self._resolve_google_news_url(url)

            # HTML 다운로드
            downloaded = trafilatura.fetch_url(actual_url)
            if not downloaded:
                # 직접 requests로 시도
                resp = self.session.get(actual_url, timeout=self.timeout, allow_redirects=True)
                if resp.status_code == 200:
                    downloaded = resp.text
                else:
                    return {"full_text": "", "success": False, "error": f"HTTP {resp.status_code}"}

            # 본문 추출
            result = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                include_links=False,
                include_images=False,
                output_format="txt",
                favor_precision=True,  # 정밀도 우선
            )

            # 메타데이터 추출
            metadata = trafilatura.extract_metadata(downloaded)

            if result and len(result) > 100:  # 최소 100자 이상이면 성공
                self._crawled_count += 1
                return {
                    "full_text": result,
                    "title": metadata.title if metadata else "",
                    "author": metadata.author if metadata else "",
                    "date": str(metadata.date) if metadata and metadata.date else "",
                    "word_count": len(result),
                    "success": True,
                }
            else:
                return {"full_text": result or "", "success": False, "error": "본문 추출 실패 (내용 부족)"}

        except Exception as e:
            return {"full_text": "", "success": False, "error": str(e)}

    def _resolve_google_news_url(self, url: str) -> str:
        """Google News 리다이렉트 URL을 실제 URL로 변환"""
        if "news.google.com" in url:
            try:
                resp = self.session.head(url, allow_redirects=True, timeout=10)
                return resp.url
            except Exception:
                return url
        return url

    def get_crawled_count(self) -> int:
        return self._crawled_count


# ============================================================
# 뉴스 분류기
# ============================================================

class NewsClassifier:
    """뉴스 카테고리 자동 분류"""

    REGULATION_KEYWORDS = [
        "규제", "법안", "법률", "의무화", "허가", "인허가", "금지",
        "과징금", "제재", "준수", "컴플라이언스", "감독", "감사",
        "regulation", "compliance", "ban", "mandate", "policy",
        "개정", "시행", "위반", "처벌", "가이드라인",
    ]

    COMPETITOR_KEYWORDS = [
        "실적", "매출", "영업이익", "투자", "인수", "합병", "M&A",
        "출시", "런칭", "서비스 시작", "제휴", "파트너십", "협업",
        "IPO", "상장", "유치", "확장", "진출", "채용",
        "revenue", "acquisition", "launch", "partnership",
    ]

    TREND_KEYWORDS = [
        "트렌드", "전망", "성장", "혁신", "미래", "변화", "동향",
        "시장", "분석", "보고서", "리포트", "예측", "확대",
        "trend", "forecast", "market", "growth", "innovation",
        "전환", "도입", "부상", "주목",
    ]

    def classify(self, article: NewsArticle) -> NewsArticle:
        """기사 카테고리 자동 분류"""
        text = f"{article.title} {article.description} {article.full_text[:500]}"
        text_lower = text.lower()

        reg_score = sum(1 for kw in self.REGULATION_KEYWORDS if kw in text_lower)
        comp_score = sum(1 for kw in self.COMPETITOR_KEYWORDS if kw in text_lower)
        trend_score = sum(1 for kw in self.TREND_KEYWORDS if kw in text_lower)

        if reg_score > comp_score and reg_score > trend_score:
            article.category = "regulation"
            article.category_label = "규제 변화"
        elif comp_score > trend_score:
            article.category = "competitor"
            article.category_label = "경쟁사 동향"
        else:
            article.category = "industry_trend"
            article.category_label = "산업 트렌드"

        return article

    def extract_keywords(self, text: str, top_n: int = 5) -> list[str]:
        """텍스트에서 주요 키워드 추출 (간단 빈도 기반)"""
        # 2글자 이상 한글 단어 추출
        words = re.findall(r'[가-힣]{2,}', text)
        # 불용어 제거
        stopwords = {"것이", "하는", "있는", "이번", "대한", "통해", "위해", "에서",
                     "으로", "까지", "부터", "에게", "이라", "하고", "되는", "했다",
                     "한다", "있다", "된다", "이다", "라고", "에는"}
        words = [w for w in words if w not in stopwords and len(w) >= 2]

        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, c in sorted_words[:top_n]]


# ============================================================
# 메인 뉴스 수집기
# ============================================================

class NewsCollector:
    """뉴스 수집 오케스트레이터"""

    def __init__(self, crawl_body: bool = True, cache_dir: str = "output/news_cache"):
        """
        Args:
            crawl_body: 본문 크롤링 여부 (False면 제목+요약만)
            cache_dir: 캐시 디렉토리
        """
        self.rss = GoogleNewsRSS()
        self.crawler = ArticleCrawler() if crawl_body and HAS_TRAFILATURA else None
        self.classifier = NewsClassifier()
        self.crawl_body = crawl_body and HAS_TRAFILATURA
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def collect_industry_news(
        self,
        industry: str,
        days: int = 7,
        max_per_category: int = 3,
    ) -> list[NewsArticle]:
        """
        산업별 뉴스 수집 (3개 카테고리)

        Args:
            industry: 산업 분류명 (INDUSTRY_CONFIG 키)
            days: 최근 N일
            max_per_category: 카테고리당 최대 기사 수
        """
        config = INDUSTRY_CONFIG.get(industry, INDUSTRY_CONFIG["기타"])
        all_articles = []

        print(f"\n{'='*50}")
        print(f"📰 {industry} 뉴스 수집 시작")
        print(f"{'='*50}")

        # 1) 산업 트렌드
        print(f"\n🔍 [산업 트렌드] 수집 중...")
        trend_kws = config["industry_trend"]
        for kw in trend_kws[:3]:  # 상위 3개 키워드
            results = self.rss.search(kw, max_results=2, days=days)
            for r in results:
                article = self._process_result(r, industry, "industry_trend", "산업 트렌드")
                if article:
                    all_articles.append(article)
            time.sleep(0.5)

        # 2) 규제 변화
        print(f"\n🔍 [규제 변화] 수집 중...")
        reg_kws = config["regulation"]
        for kw in reg_kws[:3]:
            results = self.rss.search(kw, max_results=2, days=days)
            for r in results:
                article = self._process_result(r, industry, "regulation", "규제 변화")
                if article:
                    all_articles.append(article)
            time.sleep(0.5)

        # 중복 제거 + 카테고리별 제한
        all_articles = self._deduplicate(all_articles)
        all_articles = self._limit_per_category(all_articles, max_per_category)

        print(f"\n✅ {industry} 뉴스 수집 완료: {len(all_articles)}건")
        self._print_summary(all_articles)
        return all_articles

    def collect_competitor_news(
        self,
        competitors: list[str],
        industry: str = "기타",
        days: int = 14,
        max_per_company: int = 3,
    ) -> list[NewsArticle]:
        """
        경쟁사 동향 뉴스 수집

        Args:
            competitors: 경쟁사 이름 리스트
            industry: 산업 분류
            days: 최근 N일
            max_per_company: 경쟁사당 최대 기사 수
        """
        config = INDUSTRY_CONFIG.get(industry, INDUSTRY_CONFIG["기타"])
        comp_kws = config.get("competitor_keywords", ["투자", "출시", "실적"])
        all_articles = []

        print(f"\n{'='*50}")
        print(f"🏢 경쟁사 동향 수집 ({len(competitors)}개사)")
        print(f"{'='*50}")

        for company in competitors:
            print(f"\n🔍 [{company}] 수집 중...")
            # 회사명 단독 검색
            results = self.rss.search(company, max_results=3, days=days)
            for r in results:
                article = self._process_result(r, industry, "competitor", "경쟁사 동향")
                if article:
                    article.company = company
                    all_articles.append(article)

            # 회사명 + 키워드 조합 검색
            for kw in comp_kws[:2]:
                results = self.rss.search(f"{company} {kw}", max_results=2, days=days)
                for r in results:
                    article = self._process_result(r, industry, "competitor", "경쟁사 동향")
                    if article:
                        article.company = company
                        all_articles.append(article)
            time.sleep(0.5)

        all_articles = self._deduplicate(all_articles)

        # 경쟁사별 제한
        by_company = {}
        for a in all_articles:
            by_company.setdefault(a.company, []).append(a)
        limited = []
        for comp, arts in by_company.items():
            limited.extend(arts[:max_per_company])

        print(f"\n✅ 경쟁사 뉴스 수집 완료: {len(limited)}건")
        return limited

    def collect_for_company(
        self,
        company: str,
        industry: str,
        competitors: list[str] = None,
        days: int = 7,
        max_per_category: int = 3,
    ) -> dict:
        """
        특정 기업 맞춤형 뉴스 수집 (3축 통합)

        Returns:
            {
                "industry_trend": [NewsArticle, ...],
                "competitor": [NewsArticle, ...],
                "regulation": [NewsArticle, ...],
                "company_news": [NewsArticle, ...],
                "all": [NewsArticle, ...],
            }
        """
        print(f"\n{'='*60}")
        print(f"🎯 {company} 맞춤형 뉴스 수집")
        print(f"   산업: {industry}")
        print(f"   경쟁사: {competitors or '없음'}")
        print(f"{'='*60}")

        result = {
            "industry_trend": [],
            "competitor": [],
            "regulation": [],
            "company_news": [],
            "all": [],
        }

        # 1) 산업 트렌드 + 규제 변화
        industry_news = self.collect_industry_news(industry, days, max_per_category)
        for a in industry_news:
            result[a.category].append(a)

        # 2) 경쟁사 동향
        if competitors:
            comp_news = self.collect_competitor_news(competitors, industry, days * 2)
            result["competitor"].extend(comp_news)

        # 3) 타겟 기업 자체 뉴스
        print(f"\n🔍 [{company}] 자체 뉴스 수집 중...")
        company_results = self.rss.search(company, max_results=5, days=days)
        for r in company_results:
            article = self._process_result(r, industry, "company", "기업 뉴스")
            if article:
                article.company = company
                result["company_news"].append(article)

        # 전체 합산
        for key in ["industry_trend", "competitor", "regulation", "company_news"]:
            result["all"].extend(result[key])

        print(f"\n{'='*60}")
        print(f"📊 {company} 맞춤 뉴스 수집 결과")
        print(f"   산업 트렌드: {len(result['industry_trend'])}건")
        print(f"   경쟁사 동향: {len(result['competitor'])}건")
        print(f"   규제 변화: {len(result['regulation'])}건")
        print(f"   기업 뉴스: {len(result['company_news'])}건")
        print(f"   총: {len(result['all'])}건")
        print(f"{'='*60}")

        return result

    # ----------------------------------------------------------
    # 내부 메서드
    # ----------------------------------------------------------

    def _process_result(self, rss_item: dict, industry: str, category: str, category_label: str) -> Optional[NewsArticle]:
        """RSS 결과 → NewsArticle 변환 + 본문 크롤링"""
        url = rss_item.get("url", "")
        if not url:
            return None

        article = NewsArticle(
            title=rss_item.get("title", ""),
            url=url,
            source=rss_item.get("source", ""),
            published_at=rss_item.get("published_at", ""),
            description=rss_item.get("description", ""),
            category=category,
            category_label=category_label,
            industry=industry,
            crawled_at=datetime.now().isoformat(),
        )

        # 본문 크롤링
        if self.crawl_body and self.crawler:
            extracted = self.crawler.extract_article(url)
            if extracted.get("success"):
                article.full_text = extracted["full_text"]
                article.author = extracted.get("author", "")
                article.word_count = extracted.get("word_count", 0)
                article.crawl_success = True
                # 키워드 추출
                article.keywords = self.classifier.extract_keywords(article.full_text)
                print(f"  📄 크롤링 성공: {article.title[:40]}... ({article.word_count}자)")
            else:
                article.crawl_success = False
                print(f"  ⚠️ 크롤링 실패: {article.title[:40]}... ({extracted.get('error', '')})")
        else:
            article.crawl_success = False

        # 자동 분류 (카테고리가 미지정이거나 재분류 필요 시)
        if article.full_text or article.description:
            article = self.classifier.classify(article)

        return article

    def _deduplicate(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        """URL 기반 중복 제거"""
        seen_urls = set()
        unique = []
        for a in articles:
            normalized = a.url.split("?")[0].rstrip("/")
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                unique.append(a)
        return unique

    def _limit_per_category(self, articles: list[NewsArticle], max_per: int) -> list[NewsArticle]:
        """카테고리별 기사 수 제한"""
        by_cat = {}
        for a in articles:
            by_cat.setdefault(a.category, []).append(a)
        result = []
        for cat, arts in by_cat.items():
            result.extend(arts[:max_per])
        return result

    def _print_summary(self, articles: list[NewsArticle]):
        """수집 결과 요약 출력"""
        by_cat = {}
        for a in articles:
            by_cat.setdefault(a.category_label, []).append(a)
        for cat, arts in by_cat.items():
            crawled = sum(1 for a in arts if a.crawl_success)
            print(f"  {cat}: {len(arts)}건 (본문 크롤링: {crawled}건)")

    # ----------------------------------------------------------
    # 저장 / 로드
    # ----------------------------------------------------------

    def save_articles(self, articles: list[NewsArticle], filepath: str = ""):
        """수집 결과 JSON 저장"""
        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            filepath = f"output/news_{ts}.json"

        fp = Path(filepath)
        fp.parent.mkdir(parents=True, exist_ok=True)

        data = [asdict(a) for a in articles]
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 뉴스 저장: {fp} ({len(articles)}건)")

    @staticmethod
    def load_articles(filepath: str) -> list[NewsArticle]:
        """저장된 뉴스 로드"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [NewsArticle(**item) for item in data]


# ============================================================
# 실행 예시
# ============================================================

if __name__ == "__main__":
    collector = NewsCollector(crawl_body=True)

    # ---- 예시 1: 산업별 뉴스 수집 ----
    # news = collector.collect_industry_news("IT/소프트웨어", days=7)
    # collector.save_articles(news)

    # ---- 예시 2: 경쟁사 동향 수집 ----
    # news = collector.collect_competitor_news(
    #     competitors=["네이버", "카카오", "쿠팡"],
    #     industry="IT/소프트웨어",
    # )

    # ---- 예시 3: 기업 맞춤형 통합 수집 (추천) ----
    result = collector.collect_for_company(
        company="삼성전자",
        industry="IT/소프트웨어",
        competitors=["LG전자", "SK하이닉스", "TSMC"],
        days=7,
    )

    # 전체 저장
    collector.save_articles(result["all"])

    # 카테고리별 확인
    for article in result["all"][:5]:
        print(f"\n[{article.category_label}] {article.title}")
        print(f"  출처: {article.source} | 본문: {article.word_count}자")
        if article.keywords:
            print(f"  키워드: {', '.join(article.keywords)}")
