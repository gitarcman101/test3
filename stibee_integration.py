"""
스티비(Stibee) API 연동 모듈
============================
스티비 v2 API를 활용한 구독자 관리 + 이메일 생성/발송 자동화

기능:
- 주소록에 구독자(담당자) 일괄 추가
- 이메일 생성 (HTML 콘텐츠)
- 이메일 발송
- 자동 이메일 API 트리거 (개인화 발송)
- 발송 통계 조회

요금제별 사용 가능 API:
- 스탠다드: 구독자 API만
- 프로: 구독자 + 이메일 API
- 엔터프라이즈: 전체

사용법:
1. 스티비 워크스페이스 설정 → API 키 발급
2. .env에 STIBEE_API_KEY 설정
3. 주소록 ID, 자동이메일 URL 확인 후 설정
"""

import json
import time
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

try:
    import requests
except ImportError:
    print("pip install requests 필요")
    exit(1)


# ============================================================
# 설정
# ============================================================

def _load_env() -> dict:
    import os as _os
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
            import streamlit as _st
            for k, v in _st.secrets.items():
                if isinstance(v, str):
                    env[k] = v
        except Exception:
            pass
    # 3) 환경변수 fallback
    for key in ["STIBEE_API_KEY", "STIBEE_LIST_ID", "STIBEE_AUTO_EMAIL_URL",
                "SENDER_EMAIL", "SENDER_NAME"]:
        if key not in env and _os.environ.get(key):
            env[key] = _os.environ[key]
    return env

ENV = _load_env()

STIBEE_API_KEY = ENV.get("STIBEE_API_KEY", "")
STIBEE_LIST_ID = ENV.get("STIBEE_LIST_ID", "")  # 주소록 ID
STIBEE_AUTO_EMAIL_URL = ENV.get("STIBEE_AUTO_EMAIL_URL", "")  # 자동 이메일 API URL


# ============================================================
# 스티비 API v2 클라이언트
# ============================================================

