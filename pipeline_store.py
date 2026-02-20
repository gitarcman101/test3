"""
Pipeline State Store — JSON 기반 영속화
========================================
1) Run Store: 파이프라인 실행(run) 단위로 리드/뉴스/인사이트/HTML/리뷰 상태를 JSON 파일로 저장.
2) Lead CRM: 리드별 상태 추적 (new → researched → sent → replied → meeting_set / no_response)

data/runs/
  run_YYYYMMDD_HHMM/
    meta.json       — run 메타데이터
    leads.json      — 리드 정보 리스트
    news.json       — {lead_idx: [뉴스 목록]}
    insights.json   — {lead_idx: insight_dict}
    html/           — 리드별 HTML 파일
    reviews.json    — {lead_idx: {status, reviewer, comment, timestamp}}
    send.json       — {lead_idx: status}

data/crm/
  leads.json        — 리드 CRM 데이터 (status 추적)
"""

import json
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "runs"
CRM_DIR = Path(__file__).parent / "data" / "crm"

# ── 리드 CRM 상태 정의 ──
LEAD_STATUSES = {
    "new": "리드 입력됨, 아직 미발송",
    "researched": "기업 리서치 완료",
    "sent": "메일 발송됨",
    "replied": "회신 수신",
    "meeting_set": "미팅 확정",
    "converted_subscriber": "뉴스레터 구독 전환",
    "no_response": "무응답",
    "archived": "더 이상 추적 안 함",
}


