"""
Pipeline State Store — JSON 기반 영속화
========================================
파이프라인 실행(run) 단위로 리드/뉴스/인사이트/HTML/리뷰 상태를 JSON 파일로 저장.
세션 소실(브라우저 새로고침) 시 복구 가능.

data/runs/
  run_YYYYMMDD_HHMM/
    meta.json       — run 메타데이터
    leads.json      — 리드 정보 리스트
    news.json       — {lead_idx: [뉴스 목록]}
    insights.json   — {lead_idx: insight_dict}
    html/           — 리드별 HTML 파일
    reviews.json    — {lead_idx: {status, reviewer, comment, timestamp}}
    send.json       — {lead_idx: status}
"""

import json
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "runs"


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
