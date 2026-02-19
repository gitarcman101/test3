"""
통합 뉴스레터 파이프라인 (Newsletter Pipeline)
================================================
Apollo 리드 → 뉴스 수집 → Claude 인사이트 생성 → HTML 빌드 → 스티비 발송

구성 모듈:
- apollo_lead_extractor.py  → 담당자 Enrichment (People Enrichment API)
- news_collector_1.py       → 뉴스 3축 수집 (Google News RSS + trafilatura)
- stibee_integration.py     → 스티비 발송 (API v2)
- 본 모듈                   → 인사이트 생성 + HTML 빌드 + 전체 오케스트레이션

사용법:
    # 1) dry-run (HTML만 생성)
    python newsletter_pipeline.py --leads output/apollo_leads.xlsx

    # 2) 실제 발송
    python newsletter_pipeline.py --leads output/apollo_leads.xlsx --send

    # 3) 코드에서 직접 호출
    from newsletter_pipeline import run_pipeline
    run_pipeline(leads_file="output/apollo_leads.xlsx", send_emails=False)
"""

import csv
import json
import logging
import os
import re
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import asdict
from typing import Optional

# ------------------------------------
# 로깅 설정
# ------------------------------------

logger = logging.getLogger("deta_pipeline")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # 파일 로그 (선택)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
    logger.addHandler(fh)


# ------------------------------------
# 환경변수 + 설정 로더
# ------------------------------------

def _load_env() -> dict:
    """config/.env, Streamlit secrets, 또는 환경변수에서 로드"""
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
    for key in ["ANTHROPIC_API_KEY", "STIBEE_API_KEY", "STIBEE_LIST_ID",
                "STIBEE_AUTO_EMAIL_URL", "SENDER_EMAIL", "SENDER_NAME"]:
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _load_config() -> dict:
    """config/config.yaml 로드 (선택)"""
    try:
        import yaml
        cfg_path = Path("config/config.yaml")
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except ImportError:
        pass
    return {}


_ENV = _load_env()
_CONFIG = _load_config()

# API 키들 (stibee_integration.py 호환용으로 모듈 레벨 변수 유지)
ANTHROPIC_API_KEY = _ENV.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
NEWS_API_KEY = _ENV.get("NEWS_API_KEY", "")  # 미사용 (Google News RSS 무료), 하위 호환용
STIBEE_API_KEY = _ENV.get("STIBEE_API_KEY", "")
STIBEE_LIST_ID = _ENV.get("STIBEE_LIST_ID", "")
STIBEE_AUTO_EMAIL_URL = _ENV.get("STIBEE_AUTO_EMAIL_URL", "")
SENDER_EMAIL = _ENV.get("SENDER_EMAIL", "bnnmoy-gmail.com@send.stibee.com")
SENDER_NAME = _ENV.get("SENDER_NAME", "DETA Intelligence")


# ============================================================
# 산업 매핑
# ============================================================

# Apollo 산업 분류 → news_collector_1.py INDUSTRY_CONFIG 키 매핑
# deta.kr 12개 산업 분류 기준
INDUSTRY_MAP = {
    # ── 화학 및 재료 ──
    "chemicals": "화학 및 재료",
    "materials": "화학 및 재료",
    "mining & metals": "화학 및 재료",
    "plastics": "화학 및 재료",
    "화학": "화학 및 재료",
    "재료": "화학 및 재료",
    "소재": "화학 및 재료",
    # ── 정보통신기술(ICT) ──
    "information technology": "정보통신기술(ICT)",
    "computer software": "정보통신기술(ICT)",
    "internet": "정보통신기술(ICT)",
    "telecommunications": "정보통신기술(ICT)",
    "computer networking": "정보통신기술(ICT)",
    "it": "정보통신기술(ICT)",
    "소프트웨어": "정보통신기술(ICT)",
    "정보기술": "정보통신기술(ICT)",
    "통신": "정보통신기술(ICT)",
    "ict": "정보통신기술(ICT)",
    # ── 전자(반도체 등) ──
    "semiconductors": "전자(반도체 등)",
    "computer hardware": "전자(반도체 등)",
    "electrical/electronic manufacturing": "전자(반도체 등)",
    "consumer electronics": "전자(반도체 등)",
    "반도체": "전자(반도체 등)",
    "전자": "전자(반도체 등)",
    "디스플레이": "전자(반도체 등)",
    # ── 자동화 ──
    "industrial automation": "자동화",
    "machinery": "자동화",
    "manufacturing": "자동화",
    "로봇": "자동화",
    "자동화": "자동화",
    "제조": "자동화",
    "제조업": "자동화",
    # ── 자동차 ──
    "automotive": "자동차",
    "자동차": "자동차",
    # ── 우주 및 국방 ──
    "defense & space": "우주 및 국방",
    "military": "우주 및 국방",
    "aviation & aerospace": "우주 및 국방",
    "국방": "우주 및 국방",
    "우주": "우주 및 국방",
    "항공": "우주 및 국방",
    "방위": "우주 및 국방",
    # ── 에너지 ──
    "oil & energy": "에너지",
    "renewables & environment": "에너지",
    "utilities": "에너지",
    "에너지": "에너지",
    "전력": "에너지",
    "신재생": "에너지",
    # ── 식음료 ──
    "food & beverages": "식음료",
    "food production": "식음료",
    "restaurants": "식음료",
    "식품": "식음료",
    "음료": "식음료",
    "식음료": "식음료",
    "외식": "식음료",
    # ── 소비재 및 서비스 ──
    "retail": "소비재 및 서비스",
    "consumer goods": "소비재 및 서비스",
    "wholesale": "소비재 및 서비스",
    "e-commerce": "소비재 및 서비스",
    "marketing and advertising": "소비재 및 서비스",
    "online media": "소비재 및 서비스",
    "public relations": "소비재 및 서비스",
    "hospitality": "소비재 및 서비스",
    "luxury goods & jewelry": "소비재 및 서비스",
    "유통": "소비재 및 서비스",
    "이커머스": "소비재 및 서비스",
    "소매": "소비재 및 서비스",
    "소비재": "소비재 및 서비스",
    "마케팅": "소비재 및 서비스",
    "광고": "소비재 및 서비스",
    "서비스": "소비재 및 서비스",
    # ── 생명과학 및 헬스케어 ──
    "health care": "생명과학 및 헬스케어",
    "hospital & health care": "생명과학 및 헬스케어",
    "pharmaceuticals": "생명과학 및 헬스케어",
    "biotechnology": "생명과학 및 헬스케어",
    "medical devices": "생명과학 및 헬스케어",
    "헬스케어": "생명과학 및 헬스케어",
    "의료": "생명과학 및 헬스케어",
    "바이오": "생명과학 및 헬스케어",
    "제약": "생명과학 및 헬스케어",
    "생명과학": "생명과학 및 헬스케어",
    # ── 교육 ──
    "education management": "교육",
    "e-learning": "교육",
    "higher education": "교육",
    "primary/secondary education": "교육",
    "교육": "교육",
    "에듀테크": "교육",
    # ── 농업 ──
    "farming": "농업",
    "agriculture": "농업",
    "dairy": "농업",
    "fishery": "농업",
    "농업": "농업",
    "축산": "농업",
    "수산": "농업",
    # ── 금융 (기타 매핑 — 12개 분류에는 없지만 Apollo에서 올 수 있음) ──
    "financial services": "소비재 및 서비스",
    "banking": "소비재 및 서비스",
    "insurance": "소비재 및 서비스",
    "capital markets": "소비재 및 서비스",
    "investment management": "소비재 및 서비스",
    "금융": "소비재 및 서비스",
    "은행": "소비재 및 서비스",
    "보험": "소비재 및 서비스",
}