class PipelineStore:
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── Run 관리 ──

    def create_run(self, leads: list) -> str:
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M')}"
        run_dir = self.base_dir / run_id
        # 같은 분에 중복 생성 방지
        counter = 1
        while run_dir.exists():
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M')}_{counter}"
            run_dir = self.base_dir / run_id
            counter += 1
        run_dir.mkdir(parents=True)
        (run_dir / "html").mkdir()

        meta = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "status": "in_progress",
            "total_leads": len(leads),
        }
        self._write_json(run_dir / "meta.json", meta)
        self._write_json(run_dir / "leads.json", leads)
        self._write_json(run_dir / "reviews.json", {})
        self._write_json(run_dir / "send.json", {})
        return run_id

    def list_runs(self) -> list:
        runs = []
        for d in sorted(self.base_dir.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("run_"):
                meta_path = d / "meta.json"
                if meta_path.exists():
                    meta = self._read_json(meta_path)
                    runs.append(meta)
        return runs

    def load_run(self, run_id: str) -> dict:
        run_dir = self.base_dir / run_id
        if not run_dir.exists():
            return {}

        result = {
            "meta": self._read_json(run_dir / "meta.json"),
            "leads": self._read_json(run_dir / "leads.json"),
            "news": self._read_json(run_dir / "news.json"),
            "insights": self._read_json(run_dir / "insights.json"),
            "reviews": self._read_json(run_dir / "reviews.json"),
            "send": self._read_json(run_dir / "send.json"),
        }

        # HTML 파일 로드
        html_dir = run_dir / "html"
        html_by_lead = {}
        if html_dir.exists():
            for f in html_dir.iterdir():
                if f.suffix == ".html":
                    idx_str = f.name.split("_", 1)[0]
                    try:
                        idx = int(idx_str)
                        html_by_lead[idx] = f.read_text(encoding="utf-8")
                    except (ValueError, UnicodeDecodeError):
                        pass
        result["html"] = html_by_lead
        return result

    def update_run_status(self, run_id: str, status: str):
        run_dir = self.base_dir / run_id
        meta_path = run_dir / "meta.json"
        if meta_path.exists():
            meta = self._read_json(meta_path)
            meta["status"] = status
            self._write_json(meta_path, meta)

    # ── 데이터 저장 ──

    def save_news(self, run_id: str, news_by_lead: dict):
        run_dir = self.base_dir / run_id
        # _raw 객체는 직렬화 불가하므로 제거한 복사본 저장
        clean = {}
        for idx, articles in news_by_lead.items():
            clean[str(idx)] = [
                {k: v for k, v in art.items() if k != "_raw"}
                for art in articles
            ]
        self._write_json(run_dir / "news.json", clean)

    def save_insights(self, run_id: str, insights_by_lead: dict):
        run_dir = self.base_dir / run_id
        clean = {str(k): v for k, v in insights_by_lead.items()}
        self._write_json(run_dir / "insights.json", clean)

    def save_html(self, run_id: str, lead_idx: int, html: str, lead_name: str = ""):
        run_dir = self.base_dir / run_id
        html_dir = run_dir / "html"
        html_dir.mkdir(exist_ok=True)
        safe_name = re.sub(r'[^\w가-힣]', '_', lead_name) if lead_name else ""
        filename = f"{lead_idx}_{safe_name}.html" if safe_name else f"{lead_idx}.html"
        (html_dir / filename).write_text(html, encoding="utf-8")

    def save_review(self, run_id: str, lead_idx: int,
                    status: str, reviewer: str = "", comment: str = ""):
        run_dir = self.base_dir / run_id
        reviews_path = run_dir / "reviews.json"
        reviews = self._read_json(reviews_path)
        reviews[str(lead_idx)] = {
            "status": status,         # "approved" | "rejected" | "comment"
            "reviewer": reviewer,
            "comment": comment,
            "timestamp": datetime.now().isoformat(),
        }
        self._write_json(reviews_path, reviews)

    def save_send_status(self, run_id: str, lead_idx: int, status: str):
        run_dir = self.base_dir / run_id
        send_path = run_dir / "send.json"
        send_data = self._read_json(send_path)
        send_data[str(lead_idx)] = status
        self._write_json(send_path, send_data)

    # ── 조회 ──

    def get_reviews(self, run_id: str) -> dict:
        run_dir = self.base_dir / run_id
        return self._read_json(run_dir / "reviews.json")

    def get_run_summary(self, run_id: str) -> dict:
        run_dir = self.base_dir / run_id
        if not run_dir.exists():
            return {}

        leads = self._read_json(run_dir / "leads.json")
        news = self._read_json(run_dir / "news.json")
        insights = self._read_json(run_dir / "insights.json")
        reviews = self._read_json(run_dir / "reviews.json")
        send = self._read_json(run_dir / "send.json")
        html_dir = run_dir / "html"
        html_indices = set()
        if html_dir.exists():
            for f in html_dir.iterdir():
                if f.suffix == ".html":
                    try:
                        html_indices.add(int(f.name.split("_", 1)[0]))
                    except ValueError:
                        pass

        summary = []
        for i, ld in enumerate(leads or []):
            si = str(i)
            review_info = reviews.get(si, {})
            stage = "input"
            if si in news:
                stage = "news"
            if si in insights:
                stage = "insight"
            if i in html_indices:
                stage = "html"
            if review_info.get("status") == "approved":
                stage = "approved"
            elif review_info.get("status") == "rejected":
                stage = "rejected"
            if send.get(si) == "sent":
                stage = "sent"
            elif send.get(si) == "failed":
                stage = "failed"

            summary.append({
                "index": i,
                "name": ld.get("이름", ""),
                "company": ld.get("회사명", ""),
                "stage": stage,
                "review": review_info,
            })
        return {"leads": summary, "total": len(leads or [])}

    def get_lead_stage(self, run_id: str, lead_idx: int) -> str:
        summary = self.get_run_summary(run_id)
        for ld in summary.get("leads", []):
            if ld["index"] == lead_idx:
                return ld["stage"]
        return "input"

    # ── 유틸리티 ──

    def _write_json(self, path: Path, data):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _read_json(self, path: Path):
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}


