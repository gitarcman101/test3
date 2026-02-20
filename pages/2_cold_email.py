"""
DETA Cold Email Pipeline — Track A
====================================
리드 입력 → 기업 리서치 → 콜드메일 생성 → 리뷰 → 발송

Streamlit Multi-Page 기능으로 사이드바에 자동 등록됨.
"""

import streamlit as st
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_store import PipelineStore, LeadCRM

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
    page_title="DETA Cold Email",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── 환경변수 로드 ──
def _load_env():
    """3-tier env fallback: config/.env → st.secrets → os.environ"""
    env = {}
    env_path = Path(__file__).parent.parent / "config" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")

    for key in ["ANTHROPIC_API_KEY", "STIBEE_API_KEY", "STIBEE_LIST_ID",
                "STIBEE_AUTO_EMAIL_URL", "REVIEW_PASSWORD"]:
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
    if st.session_state.get("cold_email_authed"):
        return True
    env = _load_env()
    pw = env.get("REVIEW_PASSWORD", "")
    if not pw:
        return True  # 비밀번호 미설정 시 통과
    entered = st.text_input("비밀번호를 입력하세요", type="password", key="cold_email_pw")
    if entered == pw:
        st.session_state.cold_email_authed = True
        st.rerun()
    elif entered:
        st.error("비밀번호가 일치하지 않습니다.")
    return False


if not _check_auth():
    st.stop()


# ── 세션 초기화 ──
if "ce_step" not in st.session_state:
    st.session_state.ce_step = 1          # 1: 리드 입력, 2: 리서치, 3: 메일 생성, 4: 리뷰/발송
if "ce_lead" not in st.session_state:
    st.session_state.ce_lead = None       # 현재 작업 중인 리드 (dict)
if "ce_research" not in st.session_state:
    st.session_state.ce_research = None   # 리서치 결과
if "ce_email" not in st.session_state:
    st.session_state.ce_email = None      # 생성된 콜드메일
if "ce_html" not in st.session_state:
    st.session_state.ce_html = None       # 생성된 HTML


# ── CSS (Palantir 테마 간소화) ──
st.markdown("""
<style>
    .stApp { background-color: #111418; }
    h1, h2 { color: #E0E0E0 !important; }
    h3 { color: #C5CBD3 !important; }
    .step-indicator {
        display: inline-block; padding: 4px 12px; border-radius: 3px;
        font-size: 12px; font-weight: 600; letter-spacing: 1px;
        margin-right: 8px;
    }
    .step-active { background: #252A31; color: #E0E0E0; border: 1px solid #383E47; }
    .step-done { background: #1C2127; color: #738091; }
    .step-pending { background: transparent; color: #404854; }
</style>
""", unsafe_allow_html=True)


# ── 사이드바 ──
with st.sidebar:
    st.markdown("""
    <div style="padding: 8px 0 16px;">
        <div style="font-size:11px;letter-spacing:2px;color:#5F6B7C;font-weight:600;">DETA COLD EMAIL</div>
        <div style="border-top: 1px solid #2F343C; margin: 10px 0;"></div>
        <div style="font-size:13px; color:#738091;">Track A: 1:1 맞춤 콜드메일</div>
    </div>
    """, unsafe_allow_html=True)

    ce_steps = {1: "리드 입력", 2: "기업 리서치", 3: "메일 생성", 4: "리뷰 & 발송"}
    for num, label in ce_steps.items():
        is_current = num == st.session_state.ce_step
        is_done = num < st.session_state.ce_step
        if is_current:
            st.markdown(f'<span class="step-indicator step-active">STEP {num:02d}  ▸ {label}</span>', unsafe_allow_html=True)
        elif is_done:
            if st.button(f"STEP {num:02d}  {label} ✓", key=f"ce_nav_{num}", use_container_width=True):
                st.session_state.ce_step = num
                st.rerun()
        else:
            st.markdown(f'<span class="step-indicator step-pending">STEP {num:02d}  {label}</span>', unsafe_allow_html=True)

    st.markdown('<div style="border-top:1px solid #2F343C;margin:16px 0;"></div>', unsafe_allow_html=True)

    # CRM 통계
    stats = _crm.get_stats()
    if stats.get("total", 0) > 0:
        st.markdown('<span style="font-size:11px;letter-spacing:2px;color:#5F6B7C;font-weight:600;">LEAD STATUS</span>', unsafe_allow_html=True)
        for status_key in ["new", "researched", "sent", "replied", "meeting_set", "no_response"]:
            cnt = stats.get(status_key, 0)
            if cnt > 0:
                st.markdown(f'<span style="color:#8F99A8;font-size:13px;">{status_key}: {cnt}</span>', unsafe_allow_html=True)