def _map_industry(raw: str) -> str:
    """Apollo 산업 분류를 INDUSTRY_CONFIG 키로 변환"""
    if not raw:
        return "기타"
    raw_lower = raw.lower().strip()
    # 정확 매칭
    if raw_lower in INDUSTRY_MAP:
        return INDUSTRY_MAP[raw_lower]
    # 부분 매칭
    for key, val in INDUSTRY_MAP.items():
        if key in raw_lower or raw_lower in key:
            return val
    return "기타"


# ============================================================
# 리드 로더 (CSV / Excel)
# ============================================================

def load_leads_from_csv(filepath: str) -> list[dict]:
    """CSV에서 리드 목록 로드"""
    leads = []
    fp = Path(filepath)
    if not fp.exists():
        print(f"⚠️ 파일 없음: {filepath}")
        return leads
    with open(fp, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(dict(row))
    print(f"📂 CSV 로드: {len(leads)}건 ({fp.name})")
    return leads


def load_leads_from_excel(filepath: str) -> list[dict]:
    """Excel에서 리드 목록 로드"""
    try:
        import openpyxl
    except ImportError:
        print("⚠️ openpyxl 미설치. pip install openpyxl")
        return []
    fp = Path(filepath)
    if not fp.exists():
        print(f"⚠️ 파일 없음: {filepath}")
        return []
    wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h or "").strip() for h in rows[0]]
    leads = []
    for row in rows[1:]:
        lead = {}
        for h, v in zip(headers, row):
            if h:
                lead[h] = str(v) if v is not None else ""
        if lead.get("이메일") or lead.get("email"):
            leads.append(lead)
    wb.close()
    print(f"📂 Excel 로드: {len(leads)}건 ({fp.name})")
    return leads


# ============================================================
# 인사이트 생성기 (Claude API)
# ============================================================