class LeadCRM:
    """
    리드 CRM — 리드별 상태 추적 (run과 독립적으로 유지)

    Status flow:
        new → researched → sent → replied → meeting_set
                                ↓
                              no_response → archived

    data/crm/leads.json에 전체 리드 목록 저장.
    """

    def __init__(self, crm_dir: Path = None):
        self.crm_dir = crm_dir or CRM_DIR
        self.crm_dir.mkdir(parents=True, exist_ok=True)
        self.leads_path = self.crm_dir / "leads.json"

    # ── 리드 CRUD ──

    def add_lead(self, lead_data: dict) -> dict:
        """새 리드 추가. lead_id 자동 생성."""
        leads = self._load_leads()

        # lead_id 생성
        today = datetime.now().strftime("%Y%m%d")
        existing_today = [l for l in leads if l.get("lead_id", "").startswith(f"lead_{today}")]
        seq = len(existing_today) + 1
        lead_id = f"lead_{today}_{seq:03d}"

        lead = {
            "lead_id": lead_id,
            "company": lead_data.get("company", lead_data.get("회사명", "")),
            "industry": lead_data.get("industry", lead_data.get("산업", "")),
            "contact_name": lead_data.get("contact_name", lead_data.get("이름", "")),
            "contact_email": lead_data.get("contact_email", lead_data.get("이메일", "")),
            "contact_title": lead_data.get("contact_title", lead_data.get("직함", "")),
            "trigger": lead_data.get("trigger", ""),
            "source": lead_data.get("source", "manual"),
            "status": "new",
            "last_sent_at": None,
            "replied": False,
            "converted_to_subscriber": False,
            "custom_research": None,
            "created_at": datetime.now().isoformat(),
            "history": [],
        }

        leads.append(lead)
        self._save_leads(leads)
        return lead

    def get_lead(self, lead_id: str) -> dict | None:
        """lead_id로 리드 조회."""
        leads = self._load_leads()
        for lead in leads:
            if lead.get("lead_id") == lead_id:
                return lead
        return None

    def get_lead_by_email(self, email: str) -> dict | None:
        """이메일로 리드 조회."""
        leads = self._load_leads()
        for lead in leads:
            if lead.get("contact_email") == email:
                return lead
        return None

    def update_lead(self, lead_id: str, updates: dict) -> bool:
        """리드 필드 업데이트 + history에 기록."""
        leads = self._load_leads()
        for i, lead in enumerate(leads):
            if lead.get("lead_id") == lead_id:
                # history 추가
                old_status = lead.get("status")
                new_status = updates.get("status", old_status)

                if "history" not in lead:
                    lead["history"] = []

                if old_status != new_status:
                    lead["history"].append({
                        "action": f"status: {old_status} → {new_status}",
                        "timestamp": datetime.now().isoformat(),
                    })

                # 필드 업데이트
                for key, val in updates.items():
                    if key != "lead_id":  # lead_id는 변경 불가
                        lead[key] = val

                leads[i] = lead
                self._save_leads(leads)
                return True
        return False

    def update_status(self, lead_id: str, new_status: str, note: str = "") -> bool:
        """리드 상태 변경 (유효성 검사 포함)."""
        if new_status not in LEAD_STATUSES:
            return False

        updates = {"status": new_status}
        if new_status == "sent":
            updates["last_sent_at"] = datetime.now().isoformat()
        elif new_status == "replied":
            updates["replied"] = True
        elif new_status == "converted_subscriber":
            updates["converted_to_subscriber"] = True

        leads = self._load_leads()
        for i, lead in enumerate(leads):
            if lead.get("lead_id") == lead_id:
                old_status = lead.get("status")
                if "history" not in lead:
                    lead["history"] = []
                lead["history"].append({
                    "action": f"status: {old_status} → {new_status}",
                    "note": note,
                    "timestamp": datetime.now().isoformat(),
                })
                for key, val in updates.items():
                    lead[key] = val
                leads[i] = lead
                self._save_leads(leads)
                return True
        return False

    def list_leads(self, status: str = None) -> list:
        """전체 리드 목록 (status 필터 가능)."""
        leads = self._load_leads()
        if status:
            return [l for l in leads if l.get("status") == status]
        return leads

    def get_stats(self) -> dict:
        """리드 현황 통계."""
        leads = self._load_leads()
        stats = {s: 0 for s in LEAD_STATUSES}
        for lead in leads:
            s = lead.get("status", "new")
            if s in stats:
                stats[s] += 1
        stats["total"] = len(leads)
        return stats

    def delete_lead(self, lead_id: str) -> bool:
        """리드 삭제."""
        leads = self._load_leads()
        original_len = len(leads)
        leads = [l for l in leads if l.get("lead_id") != lead_id]
        if len(leads) < original_len:
            self._save_leads(leads)
            return True
        return False

    # ── 배치 가져오기 ──

    def import_leads_from_run(self, store: "PipelineStore", run_id: str) -> list:
        """
        기존 PipelineStore run에서 리드를 CRM으로 가져오기.
        이미 존재하는 이메일은 건너뜀.
        """
        run_data = store.load_run(run_id)
        if not run_data:
            return []

        imported = []
        existing_emails = {l.get("contact_email") for l in self._load_leads()}

        for ld in run_data.get("leads", []):
            email = ld.get("이메일", "")
            if email and email not in existing_emails:
                lead = self.add_lead({
                    "company": ld.get("회사명", ""),
                    "industry": ld.get("산업", ""),
                    "contact_name": ld.get("이름", ""),
                    "contact_email": email,
                    "contact_title": ld.get("직함", ""),
                    "source": "pipeline_import",
                })
                imported.append(lead)
                existing_emails.add(email)

        return imported

    # ── 내부 유틸 ──

    def _load_leads(self) -> list:
        if not self.leads_path.exists():
            return []
        try:
            data = json.loads(self.leads_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []

    def _save_leads(self, leads: list):
        self.leads_path.write_text(
            json.dumps(leads, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
