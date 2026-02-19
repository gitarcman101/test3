"""
스티비 이메일 에디터에 HTML 삽입 도우미
======================================
localhost:8899 → "복사" 버튼 → 스티비 에디터에 Ctrl+V

사용법:  python inject_html_stibee.py [이메일ID] [HTML파일경로]
예시:    python inject_html_stibee.py 3241755
         python inject_html_stibee.py 3241755 output/first_newsletter/final_briefing.html
"""

import http.server
import json
import webbrowser
import sys
from pathlib import Path

DEFAULT_HTML_FILE = "output/first_newsletter/final_briefing.html"
PORT = 8899


def main():
    # 인자 파싱: [이메일ID] [HTML파일경로]
    email_id = sys.argv[1] if len(sys.argv) > 1 else ""
    html_file = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HTML_FILE

    html_path = Path(html_file)
    if not html_path.exists():
        print(f"파일 없음: {html_file}")
        sys.exit(1)

    html_content = html_path.read_text(encoding="utf-8")
    js_escaped = json.dumps(html_content, ensure_ascii=False)
    size_str = f"{len(html_content):,}"

    # 스티비 에디터 버튼 (이메일ID가 있을 때만 표시) — step05(HTML 에디터)로 이동
    stibee_btn = ""
    if email_id:
        stibee_url = f"https://stibee.com/email/{email_id}/edit/step05"
        stibee_btn = f'<button class="btn b2" onclick="window.open(\'{stibee_url}\')">🔗 스티비 에디터 열기 (Step 05)</button>'

    helper_page = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">'
        "<title>HTML 복사 도우미</title>"
        "<style>"
        "body{font-family:'Segoe UI',sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0;padding:40px}"
        ".c{max-width:700px;margin:0 auto}"
        "h1{color:#7C3AED}"
        "#st{padding:16px 20px;border-radius:8px;margin:20px 0;font-size:15px;background:#1e3a5f;border:1px solid #3b82f6}"
        ".done{background:#14532d !important;border-color:#22c55e !important}"
        ".btn{display:inline-block;padding:14px 32px;border-radius:8px;font-size:16px;"
        "font-weight:700;cursor:pointer;border:none;margin:8px 4px;color:#fff}"
        ".b1{background:#4F46E5}.b1:hover{background:#4338CA}"
        ".b2{background:#374151}.b2:hover{background:#4B5563}"
        "ol{background:#16213e;padding:20px 24px 20px 44px;border-radius:8px;margin:20px 0}"
        "li{margin:8px 0;line-height:1.7}"
        "code{background:#0d1117;padding:2px 6px;border-radius:3px;color:#7dd3fc}"
        "</style></head><body>"
        '<div class="c">'
        "<h1>DETA 뉴스레터 HTML 삽입</h1>"
        f'<div id="st">HTML 준비됨 ({size_str} bytes) — 아래 버튼 클릭</div>'
        '<button class="btn b1" onclick="doCopy()">📋 HTML 코드 복사</button> '
        f'{stibee_btn}'
        "<ol>"
        "<li><b>HTML 코드 복사</b> 버튼 클릭</li>"
        "<li><b>스티비 에디터 열기</b> 버튼 클릭 → Step 05 (HTML 에디터) 페이지로 이동</li>"
        "<li>하단의 <b>직접 만들기</b> → <code>HTML 에디터로 만들기</code> 선택</li>"
        "<li>Step 05 HTML 에디터에서 왼쪽 코드 영역 클릭</li>"
        "<li><code>Ctrl+A</code> → <code>Ctrl+V</code> 로 붙여넣기</li>"
        "<li>오른쪽 미리보기 확인 후 <b>다음</b> → <b>발송하기</b></li>"
        "</ol>"
        "</div>"
        "<script>"
        f"var H={js_escaped};"
        "function doCopy(){"
        "navigator.clipboard.writeText(H).then(function(){"
        "document.getElementById('st').className='done';"
        "document.getElementById('st').textContent='클립보드에 복사 완료! 스티비 에디터에서 Ctrl+A → Ctrl+V';"
        "}).catch(function(){"
        "var t=document.createElement('textarea');t.value=H;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);"
        "document.getElementById('st').className='done';"
        "document.getElementById('st').textContent='클립보드에 복사 완료! 스티비 에디터에서 Ctrl+A → Ctrl+V';"
        "});}"
        "</script></body></html>"
    )

    page_bytes = helper_page.encode("utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page_bytes)))
            self.end_headers()
            self.wfile.write(page_bytes)

        def log_message(self, *a):
            pass

    print(f"서버: http://localhost:{PORT}")
    print("브라우저에서 열립니다... (Ctrl+C 종료)")

    webbrowser.open(f"http://localhost:{PORT}")

    s = http.server.HTTPServer(("", PORT), H)
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        s.server_close()


if __name__ == "__main__":
    main()