class InsightGenerator:
    """Claude API 기반 기업 맞춤형 인사이트 생성"""

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-5-20250929"):
        self.api_key = api_key or ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("pip install anthropic 필요")
        self.model = model

    def generate_insight(
        self,
        name: str,
        title: str,
        company: str,
        industry: str,
        industry_news: list,
        company_news: list = None,
        company_context: dict = None,
    ) -> dict:
        """
        기업 현황 기반 맞춤형 Deep-Dive 인사이트 생성

        Args:
            company_context: {
                "description": "회사 설명",
                "domain": "회사 도메인",
                "size": "직원수",
                "revenue": "매출",
                "location": "위치",
            }

        Returns:
            {
                "subject_line": "이메일 제목",
                "greeting": "인사말",
                "insight_1": {"title": "...", "content": "...", "source": "..."},
                "insight_2": {"title": "...", "content": "..."},
                "industry_insight": "산업 인사이트 HTML",
                "company_relevance": "기업 관련성",
                "key_takeaway": "핵심 시사점",
                "cta": "CTA 문구",
            }
        """
        # 뉴스 요약 텍스트 구성
        news_text = self._format_news(industry_news, company_news)

        # 기업 현황 컨텍스트 구성
        ctx = company_context or {}
        company_profile = self._build_company_profile(
            company, industry, title, ctx, company_news
        )

        prompt = f"""당신은 B2B 전략 컨설팅 전문가입니다.

═══════════════════════════════
📌 기업 현황 (Company Profile)
═══════════════════════════════
{company_profile}

═══════════════════════════════
📰 최근 뉴스
═══════════════════════════════
{news_text}

═══════════════════════════════
🔬 리서치 방법론
═══════════════════════════════
Search for this information in a structured way. As you gather data, develop several competing hypotheses. Track your confidence levels in your progress notes to improve calibration. Regularly self-critique your approach and plan. Update a hypothesis tree or research notes file to persist information and provide transparency. Break down this complex research task systematically.

구체적 단계:
1. {company}의 사업 모델·제품·고객 기반으로 핵심 경쟁사 2-3개를 먼저 식별
   - 경쟁사 후보를 나열하고, 각 후보에 대해 "{company}와 동일 고객군을 두고 경쟁하는가?" 기준으로 평가
   - 신뢰도가 높은 경쟁사를 최종 선정
2. 뉴스를 훑으며 {company} 및 경쟁사와 관련성이 높은 후보 이슈 2-3개를 도출
3. 각 후보에 대해 "{title}이(가) 즉시 팀에 공유하고 싶을 정도로 관련성이 높은가?" 기준으로 평가
4. 경쟁 가설을 세우고 가장 신뢰도 높은 이슈 1개를 최종 선정
5. 선정된 이슈를 {company}의 사업 모델·제품·고객 관점에서 Deep-Dive 분석 (경쟁사 대비 포지셔닝 포함)
6. 분석 중 자기비판 — "이 분석이 {company}에게 실질적 가치가 있는가?" 검증

═══════════════════════════════
✍️ 작성 지침
═══════════════════════════════

선정된 이슈 1개를 기반으로, 서로 다른 각도의 Deep-Dive 인사이트 2개를 작성하세요.

- insight_1: 이슈의 배경·현황을 소개하고 {company}에 미치는 구체적 영향을 분석 (2-3문장, 최대 3줄)
- insight_2: 같은 이슈를 다른 시각에서 분석 — 기회, 리스크, 전략, 시장 변화 등 자유롭게 (2-3문장, 최대 3줄)

⚠️ 두 인사이트의 title은 고정 라벨이 아니라, 인사이트 내용을 함축하는 구체적 제목이어야 합니다.
   ⚠️ 제목은 반드시 8단어 이내로 작성 (짧고 임팩트 있게)
   예: "EU AI Act, B2B SaaS 수익 구조 재편", "선제적 컴플라이언스가 만드는 프리미엄"

아래 JSON 형식으로 정확히 응답해주세요 (JSON만, 다른 텍스트 없이):
{{
    "subject_line": "이메일 제목 (규칙: 느낌표(!) 금지, 전체 대문자 금지, '무료/긴급/클릭/지금 바로' 등 스팸 트리거 단어 금지, 15자 이내 간결하게, {company}명 포함). 예: '{company} {industry} 시장 이슈 브리핑'",
    "greeting": "인사 문구 (규칙: title이 유효한 한국어 직함(대표, 이사, 부장, 팀장, 과장, 매니저 등)이면 '안녕하세요, {name} {title}님.' / title이 비어있거나 부서명(부서,팀,본부,실,센터 포함)이거나 영문이면 '안녕하세요, {name}님.' — 이름과 님 사이에 공백 넣지 말 것). 뒤에 '{company}에 직접적으로 영향을 줄 수 있는 {industry} 핵심 이슈를 심층 분석했습니다.' 이어붙이기.",
    "insight_1": {{
        "title": "인사이트 내용을 함축하는 구체적 제목 (고정 라벨 금지)",
        "content": "이슈 배경 + {company} 관점 Deep-Dive 분석 (2-3문장, 최대 3줄)",
        "source": "관련 출처명 (복수 가능, 쉼표로 구분)"
    }},
    "insight_2": {{
        "title": "인사이트 내용을 함축하는 구체적 제목 (고정 라벨 금지)",
        "content": "같은 이슈의 다른 각도 Deep-Dive 분석 (2-3문장, 최대 3줄)"
    }},
    "industry_insight": "위 내용을 HTML 형식으로 간결하게 정리 (p, ul, li 태그 사용)",
    "company_relevance": "{company}가 이 이슈에 선제적으로 대응해야 하는 이유 (1-2문장)",
    "key_takeaway": "경영진이 기억해야 할 핵심 시사점 한 줄",
    "cta": "더 자세한 {industry} 시장 분석이 필요하시면 무료 상담을 신청해보세요."
}}

규칙:
- 인사이트 2개가 곧 Deep-Dive 분석 그 자체 (별도 main_issue 없음)
- 각 인사이트의 title이 곧 섹션 제목 — "비즈니스 영향", "대응 전략" 같은 고정 라벨 사용 금지
- 기업 현황에 기반한 이슈 선정 (기업과 무관한 이슈 선정 금지)
- 한 가지 이슈에 집중하여 깊이 있는 분석 제공 (산발적 나열 금지)
- 전문적이면서도 읽기 쉬운 한국 임원보고 문체
- 각 항목은 반드시 한국어로 작성
- 총 읽기 시간 1분 이내가 되도록 간결하되, 내용은 밀도 있게
- {company}의 구체적 사업/제품을 언급하며 시사점 도출"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
            # JSON 파싱 (코드 블록 제거)
            if response_text.startswith("```"):
                response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
                response_text = re.sub(r"\s*```$", "", response_text)
            parsed = json.loads(response_text)

            # Claude 응답의 과다 개행 정리
            def _clean_nl(obj):
                if isinstance(obj, str):
                    return re.sub(r'\n{3,}', '\n\n', obj).strip()
                if isinstance(obj, dict):
                    return {k: _clean_nl(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_clean_nl(v) for v in obj]
                return obj
            return _clean_nl(parsed)
        except json.JSONDecodeError as je:
            print(f"  ⚠️ JSON 파싱 실패, 폴백 사용")
            print(f"  📝 Claude 응답 (처음 500자): {response_text[:500]}")
            return FallbackInsightGenerator().generate_insight(
                name, title, company, industry, industry_news, company_news,
                company_context=company_context,
            )
        except Exception as e:
            print(f"  ❌ Claude API 오류: {e}")
            return FallbackInsightGenerator().generate_insight(
                name, title, company, industry, industry_news, company_news,
                company_context=company_context,
            )

    @staticmethod
    def _build_company_profile(
        company: str,
        industry: str,
        title: str,
        ctx: dict,
        company_news: list = None,
    ) -> str:
        """기업 현황 컨텍스트 텍스트 구성"""
        lines = [f"회사명: {company}", f"산업: {industry}", f"수신자 직함: {title}"]

        if ctx.get("description"):
            lines.append(f"사업 설명: {ctx['description']}")
        if ctx.get("domain"):
            lines.append(f"도메인: {ctx['domain']}")
        if ctx.get("size"):
            lines.append(f"직원 규모: {ctx['size']}명")
        if ctx.get("revenue"):
            lines.append(f"연 매출: {ctx['revenue']}")
        if ctx.get("location"):
            lines.append(f"소재지: {ctx['location']}")

        # 기업 관련 뉴스에서 추가 컨텍스트 추출
        if company_news:
            recent = []
            for article in company_news[:3]:
                t = article.title if hasattr(article, "title") else article.get("title", "")
                if t:
                    recent.append(t)
            if recent:
                lines.append(f"최근 기업 동향: {' / '.join(recent)}")

        return "\n".join(lines)

    def _format_news(self, industry_news: list, company_news: list = None) -> str:
        """뉴스 목록을 텍스트로 포맷"""
        lines = []
        for i, article in enumerate(industry_news[:8], 1):
            # NewsArticle 객체 또는 dict 지원
            if hasattr(article, "title"):
                title = article.title
                desc = article.full_text[:300] if article.full_text else article.description
                source = article.source
                cat = article.category_label
            else:
                title = article.get("title", "")
                desc = article.get("full_text", article.get("description", ""))[:300]
                source = article.get("source", "")
                cat = article.get("category_label", "")
            lines.append(f"[{cat}] {title}")
            if desc:
                lines.append(f"  {desc}")
            if source:
                lines.append(f"  출처: {source}")
            lines.append("")

        if company_news:
            lines.append("--- 기업 관련 뉴스 ---")
            for article in company_news[:3]:
                if hasattr(article, "title"):
                    lines.append(f"[기업 뉴스] {article.title}")
                    if article.full_text:
                        lines.append(f"  {article.full_text[:200]}")
                else:
                    lines.append(f"[기업 뉴스] {article.get('title', '')}")
                lines.append("")

        return "\n".join(lines) if lines else "최신 뉴스 없음"


# ============================================================
# 폴백 인사이트 (Claude 없이 템플릿 기반)
# ============================================================

class FallbackInsightGenerator:
    """Claude API 없이 템플릿 기반 인사이트 생성"""

    def generate_insight(
        self,
        name: str,
        title: str,
        company: str,
        industry: str,
        industry_news: list,
        company_news: list = None,
        company_context: dict = None,
    ) -> dict:
        """뉴스 기사를 기반으로 템플릿 인사이트 생성 (Deep-Dive 2개)"""
        ctx = company_context or {}
        desc = ctx.get("description", "")

        # 첫 번째 기사에서 이슈 정보 추출
        lead_article = self._get_article_info(industry_news[0]) if industry_news else {
            "title": f"{industry} 시장 동향",
            "content": "최신 산업 동향을 분석하고 있습니다.",
            "source": "DETA Research",
        }

        # 인사이트 1: 이슈 배경 + 기업 영향 분석
        biz_context = f" ({desc[:80]})" if desc else ""
        insight1 = {
            "title": f"{lead_article['title']}이 {company}에 미치는 영향",
            "content": f"{lead_article['content']} 이 이슈가 {company}{biz_context}의 {industry} 사업에 미치는 영향을 분석합니다.",
            "source": lead_article.get("source", ""),
        }

        # 인사이트 2: 같은 이슈의 다른 관점
        insight2 = {
            "title": f"{company}의 선제적 대응이 만드는 기회",
            "content": f"{company}가 이 변화에 선제적으로 대응하면 확보할 수 있는 전략적 기회를 분석합니다.",
        }

        # HTML 형식 인사이트
        news_items = ""
        for article in industry_news[:5]:
            info = self._get_article_info(article)
            news_items += f"<li><strong>{info['title']}</strong>: {info['content'][:100]}</li>\n"

        industry_insight_html = f"""
