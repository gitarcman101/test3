"""
DETA Newsletter Pipeline — Streamlit Dashboard
================================================
인간 검토 포인트가 포함된 뉴스레터 자동화 대시보드

실행:  streamlit run streamlit_app.py
"""

import streamlit as st
import json
import re
import time
import os
import sys
from datetime import datetime
from pathlib import Path

MAX_LEADS = 10  # 한 번에 처리할 최대 리드 수

from pipeline_store import PipelineStore
_store = PipelineStore()

# ── 인코딩 설정 ──
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except (OSError, AttributeError):
    pass  # Streamlit 환경에서는 reconfigure 불가

# ── 페이지 설정 ──
st.set_page_config(
    page_title="DETA Newsletter Pipeline",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Palantir 다크 테마 적용 ──
from ui_theme import apply_theme
apply_theme()


# ============================================================
# 환경 변수 로드 (인증보다 먼저 정의되어야 함)
# ============================================================

def load_env_keys():
    """config/.env 또는 Streamlit Cloud secrets에서 API 키 로드"""
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
    # 2) Streamlit Cloud secrets (st.secrets) — 파일이 없을 때 fallback
    if not env:
        try:
            for k, v in st.secrets.items():
                if isinstance(v, str):
                    env[k] = v
        except Exception:
            pass
    # 3) 환경변수 fallback (개별 키)
    for key in ["ANTHROPIC_API_KEY", "STIBEE_API_KEY", "STIBEE_LIST_ID",
                "STIBEE_AUTO_EMAIL_URL", "APOLLO_API_KEY", "REVIEW_PASSWORD",
                "SENDER_EMAIL", "SENDER_NAME"]:
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]
    return env


# ============================================================
# 메인 앱 인증 (리뷰 대시보드와 동일한 REVIEW_PASSWORD 사용)
# ============================================================

