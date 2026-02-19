"""
DETA Newsletter Automation - Main Entry Point
==============================================
Apollo 리드 → 뉴스 수집 → 인사이트 생성 → HTML 빌드 → 스티비 발송

사용법:
    # dry-run (HTML만 생성)
    python main.py --leads output/apollo_leads.xlsx

    # 실제 발송
    python main.py --leads output/apollo_leads.xlsx --send

    # 스티비 구독자 추가 + 발송
    python main.py --leads output/apollo_leads.xlsx --send --add-stibee

    # 테스트 (5건만, 본문 크롤링 없이)
    python main.py --leads output/apollo_leads.xlsx --max 5 --no-crawl

    # Apollo Enrichment 먼저 실행 후 파이프라인
    python main.py --enrich --leads targets.csv
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from newsletter_pipeline import run_pipeline, main as pipeline_main


def main():
    """Main entry point — delegates to newsletter_pipeline CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="DETA 통합 뉴스레터 자동화 시스템",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python main.py --leads output/apollo_leads.xlsx              # dry-run
  python main.py --leads output/apollo_leads.xlsx --send       # 실제 발송
  python main.py --leads output/apollo_leads.xlsx --max 5      # 5건만 테스트
  python main.py --enrich --leads targets.csv                  # Enrichment 먼저 실행
""",
    )
    parser.add_argument("--leads", help="Apollo 추출 결과 CSV/Excel 파일")
    parser.add_argument("--send", action="store_true", help="실제 스티비 발송")
    parser.add_argument("--add-stibee", action="store_true", help="스티비 구독자 추가")
    parser.add_argument("--no-claude", action="store_true", help="Claude 없이 템플릿 모드")
    parser.add_argument("--no-crawl", action="store_true", help="뉴스 본문 크롤링 비활성화")
    parser.add_argument("--max", type=int, default=0, help="최대 처리 건수")
    parser.add_argument("--output", default="output/newsletters", help="HTML 저장 디렉토리")
    parser.add_argument("--mode", choices=["auto", "smtp", "stibee", "bulk"], default="auto",
                        help="발송 모드: auto(자동이메일), smtp(직접), stibee(Email API), bulk(일괄)")
    parser.add_argument("--enrich", action="store_true", help="Apollo Enrichment 먼저 실행")

    args = parser.parse_args()

    # Apollo Enrichment 모드
    if args.enrich:
        print("=" * 60)
        print("🔍 Apollo People Enrichment 실행")
        print("=" * 60)
        try:
            from apollo_lead_extractor import run_enrichment
            result = run_enrichment()
            if result and not args.leads:
                # Enrichment 결과 파일을 자동으로 leads로 사용
                import glob
                xlsx_files = sorted(glob.glob("output/apollo_leads_*.xlsx"))
                csv_files = sorted(glob.glob("output/apollo_leads_*.csv"))
                latest = (xlsx_files or csv_files or [""])[-1]
                if latest:
                    args.leads = latest
                    print(f"\n📂 Enrichment 결과 사용: {latest}")
        except ImportError:
            print("⚠️ apollo_lead_extractor.py를 찾을 수 없습니다.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Enrichment 실패: {e}")
            sys.exit(1)

    # 뉴스레터 파이프라인
    if not args.leads:
        parser.print_help()
        print("\n⚠️ --leads 옵션으로 리드 파일을 지정해주세요.")
        sys.exit(1)

    run_pipeline(
        leads_file=args.leads,
        send_emails=args.send,
        add_to_stibee=args.add_stibee,
        use_claude=not args.no_claude,
        crawl_body=not args.no_crawl,
        max_leads=args.max,
        output_dir=args.output,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