<p>{name}님, {company}에 영향을 줄 수 있는 {industry} 시장의 핵심 이슈를 분석했습니다.</p>
<ul>
{news_items}
</ul>
"""

        # 직함 유효성 판별 (한국어 직함만 사용)
        _title_valid = (
            bool(title) and title.strip() and title != name
            and not any(k in title for k in ["부서", "팀", "본부", "실", "센터"])
            and not title.strip().isascii()  # 영문 직함 제외
        )
        greeting_prefix = f"안녕하세요, {name} {title}님." if _title_valid else f"안녕하세요, {name}님."

        return {
            "subject_line": f"[{industry}] {company}를 위한 핵심 이슈 브리핑",
            "greeting": f"{greeting_prefix} {company}에 직접적으로 영향을 줄 수 있는 {industry} 핵심 이슈를 분석했습니다.",
            "insight_1": insight1,
            "insight_2": insight2,
            "industry_insight": industry_insight_html,
            "company_relevance": f"{company}의 {industry} 사업에 영향을 줄 수 있는 주요 이슈입니다.",
            "key_takeaway": f"이번 주 {industry} 시장은 빠르게 변화하고 있으며, 선제적 대응이 필요합니다.",
            "cta": f"더 자세한 {industry} 시장 분석이 필요하시면 무료 상담을 신청해보세요.",
        }

    @staticmethod
    def _get_article_info(article) -> dict:
        """NewsArticle 또는 dict에서 기사 정보 추출"""
        if hasattr(article, "title"):
            return {
                "title": article.title,
                "content": (article.full_text[:200] if article.full_text
                            else article.description[:200] if article.description
                            else ""),
                "source": article.source or "",
            }
        return {
            "title": article.get("title", ""),
            "content": article.get("full_text", article.get("description", ""))[:200],
            "source": article.get("source", ""),
        }


# ============================================================
# 뉴스레터 HTML 빌더 (Jinja2 기반)
# ============================================================

class NewsletterBuilder:
    """인사이트 데이터 → HTML 뉴스레터 빌드 (Jinja2 템플릿)"""

    def __init__(self, template_dir: str = ""):
        """
        Args:
            template_dir: 템플릿 디렉토리 (기본: 프로젝트 루트/templates)
        """
        if not template_dir:
            template_dir = str(Path(__file__).parent / "templates")
        self.template_dir = Path(template_dir)

        # Jinja2 환경 초기화
        try:
            from jinja2 import Environment, FileSystemLoader
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=False,  # HTML 콘텐츠 허용
            )
            self._use_jinja = True
        except ImportError:
            print("⚠️ jinja2 미설치. pip install jinja2 (인라인 템플릿으로 폴백)")
            self._use_jinja = False

    def build_html(self, insight: dict, news_articles: list = None, template_name: str = "newsletter_v2.html") -> str:
        """
        인사이트 데이터를 HTML 뉴스레터로 변환

        Args:
            insight: InsightGenerator 결과
            news_articles: 원본 뉴스 기사 리스트 (참조 링크용)
            template_name: Jinja2 템플릿 파일명

        Returns:
            HTML 문자열
        """
        # 뉴스 소스 링크 구성
        sources = []
        if news_articles:
            for article in news_articles[:5]:
                if hasattr(article, "title"):
                    sources.append({"title": article.title, "url": article.url, "source": article.source})
                else:
                    sources.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", "#"),
                        "source": article.get("source", ""),
                    })

        # 템플릿 변수
        context = {
            "newsletter_title": "DETA Intelligence Brief",
            "tagline": "1분 안에 읽는 글로벌 시장 인텔리전스",
            "subject_line": insight.get("subject_line", "DETA Intelligence Brief"),
            "preview_text": insight.get("greeting", ""),
            "greeting": insight.get("greeting", "안녕하세요."),
            "issue_date": datetime.now().strftime("%Y.%m.%d"),
            "year": str(datetime.now().year),
            # 인사이트 (Deep-Dive 2개 — main_issue 없음)
            "insight_1": insight.get("insight_1", {}),
            "insight_2": insight.get("insight_2", {}),
            "company_relevance": insight.get("company_relevance", ""),
            "key_takeaway": insight.get("key_takeaway", ""),
            "cta": insight.get("cta", ""),
            # 소스
            "sources": sources,
            # CTA URLs
            "report_url": "https://deta.kr",
            "consult_url": "https://deta.kr",
        }

        # context 값의 과다 개행 정리 (HTML 렌더 전)
        for key in list(context.keys()):
            val = context[key]
            if isinstance(val, str):
                context[key] = re.sub(r'\n{3,}', '\n\n', val)
            elif isinstance(val, dict):
                for k2 in list(val.keys()):
                    if isinstance(val[k2], str):
                        val[k2] = re.sub(r'\n{3,}', '\n\n', val[k2])

        # Jinja2 렌더링
        if self._use_jinja and (self.template_dir / template_name).exists():
            try:
                template = self.jinja_env.get_template(template_name)
                return template.render(**context)
            except Exception as e:
                print(f"  ⚠️ Jinja2 렌더링 실패: {e}, 인라인 폴백 사용")

        # 인라인 폴백 (Jinja2 없을 때)
        return self._build_inline_html(context)

    @staticmethod
    def _build_inline_html(ctx: dict) -> str:
        """Jinja2 없이 인라인 f-string 기반 HTML 생성 (폴백)"""
        i1 = ctx.get("insight_1", {})
        i2 = ctx.get("insight_2", {})

        source_rows = ""
        for s in ctx.get("sources", []):
            t = s.get("title", "")[:60]
            source_rows += f'<tr><td style="padding:3px 0;font-size:12px;"><a href="{s.get("url","#")}" style="color:#738091;text-decoration:none;">{t}</a> <span style="color:#404854;"> — {s.get("source","")}</span></td></tr>'

        # 시사점 + 핵심한줄 통합
        relevance_text = ctx.get('company_relevance', '')
        takeaway_text = ctx.get('key_takeaway', '')
        combined_relevance = f"{relevance_text} {takeaway_text}".strip() if relevance_text else ""

        return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{ctx.get('subject_line','DETA Intelligence Brief')}</title></head>
<body style="margin:0;padding:0;background:#111418;font-family:'Segoe UI',-apple-system,BlinkMacSystemFont,'Noto Sans KR','Malgun Gothic',sans-serif;word-break:keep-all;overflow-wrap:break-word;">
<div style="display:none;font-size:1px;color:#111418;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">{ctx.get('preview_text', ctx.get('greeting', ''))}</div>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#111418;"><tr><td align="center" style="padding:20px 12px;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#1C2127;border-radius:4px;overflow:hidden;">
<tr><td style="background:#1C2127;border-bottom:2px solid #383E47;padding:32px 36px 24px;">
<table width="100%"><tr><td style="font-size:11px;letter-spacing:2px;color:#5F6B7C;font-weight:600;">DETA BRIEFING</td><td style="text-align:right;font-size:11px;color:#5F6B7C;">{ctx.get('issue_date','')}</td></tr></table>
<table width="100%" style="margin-top:14px;"><tr><td style="border-top:1px solid #2F343C;"></td></tr></table>
<h1 style="margin:16px 0 0;color:#E0E0E0;font-size:24px;font-weight:700;letter-spacing:-0.3px;">{ctx.get('newsletter_title','DETA Intelligence Brief')}</h1>
<p style="margin:8px 0 0;font-size:13px;color:#738091;">{ctx.get('tagline','')}</p>
</td></tr>
<tr><td style="padding:24px 36px 0;">
<p style="margin:0;font-size:14px;color:#ABB3BF;line-height:1.7;">{ctx.get('greeting','')}</p>
</td></tr>
<tr><td style="padding:28px 36px 0;">
<table width="100%" style="background:#252A31;border-radius:4px;border-left:3px solid #E0E0E0;"><tr><td style="padding:20px 22px;">
<h3 style="margin:0 0 10px;font-size:16px;color:#E0E0E0;font-weight:600;">{i1.get('title','')}</h3>
<p style="margin:0;font-size:13.5px;color:#8F99A8;line-height:1.75;">{i1.get('content','')}</p>
{'<p style="margin:12px 0 0;font-size:11px;color:#5F6B7C;">Source: '+i1.get('source','')+'</p>' if i1.get('source') else ''}
</td></tr></table></td></tr>
<tr><td style="padding:20px 36px 0;">
<table width="100%" style="background:#252A31;border-radius:4px;border-left:3px solid #738091;"><tr><td style="padding:20px 22px;">
<h3 style="margin:0 0 10px;font-size:16px;color:#C5CBD3;font-weight:600;">{i2.get('title','')}</h3>
<p style="margin:0;font-size:13.5px;color:#8F99A8;line-height:1.75;">{i2.get('content','')}</p>
</td></tr></table></td></tr>
{'<tr><td style="padding:24px 36px 0;"><table width="100%" style="background:#252A31;border-radius:4px;border:1px solid #383E47;"><tr><td style="padding:16px 20px;"><p style="margin:0;font-size:13px;color:#E0E0E0;line-height:1.6;font-weight:600;">'+combined_relevance+'</p></td></tr></table></td></tr>' if combined_relevance else ''}
<tr><td style="padding:28px 36px 0;"><table width="100%"><tr><td style="border-top:1px solid #2F343C;"></td></tr></table></td></tr>
<tr><td style="padding:24px 36px 0;text-align:center;">
<p style="margin:0 0 18px;font-size:14px;color:#ABB3BF;font-weight:500;">{ctx.get('cta','더 자세한 시장 분석이 필요하시면')}</p>
<a href="{ctx.get('report_url','https://deta.kr')}" style="display:inline-block;background:#E0E0E0;color:#1C2127;padding:10px 24px;text-decoration:none;border-radius:3px;font-weight:700;font-size:12px;letter-spacing:0.5px;margin:4px;">SAMPLE REPORT</a>
<a href="{ctx.get('consult_url','https://deta.kr')}" style="display:inline-block;background:#1C2127;color:#ABB3BF;padding:9px 24px;text-decoration:none;border-radius:3px;font-weight:600;font-size:12px;border:1px solid #5F6B7C;letter-spacing:0.5px;margin:4px;">CONTACT US</a>
</td></tr>
{'<tr><td style="padding:28px 36px 0;"><span style="font-size:10px;font-weight:700;color:#5F6B7C;letter-spacing:1.5px;">SOURCES</span><table width="100%" style="margin-top:10px;">'+source_rows+'</table></td></tr>' if source_rows else ''}
<tr><td style="padding-top:28px;"><table width="100%" style="background:#111418;border-top:1px solid #2F343C;"><tr><td style="padding:20px 36px;text-align:center;">
<span style="font-size:11px;letter-spacing:2px;color:#404854;font-weight:600;">DETA</span> <span style="font-size:11px;color:#383E47;">· 데타에이아이컨설팅코리아</span>
<p style="margin:8px 0 0;font-size:10px;color:#383E47;">&copy; {ctx.get('year','2026')} DETA. All rights reserved.</p>
</td></tr></table></td></tr>
</table></td></tr></table></body></html>"""