# ── 유틸리티 함수 ──

def _show_research_preview(research: dict):
    """리서치 결과 미리보기"""
    sections = [
        ("산업 트렌드", research.get("industry_context", [])),
        ("기업 뉴스", research.get("company_context", [])),
        ("경쟁사 동향", research.get("competitor_context", [])),
        ("규제 변화", research.get("regulation_context", [])),
    ]
    for section_name, articles in sections:
        if articles:
            with st.expander(f"{section_name} ({len(articles)}건)", expanded=False):
                for art in articles[:3]:
                    st.markdown(f"- **{art.get('title', '제목 없음')}** ({art.get('source', '')})")
                    desc = art.get("description", "")
                    if desc:
                        st.caption(desc[:150])


# ============================================================
# STEP 1: 리드 입력
# ============================================================

if st.session_state.ce_step == 1:
    st.markdown("### 🎯 콜드메일 — 리드 입력")
    st.markdown('<span style="color:#738091;font-size:14px;">콜드메일을 보낼 리드 정보를 입력합니다.</span>', unsafe_allow_html=True)
    st.markdown("")

    # 기존 CRM 리드 선택 또는 신규 입력
    existing_leads = _crm.list_leads(status="new") + _crm.list_leads(status="researched")

    tab_new, tab_existing = st.tabs(["신규 리드 입력", f"기존 리드 선택 ({len(existing_leads)}건)"])

    with tab_new:
        with st.form("new_lead_form"):
            col1, col2 = st.columns(2)
            with col1:
                company = st.text_input("회사명 *", placeholder="삼성엔지니어링")
                contact_name = st.text_input("담당자명 *", placeholder="김OO")
                contact_email = st.text_input("이메일 *", placeholder="kim@company.com")
            with col2:
                contact_title = st.text_input("직함", placeholder="해외사업본부 과장")
                industry = st.text_input("산업 *", placeholder="chemicals")
                trigger = st.text_input("트리거 (연락 계기)", placeholder="최근 사우디 화학플랜트 수주")
            source = st.text_input("리드 출처", value="manual", placeholder="Apollo / KOTRA / 직접")

            submitted = st.form_submit_button("리드 등록 & 다음 단계", use_container_width=True)
            if submitted:
                if not company or not contact_name or not contact_email or not industry:
                    st.error("필수 항목(*)을 모두 입력해주세요.")
                else:
                    lead = _crm.add_lead({
                        "company": company,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "contact_title": contact_title,
                        "industry": industry,
                        "trigger": trigger,
                        "source": source,
                    })
                    st.session_state.ce_lead = lead
                    st.session_state.ce_step = 2
                    st.success(f"리드 등록됨: {lead['lead_id']}")
                    st.rerun()

    with tab_existing:
        if existing_leads:
            for lead in existing_leads:
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f"**{lead.get('company', '')}** — {lead.get('contact_name', '')} "
                        f"({lead.get('contact_email', '')})"
                        f"<br><span style='color:#738091;font-size:12px;'>"
                        f"산업: {lead.get('industry', '')} | 상태: {lead.get('status', '')} | "
                        f"{lead.get('lead_id', '')}</span>",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    if st.button("선택", key=f"sel_{lead['lead_id']}", use_container_width=True):
                        st.session_state.ce_lead = lead
                        # 이미 리서치된 리드는 Step 3으로
                        if lead.get("status") == "researched":
                            st.session_state.ce_research = lead.get("custom_research")
                            st.session_state.ce_step = 3
                        else:
                            st.session_state.ce_step = 2
                        st.rerun()
                st.markdown('<div style="border-top:1px solid #2F343C;margin:8px 0;"></div>', unsafe_allow_html=True)
        else:
            st.info("등록된 신규/리서치 완료 리드가 없습니다. 왼쪽 탭에서 새 리드를 입력하세요.")


