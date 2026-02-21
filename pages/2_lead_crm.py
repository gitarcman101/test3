"""
DETA Lead CRM — 리드 관리 대시보드
====================================
리드 상태 추적, 통계, 관리 기능.

Streamlit Multi-Page 기능으로 사이드바에 자동 등록됨.
"""

import streamlit as st
import os
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_store import PipelineStore, LeadCRM, LEAD_STATUSES

_store = PipelineStore()
_crm = LeadCRM()

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
    page_title="DETA Lead CRM",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── 환경변수 로드 ──
def _load_env():
    env = {}
    env_path = Path(__file__).parent.parent / "config" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    for key in ["REVIEW_PASSWORD"]:
        if key not in env or not env[key]:
            try:
                env[key] = st.secrets.get(key, "")
            except Exception:
                pass
        if key not in env or not env[key]:
            env[key] = os.environ.get(key, "")
    return env


# ── 인증 ──
def _check_auth():
    """메인 앱에서 로그인했으면 통과, 아니면 여기서 인증"""
    if st.session_state.get("authenticated"):
        return True
    env = _load_env()
    pw = env.get("REVIEW_PASSWORD", "")
    if not pw:
        return True
    entered = st.text_input("비밀번호를 입력하세요", type="password", key="crm_pw")
    if entered == pw:
        st.session_state.authenticated = True
        st.rerun()
    elif entered:
        st.error("비밀번호가 일치하지 않습니다.")
    return False


if not _check_auth():
    st.stop()


# ── Palantir 다크 테마 적용 ──
from ui_theme import apply_theme
apply_theme()


# ── 사이드바 ──
with st.sidebar:
    st.markdown("""
    <div style="padding: 8px 0 16px;">
        <div class="palantir-header">DETA CRM</div>
        <div style="border-top: 1px solid #222222; margin: 10px 0;"></div>
        <div style="font-size:13px; color:#666666;">Lead Management</div>
    </div>
    """, unsafe_allow_html=True)

    # 필터
    status_filter = st.selectbox(
        "상태 필터",
        options=["전체"] + list(LEAD_STATUSES.keys()),
        format_func=lambda x: f"{x} — {LEAD_STATUSES[x]}" if x in LEAD_STATUSES else "전체",
    )


# ============================================================
# 메인 콘텐츠
# ============================================================

st.markdown("### 📊 리드 관리 (CRM)")
st.markdown("")

# ── 통계 카드 ──
stats = _crm.get_stats()
total = stats.get("total", 0)

if total == 0:
    st.info("등록된 리드가 없습니다. '콜드메일' 페이지에서 리드를 등록하세요.")
    st.stop()

# 상태별 카운트 표시
status_cols = st.columns(min(len([s for s, c in stats.items() if c > 0 and s != "total"]), 6) or 1)
col_idx = 0
for status_key in ["new", "researched", "sent", "replied", "meeting_set", "no_response", "archived"]:
    cnt = stats.get(status_key, 0)
    if cnt > 0 and col_idx < len(status_cols):
        with status_cols[col_idx]:
            st.metric(status_key, cnt)
        col_idx += 1

st.metric("전체 리드", total)
st.markdown("")

# ── 리드 목록 ──
st.markdown("---")
leads = _crm.list_leads(status=status_filter if status_filter != "전체" else None)

if not leads:
    st.info(f"'{status_filter}' 상태의 리드가 없습니다.")
    st.stop()

# DataFrame으로 표시
df_data = []
for lead in leads:
    df_data.append({
        "ID": lead.get("lead_id", ""),
        "회사명": lead.get("company", ""),
        "담당자": lead.get("contact_name", ""),
        "이메일": lead.get("contact_email", ""),
        "산업": lead.get("industry", ""),
        "상태": lead.get("status", ""),
        "발송일": lead.get("last_sent_at", "-") or "-",
        "등록일": lead.get("created_at", "")[:10] if lead.get("created_at") else "",
    })

df = pd.DataFrame(df_data)
st.dataframe(df, use_container_width=True, hide_index=True)

# ── 리드 상세 & 상태 변경 ──
st.markdown("")
st.markdown("### 리드 상태 변경")

selected_lead_id = st.selectbox(
    "리드 선택",
    options=[l.get("lead_id", "") for l in leads],
    format_func=lambda lid: next(
        (f"{l.get('company', '')} — {l.get('contact_name', '')} ({lid})"
         for l in leads if l.get("lead_id") == lid),
        lid,
    ),
)

if selected_lead_id:
    lead = _crm.get_lead(selected_lead_id)
    if lead:
        col_detail, col_action = st.columns([2, 1])

        with col_detail:
            st.json(lead)

        with col_action:
            new_status = st.selectbox(
                "새 상태",
                options=list(LEAD_STATUSES.keys()),
                index=list(LEAD_STATUSES.keys()).index(lead.get("status", "new")),
            )
            note = st.text_input("메모 (선택)", placeholder="상태 변경 사유")

            if st.button("상태 변경", use_container_width=True, type="primary"):
                if new_status != lead.get("status"):
                    success = _crm.update_status(selected_lead_id, new_status, note=note)
                    if success:
                        st.success(f"상태 변경: {lead.get('status')} → {new_status}")
                        st.rerun()
                    else:
                        st.error("상태 변경 실패")
                else:
                    st.info("같은 상태입니다.")

            st.markdown("")
            if st.button("🗑️ 리드 삭제", use_container_width=True):
                if _crm.delete_lead(selected_lead_id):
                    st.success(f"리드 삭제됨: {selected_lead_id}")
                    st.rerun()

# ── 파이프라인 리드 가져오기 ──
st.markdown("---")
with st.expander("📂 기존 파이프라인에서 리드 가져오기", expanded=False):
    runs = _store.list_runs()
    if runs:
        for run in runs[:5]:
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.markdown(
                    f"**{run.get('run_id', '')}** — "
                    f"{run.get('total_leads', 0)}건 | "
                    f"{run.get('created_at', '')[:16]}",
                )
            with col_btn:
                if st.button("가져오기", key=f"import_{run['run_id']}", use_container_width=True):
                    imported = _crm.import_leads_from_run(_store, run["run_id"])
                    if imported:
                        st.success(f"{len(imported)}건 리드를 CRM에 추가했습니다.")
                        st.rerun()
                    else:
                        st.info("추가할 새 리드가 없습니다 (이미 존재하거나 이메일 없음).")
    else:
        st.info("이전 파이프라인 실행 기록이 없습니다.")