class StibeeClient:
    """스티비 API v2 클라이언트 (공식 문서 기반)"""

    BASE_URL_V1 = "https://api.stibee.com/v1"
    BASE_URL = "https://api.stibee.com/v2"
    AUTO_BASE_URL = "https://stibee.com/api/v1.0"  # 자동 이메일은 v1.0

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or STIBEE_API_KEY
        if not self.api_key:
            raise ValueError(
                "스티비 API 키가 설정되지 않았습니다.\n"
                "1) .env 파일에 STIBEE_API_KEY=your_key 추가\n"
                "2) 또는 StibeeClient(api_key='...') 으로 직접 전달"
            )
        self.session = requests.Session()
        self.session.headers.update({
            "AccessToken": self.api_key,
            "Content-Type": "application/json",
        })

    # ----------------------------------------------------------
    # 인증 테스트
    # ----------------------------------------------------------
    def check_auth(self) -> bool:
        """API 키 유효성 확인"""
        try:
            resp = self.session.get(f"{self.BASE_URL}/auth-check", timeout=10)
            if resp.status_code == 200:
                print("✅ 스티비 API 인증 성공")
                return True
            else:
                print(f"❌ 스티비 API 인증 실패 ({resp.status_code}): {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ 스티비 연결 실패: {e}")
            return False

    # ----------------------------------------------------------
    # 주소록 관리
    # ----------------------------------------------------------
    def get_lists(self) -> list:
        """주소록 목록 조회 (엔터프라이즈)"""
        resp = self._get("/lists")
        return resp.get("data", []) if resp else []

    # ----------------------------------------------------------
    # 구독자 관리 — v1 API (공식 문서 기반)
    # POST /v1/lists/{listId}/subscribers
    # ----------------------------------------------------------
    def add_subscribers(self, list_id: str, subscribers: list[dict], group_ids: list[str] = None) -> dict:
        """
        구독자 일괄 추가 (v1 batch API — 공식 스펙)

        POST https://api.stibee.com/v1/lists/{listId}/subscribers

        Args:
            subscribers: [{"email": "...", "name": "...", ...}, ...]
            group_ids: 그룹 ID 리스트 (선택)

        Response format:
            {"Ok": true, "Value": {"success": [...], "update": [...], "failExistEmail": [...], ...}}
        """
        payload = {
            "eventOccuredBy": "MANUAL",
            "confirmEmailYN": "N",
            "subscribers": subscribers,
        }
        if group_ids:
            payload["groupIds"] = group_ids

        try:
            resp = self.session.post(
                f"{self.BASE_URL_V1}/lists/{list_id}/subscribers",
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("Ok"):
                    value = data.get("Value", {})
                    success = value.get("success", [])
                    update = value.get("update", [])
                    fail_exist = value.get("failExistEmail", [])
                    fail_wrong = value.get("failWrongEmail", [])
                    fail_unknown = value.get("failUnknown", [])
                    total_ok = len(success) + len(update)
                    print(f"  구독자 추가: 성공 {len(success)}건, 업데이트 {len(update)}건, "
                          f"기존 {len(fail_exist)}건, 실패 {len(fail_wrong) + len(fail_unknown)}건")
                    return value
                else:
                    error = data.get("Error", {})
                    print(f"  ❌ 구독자 추가 실패: {error}")
                    return {}
            else:
                print(f"  ⚠️ 구독자 API 오류 ({resp.status_code}): {resp.text[:200]}")
                return {}
        except Exception as e:
            print(f"  ❌ 구독자 추가 오류: {e}")
            return {}

    def add_subscriber_v1(self, list_id: str, subscriber: dict, group_ids: list = None) -> dict:
        """구독자 1건 추가 (batch API 래핑)"""
        return self.add_subscribers(list_id, [subscriber], group_ids)

    def get_subscribers(self, list_id: str, offset: int = 0, limit: int = 100) -> dict:
        """구독자 목록 조회 (최대 100회/분)"""
        return self._get(f"/lists/{list_id}/subscribers", params={"offset": offset, "limit": limit})

    def get_subscriber(self, list_id: str, email: str) -> dict:
        """특정 구독자 조회"""
        return self._get(f"/lists/{list_id}/subscribers/{email}")

    def delete_subscriber(self, list_id: str, email: str) -> dict:
        """구독자 삭제"""
        return self._delete(f"/lists/{list_id}/subscribers/{email}")

    # ----------------------------------------------------------
    # 이메일 관리 (프로+)
    # ----------------------------------------------------------
    def create_email(self, list_id: str, subject: str, sender_email: str = "", sender_name: str = "") -> dict:
        """
        이메일 생성 (v2 POST /emails)

        Required: listId(int), senderEmail(email), senderName(str), subject(str)
        Response: {"id": 1234}
        """
        payload = {
            "listId": int(list_id),
            "subject": subject,
            "senderEmail": sender_email or ENV.get("SENDER_EMAIL", "bnnmoy-gmail.com@send.stibee.com"),
            "senderName": sender_name or ENV.get("SENDER_NAME", "DETA Intelligence"),
        }

        resp = self._post("/emails", payload)
        if resp and resp.get("id"):
            email_id = resp["id"]
            print(f"  ✅ 이메일 생성 완료 (ID: {email_id})")
            return resp
        return {}

    def set_email_content(self, email_id, html_content: str) -> dict:
        """이메일 콘텐츠(HTML) 설정 (v2 POST /emails/{id}/content)"""
        payload = {
            "content": html_content,
        }
        result = self._post(f"/emails/{email_id}/content", payload)
        if result is not None:
            print(f"  ✅ 이메일 콘텐츠 설정 완료 (ID: {email_id})")
        return result or {}

    def send_email(self, email_id) -> bool:
        """이메일 발송 (v2 POST /emails/{id}/send) — 응답: 'ok'"""
        result = self._post(f"/emails/{email_id}/send", None)
        if result is not None:
            print(f"  ✅ 이메일 발송 완료 (ID: {email_id})")
            return True
        return False

    def reserve_email(self, email_id, reserve_time: str) -> bool:
        """
        이메일 예약 발송 (v2 POST /emails/{id}/reserve)
        reserve_time: YYYYMMDDhhmmss (KST)
        """
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/emails/{email_id}/reserve",
                params={"reserveTime": reserve_time},
                timeout=15,
            )
            if resp.status_code == 200:
                print(f"  ✅ 이메일 예약 완료 (ID: {email_id}, 시간: {reserve_time})")
                return True
            print(f"  ⚠️ 이메일 예약 실패 ({resp.status_code}): {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"  ❌ 이메일 예약 오류: {e}")
            return False

    def get_email_stats(self, email_id: str) -> dict:
        """이메일 발송 통계 조회"""
        return self._get(f"/emails/{email_id}/logs")

    def get_emails(self, list_id: int = None, offset: int = 0, limit: int = 20) -> dict:
        """이메일 목록 조회 (v2 GET /emails)"""
        params = {"offset": offset, "limit": limit}
        if list_id:
            params["listId"] = list_id
        return self._get("/emails", params=params)

    # ----------------------------------------------------------
    # 자동 이메일 API (v1.0) - 개인화 발송용
    # ----------------------------------------------------------
    def trigger_auto_email(self, auto_email_url: str, subscriber_email: str, custom_fields: dict = None) -> bool:
        """
        자동 이메일 트리거 (1건씩 개인화 발송)

        사전 준비:
        1. 스티비에서 자동 이메일 생성
        2. 트리거: "API로 직접 요청" 선택
        3. 이메일 본문에 $%field_name%$ 형식으로 치환 변수 삽입
        4. 자동 이메일 "실행" 상태로 전환

        Args:
            auto_email_url: 자동 이메일 API URL (스티비에서 확인)
            subscriber_email: 수신자 이메일
            custom_fields: 치환할 사용자 정의 필드
                예: {"name": "홍길동", "insight": "<p>인사이트 내용</p>"}
        """
        payload = {
            "subscriber": subscriber_email,
        }
        if custom_fields:
            payload.update(custom_fields)

        try:
            resp = self.session.post(
                auto_email_url,
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                return True
            else:
                print(f"  ⚠️ 자동 이메일 트리거 실패 ({resp.status_code}): {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"  ❌ 자동 이메일 트리거 오류: {e}")
            return False

    # ----------------------------------------------------------
    # 내부 헬퍼
    # ----------------------------------------------------------
    def _get(self, endpoint: str, params: dict = None) -> dict:
        try:
            resp = self.session.get(f"{self.BASE_URL}{endpoint}", params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            print(f"  ⚠️ GET {endpoint} ({resp.status_code}): {resp.text[:200]}")
            return {}
        except Exception as e:
            print(f"  ❌ GET {endpoint} 오류: {e}")
            return {}

    def _post(self, endpoint: str, data: dict = None):
        try:
            kwargs = {"timeout": 30}
            if data is not None:
                kwargs["json"] = data
            resp = self.session.post(f"{self.BASE_URL}{endpoint}", **kwargs)
            if resp.status_code in (200, 201):
                # v2 API: some endpoints return text/plain "ok"
                ct = resp.headers.get("content-type", "")
                if "application/json" in ct:
                    return resp.json()
                return {"ok": resp.text.strip()}
            print(f"  ⚠️ POST {endpoint} ({resp.status_code}): {resp.text[:300]}")
            return None
        except Exception as e:
            print(f"  ❌ POST {endpoint} 오류: {e}")
            return None

    def _delete(self, endpoint: str) -> dict:
        try:
            resp = self.session.delete(f"{self.BASE_URL}{endpoint}", timeout=15)
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            print(f"  ❌ DELETE {endpoint} 오류: {e}")
            return {}


# ============================================================
# SMTP 직접 발송 (Stibee Email API 대안)
# ============================================================

def send_via_smtp(
    to_email: str,
    subject: str,
    html_content: str,
    from_email: str = "",
    from_name: str = "DETA Intelligence",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> bool:
    """
    SMTP로 HTML 이메일 직접 발송

    Gmail 앱 비밀번호 설정 필요:
    1. Google 계정 → 보안 → 2단계 인증 활성화
    2. 앱 비밀번호 생성 → .env의 SMTP_PASSWORD에 설정
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.utils import formataddr

    host = smtp_host or _ENV.get("SMTP_HOST", "smtp.gmail.com")
    port = smtp_port or int(_ENV.get("SMTP_PORT", "587"))
    user = smtp_user or _ENV.get("SMTP_USER", "")
    password = smtp_password or _ENV.get("SMTP_PASSWORD", "")
    sender = from_email or _ENV.get("SMTP_FROM_EMAIL", user)
    name = from_name or _ENV.get("SMTP_FROM_NAME", "DETA Intelligence")

    if not user or not password:
        print("  ❌ SMTP 인증 정보 없음 (SMTP_USER, SMTP_PASSWORD 설정 필요)")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((name, sender))
    msg["To"] = to_email

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"  ❌ SMTP 발송 오류: {e}")
        return False


def send_emails_smtp(
    leads_with_insights: list[dict],
    delay_seconds: float = 1.0,
) -> dict:
    """SMTP로 뉴스레터 일괄 발송"""
    sent = 0
    failed = 0

    print(f"\n📧 SMTP 이메일 발송 시작 ({len(leads_with_insights)}건)")

    for i, item in enumerate(leads_with_insights, 1):
        email = item.get("email", "")
        name = item.get("name", "")
        company = item.get("company", "")
        subject = item.get("insight", {}).get("subject_line", "DETA Intelligence Brief")
        html = item.get("html", "")

        print(f"\n[{i}/{len(leads_with_insights)}] {name} ({company}) → {email}")

        if send_via_smtp(email, subject, html):
            print(f"  ✅ 발송 완료")
            sent += 1
        else:
            print(f"  ❌ 발송 실패")
            failed += 1

        time.sleep(max(delay_seconds, 0.5))

    print(f"\n📊 SMTP 발송 결과: 성공 {sent}건, 실패 {failed}건")
    return {"sent": sent, "failed": failed}

def convert_leads_to_subscribers(leads: list[dict]) -> list[dict]:
    """
    Apollo 추출 리드를 스티비 구독자 형식으로 변환

    스티비 주소록에 아래 사용자 정의 필드가 등록되어 있어야 합니다:
    - name: 이름
    - company: 회사명
    - title: 직함
    - industry: 산업
    - seniority: 직급
    - linkedin: LinkedIn URL
    - phone: 전화번호
    """
    subscribers = []
    seen_emails = set()

    for lead in leads:
        email = lead.get("이메일", "").strip()
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)

        subscriber = {
            "email": email,
            "name": lead.get("이름", ""),
            "company": lead.get("회사명", ""),
            "title": lead.get("직함", ""),
            "industry": lead.get("회사_산업", ""),
            "seniority": lead.get("직급", ""),
            "linkedin": lead.get("LinkedIn", ""),
            "phone": lead.get("전화번호", ""),
        }
        subscribers.append(subscriber)

    print(f"📋 {len(subscribers)}건 구독자 변환 완료 (중복 제거: {len(leads) - len(subscribers)}건)")
    return subscribers


# ============================================================
# 발송 방식 A: 자동 이메일 API (추천 - 개인화 발송)
# ============================================================

def send_personalized_via_auto_email(
    leads_with_insights: list[dict],
    auto_email_url: str = "",
    stibee_api_key: str = "",
    delay_seconds: float = 1.0,
) -> dict:
    """
    자동 이메일 API로 개인화된 뉴스레터 발송

    이 방식의 장점:
    - 1건씩 개인화된 콘텐츠 발송 가능
    - 스티비 대시보드에서 통계 확인 가능
    - 수신거부 자동 처리

    사전 준비 (스티비 웹에서):
    1. 자동 이메일 생성
    2. 트리거: "API로 직접 요청"
    3. 이메일 제목: $%subject_line%$ (또는 고정 제목)
    4. 이메일 본문에 치환 변수 삽입:
       - $%name%$         → 수신자 이름
       - $%company%$      → 회사명
       - $%insight_html%$ → 인사이트 HTML 콘텐츠
    5. 자동 이메일 "실행" 상태로 전환
    6. API URL 복사 → .env의 STIBEE_AUTO_EMAIL_URL에 설정

    Args:
        leads_with_insights: 인사이트가 포함된 리드 리스트
            각 항목: {
                "email": "...",
                "name": "...",
                "company": "...",
                "insight": { ... },  # InsightGenerator 결과
                "html": "..."        # 생성된 HTML
            }
        auto_email_url: 자동 이메일 API URL
        stibee_api_key: 스티비 API 키
        delay_seconds: 발송 간격 (초)
    """
    url = auto_email_url or STIBEE_AUTO_EMAIL_URL
    if not url:
        print("❌ 자동 이메일 API URL이 설정되지 않았습니다.")
        print("   .env에 STIBEE_AUTO_EMAIL_URL 설정 필요")
        return {"sent": 0, "failed": 0}

    client = StibeeClient(stibee_api_key)
    sent = 0
    failed = 0

    print(f"\n📧 자동 이메일 발송 시작 ({len(leads_with_insights)}건)")
    print(f"   API URL: {url[:50]}...")

    for i, item in enumerate(leads_with_insights, 1):
        email = item.get("email", "")
        name = item.get("name", "")
        company = item.get("company", "")
        insight = item.get("insight", {})
        html = item.get("html", "")

        print(f"\n[{i}/{len(leads_with_insights)}] {name} ({company}) → {email}")

        # 치환 필드 구성
        custom_fields = {
            "name": name,
            "company": company,
            "subject_line": insight.get("subject_line", "산업 인사이트 브리핑"),
            "greeting": insight.get("greeting", f"{name}님, 안녕하세요."),
            "industry_insight": insight.get("industry_insight", ""),
            "company_relevance": insight.get("company_relevance", ""),
            "key_takeaway": insight.get("key_takeaway", ""),
            "cta": insight.get("cta", ""),
            # HTML 전체를 하나의 필드로 전달할 수도 있음
            "insight_html": html,
        }

        success = client.trigger_auto_email(url, email, custom_fields)
        if success:
            print(f"  ✅ 발송 완료")
            sent += 1
        else:
            print(f"  ❌ 발송 실패")
            failed += 1

        # 레이트 리밋 (1초당 3회 제한)
        time.sleep(max(delay_seconds, 0.4))

    print(f"\n📊 발송 결과: 성공 {sent}건, 실패 {failed}건")
    return {"sent": sent, "failed": failed}


# ============================================================
# 발송 방식 B: 이메일 API (일괄 발송)
# ============================================================

def send_bulk_via_email_api(
    list_id: str,
    subject: str,
    html_content: str,
    sender_email: str,
    sender_name: str = "",
    stibee_api_key: str = "",
) -> dict:
    """
    이메일 API로 주소록 전체에 일괄 발송 (프로 요금제+)

    이 방식의 장점:
    - 주소록 전체에 한 번에 발송
    - 간단한 설정

    단점:
    - 개인별 콘텐츠 커스터마이징 제한적
    - $%name%$ 등 기본 치환만 가능

    Args:
        list_id: 주소록 ID
        subject: 이메일 제목
        html_content: HTML 콘텐츠
        sender_email: 발신자 이메일
        sender_name: 발신자 이름
    """
    client = StibeeClient(stibee_api_key)

    # 1) 이메일 생성
    print("📝 이메일 생성 중...")
    result = client.create_email(list_id, subject, sender_email, sender_name)
    if not result.get("data"):
        print("❌ 이메일 생성 실패")
        return {}

    email_id = str(result["data"]["id"])

    # 2) 콘텐츠 설정
    print("📄 콘텐츠 설정 중...")
    client.set_email_content(email_id, html_content)

    # 3) 발송
    print("🚀 발송 중...")
    send_result = client.send_email(email_id)

    return {"email_id": email_id, "result": send_result}


# ============================================================
# 통합 파이프라인 (Apollo 추출 → 스티비 발송)
# ============================================================

def run_stibee_pipeline(
    leads_file: str,
    list_id: str = "",
    auto_email_url: str = "",
    mode: str = "auto",          # "auto" (개인화) 또는 "bulk" (일괄)
    add_to_address_book: bool = True,
    send_emails: bool = False,   # True면 실제 발송!
    use_claude_api: bool = True,
    max_leads: int = 0,
    output_dir: str = "output/newsletters",
):
    """
    통합 파이프라인: Apollo 리드 → 뉴스 수집 → 인사이트 생성 → 스티비 발송

    Args:
        leads_file: Apollo 추출 결과 CSV/Excel 파일
        list_id: 스티비 주소록 ID
        auto_email_url: 자동 이메일 API URL (mode="auto"일 때)
        mode: "auto" (개인화) 또는 "bulk" (일괄)
        add_to_address_book: 구독자로 추가 여부
        send_emails: 실제 발송 여부 (False면 HTML만 생성)
        use_claude_api: Claude API 사용 여부
        max_leads: 최대 처리 건수 (0=전체)
        output_dir: HTML 저장 폴더
    """
    # newsletter_pipeline 모듈 임포트
    from newsletter_pipeline import (
        load_leads_from_csv, load_leads_from_excel,
        NewsCollector, InsightGenerator, FallbackInsightGenerator,
        NewsletterBuilder, _map_industry,
        NEWS_API_KEY, ANTHROPIC_API_KEY,
    )
    # NewsCollector = NewsCollectorWrapper (news_collector_1 래핑)
    # collect_by_industry(), collect_by_company() 메서드 제공

    list_id = list_id or STIBEE_LIST_ID
    auto_email_url = auto_email_url or STIBEE_AUTO_EMAIL_URL

    print("=" * 60)
    print("🚀 스티비 연동 뉴스레터 파이프라인")
    print("=" * 60)

    # 1) 리드 로드
    if leads_file.endswith(".csv"):
        leads = load_leads_from_csv(leads_file)
    else:
        leads = load_leads_from_excel(leads_file)

    if max_leads > 0:
        leads = leads[:max_leads]

    if not leads:
        print("⚠️ 담당자가 없습니다.")
        return

    # 2) 스티비 주소록에 구독자 추가
    if add_to_address_book and list_id:
        print("\n📋 스티비 주소록에 구독자 추가 중...")
        client = StibeeClient()
        subscribers = convert_leads_to_subscribers(leads)

        # 배치 사이즈 100건씩
        batch_size = 100
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            client.add_subscribers(list_id, batch)
            if i + batch_size < len(subscribers):
                time.sleep(7)  # 10회/분 제한 준수

    # 3) 뉴스 수집 + 인사이트 생성
    news_collector = NewsCollector(NEWS_API_KEY)

    if use_claude_api and ANTHROPIC_API_KEY:
        insight_gen = InsightGenerator(ANTHROPIC_API_KEY)
        print("\n🤖 Claude API 인사이트 모드")
    else:
        insight_gen = FallbackInsightGenerator()
        print("\n📝 템플릿 기반 인사이트 모드")

    builder = NewsletterBuilder()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    news_cache = {}
    leads_with_insights = []

    for i, lead in enumerate(leads, 1):
        name = lead.get("이름", "담당자")
        email = lead.get("이메일", "")
        title = lead.get("직함", "")
        company = lead.get("회사명", "")
        industry = _map_industry(lead.get("회사_산업", ""))

        print(f"\n[{i}/{len(leads)}] {name} ({company})")

        if not email:
            print("  ⏭️ 이메일 없음 - 건너뜀")
            continue

        # 뉴스 수집 (캐시)
        if industry not in news_cache:
            print(f"  📰 {industry} 뉴스 수집 중...")
            news_cache[industry] = news_collector.collect_by_industry(industry)

        industry_news = news_cache[industry]
        company_news = news_collector.collect_by_company(company, 2) if company else []

        # 인사이트 생성
        print(f"  💡 인사이트 생성 중...")
        insight = insight_gen.generate_insight(name, title, company, industry, industry_news, company_news)

        # HTML 생성
        html = builder.build_html(insight, industry_news)

        # HTML 저장
        safe_name = re.sub(r'[^\w가-힣]', '_', f"{company}_{name}")
        html_file = out_path / f"{safe_name}.html"
        html_file.write_text(html, encoding="utf-8")

        leads_with_insights.append({
            "email": email,
            "name": name,
            "company": company,
            "title": title,
            "industry": industry,
            "insight": insight,
            "html": html,
            "html_file": str(html_file),
        })

    # 4) 발송
    if send_emails and leads_with_insights:
        if mode == "auto":
            print("\n" + "=" * 60)
            print("📧 자동 이메일 API로 개인화 발송")
            print("=" * 60)
            result = send_personalized_via_auto_email(leads_with_insights, auto_email_url)
        else:
            print("\n⚠️ 일괄 발송 모드는 개인화가 제한됩니다.")
            print("   개인화 발송을 원하면 mode='auto'를 사용하세요.")
    else:
        print(f"\n📄 HTML 파일 {len(leads_with_insights)}건 생성 완료")
        print(f"   저장 위치: {out_path}/")
        if not send_emails:
            print("   💡 실제 발송하려면 send_emails=True로 설정하세요.")

    # 5) 결과 로그
    log_data = {
        "run_at": datetime.now().isoformat(),
        "mode": mode,
        "total_leads": len(leads),
        "processed": len(leads_with_insights),
        "send_emails": send_emails,
        "details": [
            {k: v for k, v in item.items() if k != "html"}
            for item in leads_with_insights
        ],
    }
    log_file = out_path / f"stibee_log_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ 파이프라인 완료. 로그: {log_file}")
    return leads_with_insights


# ============================================================
# 실행 예시
# ============================================================

if __name__ == "__main__":
    import glob

    # API 인증 테스트
    try:
        client = StibeeClient()
        client.check_auth()
    except ValueError as e:
        print(e)
        print("\n.env 파일을 먼저 설정해주세요.")
        exit(1)

    # 가장 최근 Apollo 추출 파일 탐색
    xlsx_files = sorted(glob.glob("output/apollo_leads_*.xlsx"))
    csv_files = sorted(glob.glob("output/apollo_leads_*.csv"))
    leads_file = (xlsx_files or csv_files or [""])[-1]

    if not leads_file:
        print("⚠️ Apollo 추출 결과 파일이 없습니다.")
        print("   먼저 apollo_lead_extractor.py를 실행하세요.")
        exit(1)

    print(f"📂 사용 파일: {leads_file}")

    # 파이프라인 실행
    run_stibee_pipeline(
        leads_file=leads_file,
        list_id=STIBEE_LIST_ID,
        auto_email_url=STIBEE_AUTO_EMAIL_URL,
        mode="auto",              # "auto" (개인화) 추천
        add_to_address_book=True,  # 스티비 주소록에 구독자 추가
        send_emails=False,         # ⚠️ True로 변경 시 실제 발송!
        use_claude_api=True,
        max_leads=5,               # 테스트: 5건만
    )
