"""
DETA Newsletter Pipeline — 리뷰 대시보드
=========================================
팀원이 뉴스레터를 검토하고 승인/반려/코멘트를 남기는 페이지.
Streamlit Multi-Page 기능으로 사이드바에 자동 등록됨.
"""

import streamlit as st
import streamlit.components.v1 as components
import os
import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 path에 추가 (pages/ 하위이므로)
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_store import PipelineStore

_store = PipelineStore()

# ── 인코딩 설정 ──
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except (OSError, AttributeError):
    pass

# ── 페이지 설정 ──
st.set_page_config(
    page_title="DETA Review Dashboard",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── 환경변수 로드 ──
def _load_env():
    env = {}
    # 1) 로컬 파일 우선
    for env_path in [Path("config/.env"), Path(".env")]:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
            break
    # 2) Streamlit Cloud secrets fallback
    if not env:
        try:
            for k, v in st.secrets.items():
                if isinstance(v, str):
                    env[k] = v
        except Exception:
            pass
    # 3) 환경변수 fallback
    for key in ["REVIEW_PASSWORD"]:
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]
    return env


# ── Palantir 다크 테마 CSS ──
st.markdown("""
<style>
    .stApp { background-color: #111418; }
    .stApp > header { background-color: #111418 !important; }

    [data-testid="stSidebar"] {
        background-color: #1C2127;
        border-right: 1px solid #2F343C;
    }
    [data-testid="stSidebar"] * { color: #ABB3BF; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #E0E0E0 !important; }

    h1, h2 { color: #E0E0E0 !important; letter-spacing: -0.3px; }
    h3 { color: #C5CBD3 !important; }
    p, li, span, label { color: #ABB3BF; }
    .stCaption, caption { color: #5F6B7C !important; }
    a { color: #738091 !important; }
    a:hover { color: #ABB3BF !important; }

    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > div {
        background-color: #252A31 !important;
        border: 1px solid #383E47 !important;
        color: #E0E0E0 !important;
        border-radius: 4px !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #738091 !important;
        box-shadow: 0 0 0 1px #738091 !important;
    }
    .stTextInput label, .stTextArea label,
    .stSelectbox label, .stFileUploader label {
        color: #8F99A8 !important;
        font-weight: 500 !important;
        font-size: 13px !important;
    }

    .stButton > button {
        background-color: #252A31 !important;
        color: #E0E0E0 !important;
        border: 1px solid #383E47 !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background-color: #2F343C !important;
        border-color: #738091 !important;
    }
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: #E0E0E0 !important;
        color: #1C2127 !important;
        border: none !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: #C5CBD3 !important;
    }

    .stAlert > div {
        border-radius: 4px !important;
        border-width: 1px !important;
    }
    hr { border-color: #2F343C !important; }

    .streamlit-expanderHeader {
        background-color: #1C2127 !important;
        border: 1px solid #2F343C !important;
        border-radius: 4px !important;
        color: #ABB3BF !important;
    }
    .streamlit-expanderContent {
        background-color: #1C2127 !important;
        border: 1px solid #2F343C !important;
        border-top: none !important;
    }

    .palantir-header {
        font-size: 11px;
        letter-spacing: 2px;
        color: #5F6B7C;
        font-weight: 600;
        text-transform: uppercase;
    }
    .palantir-title {
        font-size: 28px;
        font-weight: 700;
        color: #E0E0E0;
        letter-spacing: -0.5px;
        margin: 4px 0 0;
    }
    .palantir-sub {
        font-size: 13px;
        color: #738091;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ── 인증 ──
def _check_auth():
    """간단한 비밀번호 인증. REVIEW_PASSWORD가 env에 없으면 인증 스킵."""
    env = _load_env()
    password = env.get("REVIEW_PASSWORD", "")

    if not password:
        # 비밀번호 미설정 시 인증 없이 접근 허용
        return True

    if st.session_state.get("review_authenticated"):
        return True

    st.markdown("""
    <div class="palantir-header">DETA PIPELINE</div>
    <div class="palantir-title">리뷰 대시보드</div>
    <div class="palantir-sub">접근 권한이 필요합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.form("review_auth_form"):
        pw_input = st.text_input("비밀번호", type="password", placeholder="리뷰 비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", type="primary")

    if submitted:
        if pw_input == password:
            st.session_state.review_authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    st.caption("config/.env에 REVIEW_PASSWORD를 설정하여 접근을 제어합니다.")
    return False


# ── 파이프라인 트래커 (streamlit_app.py와 동일한 로직) ──
def _render_tracker(run_data):
    """run 데이터로 파이프라인 트래커 HTML 렌더링"""
    leads = run_data.get("leads", [])
    if not leads:
        return

    news = run_data.get("news", {})
    insights = run_data.get("insights", {})
    html_data = run_data.get("html", {})
    reviews = run_data.get("reviews", {})
    send = run_data.get("send", {})

    rows_html = ""
    for i, ld in enumerate(leads):
        si = str(i)
        has_news = si in news
        has_insight = si in insights
        has_html = i in html_data
        review_info = reviews.get(si, {})
        review_st = review_info.get("status", "")
        send_st = send.get(si, "")

        def _dot(done, failed=False, pending=False):
            if failed:
                return '<span style="color:#C5504C;">✗</span>'
            if pending:
                return '<span style="color:#A68B2D;">◐</span>'
            if done:
                return '<span style="color:#738091;">●</span>'
            return '<span style="color:#383E47;">○</span>'

        news_dot = _dot(has_news)
        ai_dot = _dot(has_insight)
        html_dot = _dot(has_html)
        review_dot = _dot(
            review_st == "approved",
            failed=(review_st == "rejected"),
            pending=(has_html and review_st not in ("approved", "rejected")),
        )
        send_dot = _dot(
            send_st == "sent",
            failed=(send_st == "failed"),
            pending=(review_st == "approved" and send_st not in ("sent", "failed")),
        )

        name = ld.get("이름", "")[:6]
        company = ld.get("회사명", "")[:6]
        rows_html += (
            f'<tr style="border-bottom:1px solid #2F343C;">'
            f'<td style="padding:4px 8px;color:#ABB3BF;font-size:12px;">{name}</td>'
            f'<td style="padding:4px 8px;color:#5F6B7C;font-size:12px;">{company}</td>'
            f'<td style="text-align:center;padding:4px;">{news_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{ai_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{html_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{review_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{send_dot}</td>'
            f'</tr>'
        )

    table_html = f"""
    <div style="background:#1C2127;border:1px solid #2F343C;border-radius:4px;padding:8px;margin-bottom:12px;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="border-bottom:1px solid #383E47;">
                    <th style="text-align:left;padding:4px 8px;color:#5F6B7C;font-size:10px;letter-spacing:1px;">LEAD</th>
                    <th style="text-align:left;padding:4px 8px;color:#5F6B7C;font-size:10px;letter-spacing:1px;">CO.</th>
                    <th style="text-align:center;padding:4px;color:#5F6B7C;font-size:10px;">NEWS</th>
                    <th style="text-align:center;padding:4px;color:#5F6B7C;font-size:10px;">AI</th>
                    <th style="text-align:center;padding:4px;color:#5F6B7C;font-size:10px;">HTML</th>
                    <th style="text-align:center;padding:4px;color:#5F6B7C;font-size:10px;">REV</th>
                    <th style="text-align:center;padding:4px;color:#5F6B7C;font-size:10px;">SEND</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ============================================================
# 메인 리뷰 대시보드
# ============================================================

def main():
    if not _check_auth():
        st.stop()

    # ── 헤더 ──
    st.markdown("""
    <div class="palantir-header">DETA PIPELINE</div>
    <div class="palantir-title">리뷰 대시보드</div>
    <div class="palantir-sub">뉴스레터를 검토하고 승인/반려/코멘트를 남기세요.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    # ── 파이프라인 선택 ──
    runs = _store.list_runs()
    if not runs:
        st.info("진행 중인 파이프라인이 없습니다. 운영자가 파이프라인을 생성하면 여기에 표시됩니다.")
        st.stop()

    run_options = {
        r["run_id"]: f"{r['run_id']} ({r.get('total_leads', '?')}명, {r.get('status', '')})"
        for r in runs
    }
    selected_run_id = st.selectbox(
        "파이프라인 선택",
        options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
    )

    if not selected_run_id:
        st.stop()

    # ── 데이터 로드 ──
    run_data = _store.load_run(selected_run_id)
    if not run_data:
        st.warning("파이프라인 데이터를 불러올 수 없습니다.")
        st.stop()

    leads = run_data.get("leads", [])
    news = run_data.get("news", {})
    insights = run_data.get("insights", {})
    html_data = run_data.get("html", {})
    reviews = run_data.get("reviews", {})
    send = run_data.get("send", {})

    # ── 파이프라인 트래커 ──
    with st.expander("📊 파이프라인 트래커", expanded=True):
        _render_tracker(run_data)

    # ── 요약 통계 ──
    total = len(leads)
    n_html_ready = sum(1 for i in range(total) if i in html_data)
    n_approved = sum(1 for v in reviews.values() if v.get("status") == "approved")
    n_rejected = sum(1 for v in reviews.values() if v.get("status") == "rejected")
    n_pending = n_html_ready - n_approved - n_rejected

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("전체 리드", total)
    with col_m2:
        st.metric("HTML 준비", n_html_ready)
    with col_m3:
        st.metric("승인", n_approved)
    with col_m4:
        st.metric("반려", n_rejected)

    st.divider()

    # ── 리드별 리뷰 ──
    if n_html_ready == 0:
        st.info("아직 HTML이 생성된 리드가 없습니다. 운영자가 Step 4까지 진행하면 검토할 수 있습니다.")
        st.stop()

    # 리뷰어 이름 (세션에 저장)
    if "reviewer_name" not in st.session_state:
        st.session_state.reviewer_name = ""
    reviewer = st.text_input(
        "리뷰어 이름",
        value=st.session_state.reviewer_name,
        placeholder="이름을 입력하세요",
        key="reviewer_input",
    )
    st.session_state.reviewer_name = reviewer

    for i, ld in enumerate(leads):
        si = str(i)
        has_html = i in html_data
        if not has_html:
            continue

        review_info = reviews.get(si, {})
        review_status = review_info.get("status", "")
        send_status = send.get(si, "")

        # 상태 표시
        if send_status == "sent":
            status_badge = '<span style="background:#14532d;color:#22c55e;padding:2px 8px;border-radius:3px;font-size:11px;">✅ 발송 완료</span>'
        elif review_status == "approved":
            status_badge = '<span style="background:#14532d;color:#22c55e;padding:2px 8px;border-radius:3px;font-size:11px;">✅ 승인됨</span>'
        elif review_status == "rejected":
            status_badge = '<span style="background:#450a0a;color:#ef4444;padding:2px 8px;border-radius:3px;font-size:11px;">❌ 반려됨</span>'
        else:
            status_badge = '<span style="background:#422006;color:#f59e0b;padding:2px 8px;border-radius:3px;font-size:11px;">⏳ 검토 대기</span>'

        insight = insights.get(si, {})
        subject = insight.get("subject_line", "제목 없음")

        expander_label = f"{i+1}. {ld.get('이름', '')} ({ld.get('회사명', '')}) — {subject}"
        with st.expander(expander_label, expanded=(review_status == "")):
            # 상태 배지
            st.markdown(status_badge, unsafe_allow_html=True)

            # ── 인사이트 요약 ──
            if insight:
                st.markdown("##### 인사이트 요약")
                i1 = insight.get("insight_1", {})
                i2 = insight.get("insight_2", {})

                summary_html = f"""
                <div style="background:#252A31;border:1px solid #383E47;border-radius:4px;padding:12px;margin:8px 0;">
                    <div style="color:#8F99A8;font-size:11px;letter-spacing:1px;margin-bottom:4px;">DEEP DIVE 1</div>
                    <div style="color:#E0E0E0;font-size:14px;font-weight:600;">{i1.get('title', '')}</div>
                    <div style="color:#ABB3BF;font-size:12px;margin-top:4px;">{i1.get('body', '')[:150]}...</div>
                </div>
                <div style="background:#252A31;border:1px solid #383E47;border-radius:4px;padding:12px;margin:8px 0;">
                    <div style="color:#8F99A8;font-size:11px;letter-spacing:1px;margin-bottom:4px;">DEEP DIVE 2</div>
                    <div style="color:#E0E0E0;font-size:14px;font-weight:600;">{i2.get('title', '')}</div>
                    <div style="color:#ABB3BF;font-size:12px;margin-top:4px;">{i2.get('body', '')[:150]}...</div>
                </div>
                """
                st.markdown(summary_html, unsafe_allow_html=True)

                if insight.get("company_relevance"):
                    st.markdown(f"**시사점:** {insight['company_relevance']}")
                if insight.get("key_takeaway"):
                    st.markdown(f"**핵심:** {insight['key_takeaway']}")

            # ── HTML 미리보기 ──
            if st.checkbox("미리보기 열기", key=f"rev_preview_{i}"):
                components.html(html_data[i], height=600, scrolling=True)

            # ── 승인/반려 버튼 ──
            col_approve, col_reject = st.columns(2)
            with col_approve:
                if st.button("✅ 승인", key=f"approve_{i}", type="primary",
                             disabled=(review_status == "approved")):
                    _store.save_review(selected_run_id, i, "approved", reviewer=reviewer)
                    st.rerun()
            with col_reject:
                if st.button("❌ 반려", key=f"reject_{i}",
                             disabled=(review_status == "rejected")):
                    _store.save_review(selected_run_id, i, "rejected", reviewer=reviewer)
                    st.rerun()

            # ── 코멘트 ──
            comment_text = st.text_area(
                "코멘트", key=f"comment_{i}",
                placeholder="수정 사항이나 피드백을 남기세요...",
                height=80,
            )
            if st.button("💬 코멘트 저장", key=f"save_comment_{i}"):
                if comment_text.strip():
                    _store.save_review(
                        selected_run_id, i,
                        review_status or "comment",
                        reviewer=reviewer,
                        comment=comment_text.strip(),
                    )
                    st.success("코멘트가 저장되었습니다.")
                    st.rerun()
                else:
                    st.warning("코멘트를 입력하세요.")

            # ── 이전 코멘트/리뷰 이력 ──
            if review_info:
                st.markdown("---")
                st.markdown("##### 리뷰 이력")
                rev_time = review_info.get("timestamp", "")
                rev_reviewer = review_info.get("reviewer", "익명")
                rev_status = review_info.get("status", "")
                rev_comment = review_info.get("comment", "")

                status_text = {"approved": "승인", "rejected": "반려", "comment": "코멘트"}.get(
                    rev_status, rev_status
                )

                history_html = f"""
                <div style="background:#1C2127;border:1px solid #2F343C;border-radius:4px;padding:10px;margin:4px 0;">
                    <div style="color:#738091;font-size:11px;">{rev_time} — {rev_reviewer} — <b>{status_text}</b></div>
                """
                if rev_comment:
                    history_html += f'<div style="color:#ABB3BF;font-size:13px;margin-top:4px;">"{rev_comment}"</div>'
                history_html += "</div>"
                st.markdown(history_html, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
else:
    main()
