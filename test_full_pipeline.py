"""
전체 파이프라인 단계별 테스트
============================
1. 뉴스 수집 (news_collector_1.py)
2. 인사이트 생성 + HTML 빌드 (newsletter_pipeline.py)
3. 스티비 API 인증 (stibee_integration.py)
4. 전체 파이프라인 E2E (발송 제외)
"""

import sys
import json
import time
from datetime import datetime
from pathlib import Path

# 작업 디렉토리 설정
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


# ============================================================
# 더미 리드 데이터 (Apollo Enrichment 결과 형식)
# ============================================================
DUMMY_LEADS = [
    {
        "이름": "김테스트",
        "직함": "CTO",
        "직급": "c_suite",
        "부서": "engineering",
        "이메일": "test@example.com",
        "이메일_상태": "verified",
        "전화번호": "",
        "LinkedIn": "",
        "회사명": "삼성전자",
        "회사_도메인": "samsung.com",
        "회사_산업": "information technology",
        "회사_규모": "10000+",
        "회사_위치": "Seoul, Korea",
        "품질_점수": 80,
    },
    {
        "이름": "박데이터",
        "직함": "마케팅 디렉터",
        "직급": "director",
        "부서": "marketing",
        "이메일": "test2@example.com",
        "이메일_상태": "guessed",
        "전화번호": "",
        "LinkedIn": "",
        "회사명": "네이버",
        "회사_도메인": "naver.com",
        "회사_산업": "internet",
        "회사_규모": "5000",
        "회사_위치": "Seongnam, Korea",
        "품질_점수": 55,
    },
]


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# ============================================================
# 테스트 1: 뉴스 수집
# ============================================================
def test_news_collector():
    separator("TEST 1: 뉴스 수집 (news_collector_1.py)")

    try:
        from news_collector_1 import NewsCollector, INDUSTRY_CONFIG

        print("1-1) 지원 산업 목록:")
        for k in INDUSTRY_CONFIG:
            print(f"     - {k}")

        print("\n1-2) IT/소프트웨어 산업 뉴스 수집 (본문 크롤링 OFF, 빠른 테스트)...")
        collector = NewsCollector(crawl_body=False)
        articles = collector.collect_industry_news("IT/소프트웨어", days=7, max_per_category=2)

        if articles:
            print(f"\n     수집 결과: {len(articles)}건")
            for i, a in enumerate(articles[:5], 1):
                print(f"     [{i}] [{a.category_label}] {a.title[:50]}")
                print(f"         출처: {a.source} | URL: {a.url[:60]}...")
            print("\n     [PASS] 뉴스 수집 성공")
            return articles
        else:
            print("     [WARN] 수집된 뉴스 없음 (네트워크 또는 Google News 접근 문제일 수 있음)")
            return []

    except Exception as e:
        print(f"     [FAIL] 뉴스 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return []


# ============================================================
# 테스트 2: 인사이트 생성 + HTML 빌드
# ============================================================
def test_insight_and_html(articles):
    separator("TEST 2: 인사이트 생성 + HTML 빌드")

    try:
        from newsletter_pipeline import (
            FallbackInsightGenerator, InsightGenerator,
            NewsletterBuilder, _map_industry,
        )

        lead = DUMMY_LEADS[0]
        name = lead["이름"]
        title = lead["직함"]
        company = lead["회사명"]
        industry = _map_industry(lead["회사_산업"])
        print(f"2-0) 산업 매핑: '{lead['회사_산업']}' → '{industry}'")

        # 2-1) 폴백 템플릿 인사이트
        print(f"\n2-1) 폴백 인사이트 (템플릿 모드)...")
        fallback = FallbackInsightGenerator()
        test_articles = articles if articles else []

        if not test_articles:
            # 더미 기사 생성
            print("     (뉴스 없음 → 더미 기사 사용)")
            from news_collector_1 import NewsArticle
            test_articles = [
                NewsArticle(title="AI 시장 2025년 전망", description="글로벌 AI 시장이 급성장하고 있다", source="테크뉴스", category_label="산업 트렌드"),
                NewsArticle(title="EU AI Act 시행", description="유럽연합이 AI 규제를 강화한다", source="규제뉴스", category_label="규제 변화"),
                NewsArticle(title="삼성전자 AI 투자 확대", description="삼성전자가 AI 분야에 대규모 투자를 발표했다", source="경제뉴스", category_label="경쟁사 동향"),
            ]

        insight = fallback.generate_insight(name, title, company, industry, test_articles)
        print(f"     subject: {insight.get('subject_line', '')[:60]}")
        print(f"     greeting: {insight.get('greeting', '')[:60]}")
        print(f"     main_issue: {insight.get('main_issue', {}).get('title', '')[:50]}")
        print(f"     insight_1: {insight.get('insight_1', {}).get('title', '')[:50]}")
        print(f"     insight_2: {insight.get('insight_2', {}).get('title', '')[:50]}")
        print("     [PASS] 폴백 인사이트 생성 성공")

        # 2-2) Claude API 인사이트 (선택)
        print(f"\n2-2) Claude API 인사이트...")
        try:
            gen = InsightGenerator()
            claude_insight = gen.generate_insight(name, title, company, industry, test_articles)
            print(f"     subject: {claude_insight.get('subject_line', '')[:60]}")
            print(f"     greeting: {claude_insight.get('greeting', '')[:60]}")
            print(f"     main_issue: {claude_insight.get('main_issue', {}).get('title', '')[:50]}")
            print("     [PASS] Claude API 인사이트 생성 성공")
            insight = claude_insight  # Claude 결과를 HTML에 사용
        except Exception as e:
            print(f"     [SKIP] Claude API 사용 불가: {e}")

        # 2-3) HTML 빌드
        print(f"\n2-3) HTML 빌드...")
        builder = NewsletterBuilder()
        html = builder.build_html(insight, test_articles)

        out_dir = ROOT / "output" / "test"
        out_dir.mkdir(parents=True, exist_ok=True)
        html_file = out_dir / f"test_{company}_{datetime.now().strftime('%H%M%S')}.html"
        html_file.write_text(html, encoding="utf-8")

        print(f"     HTML 크기: {len(html):,} bytes")
        print(f"     저장: {html_file}")
        print(f"     브라우저에서 열어서 확인하세요!")
        print("     [PASS] HTML 빌드 성공")
        return html_file

    except Exception as e:
        print(f"     [FAIL] 인사이트/HTML 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# 테스트 3: 스티비 API 인증
# ============================================================
def test_stibee_auth():
    separator("TEST 3: 스티비 API 인증")

    try:
        from stibee_integration import StibeeClient, STIBEE_API_KEY, STIBEE_LIST_ID

        if not STIBEE_API_KEY:
            print("     [SKIP] STIBEE_API_KEY 미설정")
            return False

        print(f"3-1) API 키: {STIBEE_API_KEY[:10]}...{STIBEE_API_KEY[-6:]}")
        print(f"     주소록 ID: {STIBEE_LIST_ID}")

        client = StibeeClient()
        auth_ok = client.check_auth()

        if auth_ok:
            print("     [PASS] 스티비 API 인증 성공")
        else:
            print("     [FAIL] 스티비 API 인증 실패")

        return auth_ok

    except Exception as e:
        print(f"     [FAIL] 스티비 인증 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 테스트 4: 전체 파이프라인 E2E (발송 제외)
# ============================================================
def test_full_pipeline():
    separator("TEST 4: 전체 파이프라인 E2E (발송 제외)")

    try:
        from newsletter_pipeline import run_pipeline

        print("4-1) 더미 리드 2건으로 파이프라인 실행...")
        print("     - 뉴스 수집: ON (본문 크롤링 OFF)")
        print("     - 인사이트: 폴백 템플릿 모드")
        print("     - 발송: OFF (HTML만 생성)")
        print()

        results = run_pipeline(
            leads_list=DUMMY_LEADS,
            send_emails=False,
            add_to_stibee=False,
            use_claude=False,        # 템플릿 모드 (빠른 테스트)
            crawl_body=False,        # 본문 크롤링 OFF (빠른 테스트)
            max_leads=2,
            output_dir="output/test_pipeline",
        )

        if results:
            print(f"\n4-2) 파이프라인 결과:")
            for r in results:
                print(f"     - {r['name']} ({r['company']}) → {r['industry']}")
                print(f"       이메일: {r['email']}")
                print(f"       HTML: {r['html_file']}")
                print(f"       제목: {r['insight'].get('subject_line', '')[:50]}")
            print(f"\n     [PASS] 전체 파이프라인 E2E 성공 ({len(results)}건 처리)")
        else:
            print("     [WARN] 파이프라인 결과 없음")

        return results

    except Exception as e:
        print(f"     [FAIL] 파이프라인 오류: {e}")
        import traceback
        traceback.print_exc()
        return []


# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    print()
    print("*" * 60)
    print("  DETA 뉴스레터 파이프라인 — 전체 테스트")
    print(f"  시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("*" * 60)

    results = {}

    # Test 1: 뉴스 수집
    articles = test_news_collector()
    results["news_collector"] = "PASS" if articles else "WARN"

    # Test 2: 인사이트 + HTML
    html_file = test_insight_and_html(articles)
    results["insight_html"] = "PASS" if html_file else "FAIL"

    # Test 3: 스티비 인증
    stibee_ok = test_stibee_auth()
    results["stibee_auth"] = "PASS" if stibee_ok else "FAIL/SKIP"

    # Test 4: 전체 파이프라인
    pipeline_results = test_full_pipeline()
    results["full_pipeline"] = "PASS" if pipeline_results else "FAIL"

    # 최종 요약
    separator("테스트 결과 요약")
    for name, status in results.items():
        icon = {"PASS": "[OK]", "FAIL": "[X]", "WARN": "[!]", "FAIL/SKIP": "[~]"}.get(status, "[?]")
        print(f"  {icon} {name}: {status}")

    print(f"\n  총: {sum(1 for v in results.values() if v == 'PASS')}/{len(results)} PASS")
    print()