# ============================================================
# 뉴스 수집 래퍼 (news_collector_1.py 연동)
# ============================================================

class NewsCollectorWrapper:
    """
    news_collector_1.py의 NewsCollector를 래핑하여
    stibee_integration.py 호환 인터페이스 제공

    호환 메서드:
    - collect_by_industry(industry) → list
    - collect_by_company(company, max_results) → list
    """

    def __init__(self, crawl_body: bool = True):
        # news_collector_1 모듈 import
        try:
            from news_collector_1 import NewsCollector as NC1
            self._collector = NC1(crawl_body=crawl_body)
        except ImportError:
            print("⚠️ news_collector_1.py를 찾을 수 없습니다. 같은 디렉토리에 있어야 합니다.")
            self._collector = None

    def collect_by_industry(self, industry: str, days: int = 14, max_per_category: int = 3) -> list:
        """산업별 뉴스 수집 (호환 인터페이스, 기본 2주)"""
        if not self._collector:
            return []
        return self._collector.collect_industry_news(industry, days, max_per_category)

    def collect_by_company(self, company: str, max_results: int = 3) -> list:
        """기업 뉴스 수집 (호환 인터페이스, 기본 2주)"""
        if not self._collector:
            return []
        articles = []
        results = self._collector.rss.search(company, max_results=max_results, days=14)
        for r in results:
            article = self._collector._process_result(r, "기타", "company", "기업 뉴스")
            if article:
                article.company = company
                articles.append(article)
        return articles

    def collect_for_company(
        self,
        company: str,
        industry: str,
        competitors: list = None,
        days: int = 14,
        max_per_category: int = 3,
    ) -> dict:
        """기업 맞춤형 3축 통합 수집 (직접 위임)"""
        if not self._collector:
            return {"industry_trend": [], "competitor": [], "regulation": [], "company_news": [], "all": []}
        return self._collector.collect_for_company(
            company, industry, competitors, days, max_per_category
        )


