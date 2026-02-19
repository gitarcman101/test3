"""통합 파이프라인 검증 테스트 (mock 데이터)"""
from newsletter_pipeline import (
    run_pipeline, FallbackInsightGenerator, NewsletterBuilder,
    _map_industry, load_leads_from_csv,
)
from pathlib import Path
import json

print("=" * 60)
print("TEST 1: InsightGenerator (Fallback)")
print("=" * 60)

# Mock 뉴스 기사 (dict 형태)
mock_news = [
    {"title": "AI 트렌드 2025: 기업 도입 급증", "description": "생성형 AI 기업 도입률이 2025년 80%에 달할 전망", "source": "매일경제", "category_label": "산업 트렌드", "full_text": ""},
    {"title": "SaaS 시장 20% 성장 전망", "description": "글로벌 SaaS 시장이 전년 대비 20% 성장할 것으로 예상", "source": "한국경제", "category_label": "산업 트렌드", "full_text": ""},
    {"title": "EU AI Act 시행 임박", "description": "유럽연합 AI 규제법 연내 시행 예정", "source": "조선일보", "category_label": "규제 변화", "full_text": ""},
]

gen = FallbackInsightGenerator()
insight = gen.generate_insight(
    name="김철수",
    title="CTO",
    company="테스트코리아",
    industry="IT/소프트웨어",
    industry_news=mock_news,
)

print(f"  subject_line: {insight['subject_line']}")
print(f"  main_issue.title: {insight['main_issue']['title']}")
print(f"  insight_1.title: {insight['insight_1']['title']}")
print(f"  insight_2.title: {insight['insight_2']['title']}")
print(f"  company_relevance: {insight['company_relevance'][:50]}...")
print("  ✅ FallbackInsightGenerator 정상")

print()
print("=" * 60)
print("TEST 2: NewsletterBuilder (HTML)")
print("=" * 60)

builder = NewsletterBuilder()
html = builder.build_html(insight, mock_news)

out = Path("output/test_newsletter.html")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding="utf-8")

print(f"  HTML 길이: {len(html)} chars")
print(f"  파일 저장: {out}")
assert "DETA Intelligence Brief" in html
assert "메인 이슈" in html or "main_issue" in html.lower()
print("  ✅ NewsletterBuilder 정상")

print()
print("=" * 60)
print("TEST 3: run_pipeline (mock leads, no-crawl)")
print("=" * 60)

mock_leads = [
    {"이름": "홍길동", "이메일": "hong@example.com", "직함": "CEO", "회사명": "에이블코리아", "회사_산업": "information technology"},
    {"이름": "김영희", "이메일": "kim@example.com", "직함": "CTO", "회사명": "핀테크랩", "회사_산업": "financial services"},
]

results = run_pipeline(
    leads_list=mock_leads,
    send_emails=False,
    use_claude=False,
    crawl_body=False,
    output_dir="output/test_newsletters",
)

print(f"\n  처리 결과: {len(results)}건")
for r in results:
    print(f"    {r['name']} ({r['company']}) → {r['html_file']}")
    assert Path(r["html_file"]).exists(), f"HTML 파일 없음: {r['html_file']}"

print("  ✅ run_pipeline 정상")

print()
print("=" * 60)
print("✅ 모든 테스트 통과!")
print("=" * 60)
