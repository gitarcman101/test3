import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from newsletter_pipeline import run_pipeline

lead = {
    "이름": "김피엠",
    "이메일": "detaaiconsultingkorea@gmail.com",
    "직함": "PM",
    "회사명": "데타",
    "회사_산업": "information technology",
    "회사_도메인": "deta.kr",
    "회사_설명": "AI 컨설팅 전문 기업. B2B 대상 AI 전략 수립, 데이터 분석, AI 솔루션 도입 컨설팅 제공. 기업의 디지털 전환 및 AI 기반 업무 자동화 지원.",
    "회사_규모": "10",
    "회사_위치": "서울, 한국",
}

results = run_pipeline(
    leads_list=[lead],
    use_claude=True,
    send_emails=False,
    add_to_stibee=False,
    output_dir="output/deta_newsletter",
)
print("\n=== DONE ===")
for r in results:
    print(f"HTML: {r.get('html_file', 'N/A')}")
    print(f"Subject: {r.get('insight', {}).get('subject_line', 'N/A')}")