# stibee_integration.py 호환용 alias
NewsCollector = NewsCollectorWrapper


# ============================================================
# 통합 파이프라인 실행
# ============================================================

def run_pipeline(
    leads_file: str = "",
    leads_list: list[dict] = None,
    send_emails: bool = False,
    add_to_stibee: bool = False,
    use_claude: bool = True,
    crawl_body: bool = True,
    max_leads: int = 0,
    output_dir: str = "output/newsletters",
    mode: str = "auto",
) -> list[dict]:
    """
    전체 파이프라인 실행:
    Apollo 리드 → 뉴스 수집 → 인사이트 생성 → HTML 빌드 → (선택) 스티비 발송

    Args:
        leads_file: Apollo 추출 결과 CSV/Excel 파일 경로
        leads_list: 리드 딕셔너리 리스트 (leads_file 대신 직접 전달)
        send_emails: True면 실제 스티비 발송
        add_to_stibee: 스티비 주소록에 구독자 추가
        use_claude: Claude API 인사이트 사용 (False면 템플릿)
        crawl_body: 뉴스 본문 크롤링 여부
        max_leads: 최대 처리 건수 (0=전체)
        output_dir: HTML 저장 디렉토리
        mode: "auto" (개인화) 또는 "bulk" (일괄)

    Returns:
        인사이트가 포함된 리드 리스트
    """
    print("=" * 60)
    print("🚀 DETA 통합 뉴스레터 파이프라인")
    print(f"   시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # ─── 1) 리드 로드 ────────────────────────────
    if leads_list:
        leads = leads_list
        print(f"\n📋 리드 직접 전달: {len(leads)}건")
    elif leads_file:
        if leads_file.lower().endswith(".csv"):
            leads = load_leads_from_csv(leads_file)
        else:
            leads = load_leads_from_excel(leads_file)
    else:
        print("⚠️ leads_file 또는 leads_list 중 하나를 지정해주세요.")
        return []

    if max_leads > 0:
        leads = leads[:max_leads]

    if not leads:
        print("⚠️ 처리할 리드가 없습니다.")
        return []

    print(f"   처리 대상: {len(leads)}건")

    # ─── 2) 스티비 구독자 추가 (선택) ──────────────
    if add_to_stibee and STIBEE_LIST_ID:
        print("\n📋 스티비 주소록에 구독자 추가 중...")
        try:
            from stibee_integration import StibeeClient, convert_leads_to_subscribers
            client = StibeeClient()
            subscribers = convert_leads_to_subscribers(leads)
            batch_size = 100
            for i in range(0, len(subscribers), batch_size):
                batch = subscribers[i:i + batch_size]
                client.add_subscribers(STIBEE_LIST_ID, batch)
                if i + batch_size < len(subscribers):
                    time.sleep(7)
        except Exception as e:
            print(f"  ⚠️ 스티비 구독자 추가 실패: {e}")

    # ─── 3) 뉴스 수집 + 인사이트 생성 ─────────────
    news_collector = NewsCollectorWrapper(crawl_body=crawl_body)

    if use_claude and ANTHROPIC_API_KEY:
        try:
            insight_gen = InsightGenerator(ANTHROPIC_API_KEY)
            print("\n🤖 Claude API 인사이트 모드")
        except Exception as e:
            print(f"\n⚠️ Claude 초기화 실패: {e}")
            insight_gen = FallbackInsightGenerator()
            print("📝 템플릿 기반 인사이트 모드로 전환")
    else:
        insight_gen = FallbackInsightGenerator()
        print("\n📝 템플릿 기반 인사이트 모드")

    builder = NewsletterBuilder()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    news_cache = {}
    leads_with_insights = []

    for i, lead in enumerate(leads, 1):
        # 필드명 유연 처리 (한국어/영어 둘 다 지원)
        name = lead.get("이름", lead.get("name", "담당자"))
        email = lead.get("이메일", lead.get("email", ""))
        title = lead.get("직함", lead.get("title", ""))
        company = lead.get("회사명", lead.get("company", ""))
        raw_industry = lead.get("회사_산업", lead.get("industry", ""))
        industry = _map_industry(raw_industry)

        # 기업 현황 컨텍스트 구성 (Apollo 데이터 활용)
        company_context = {
            "description": lead.get("회사_설명", lead.get("company_description", "")),
            "domain": lead.get("회사_도메인", lead.get("company_domain", "")),
            "size": lead.get("회사_규모", lead.get("company_size", "")),
            "revenue": lead.get("회사_매출", lead.get("company_revenue", "")),
            "location": lead.get("회사_위치", lead.get("company_location", "")),
        }

        print(f"\n[{i}/{len(leads)}] {name} ({company}) — {industry}")
        if company_context.get("description"):
            print(f"  🏢 기업 프로필: {company_context['description'][:60]}...")

        if not email:
            print("  ⏭️ 이메일 없음 - 건너뜀")
            continue

        # 뉴스 수집 (산업별 캐싱)
        if industry not in news_cache:
            print(f"  📰 {industry} 뉴스 수집 중...")
            news_cache[industry] = news_collector.collect_by_industry(industry)

        industry_news = news_cache[industry]
        company_news = news_collector.collect_by_company(company, 2) if company else []

        # 인사이트 생성 (기업 현황 기반)
        print(f"  💡 기업 현황 기반 Deep-Dive 인사이트 생성 중...")
        insight = insight_gen.generate_insight(
            name, title, company, industry, industry_news, company_news,
            company_context=company_context,
        )

        # HTML 생성
        all_news = industry_news + (company_news or [])
        html = builder.build_html(insight, all_news)

        # HTML 저장
        safe_name = re.sub(r'[^\w가-힣]', '_', f"{company}_{name}")
        html_file = out_path / f"{safe_name}.html"
        html_file.write_text(html, encoding="utf-8")
        print(f"  📄 HTML 저장: {html_file.name}")

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

    # ─── 4) 발송 (선택) ──────────────────────────
    if send_emails and leads_with_insights:
        print("\n" + "=" * 60)
        print("📧 이메일 발송 시작")
        print("=" * 60)
        try:
            if mode == "smtp":
                # SMTP 직접 발송
                from stibee_integration import send_emails_smtp
                send_emails_smtp(leads_with_insights)

            elif mode == "auto" and STIBEE_AUTO_EMAIL_URL:
                # 스티비 자동 이메일 API (v1.0 트리거)
                from stibee_integration import send_personalized_via_auto_email
                send_personalized_via_auto_email(
                    leads_with_insights,
                    auto_email_url=STIBEE_AUTO_EMAIL_URL,
                )

            elif mode == "stibee" and STIBEE_LIST_ID:
                # 스티비 Email API v2 (프로 요금제)
                from stibee_integration import StibeeClient
                client = StibeeClient()
                sender_email = _ENV.get("SENDER_EMAIL", "")
                sender_name = _ENV.get("SENDER_NAME", "DETA Intelligence")

                for item in leads_with_insights:
                    insight = item.get("insight", {})
                    subject = insight.get("subject_line", "DETA Intelligence Brief")
                    html = item.get("html", "")

                    # 1) 이메일 생성 (draft)
                    resp = client.create_email(
                        list_id=STIBEE_LIST_ID,
                        subject=subject,
                        sender_email=sender_email,
                        sender_name=sender_name,
                    )
                    if resp:
                        email_id = resp.get("data", {}).get("id")
                        if email_id:
                            # 2) HTML 콘텐츠 설정
                            client.set_email_content(str(email_id), html)
                            # 3) 발송
                            client.send_email(str(email_id))

            else:
                # 기본: 스티비 구독자 필드 업데이트 + SMTP 시도
                from stibee_integration import StibeeClient, send_emails_smtp

                # 1) 구독자 정보 업데이트
                if STIBEE_LIST_ID:
                    client = StibeeClient()
                    for item in leads_with_insights:
                        subscriber_data = {
                            "email": item.get("email", ""),
                            "name": item.get("name", ""),
                            "company": item.get("company", ""),
                            "industry": item.get("industry", ""),
                        }
                        client.add_subscriber_v1(STIBEE_LIST_ID, subscriber_data)
                        time.sleep(0.3)
                    print(f"  ✅ 스티비 구독자 정보 업데이트 완료")

                # 2) SMTP 발송 시도
                smtp_user = _ENV.get("SMTP_USER", "")
                if smtp_user:
                    send_emails_smtp(leads_with_insights)
                else:
                    print("\n📌 발송 방법을 선택해주세요:")
                    print("   --mode smtp    → SMTP 직접 발송 (SMTP_USER/PASSWORD 설정 필요)")
                    print("   --mode stibee  → 스티비 Email API (발신자 설정 필요)")
                    print("   --mode auto    → 스티비 자동 이메일 (AUTO_EMAIL_URL 필요)")

        except Exception as e:
            print(f"  ❌ 발송 실패: {e}")
    else:
        print(f"\n📄 HTML 파일 {len(leads_with_insights)}건 생성 완료")
        print(f"   저장 위치: {out_path.absolute()}")
        if not send_emails:
            print("   💡 실제 발송하려면 --send 옵션 또는 send_emails=True 설정")

    # ─── 5) 결과 로그 ─────────────────────────────
    log_data = {
        "run_at": datetime.now().isoformat(),
        "mode": mode,
        "use_claude": use_claude and bool(ANTHROPIC_API_KEY),
        "crawl_body": crawl_body,
        "total_leads": len(leads),
        "processed": len(leads_with_insights),
        "sent": send_emails,
        "industries": list(news_cache.keys()),
        "details": [
            {k: v for k, v in item.items() if k not in ("html",)}
            for item in leads_with_insights
        ],
    }
    log_file = out_path / f"pipeline_log_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ 파이프라인 완료")
    print(f"   처리: {len(leads_with_insights)}건")
    print(f"   로그: {log_file}")
    print("=" * 60)

    return leads_with_insights