# ============================================================
# STEP 2: 기업 리서치
# ============================================================

elif st.session_state.ce_step == 2:
    lead = st.session_state.ce_lead
    if not lead:
        st.warning("리드가 선택되지 않았습니다. Step 1으로 돌아가세요.")
        if st.button("◀️ Step 1로 돌아가기"):
            st.session_state.ce_step = 1
            st.rerun()
        st.stop()

    st.markdown("### 🔬 기업 리서치")
    st.markdown(
        f'<span style="color:#738091;font-size:14px;">'
        f'**{lead["company"]}** ({lead["industry"]}) — {lead["contact_name"]}에 대한 맞춤 리서치를 수행합니다.'
        f'</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # 리드 정보 요약
    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("회사명", lead.get("company", ""))
        col2.metric("산업", lead.get("industry", ""))
        col3.metric("트리거", lead.get("trigger", "-") or "-")

    st.markdown("")

    if st.session_state.ce_research:
        st.success(f"리서치 완료: {st.session_state.ce_research.get('total_articles', 0)}건 수집")
        _show_research_preview(st.session_state.ce_research)
        if st.button("▶️ 메일 생성으로", use_container_width=True):
            st.session_state.ce_step = 3
            st.rerun()
    else:
        if st.button("🔍 기업 리서치 시작", use_container_width=True, type="primary"):
            with st.spinner(f"{lead['company']} 리서치 중... (뉴스 수집 + 분석)"):
                try:
                    from lead_researcher import research_lead, format_research_for_prompt
                    research = research_lead(lead, days=7, max_per_category=3)

                    # CRM 업데이트
                    _crm.update_lead(lead["lead_id"], {
                        "custom_research": research,
                        "status": "researched",
                    })

                    st.session_state.ce_research = research
                    st.session_state.ce_lead["status"] = "researched"
                    st.session_state.ce_lead["custom_research"] = research
                    st.success(f"리서치 완료: {research.get('total_articles', 0)}건 뉴스 수집")
                    st.rerun()
                except Exception as e:
                    st.error(f"리서치 오류: {e}")

    st.markdown("")
    if st.button("◀️ Step 1로 돌아가기"):
        st.session_state.ce_step = 1
        st.rerun()


# ============================================================
# STEP 3: 콜드메일 생성
# ============================================================

elif st.session_state.ce_step == 3:
    lead = st.session_state.ce_lead
    research = st.session_state.ce_research
    if not lead:
        st.warning("리드가 선택되지 않았습니다.")
        st.stop()

    st.markdown("### ✍️ 콜드메일 생성")
    st.markdown(
        f'<span style="color:#738091;font-size:14px;">'
        f'**{lead["company"]}** {lead["contact_name"]}님께 보낼 콜드메일을 AI가 작성합니다.'
        f'</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    if st.session_state.ce_email:
        # 이미 생성된 메일 표시
        email = st.session_state.ce_email
        st.markdown(f"**제목:** {email.get('subject_line', '')}")
        st.markdown(f"**인사:** {email.get('greeting', '')}")
        st.markdown("**본문:**")
        st.markdown(f"<div style='background:#1C2127;border:1px solid #2F343C;border-radius:4px;padding:16px;color:#ABB3BF;line-height:1.8;'>{email.get('body', '').replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#5F6B7C;font-size:13px;'>{email.get('signature', '').replace(chr(10), '<br>')}</span>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 재생성", use_container_width=True):
                st.session_state.ce_email = None
                st.session_state.ce_html = None
                st.rerun()
        with col2:
            if st.button("▶️ 리뷰 & 발송으로", use_container_width=True, type="primary"):
                # HTML 생성
                try:
                    from newsletter_pipeline import ColdEmailBuilder
                    builder = ColdEmailBuilder()
                    html = builder.build_html(email, lead)
                    st.session_state.ce_html = html
                except Exception as e:
                    st.warning(f"HTML 생성 오류: {e}. 인라인 폴백 사용.")
                st.session_state.ce_step = 4
                st.rerun()
    else:
        if st.button("🤖 Claude로 콜드메일 생성", use_container_width=True, type="primary"):
            with st.spinner("콜드메일 작성 중..."):
                try:
                    from newsletter_pipeline import ColdEmailInsightGenerator
                    from lead_researcher import format_research_for_prompt

                    env = _load_env()
                    gen = ColdEmailInsightGenerator(api_key=env.get("ANTHROPIC_API_KEY", ""))

                    research_text = ""
                    if research:
                        research_text = format_research_for_prompt(research)

                    email = gen.generate_cold_email(lead, research_context=research_text)
                    st.session_state.ce_email = email
                    st.success("콜드메일 생성 완료")
                    st.rerun()
                except Exception as e:
                    st.error(f"콜드메일 생성 오류: {e}")

    st.markdown("")
    if st.button("◀️ Step 2로 돌아가기"):
        st.session_state.ce_step = 2
        st.rerun()


# ============================================================
# STEP 4: 리뷰 & 발송
# ============================================================

elif st.session_state.ce_step == 4:
    lead = st.session_state.ce_lead
    email = st.session_state.ce_email
    html = st.session_state.ce_html

    if not lead or not email:
        st.warning("메일이 생성되지 않았습니다.")
        st.stop()

    st.markdown("### 📤 리뷰 & 발송")
    st.markdown(
        f'<span style="color:#738091;font-size:14px;">'
        f'**{lead.get("contact_email", "")}**로 콜드메일을 발송합니다.'
        f'</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # 미리보기
    col_preview, col_action = st.columns([3, 1])

    with col_preview:
        st.markdown(f"**제목:** {email.get('subject_line', '')}")
        st.markdown(f"**수신:** {lead.get('contact_name', '')} ({lead.get('contact_email', '')})")
        st.markdown("---")

        if html:
            with st.expander("HTML 미리보기", expanded=True):
                import streamlit.components.v1 as components
                components.html(html, height=400, scrolling=True)
        else:
            st.markdown(f"**인사:** {email.get('greeting', '')}")
            st.markdown(f"**본문:** {email.get('body', '')}")

    with col_action:
        st.markdown("**발송 방법**")

        env = _load_env()
        auto_email_url = env.get("STIBEE_AUTO_EMAIL_URL", "")

        if auto_email_url:
            if st.button("📧 스티비 자동이메일 발송", use_container_width=True, type="primary"):
                with st.spinner("발송 중..."):
                    try:
                        from stibee_integration import StibeeClient
                        client = StibeeClient(api_key=env.get("STIBEE_API_KEY", ""))

                        # HTML 생성 (아직 없으면)
                        if not html:
                            from newsletter_pipeline import ColdEmailBuilder
                            builder = ColdEmailBuilder()
                            html = builder.build_html(email, lead)
                            st.session_state.ce_html = html

                        success, msg = client.trigger_auto_email(
                            auto_email_url=auto_email_url,
                            subscriber_email=lead.get("contact_email", ""),
                            custom_fields={
                                "name": lead.get("contact_name", ""),
                                "company": lead.get("company", ""),
                                "subject_line": email.get("subject_line", ""),
                                "greeting": email.get("greeting", ""),
                                "insight_html": html,
                            },
                        )

                        if success:
                            st.success(f"발송 성공: {msg}")
                            # CRM 상태 업데이트
                            _crm.update_status(lead["lead_id"], "sent",
                                               note=f"콜드메일 발송 → {lead.get('contact_email', '')}")
                        else:
                            st.error(f"발송 실패: {msg}")
                    except Exception as e:
                        st.error(f"발송 오류: {e}")

        # HTML 다운로드
        if html:
            st.download_button(
                "📥 HTML 다운로드",
                data=html,
                file_name=f"cold_email_{lead.get('company', 'lead')}.html",
                mime="text/html",
                use_container_width=True,
            )

        # 수동 복사
        if html:
            if st.button("📋 HTML 복사", use_container_width=True):
                st.code(html[:500] + "...", language="html")
                st.info("전체 HTML은 다운로드 버튼을 이용하세요.")

    st.markdown("")
    col_back, col_new = st.columns(2)
    with col_back:
        if st.button("◀️ Step 3으로 돌아가기", use_container_width=True):
            st.session_state.ce_step = 3
            st.rerun()
    with col_new:
        if st.button("🔄 새 콜드메일 시작", use_container_width=True):
            st.session_state.ce_step = 1
            st.session_state.ce_lead = None
            st.session_state.ce_research = None
            st.session_state.ce_email = None
            st.session_state.ce_html = None
            st.rerun()