def _check_main_auth():
    """비밀번호 인증. REVIEW_PASSWORD가 env에 없으면 인증 스킵."""
    env = load_env_keys()
    password = env.get("REVIEW_PASSWORD", "")

    if not password:
        return True  # 비밀번호 미설정 시 인증 없이 접근 허용

    if st.session_state.get("authenticated"):
        return True

    st.markdown("""
    <div class="palantir-header">DETA PIPELINE</div>
    <div class="palantir-title">뉴스레터 파이프라인</div>
    <div class="palantir-sub">접근 권한이 필요합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.form("main_auth_form"):
        pw_input = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", type="primary")

    if submitted:
        if pw_input == password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    st.caption("config/.env의 REVIEW_PASSWORD로 접근을 제어합니다.")
    return False


if not _check_main_auth():
    st.stop()


# ============================================================
# 세션 상태 초기화
# ============================================================

def init_session():
    defaults = {
        "step": 1,
        "leads": [],
        # ── multi-lead 구조 (dict-of-dicts, key=lead index) ──
        "news_by_lead": {},            # {lead_idx: [article_dicts]}
        "selected_news_by_lead": {},   # {lead_idx: [indices]}
        "insights_by_lead": {},        # {lead_idx: insight_dict}
        "html_by_lead": {},            # {lead_idx: html_string}
        "html_paths_by_lead": {},      # {lead_idx: filepath}
        "send_status_by_lead": {},     # {lead_idx: "pending"|"sent"|"failed"}
        "send_errors_by_lead": {},     # {lead_idx: error_message}
        "current_lead_idx": 0,         # Step 2~4 리드 선택 UI
        "current_run_id": "",          # PipelineStore run ID
        "pipeline_log": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── legacy 키 마이그레이션 (구 singular → 신 multi-lead) ──
    _legacy_keys = ["news_results", "selected_news_indices", "insight_data",
                    "html_content", "html_file_path", "stibee_email_id"]
    for lk in _legacy_keys:
        if lk in st.session_state:
            del st.session_state[lk]

init_session()


def _invalidate_downstream(from_step: int, lead_idx: int = None):
    """상위 스텝 변경 시 하위 데이터 자동 클리어"""
    if lead_idx is not None:
        targets = []
        if from_step <= 1:
            targets = ["news_by_lead", "selected_news_by_lead",
                       "insights_by_lead", "html_by_lead",
                       "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        elif from_step <= 2:
            targets = ["insights_by_lead", "html_by_lead",
                       "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        elif from_step <= 3:
            targets = ["html_by_lead", "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        for t in targets:
            if lead_idx in st.session_state.get(t, {}):
                del st.session_state[t][lead_idx]
    else:
        # 전체 리드 클리어
        targets = []
        if from_step <= 1:
            targets = ["news_by_lead", "selected_news_by_lead",
                       "insights_by_lead", "html_by_lead",
                       "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        elif from_step <= 2:
            targets = ["insights_by_lead", "html_by_lead",
                       "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        elif from_step <= 3:
            targets = ["html_by_lead", "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]
        for t in targets:
            st.session_state[t] = {}


def _article_to_dict(article, category: str) -> dict:
    """뉴스 기사 객체를 표준 dict로 변환 (중복 패턴 통합)"""
    return {
        "title": article.title if hasattr(article, "title") else article.get("title", ""),
        "source": article.source if hasattr(article, "source") else article.get("source", ""),
        "category": category,
        "url": article.url if hasattr(article, "url") else article.get("url", ""),
        "has_body": bool(article.full_text if hasattr(article, "full_text") else article.get("full_text", "")),
        "description": (article.description if hasattr(article, "description") else article.get("description", ""))[:200],
        "_raw": article,
    }


def _render_pipeline_tracker():
    """리드별 파이프라인 진행 상황을 HTML 테이블로 렌더링"""
    leads = st.session_state.get("leads", [])
    if not leads:
        return

    run_id = st.session_state.get("current_run_id", "")
    reviews = {}
    if run_id:
        reviews = _store.get_reviews(run_id)

    rows_html = ""
    for i, ld in enumerate(leads):
        si = str(i)
        has_news = i in st.session_state.get("news_by_lead", {})
        has_insight = i in st.session_state.get("insights_by_lead", {})
        has_html = i in st.session_state.get("html_by_lead", {})
        review_info = reviews.get(si, {})
        review_st = review_info.get("status", "")
        send_st = st.session_state.get("send_status_by_lead", {}).get(i, "")

        def _dot(done, failed=False, pending=False):
            if failed:
                return '<span style="color:#C5504C;">✗</span>'
            if pending:
                return '<span style="color:#A68B2D;">◐</span>'
            if done:
                return '<span style="color:#666666;">●</span>'
            return '<span style="color:#333333;">○</span>'

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
            f'<tr style="border-bottom:1px solid #222222;">'
            f'<td style="padding:4px 8px;color:#AAAAAA;font-size:12px;">{name}</td>'
            f'<td style="padding:4px 8px;color:#555555;font-size:12px;">{company}</td>'
            f'<td style="text-align:center;padding:4px;">{news_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{ai_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{html_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{review_dot}</td>'
            f'<td style="text-align:center;padding:4px;">{send_dot}</td>'
            f'</tr>'
        )

    table_html = f"""
    <div style="background:#111111;border:1px solid #222222;border-radius:2px;padding:8px;margin-bottom:12px;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="border-bottom:1px solid #333333;">
                    <th style="text-align:left;padding:4px 8px;color:#555555;font-size:10px;letter-spacing:1px;">LEAD</th>
                    <th style="text-align:left;padding:4px 8px;color:#555555;font-size:10px;letter-spacing:1px;">CO.</th>
                    <th style="text-align:center;padding:4px;color:#555555;font-size:10px;">NEWS</th>
                    <th style="text-align:center;padding:4px;color:#555555;font-size:10px;">AI</th>
                    <th style="text-align:center;padding:4px;color:#555555;font-size:10px;">HTML</th>
                    <th style="text-align:center;padding:4px;color:#555555;font-size:10px;">REV</th>
                    <th style="text-align:center;padding:4px;color:#555555;font-size:10px;">SEND</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ============================================================
# 유틸리티
# ============================================================

def log(msg: str, level: str = "info"):
    """파이프라인 로그 추가"""
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.pipeline_log.append({"time": ts, "level": level, "msg": msg})


# ============================================================
# 사이드바
# ============================================================

with st.sidebar:
    # Palantir 스타일 브랜딩
    st.markdown("""
    <div style="padding: 8px 0 16px;">
        <div class="palantir-header">DETA PIPELINE</div>
        <div style="border-top: 1px solid #222222; margin: 10px 0;"></div>
        <div style="font-size:13px; color:#666666;">Newsletter Automation</div>
    </div>
    """, unsafe_allow_html=True)

    # 현재 단계 표시 — 클릭 네비게이션 (모든 스텝 클릭 가능)
    steps = {
        1: ("01", "리드 입력"),
        2: ("02", "뉴스 수집"),
        3: ("03", "인사이트 생성"),
        4: ("04", "검토 & 편집"),
        5: ("05", "발송"),
    }
    for num, (code, label) in steps.items():
        if num == st.session_state.step:
            # 현재 활성 스텝 — 클릭 가능하지만 시각적 강조
            st.markdown(f"""
            <div class="step-card step-active" style="cursor:default;">
                <span style="color:#555555;font-size:10px;letter-spacing:1.5px;font-weight:600;">STEP {code}</span><br>
                <span style="color:#E0E0E0;font-weight:600;font-size:14px;">▸ {label}</span>
            </div>""", unsafe_allow_html=True)
        else:
            # 완료 / 미래 스텝 모두 클릭 가능
            done = num < st.session_state.step
            suffix = " ✓" if done else ""
            if st.button(f"STEP {code}  {label}{suffix}", key=f"nav_{num}", use_container_width=True):
                st.session_state.step = num
                st.rerun()

    st.markdown('<div style="border-top:1px solid #222222;margin:16px 0;"></div>', unsafe_allow_html=True)

    # API 상태
    env = load_env_keys()
    st.markdown('<span class="palantir-header">CONNECTIONS</span>', unsafe_allow_html=True)
    apis = {
        "Anthropic": bool(env.get("ANTHROPIC_API_KEY")),
        "Stibee": bool(env.get("STIBEE_API_KEY")),
        "Apollo": bool(env.get("APOLLO_API_KEY")),
    }
    for name, ok in apis.items():
        dot = "🟢" if ok else "⚫"
        color = "#888888" if ok else "#404854"
        st.markdown(f'<span style="color:{color};font-size:13px;">{dot} {name}</span>', unsafe_allow_html=True)

    st.markdown('<div style="border-top:1px solid #222222;margin:16px 0;"></div>', unsafe_allow_html=True)

    # 파이프라인 로그
    if st.session_state.pipeline_log:
        with st.expander("ACTIVITY LOG", expanded=False):
            for entry in reversed(st.session_state.pipeline_log[-20:]):
                icon = {"info": "·", "success": "✓", "warning": "!", "error": "✗"}.get(entry["level"], "·")
                clr = {"info": "#555555", "success": "#666666", "warning": "#A68B2D", "error": "#C5504C"}.get(entry["level"], "#555555")
                st.markdown(
                    f'<span style="color:#404854;font-size:11px;">{entry["time"]}</span> '
                    f'<span style="color:{clr};font-size:12px;">{icon} {entry["msg"]}</span>',
                    unsafe_allow_html=True,
                )


# ============================================================
# STEP 1: 리드 입력
# ============================================================

if st.session_state.step == 1:
    st.markdown("""
    <div class="palantir-header">STEP 01</div>
    <div class="palantir-title">리드 입력</div>
    <div class="palantir-sub">뉴스레터를 받을 담당자 정보를 입력합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    # ── 이전 파이프라인 불러오기 ──
    prev_runs = _store.list_runs()
    if prev_runs and not st.session_state.get("current_run_id"):
        with st.expander("📂 이전 파이프라인 불러오기", expanded=False):
            for run in prev_runs[:5]:
                run_label = f"{run.get('created_at', '')[:16]} — {run.get('total_leads', 0)}명, {run.get('status', '')}"
                col_info, col_load = st.columns([4, 1])
                with col_info:
                    st.caption(run_label)
                with col_load:
                    if st.button("불러오기", key=f"load_{run['run_id']}"):
                        data = _store.load_run(run["run_id"])
                        if data.get("leads"):
                            st.session_state.leads = data["leads"]
                            st.session_state.current_run_id = run["run_id"]
                            # news 복구 (인덱스를 int로 변환)
                            if data.get("news"):
                                for k, v in data["news"].items():
                                    st.session_state.news_by_lead[int(k)] = v
                                    st.session_state.selected_news_by_lead[int(k)] = list(range(len(v)))
                            # insights 복구
                            if data.get("insights"):
                                for k, v in data["insights"].items():
                                    st.session_state.insights_by_lead[int(k)] = v
                            # html 복구
                            if data.get("html"):
                                for k, v in data["html"].items():
                                    st.session_state.html_by_lead[int(k)] = v
                            log(f"파이프라인 불러옴: {run['run_id']}", "success")
                            st.rerun()

    tab_apollo, tab_manual, tab_upload = st.tabs(["🔍 Apollo Enrichment", "✏️ 직접 입력", "📁 파일 업로드"])

    with tab_manual:
        col1, col2 = st.columns(2)
        with col1:
            lead_name = st.text_input("이름 *", placeholder="김피엠")
            lead_email = st.text_input("이메일 *", placeholder="user@company.com")
            lead_title = st.text_input("직함", placeholder="PM, CTO, 전략기획팀장 등")
            lead_company = st.text_input("회사명 *", placeholder="데타")

        with col2:
            lead_industry = st.selectbox("산업 분류", [
                "화학 및 재료",
                "정보통신기술(ICT)",
                "전자(반도체 등)",
                "자동화",
                "자동차",
                "우주 및 국방",
                "에너지",
                "식음료",
                "소비재 및 서비스",
                "생명과학 및 헬스케어",
                "교육",
                "농업",
                "기타 (직접 입력)",
            ])
            if lead_industry == "기타 (직접 입력)":
                lead_industry = st.text_input("산업 직접 입력", placeholder="예: 물류/운송, 교육, 에너지 등")

            lead_domain = st.text_input("회사 도메인", placeholder="deta.kr")
            lead_size = st.text_input("직원 규모", placeholder="10")
            lead_location = st.text_input("소재지", placeholder="서울, 한국")

        lead_description = st.text_area(
            "회사 설명",
            placeholder="AI 컨설팅 전문 기업. B2B 대상 AI 전략 수립, 데이터 분석, AI 솔루션 도입 컨설팅 제공.",
            height=80,
        )

        col_add, col_clear = st.columns([1, 1])
        with col_add:
            if st.button("➕ 리드 추가", type="primary", use_container_width=True):
                if len(st.session_state.leads) >= MAX_LEADS:
                    st.warning(f"최대 {MAX_LEADS}명까지 추가할 수 있습니다.")
                elif lead_name and lead_email and lead_company:
                    new_lead = {
                        "이름": lead_name,
                        "이메일": lead_email,
                        "직함": lead_title,
                        "회사명": lead_company,
                        "회사_산업": lead_industry,
                        "회사_도메인": lead_domain,
                        "회사_설명": lead_description,
                        "회사_규모": lead_size,
                        "회사_위치": lead_location,
                    }
                    st.session_state.leads.append(new_lead)
                    log(f"리드 추가: {lead_name} ({lead_company})", "success")
                    st.rerun()
                else:
                    st.error("이름, 이메일, 회사명은 필수입니다.")

        with col_clear:
            if st.button("🗑️ 전체 초기화", use_container_width=True):
                st.session_state.leads = []
                _invalidate_downstream(1)
                st.rerun()

    with tab_apollo:
        st.markdown("""
        <div style="background:#111111;border:1px solid #222222;border-radius:2px;padding:16px;margin-bottom:16px;">
            <span class="palantir-header">APOLLO ENRICHMENT</span>
            <p style="color:#888888;font-size:13px;margin-top:8px;">이름 + 회사(도메인)로 Apollo API에서 이메일, 직함, 산업, 회사 정보를 자동 수집합니다.</p>
        </div>
        """, unsafe_allow_html=True)

        env = load_env_keys()
        if not env.get("APOLLO_API_KEY"):
            st.markdown("""
            <div style="background:#1A1A1A;border:1px solid #333333;border-radius:2px;padding:16px;">
                <span style="color:#C5504C;">⚫ APOLLO_API_KEY 미설정</span><br>
                <span style="color:#555555;font-size:12px;">config/.env에 APOLLO_API_KEY=your_key를 추가하세요.</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                ap_first = st.text_input("First Name", placeholder="Piem", key="ap_first")
                ap_last = st.text_input("Last Name", placeholder="Kim", key="ap_last")
            with col_a2:
                ap_domain = st.text_input("회사 도메인", placeholder="deta.kr", key="ap_domain")
                ap_org = st.text_input("또는 회사명", placeholder="DETA", key="ap_org")

            ap_email_input = st.text_input("또는 이메일로 직접 조회", placeholder="user@company.com", key="ap_email")
            ap_linkedin = st.text_input("또는 LinkedIn URL", placeholder="https://www.linkedin.com/in/...", key="ap_linkedin")

            if st.button("🔍 Apollo Enrichment 실행", type="primary", use_container_width=True):
                with st.spinner("Apollo API에서 정보를 조회하고 있습니다..."):
                    try:
                        from apollo_lead_extractor import ApolloEnrichmentClient, load_api_key
                        api_key = load_api_key()
                        client = ApolloEnrichmentClient(api_key)

                        # 검색 파라미터 구성
                        params = {}
                        if ap_first:
                            params["first_name"] = ap_first
                        if ap_last:
                            params["last_name"] = ap_last
                        if ap_domain:
                            params["domain"] = ap_domain
                        if ap_org:
                            params["organization_name"] = ap_org
                        if ap_email_input:
                            params["email"] = ap_email_input
                        if ap_linkedin:
                            params["linkedin_url"] = ap_linkedin

                        if not params:
                            st.error("최소 1개 이상의 검색 파라미터를 입력하세요.")
                        else:
                            result = client.enrich_person(params)

                            if result and result.get("person"):
                                person = result["person"]
                                org = person.get("organization", {}) or {}

                                # 결과를 리드 형식으로 변환
                                enriched_lead = {
                                    "이름": person.get("name", f"{person.get('first_name','')} {person.get('last_name','')}").strip(),
                                    "이메일": person.get("email", ""),
                                    "직함": person.get("title", ""),
                                    "회사명": org.get("name", person.get("organization_name", "")),
                                    "회사_산업": org.get("industry", ""),
                                    "회사_도메인": org.get("primary_domain", person.get("organization", {}).get("website_url", "")),
                                    "회사_설명": org.get("short_description", ""),
                                    "회사_규모": str(org.get("estimated_num_employees", "")),
                                    "회사_위치": f"{org.get('city','')}, {org.get('country','')}".strip(", "),
                                }

                                st.session_state["_apollo_result"] = enriched_lead
                                log(f"Apollo Enrichment 성공: {enriched_lead['이름']} ({enriched_lead['회사명']})", "success")
                                st.rerun()
                            else:
                                st.warning("매칭되는 결과가 없습니다. 다른 파라미터를 시도해보세요.")
                                log("Apollo Enrichment: 매칭 결과 없음", "warning")

                    except Exception as e:
                        st.error(f"Apollo API 오류: {e}")
                        log(f"Apollo API 오류: {e}", "error")

            # Enrichment 결과 표시
            if st.session_state.get("_apollo_result"):
                enriched = st.session_state["_apollo_result"]
                st.markdown("""
                <div style="border-top:1px solid #222222;margin:16px 0;"></div>
                <span class="palantir-header">ENRICHMENT RESULT</span>
                """, unsafe_allow_html=True)

                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    st.markdown(f"**이름:** {enriched['이름']}")
                    st.markdown(f"**이메일:** {enriched['이메일']}")
                    st.markdown(f"**직함:** {enriched['직함']}")
                    st.markdown(f"**회사명:** {enriched['회사명']}")
                with col_r2:
                    st.markdown(f"**산업:** {enriched['회사_산업']}")
                    st.markdown(f"**도메인:** {enriched['회사_도메인']}")
                    st.markdown(f"**규모:** {enriched['회사_규모']}명")
                    st.markdown(f"**위치:** {enriched['회사_위치']}")

                if enriched.get("회사_설명"):
                    st.caption(f"💡 {enriched['회사_설명']}")

                col_accept, col_skip = st.columns(2)
                with col_accept:
                    if st.button("✅ 리드로 추가", type="primary", use_container_width=True):
                        if len(st.session_state.leads) >= MAX_LEADS:
                            st.warning(f"최대 {MAX_LEADS}명까지 추가할 수 있습니다.")
                        else:
                            st.session_state.leads.append(enriched)
                            del st.session_state["_apollo_result"]
                            log(f"Apollo 리드 추가: {enriched['이름']}", "success")
                            st.rerun()
                with col_skip:
                    if st.button("🗑️ 무시", use_container_width=True):
                        del st.session_state["_apollo_result"]
                        st.rerun()

    with tab_upload:
        uploaded = st.file_uploader("CSV 또는 Excel 파일 업로드", type=["csv", "xlsx"])
        st.caption("필수 컬럼: 이름(name), 이메일(email), 회사명(company) — 첫 행이 헤더, 컬럼 순서 무관")
        if uploaded:
            try:
                import pandas as pd
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)

                st.dataframe(df, use_container_width=True)
                st.info(f"📊 {len(df)}건의 리드가 발견되었습니다.")

                if st.button("📥 리드 불러오기", type="primary"):
                    added = 0
                    for _, row in df.iterrows():
                        if len(st.session_state.leads) >= MAX_LEADS:
                            st.warning(f"최대 {MAX_LEADS}명 제한으로 {added}건만 추가되었습니다.")
                            break
                        lead = {
                            "이름": str(row.get("이름", row.get("name", ""))),
                            "이메일": str(row.get("이메일", row.get("email", ""))),
                            "직함": str(row.get("직함", row.get("title", ""))),
                            "회사명": str(row.get("회사명", row.get("company", ""))),
                            "회사_산업": str(row.get("회사_산업", row.get("industry", ""))),
                            "회사_도메인": str(row.get("회사_도메인", row.get("company_domain", ""))),
                            "회사_설명": str(row.get("회사_설명", row.get("company_description", ""))),
                            "회사_규모": str(row.get("회사_규모", row.get("company_size", ""))),
                            "회사_위치": str(row.get("회사_위치", row.get("company_location", ""))),
                        }
                        if lead["이메일"] and lead["이메일"] != "nan":
                            st.session_state.leads.append(lead)
                            added += 1
                    log(f"파일에서 {added}건 리드 불러옴", "success")
                    st.rerun()
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")

    # 현재 리드 목록
    st.divider()
    if st.session_state.leads:
        st.markdown(f"### 📋 등록된 리드 ({len(st.session_state.leads)}건)")

        # 수정 모드 관리
        editing_idx = st.session_state.get("_editing_lead_idx", None)

        for i, lead in enumerate(st.session_state.leads):
            if editing_idx == i:
                # ── 수정 폼 ──
                st.markdown(f"""
                <div style="background:#1A1A1A;border:1px solid #666666;border-radius:2px;padding:12px 16px;margin:4px 0;">
                    <span style="color:#E0E0E0;font-size:13px;font-weight:600;">리드 수정</span>
                </div>
                """, unsafe_allow_html=True)
                ec1, ec2 = st.columns(2)
                with ec1:
                    ed_name = st.text_input("이름", value=lead["이름"], key=f"ed_name_{i}")
                    ed_email = st.text_input("이메일", value=lead["이메일"], key=f"ed_email_{i}")
                    ed_title = st.text_input("직함", value=lead.get("직함", ""), key=f"ed_title_{i}")
                    ed_company = st.text_input("회사명", value=lead["회사명"], key=f"ed_company_{i}")
                with ec2:
                    ed_industry = st.text_input("산업", value=lead.get("회사_산업", ""), key=f"ed_industry_{i}")
                    ed_domain = st.text_input("도메인", value=lead.get("회사_도메인", ""), key=f"ed_domain_{i}")
                    ed_size = st.text_input("규모", value=lead.get("회사_규모", ""), key=f"ed_size_{i}")
                    ed_location = st.text_input("위치", value=lead.get("회사_위치", ""), key=f"ed_location_{i}")
                ed_desc = st.text_area("설명", value=lead.get("회사_설명", ""), key=f"ed_desc_{i}", height=60)

                ec_save, ec_cancel = st.columns(2)
                with ec_save:
                    if st.button("💾 저장", key=f"save_{i}", type="primary", use_container_width=True):
                        st.session_state.leads[i] = {
                            "이름": ed_name, "이메일": ed_email, "직함": ed_title,
                            "회사명": ed_company, "회사_산업": ed_industry,
                            "회사_도메인": ed_domain, "회사_설명": ed_desc,
                            "회사_규모": ed_size, "회사_위치": ed_location,
                        }
                        _invalidate_downstream(1, i)
                        st.session_state["_editing_lead_idx"] = None
                        log(f"리드 수정 완료: {ed_name}", "success")
                        st.rerun()
                with ec_cancel:
                    if st.button("취소", key=f"cancel_{i}", use_container_width=True):
                        st.session_state["_editing_lead_idx"] = None
                        st.rerun()
            else:
                # ── 일반 표시 ──
                col_info, col_edit, col_del = st.columns([5, 1, 1])
                with col_info:
                    st.markdown(
                        f"**{lead['이름']}** ({lead.get('직함', '')}) — "
                        f"{lead['회사명']} · {lead['이메일']}"
                    )
                with col_edit:
                    if st.button("✏️", key=f"edit_{i}"):
                        st.session_state["_editing_lead_idx"] = i
                        st.rerun()
                with col_del:
                    if st.button("❌", key=f"del_{i}"):
                        _invalidate_downstream(1, i)
                        st.session_state.leads.pop(i)
                        # 삭제된 리드 이후의 인덱스 재정렬
                        for store_name in ["news_by_lead", "selected_news_by_lead",
                                           "insights_by_lead", "html_by_lead",
                                           "html_paths_by_lead", "send_status_by_lead", "send_errors_by_lead"]:
                            old_store = st.session_state.get(store_name, {})
                            new_store = {}
                            for k, v in old_store.items():
                                if k < i:
                                    new_store[k] = v
                                elif k > i:
                                    new_store[k - 1] = v
                            st.session_state[store_name] = new_store
                        st.rerun()

        st.divider()
        if st.button("▶️ Step 2: 뉴스 수집으로 이동", type="primary", use_container_width=True):
            # 파이프라인 run 생성/갱신
            if not st.session_state.get("current_run_id"):
                run_id = _store.create_run(st.session_state.leads)
                st.session_state.current_run_id = run_id
                log(f"파이프라인 생성: {run_id}", "info")
            st.session_state.step = 2
            log("Step 2로 이동", "info")
            st.rerun()
    else:
        st.info("아직 등록된 리드가 없습니다. 위에서 리드를 추가하세요.")


# ============================================================
# STEP 2: 뉴스 수집
# ============================================================

elif st.session_state.step == 2:
    st.markdown("""
    <div class="palantir-header">STEP 02</div>
    <div class="palantir-title">뉴스 수집</div>
    <div class="palantir-sub">리드별 산업/기업 뉴스를 수집하고 인사이트에 사용할 기사를 선택합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.expander("📊 파이프라인 트래커", expanded=False):
        _render_pipeline_tracker()

    if not st.session_state.leads:
        st.warning("리드가 없습니다. Step 1으로 돌아가세요.")
        if st.button("◀️ Step 1로 돌아가기"):
            st.session_state.step = 1
            st.rerun()
    else:
        leads = st.session_state.leads

        # ── 전체 리드 요약 테이블 ──
        import pandas as pd
        summary_data = []
        for i, ld in enumerate(leads):
            has_news = i in st.session_state.news_by_lead
            n_news = len(st.session_state.news_by_lead.get(i, []))
            n_sel = len(st.session_state.selected_news_by_lead.get(i, []))
            summary_data.append({
                "": i + 1,
                "이름": ld["이름"],
                "회사": ld["회사명"],
                "산업": ld.get("회사_산업", ""),
                "뉴스": f"{n_sel}/{n_news}" if has_news else "미수집",
            })
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

        # ── 전체 뉴스 수집 버튼 ──
        any_missing = any(i not in st.session_state.news_by_lead for i in range(len(leads)))
        if any_missing:
            if st.button("🔍 전체 뉴스 수집 시작", type="primary", use_container_width=True):
                try:
                    from newsletter_pipeline import NewsCollectorWrapper, _map_industry
                    collector = NewsCollectorWrapper(crawl_body=True)
                    _industry_news_cache = {}  # 산업별 캐시

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, ld in enumerate(leads):
                        if i in st.session_state.news_by_lead:
                            continue  # 이미 수집된 리드 건너뛰기

                        status_text.text(f"뉴스 수집 중: {ld['이름']} ({ld['회사명']}) [{i+1}/{len(leads)}]")

                        industry = _map_industry(ld.get("회사_산업", ""))
                        all_news = []

                        # 산업 뉴스 (캐싱)
                        if industry not in _industry_news_cache:
                            _industry_news_cache[industry] = collector.collect_by_industry(industry)
                        for article in _industry_news_cache[industry]:
                            cat = article.category_label if hasattr(article, "category_label") else article.get("category_label", "")
                            all_news.append(_article_to_dict(article, cat))

                        # 기업 뉴스 (리드별 개별)
                        company_news = collector.collect_by_company(ld["회사명"], 2)
                        for article in (company_news or []):
                            all_news.append(_article_to_dict(article, "기업 뉴스"))

                        st.session_state.news_by_lead[i] = all_news
                        st.session_state.selected_news_by_lead[i] = list(range(len(all_news)))
                        progress_bar.progress((i + 1) / len(leads))

                    status_text.text("전체 뉴스 수집 완료!")
                    total = sum(len(v) for v in st.session_state.news_by_lead.values())
                    log(f"전체 뉴스 수집 완료: {len(leads)}명, 총 {total}건", "success")

                    # 파이프라인 스토어에 뉴스 저장
                    if st.session_state.get("current_run_id"):
                        _store.save_news(st.session_state.current_run_id, st.session_state.news_by_lead)

                    st.rerun()

                except Exception as e:
                    st.error(f"뉴스 수집 실패: {e}")
                    log(f"뉴스 수집 실패: {e}", "error")

        # ── 리드별 뉴스 선택 UI ──
        if st.session_state.news_by_lead:
            st.divider()

            # 리드 선택 드롭다운
            lead_options = [f"{i+1}. {ld['이름']} ({ld['회사명']})" for i, ld in enumerate(leads)]
            cur_idx = st.session_state.current_lead_idx
            if cur_idx >= len(leads):
                cur_idx = 0
                st.session_state.current_lead_idx = 0

            selected_label = st.selectbox("리드 선택", lead_options, index=cur_idx, key="s2_lead_select")
            sel_idx = lead_options.index(selected_label)
            st.session_state.current_lead_idx = sel_idx

            cur_lead = leads[sel_idx]
            cur_news = st.session_state.news_by_lead.get(sel_idx, [])
            cur_selected = st.session_state.selected_news_by_lead.get(sel_idx, [])

            if cur_news:
                st.markdown(f"### {cur_lead['이름']} — 수집된 뉴스 ({len(cur_news)}건, 선택 {len(cur_selected)}건)")
                st.caption("인사이트 생성에 사용할 뉴스를 선택/해제하세요.")

                new_selected = []
                for ni, news in enumerate(cur_news):
                    col_check, col_info, col_status = st.columns([0.5, 5, 1])
                    with col_check:
                        checked = st.checkbox(
                            "",
                            value=ni in cur_selected,
                            key=f"news_{sel_idx}_{ni}",
                        )
                        if checked:
                            new_selected.append(ni)
                    with col_info:
                        st.markdown(f"**[{news['category']}]** {news['title']}")
                        st.caption(f"📰 {news['source']} — {news['description'][:100]}...")
                    with col_status:
                        if news["has_body"]:
                            st.markdown("🟢 본문")
                        else:
                            st.markdown("🟡 제목만")

                st.session_state.selected_news_by_lead[sel_idx] = new_selected

                # ── 뉴스 추가 검색 ──
                st.divider()
                st.markdown("### 🔎 뉴스 추가 검색")
                st.caption("키워드로 추가 검색하여 이 리드의 뉴스 목록에 추가합니다.")
                add_col1, add_col2 = st.columns([3, 1])
                with add_col1:
                    add_query = st.text_input("검색 키워드", placeholder="예: 반도체 수출 규제", key="add_news_query")
                with add_col2:
                    st.markdown("")
                    add_search = st.button("🔍 추가 검색", use_container_width=True)

                if add_search and add_query:
                    with st.spinner(f"'{add_query}' 검색 중..."):
                        try:
                            from newsletter_pipeline import NewsCollectorWrapper
                            collector = NewsCollectorWrapper(crawl_body=True)
                            extra_articles = []
                            results = collector._collector.rss.search(add_query, max_results=5, days=14)
                            for r in results:
                                article = collector._collector._process_result(r, "기타", "search", "추가 검색")
                                if article:
                                    extra_articles.append(article)

                            if extra_articles:
                                for article in extra_articles:
                                    st.session_state.news_by_lead[sel_idx].append(
                                        _article_to_dict(article, "추가 검색")
                                    )
                                _invalidate_downstream(2, sel_idx)
                                log(f"추가 검색 '{add_query}': {len(extra_articles)}건 → {cur_lead['이름']}", "success")
                                st.rerun()
                            else:
                                st.warning("추가 검색 결과가 없습니다.")
                        except Exception as e:
                            st.error(f"추가 검색 실패: {e}")
            else:
                st.info(f"{cur_lead['이름']}의 뉴스가 아직 수집되지 않았습니다.")

            st.divider()
            col_back, col_next = st.columns(2)
            with col_back:
                if st.button("◀️ Step 1로 돌아가기", use_container_width=True):
                    st.session_state.step = 1
                    st.rerun()
            with col_next:
                total_sel = sum(len(v) for v in st.session_state.selected_news_by_lead.values())
                if st.button(f"▶️ Step 3: 인사이트 생성 ({total_sel}건 선택)", type="primary", use_container_width=True):
                    st.session_state.step = 3
                    log(f"전체 {total_sel}건 뉴스 선택, Step 3으로 이동", "info")
                    st.rerun()


# ============================================================
# STEP 3: Claude 인사이트 생성
# ============================================================

elif st.session_state.step == 3:
    st.markdown("""
    <div class="palantir-header">STEP 03</div>
    <div class="palantir-title">인사이트 생성</div>
    <div class="palantir-sub">선택된 뉴스를 기반으로 Claude AI가 리드별 Deep-Dive 인사이트를 일괄 생성합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.expander("📊 파이프라인 트래커", expanded=False):
        _render_pipeline_tracker()

    if not st.session_state.leads:
        st.warning("리드가 없습니다. Step 1에서 먼저 리드를 추가하세요.")
        if st.button("◀️ Step 1로 이동"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    leads = st.session_state.leads

    # 인사이트 미생성 리드 확인
    missing_leads = [i for i in range(len(leads))
                     if i not in st.session_state.insights_by_lead
                     and i in st.session_state.news_by_lead
                     and st.session_state.selected_news_by_lead.get(i)]

    # ── 자동 일괄 생성 (미생성 + 뉴스 있으면 자동) ──
    if missing_leads:
        # 자동 실행
        try:
            from newsletter_pipeline import InsightGenerator, FallbackInsightGenerator, _map_industry

            env = load_env_keys()
            api_key = env.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))

            if api_key:
                gen = InsightGenerator(api_key)
            else:
                gen = FallbackInsightGenerator()
                st.warning("API 키 없음 — 폴백 템플릿 사용")

            progress_bar = st.progress(0)
            status_text = st.empty()

            for prog_i, lead_idx in enumerate(missing_leads):
                ld = leads[lead_idx]
                status_text.text(f"인사이트 생성 중: {ld['이름']} ({ld['회사명']}) [{prog_i+1}/{len(missing_leads)}]")

                industry = _map_industry(ld.get("회사_산업", ""))
                selected_indices = st.session_state.selected_news_by_lead.get(lead_idx, [])
                lead_news = st.session_state.news_by_lead.get(lead_idx, [])
                selected_news = [lead_news[ni]["_raw"] for ni in selected_indices if ni < len(lead_news)]

                company_context = {
                    "description": ld.get("회사_설명", ""),
                    "domain": ld.get("회사_도메인", ""),
                    "size": ld.get("회사_규모", ""),
                    "revenue": ld.get("회사_매출", ""),
                    "location": ld.get("회사_위치", ""),
                }

                insight = gen.generate_insight(
                    name=ld["이름"],
                    title=ld.get("직함", ""),
                    company=ld["회사명"],
                    industry=industry,
                    industry_news=selected_news,
                    company_news=[],
                    company_context=company_context,
                )

                st.session_state.insights_by_lead[lead_idx] = insight
                progress_bar.progress((prog_i + 1) / len(missing_leads))

                if prog_i < len(missing_leads) - 1:
                    time.sleep(1)  # API 간격

            status_text.text("전체 인사이트 생성 완료!")
            log(f"인사이트 일괄 생성 완료: {len(missing_leads)}명", "success")

            # 파이프라인 스토어에 인사이트 저장
            if st.session_state.get("current_run_id"):
                _store.save_insights(st.session_state.current_run_id, st.session_state.insights_by_lead)

            st.rerun()

        except Exception as e:
            st.error(f"인사이트 생성 실패: {e}")
            log(f"인사이트 생성 실패: {e}", "error")

    elif not st.session_state.news_by_lead:
        st.warning("뉴스가 수집되지 않았습니다. Step 2에서 뉴스를 수집하세요.")
        if st.button("◀️ Step 2로 이동"):
            st.session_state.step = 2
            st.rerun()

    # ── 인사이트 결과 표시 ──
    if st.session_state.insights_by_lead:
        generated = len(st.session_state.insights_by_lead)
        st.success(f"✅ {generated}/{len(leads)}명 인사이트 생성 완료. Step 4에서 검토하세요.")

        for i, ld in enumerate(leads):
            insight = st.session_state.insights_by_lead.get(i)
            if insight:
                with st.expander(f"{ld['이름']} ({ld['회사명']}) — {insight.get('subject_line', '')}", expanded=False):
                    i1 = insight.get("insight_1", {})
                    i2 = insight.get("insight_2", {})
                    st.markdown(f"**제목:** {insight.get('subject_line', '')}")
                    st.markdown(f"**Insight 1:** {i1.get('title', '')}")
                    st.markdown(f"**Insight 2:** {i2.get('title', '')}")

                    if st.button(f"🔄 재생성", key=f"regen_{i}"):
                        if i in st.session_state.insights_by_lead:
                            del st.session_state.insights_by_lead[i]
                        _invalidate_downstream(3, i)
                        log(f"인사이트 재생성 요청: {ld['이름']}", "info")
                        st.rerun()

        st.divider()
        col_back, col_regen_all, col_next = st.columns(3)
        with col_back:
            if st.button("◀️ Step 2로 돌아가기", use_container_width=True):
                st.session_state.step = 2
                st.rerun()
        with col_regen_all:
            if st.button("🔄 전체 재생성", use_container_width=True):
                st.session_state.insights_by_lead = {}
                _invalidate_downstream(3)
                log("전체 인사이트 재생성 요청", "info")
                st.rerun()
        with col_next:
            if st.button("▶️ Step 4: 검토 & 편집", type="primary", use_container_width=True):
                st.session_state.step = 4
                log("Step 4로 이동", "info")
                st.rerun()


# ============================================================
# STEP 4: 검토 & 편집 + HTML 미리보기
# ============================================================

elif st.session_state.step == 4:
    st.markdown("""
    <div class="palantir-header">STEP 04</div>
    <div class="palantir-title">검토 & 편집</div>
    <div class="palantir-sub">전체 리드의 뉴스레터를 한눈에 검토/편집하고 HTML을 확인합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.expander("📊 파이프라인 트래커", expanded=False):
        _render_pipeline_tracker()

    if not st.session_state.leads:
        st.warning("리드가 없습니다. Step 1에서 먼저 리드를 추가하세요.")
        if st.button("◀️ Step 1로 이동", key="s4_back_s1"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    if not st.session_state.insights_by_lead:
        st.warning("인사이트가 없습니다. Step 3으로 돌아가세요.")
        if st.button("◀️ Step 3으로"):
            st.session_state.step = 3
            st.rerun()
        st.stop()

    leads = st.session_state.leads

    # ── 최초 진입 시 전체 HTML 자동 생성 ──
    missing_html = [i for i in range(len(leads))
                    if i in st.session_state.insights_by_lead
                    and i not in st.session_state.html_by_lead]
    if missing_html:
        try:
            from newsletter_pipeline import NewsletterBuilder
            builder = NewsletterBuilder()
            out_dir = Path("output/deta_newsletter")
            out_dir.mkdir(parents=True, exist_ok=True)

            for lead_idx in missing_html:
                ld = leads[lead_idx]
                insight = st.session_state.insights_by_lead[lead_idx]
                selected_indices = st.session_state.selected_news_by_lead.get(lead_idx, [])
                lead_news = st.session_state.news_by_lead.get(lead_idx, [])
                news_articles = [lead_news[ni]["_raw"] for ni in selected_indices if ni < len(lead_news)]

                html = builder.build_html(insight, news_articles)
                safe_name = re.sub(r'[^\w가-힣]', '_', f"{ld['회사명']}_{ld['이름']}")
                html_file = out_dir / f"{safe_name}.html"
                html_file.write_text(html, encoding="utf-8")

                st.session_state.html_by_lead[lead_idx] = html
                st.session_state.html_paths_by_lead[lead_idx] = str(html_file)

                # 파이프라인 스토어에 HTML 저장
                if st.session_state.get("current_run_id"):
                    _store.save_html(st.session_state.current_run_id, lead_idx, html, ld.get("이름", ""))

            log(f"HTML 일괄 생성 완료: {len(missing_html)}명", "success")
            st.rerun()
        except Exception as e:
            st.error(f"HTML 자동 생성 실패: {e}")
            log(f"HTML 자동 생성 실패: {e}", "warning")

    # ── 상단 요약 테이블 ──
    import pandas as pd
    summary_data = []
    for i, ld in enumerate(leads):
        insight = st.session_state.insights_by_lead.get(i, {})
        has_html = i in st.session_state.html_by_lead
        summary_data.append({
            "": i + 1,
            "이름": ld["이름"],
            "회사": ld["회사명"],
            "제목": insight.get("subject_line", "—")[:40],
            "HTML": "✅" if has_html else "—",
        })
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    # ── 리드별 expander ──
    for idx, ld in enumerate(leads):
        insight = st.session_state.insights_by_lead.get(idx)
        if not insight:
            continue

        with st.expander(f"{idx+1}. {ld['이름']} ({ld['회사명']}) — {insight.get('subject_line', '')}", expanded=False):
            # 편집 폼
            insight["subject_line"] = st.text_input(
                "이메일 제목", value=insight.get("subject_line", ""), key=f"subj_{idx}")
            insight["greeting"] = st.text_area(
                "인사말", value=insight.get("greeting", ""), height=60, key=f"greet_{idx}")

            st.markdown("---")
            i1 = insight.get("insight_1", {})
            i1["title"] = st.text_input("Insight 1 제목", value=i1.get("title", ""), key=f"i1t_{idx}")
            i1["content"] = st.text_area("Insight 1 내용", value=i1.get("content", ""), height=100, key=f"i1c_{idx}")
            i1["source"] = st.text_input("Insight 1 출처", value=i1.get("source", ""), key=f"i1s_{idx}")
            insight["insight_1"] = i1

            i2 = insight.get("insight_2", {})
            i2["title"] = st.text_input("Insight 2 제목", value=i2.get("title", ""), key=f"i2t_{idx}")
            i2["content"] = st.text_area("Insight 2 내용", value=i2.get("content", ""), height=100, key=f"i2c_{idx}")
            i2["source"] = st.text_input("Insight 2 출처", value=i2.get("source", ""), key=f"i2s_{idx}")
            insight["insight_2"] = i2

            st.markdown("---")
            insight["company_relevance"] = st.text_area(
                "귀사에 주는 시사점", value=insight.get("company_relevance", ""), height=60, key=f"cr_{idx}")
            insight["key_takeaway"] = st.text_input(
                "핵심 한줄", value=insight.get("key_takeaway", ""), key=f"kt_{idx}")
            insight["cta"] = st.text_input(
                "CTA 문구", value=insight.get("cta", ""), key=f"cta_{idx}")

            st.session_state.insights_by_lead[idx] = insight

            # HTML 갱신 버튼 (인사이트 수정사항도 함께 저장)
            if st.button(f"🔨 HTML 갱신", key=f"rebuild_{idx}"):
                # 인사이트 수정사항 스토어에 저장
                if st.session_state.get("current_run_id"):
                    _store.save_insights(st.session_state.current_run_id, st.session_state.insights_by_lead)
                try:
                    from newsletter_pipeline import NewsletterBuilder
                    builder = NewsletterBuilder()
                    selected_indices = st.session_state.selected_news_by_lead.get(idx, [])
                    lead_news = st.session_state.news_by_lead.get(idx, [])
                    news_articles = [lead_news[ni]["_raw"] for ni in selected_indices if ni < len(lead_news)]

                    html = builder.build_html(insight, news_articles)
                    out_dir = Path("output/deta_newsletter")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = re.sub(r'[^\w가-힣]', '_', f"{ld['회사명']}_{ld['이름']}")
                    html_file = out_dir / f"{safe_name}.html"
                    html_file.write_text(html, encoding="utf-8")

                    st.session_state.html_by_lead[idx] = html
                    st.session_state.html_paths_by_lead[idx] = str(html_file)

                    # 파이프라인 스토어에 HTML 저장
                    if st.session_state.get("current_run_id"):
                        _store.save_html(st.session_state.current_run_id, idx, html, ld.get("이름", ""))

                    log(f"HTML 갱신: {ld['이름']}", "success")
                    st.rerun()
                except Exception as e:
                    st.error(f"HTML 빌드 실패: {e}")

            # HTML 미리보기 (토글)
            if idx in st.session_state.html_by_lead:
                if st.checkbox("미리보기 열기", key=f"preview_{idx}"):
                    import streamlit.components.v1 as components
                    components.html(st.session_state.html_by_lead[idx], height=600, scrolling=True)
                st.caption(f"📁 {st.session_state.html_paths_by_lead.get(idx, '')}")

    st.divider()
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("◀️ Step 3으로 돌아가기", use_container_width=True):
            st.session_state.step = 3
            st.rerun()
    with col_next:
        html_ready = len(st.session_state.html_by_lead)
        if html_ready > 0:
            if st.button(f"▶️ Step 5: 발송 ({html_ready}건 준비)", type="primary", use_container_width=True):
                st.session_state.step = 5
                log("Step 5로 이동", "info")
                st.rerun()
        else:
            st.button("▶️ Step 5: 발송", disabled=True, use_container_width=True,
                      help="먼저 HTML을 생성하세요")


# ============================================================
# STEP 5: 스티비 발송
# ============================================================

elif st.session_state.step == 5:
    st.markdown("""
    <div class="palantir-header">STEP 05</div>
    <div class="palantir-title">Stibee 발송</div>
    <div class="palantir-sub">자동 이메일 API로 전체 리드에게 개인화된 뉴스레터를 일괄 발송합니다.</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    with st.expander("📊 파이프라인 트래커", expanded=False):
        _render_pipeline_tracker()

    if not st.session_state.leads:
        st.warning("리드가 없습니다. Step 1에서 먼저 리드를 추가하세요.")
        if st.button("◀️ Step 1로 이동", key="s5_back_s1"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    leads = st.session_state.leads
    env = load_env_keys()

    # ── 리뷰 상태 로드 ──
    run_id = st.session_state.get("current_run_id", "")
    reviews = {}
    if run_id:
        reviews = _store.get_reviews(run_id)

    # ── 발송 전 요약 테이블 ──
    import pandas as pd
    status_data = []
    for i, ld in enumerate(leads):
        si = str(i)
        has_html = i in st.session_state.html_by_lead
        send_st = st.session_state.send_status_by_lead.get(i, "pending")
        review_info = reviews.get(si, {})
        review_st = review_info.get("status", "")

        send_emoji = {"pending": "⏳", "sent": "✅", "failed": "❌"}.get(send_st, "⏳")
        review_emoji = {
            "approved": "✅ 승인",
            "rejected": "❌ 반려",
            "comment": "💬 코멘트",
        }.get(review_st, "⏳ 대기")

        status_data.append({
            "": i + 1,
            "이름": ld["이름"],
            "회사": ld["회사명"],
            "이메일": ld["이메일"],
            "HTML": "✅" if has_html else "—",
            "리뷰": review_emoji,
            "발송": f"{send_emoji} {send_st}",
        })
    st.dataframe(pd.DataFrame(status_data), use_container_width=True, hide_index=True)

    # ── 리뷰 경고 ──
    n_rejected = sum(1 for v in reviews.values() if v.get("status") == "rejected")
    n_pending_review = sum(1 for i in range(len(leads))
                           if i in st.session_state.html_by_lead
                           and reviews.get(str(i), {}).get("status", "") not in ("approved",))
    if n_rejected > 0:
        rejected_names = [leads[int(k)]["이름"] for k, v in reviews.items()
                         if v.get("status") == "rejected" and int(k) < len(leads)]
        st.warning(f"반려된 리드 {n_rejected}명: {', '.join(rejected_names)}. Step 4에서 수정 후 재검토가 필요합니다.")
        for k, v in reviews.items():
            if v.get("status") == "rejected" and v.get("comment"):
                idx = int(k)
                if idx < len(leads):
                    st.markdown(f"""
                    <div style="background:#1A1A1A;border:1px solid #C5504C;border-radius:2px;padding:8px 12px;margin:4px 0;">
                        <span style="color:#C5504C;font-size:12px;">❌ {leads[idx]['이름']}</span>
                        <span style="color:#AAAAAA;font-size:12px;"> — "{v['comment']}"</span>
                    </div>
                    """, unsafe_allow_html=True)

    if not env.get("STIBEE_API_KEY"):
        st.error("🔴 STIBEE_API_KEY가 설정되어 있지 않습니다. config/.env를 확인하세요.")

    tab_auto, tab_manual = st.tabs(["🚀 자동 이메일 API 발송", "📋 수동 복사-붙여넣기"])

    with tab_auto:
        auto_email_url = env.get("STIBEE_AUTO_EMAIL_URL", "")

        if not auto_email_url:
            st.markdown("""
            <div style="background:#1A1A1A;border:1px solid #333333;border-radius:2px;padding:16px;">
                <span style="color:#C5504C;">⚫ STIBEE_AUTO_EMAIL_URL 미설정</span><br>
                <span style="color:#888888;font-size:13px;margin-top:4px;">
                    아래에서 자동 이메일 API URL을 직접 입력하거나, config/.env에 설정할 수 있습니다.
                </span>
            </div>
            """, unsafe_allow_html=True)

            # URL 직접 입력 필드
            user_url = st.text_input(
                "자동 이메일 API URL 직접 입력",
                value=st.session_state.get("_manual_auto_email_url", ""),
                placeholder="https://stibee.com/api/v1.0/auto/...",
                help="스티비 > 자동 이메일 > 실행 중인 이메일 > API URL 복사",
                key="_input_auto_email_url",
            )
            if user_url and user_url.strip().startswith("https://stibee.com/api/"):
                auto_email_url = user_url.strip()
                st.session_state["_manual_auto_email_url"] = auto_email_url
                st.success("✅ URL이 입력되었습니다. 아래에서 발송할 수 있습니다.")
            elif user_url and user_url.strip():
                st.warning("URL은 `https://stibee.com/api/` 로 시작해야 합니다.")

            # 설정 안내 가이드
            with st.expander("📖 자동 이메일 API URL 설정 방법"):
                st.markdown("""
**스티비에서 자동 이메일을 만들고 API URL을 확인하는 방법:**

1. [스티비](https://stibee.com) 로그인
2. 좌측 메뉴 → **자동 이메일** → **+ 새로 만들기**
3. **트리거**: **API로 직접 요청** 선택
4. **주소록**: 사용 중인 주소록 선택 (ID: {list_id})
5. 이메일 **제목**에 치환 변수 사용 가능: `$%subject_line%$`
6. 이메일 **본문**에 `$%insight_html%$` 삽입 (전체 HTML 콘텐츠)
7. **저장** 후 → **실행** 상태로 전환
8. 실행 중인 자동 이메일의 **API URL 복사**
9. 위 입력 필드에 붙여넣기 또는 `config/.env`에 설정:
   ```
   STIBEE_AUTO_EMAIL_URL=https://stibee.com/api/v1.0/auto/your-url-here
   ```

> **치환 변수 목록**: `$%name%$`, `$%company%$`, `$%subject_line%$`, `$%greeting%$`, `$%insight_html%$`
                """.format(list_id=env.get("STIBEE_LIST_ID", "473532")))
            st.markdown("")

        # ── ① 구독자 일괄 등록 ──
        st.markdown("""
        <div style="background:#111111;border:1px solid #222222;border-radius:2px;padding:16px;margin-bottom:16px;">
            <span class="palantir-header">STEP 1 — SUBSCRIBER REGISTRATION</span>
            <p style="color:#888888;font-size:13px;margin-top:8px;">발송 전 전체 수신자를 Stibee 주소록에 일괄 등록합니다.</p>
        </div>
        """, unsafe_allow_html=True)

        subscriber_registered = st.session_state.get("_subscriber_registered", False)
        if subscriber_registered:
            st.markdown(f"""
            <div style="background:#1A1A1A;border:1px solid #333333;border-left:3px solid #555555;border-radius:2px;padding:12px 16px;">
                <span style="color:#666666;font-size:12px;">✓ 구독자 등록 완료 ({len(leads)}명)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            if env.get("STIBEE_API_KEY"):
                if st.button("📋 전체 구독자 등록", use_container_width=True):
                    with st.spinner("Stibee 주소록에 일괄 등록 중..."):
                        try:
                            from stibee_integration import StibeeClient
                            client = StibeeClient()
                            list_id = env.get("STIBEE_LIST_ID", "473532")

                            subscribers = []
                            for ld in leads:
                                sub = {"email": ld["이메일"], "name": ld["이름"]}
                                if ld.get("회사명"):
                                    sub["company"] = ld["회사명"]
                                if ld.get("회사_산업"):
                                    sub["industry"] = ld.get("회사_산업", "")
                                subscribers.append(sub)

                            result = client.add_subscribers(list_id, subscribers)
                            if result:
                                st.session_state["_subscriber_registered"] = True
                                log(f"Stibee 구독자 일괄 등록 완료: {len(subscribers)}명", "success")
                                st.rerun()
                            else:
                                st.error("구독자 등록 실패")
                        except Exception as e:
                            st.error(f"Stibee API 오류: {e}")
                            log(f"Stibee 구독자 등록 오류: {e}", "error")

        st.markdown('<div style="border-top:1px solid #222222;margin:16px 0;"></div>', unsafe_allow_html=True)

        # ── ② 자동 이메일 API 일괄 발송 ──
        st.markdown("""
        <div style="background:#111111;border:1px solid #222222;border-radius:2px;padding:16px;margin-bottom:16px;">
            <span class="palantir-header">STEP 2 — BATCH SEND</span>
            <p style="color:#888888;font-size:13px;margin-top:8px;">자동 이메일 API로 리드별 개인화된 뉴스레터를 일괄 발송합니다.</p>
        </div>
        """, unsafe_allow_html=True)

        # 발송 대상 확인 (리뷰가 있으면 승인된 리드만, 없으면 전체 HTML 준비된 리드)
        all_html_leads = [i for i in range(len(leads)) if i in st.session_state.html_by_lead]
        if reviews:
            approved_leads = [i for i in all_html_leads if reviews.get(str(i), {}).get("status") == "approved"]
            ready_leads = approved_leads  # 승인된 리드만 발송 대상
        else:
            approved_leads = all_html_leads
            ready_leads = all_html_leads  # 리뷰 미사용 시 전체 허용
        sent_leads = [i for i in range(len(leads)) if st.session_state.send_status_by_lead.get(i) == "sent"]
        failed_leads = [i for i in range(len(leads)) if st.session_state.send_status_by_lead.get(i) == "failed"]
        pending_leads = [i for i in ready_leads if st.session_state.send_status_by_lead.get(i, "pending") != "sent"]

        n_unapproved = len(all_html_leads) - len(approved_leads)
        st.markdown(f"승인: **{len(approved_leads)}**명 / 발송완료: **{len(sent_leads)}**명 / 실패: **{len(failed_leads)}**명")
        if n_unapproved > 0:
            st.caption(f"{n_unapproved}명의 리드가 미승인 상태입니다. 리뷰 대시보드에서 승인 후 발송할 수 있습니다.")

        if auto_email_url and pending_leads:
            btn_label = f"🚀 전체 일괄 발송 ({len(pending_leads)}명)" if not failed_leads else f"🔄 실패 포함 재발송 ({len(pending_leads)}명)"
            if st.button(btn_label, type="primary", use_container_width=True):
                try:
                    from stibee_integration import StibeeClient
                    client = StibeeClient()

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for prog_i, lead_idx in enumerate(pending_leads):
                        ld = leads[lead_idx]
                        html = st.session_state.html_by_lead.get(lead_idx, "")
                        insight = st.session_state.insights_by_lead.get(lead_idx, {})

                        status_text.text(f"발송 중: {ld['이름']} ({ld['회사명']}) [{prog_i+1}/{len(pending_leads)}]")

                        custom_fields = {
                            "name": ld["이름"],
                            "company": ld["회사명"],
                            "subject_line": insight.get("subject_line", "산업 인사이트 브리핑"),
                            "greeting": insight.get("greeting", f"안녕하세요, {ld['이름']}님."),
                            "insight_html": html,
                        }

                        success, error_msg = client.trigger_auto_email(auto_email_url, ld["이메일"], custom_fields)
                        send_result = "sent" if success else "failed"
                        st.session_state.send_status_by_lead[lead_idx] = send_result
                        if not success:
                            st.session_state.send_errors_by_lead[lead_idx] = error_msg
                        progress_bar.progress((prog_i + 1) / len(pending_leads))

                        # 파이프라인 스토어에 발송 상태 저장
                        if st.session_state.get("current_run_id"):
                            _store.save_send_status(st.session_state.current_run_id, lead_idx, send_result)

                        if prog_i < len(pending_leads) - 1:
                            time.sleep(0.4)  # 1초당 3회 제한

                    n_sent = sum(1 for i in pending_leads if st.session_state.send_status_by_lead.get(i) == "sent")
                    n_fail = sum(1 for i in pending_leads if st.session_state.send_status_by_lead.get(i) == "failed")
                    status_text.text(f"발송 완료! 성공: {n_sent}명, 실패: {n_fail}명")
                    log(f"일괄 발송 완료: 성공 {n_sent}, 실패 {n_fail}", "success" if n_fail == 0 else "warning")
                    st.rerun()
                except Exception as e:
                    st.error(f"발송 오류: {e}")
                    log(f"발송 오류: {e}", "error")

        elif not auto_email_url:
            st.info("⬆ 위에서 자동 이메일 API URL을 입력하면 발송 버튼이 활성화됩니다.")

        # 실패한 리드 개별 재시도
        if failed_leads:
            st.markdown("#### 실패한 리드")
            for fi in failed_leads:
                ld = leads[fi]
                col_fail_info, col_retry = st.columns([3, 1])
                with col_fail_info:
                    st.markdown(f"❌ {ld['이름']} ({ld['이메일']})")
                    error_detail = st.session_state.get("send_errors_by_lead", {}).get(fi, "")
                    if error_detail:
                        st.caption(f"실패 원인: {error_detail}")
                with col_retry:
                    if st.button("재시도", key=f"retry_{fi}"):
                        st.session_state.send_status_by_lead[fi] = "pending"
                        st.rerun()

    with tab_manual:
        st.markdown("### 수동 복사-붙여넣기 방법")

        if st.session_state.html_by_lead:
            import json as _json
            import streamlit.components.v1 as components

            # 리드 선택
            lead_options = [f"{i+1}. {ld['이름']} ({ld['회사명']})" for i, ld in enumerate(leads) if i in st.session_state.html_by_lead]
            lead_indices = [i for i in range(len(leads)) if i in st.session_state.html_by_lead]

            if lead_options:
                selected_label = st.selectbox("리드 선택", lead_options, key="s5_manual_lead")
                sel_pos = lead_options.index(selected_label)
                sel_idx = lead_indices[sel_pos]
                sel_lead = leads[sel_idx]
                sel_html = st.session_state.html_by_lead[sel_idx]

                st.markdown("")

                # ── HTML 전체 코드 ──
                st.markdown("""
                <div style="background:#111111;border:1px solid #222222;border-radius:2px;padding:12px 16px;margin-bottom:8px;">
                    <span class="palantir-header">HTML CODE</span>
                    <p style="color:#666666;font-size:12px;margin:4px 0 0;">아래 영역 클릭 → <code style="background:#1A1A1A;padding:1px 4px;border-radius:2px;color:#E0E0E0;">Ctrl+A</code> → <code style="background:#1A1A1A;padding:1px 4px;border-radius:2px;color:#E0E0E0;">Ctrl+C</code> 로 복사</p>
                </div>
                """, unsafe_allow_html=True)

                st.text_area(
                    "HTML 소스코드",
                    value=sel_html,
                    height=350,
                    key=f"manual_html_{sel_idx}",
                    label_visibility="collapsed",
                )

                # ── JavaScript 원클릭 복사 버튼 ──
                # </script> 태그가 iframe을 깨뜨리지 않도록 이스케이프
                _safe_html = sel_html.replace("</script>", "<\\/script>")
                _html_json = _json.dumps(_safe_html, ensure_ascii=False)
                _copy_component = f"""
                <button id="copyHtmlBtn" style="
                    width:100%;padding:12px 24px;background:#1A1A1A;color:#E0E0E0;
                    border:1px solid #333333;border-radius:2px;font-size:14px;font-weight:700;
                    cursor:pointer;letter-spacing:0.3px;margin-bottom:8px;
                " onclick="
                    var html={_html_json};
                    navigator.clipboard.writeText(html).then(function(){{
                        var b=document.getElementById('copyHtmlBtn');
                        b.innerText='✅ 복사 완료! 스티비 에디터에서 Ctrl+A → Ctrl+V';
                        b.style.background='#14532d';
                        b.style.borderColor='#22c55e';
                    }}).catch(function(){{
                        var t=document.createElement('textarea');t.value=html;
                        document.body.appendChild(t);t.select();document.execCommand('copy');
                        document.body.removeChild(t);
                        var b=document.getElementById('copyHtmlBtn');
                        b.innerText='✅ 복사 완료!';
                        b.style.background='#14532d';
                    }});
                ">📋 HTML 전체 코드 원클릭 복사</button>
                """
                components.html(_copy_component, height=55)

                # ── 다운로드 ──
                st.download_button(
                    label="📥 HTML 파일 다운로드",
                    data=sel_html,
                    file_name=f"{sel_lead['회사명']}_{sel_lead['이름']}_newsletter.html",
                    mime="text/html",
                    use_container_width=True,
                )

                # ── 절차 안내 ──
                st.markdown("""
                **수동 발송 절차:**
                1. 위 **HTML 전체 코드 원클릭 복사** 버튼 클릭
                2. 스티비 에디터 → HTML 에디터 (Step 05) 페이지로 이동
                3. 왼쪽 코드 영역 클릭 → `Ctrl+A` → `Ctrl+V` 로 붙여넣기
                4. 오른쪽 미리보기 확인 후 **발송하기**
                """)
        else:
            st.info("HTML이 생성되지 않았습니다. Step 4에서 먼저 생성하세요.")

    st.divider()
    col_back, col_restart = st.columns(2)
    with col_back:
        if st.button("◀️ Step 4로 돌아가기", use_container_width=True):
            st.session_state.step = 4
            st.rerun()
    with col_restart:
        if st.button("🔄 처음부터 다시 시작", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