# ============================================================
# CLI 엔트리포인트
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="DETA 통합 뉴스레터 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 1) dry-run (HTML만 생성, 발송 안함)
  python newsletter_pipeline.py --leads output/apollo_leads.xlsx

  # 2) 실제 발송
  python newsletter_pipeline.py --leads output/apollo_leads.xlsx --send

  # 3) 스티비 구독자 추가 + 발송
  python newsletter_pipeline.py --leads output/apollo_leads.xlsx --send --add-stibee

  # 4) 테스트 (5건만)
  python newsletter_pipeline.py --leads output/apollo_leads.xlsx --max 5

  # 5) 본문 크롤링 없이 빠르게
  python newsletter_pipeline.py --leads output/apollo_leads.xlsx --no-crawl
""",
    )
    parser.add_argument("--leads", required=True, help="Apollo 추출 결과 CSV/Excel 파일")
    parser.add_argument("--send", action="store_true", help="실제 스티비 발송 (기본: HTML만 생성)")
    parser.add_argument("--add-stibee", action="store_true", help="스티비 주소록에 구독자 추가")
    parser.add_argument("--no-claude", action="store_true", help="Claude 없이 템플릿 모드")
    parser.add_argument("--no-crawl", action="store_true", help="뉴스 본문 크롤링 비활성화")
    parser.add_argument("--max", type=int, default=0, help="최대 처리 건수 (0=전체)")
    parser.add_argument("--output", default="output/newsletters", help="HTML 저장 디렉토리")
    parser.add_argument("--mode", choices=["auto", "smtp", "stibee", "bulk"], default="auto",
                        help="발송 모드: auto(자동이메일), smtp(직접), stibee(Email API), bulk(일괄)")

    args = parser.parse_args()

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
