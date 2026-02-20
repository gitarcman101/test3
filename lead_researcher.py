"""
기업별 맞춤 리서치 모듈
========================
news_collector_1.py의 collect_for_company()를 활용하여
리드 기업에 맞춤 리서치를 수행하고 CRM에 저장.

Input:  lead dict (company, industry, trigger 등)
Output: custom_research dict (industry_context, company_context, researched_at)
"""

from dataclasses import asdict
from datetime import datetime


def research_lead(lead: dict, days: int = 7, max_per_category: int = 3) -> dict:
    """
    리드 기업에 대한 맞춤 리서치 수행.

    Args:
        lead: 리드 정보 dict (company, industry 필수)
        days: 최근 N일 뉴스 수집
        max_per_category: 카테고리당 최대 기사 수

    Returns:
        {
            "industry_context": [...],   # 산업 트렌드 뉴스 (dict 리스트)
            "company_context": [...],    # 기업 관련 뉴스 (dict 리스트)
            "competitor_context": [...], # 경쟁사 뉴스 (dict 리스트)
            "regulation_context": [...], # 규제 뉴스 (dict 리스트)
            "total_articles": int,
            "researched_at": str (ISO),
        }
    """
    from news_collector_1 import NewsCollectorWrapper

    company = lead.get("company", lead.get("회사명", ""))
    industry = lead.get("industry", lead.get("산업", ""))

    if not company or not industry:
        return {
            "industry_context": [],
            "company_context": [],
            "competitor_context": [],
            "regulation_context": [],
            "total_articles": 0,
            "researched_at": datetime.now().isoformat(),
            "error": "company 또는 industry가 비어 있습니다.",
        }

    collector = NewsCollectorWrapper()

    # collect_for_company: 산업 트렌드 + 경쟁사 + 규제 + 기업 뉴스 통합 수집
    raw = collector.collect_for_company(
        company=company,
        industry=industry,
        competitors=None,  # 경쟁사 미지정 시 건너뜀
        days=days,
        max_per_category=max_per_category,
    )

    # NewsArticle → dict 변환
    def _to_dicts(articles: list) -> list:
        result = []
        for a in articles:
            try:
                d = asdict(a)
                # _raw 필드 제거 (직렬화 불가)
                d.pop("_raw", None)
                result.append(d)
            except Exception:
                # 이미 dict인 경우
                if isinstance(a, dict):
                    result.append(a)
        return result

    research = {
        "industry_context": _to_dicts(raw.get("industry_trend", [])),
        "company_context": _to_dicts(raw.get("company_news", [])),
        "competitor_context": _to_dicts(raw.get("competitor", [])),
        "regulation_context": _to_dicts(raw.get("regulation", [])),
        "total_articles": len(raw.get("all", [])),
        "researched_at": datetime.now().isoformat(),
    }

    return research


def research_and_update_crm(lead_id: str, days: int = 7, max_per_category: int = 3) -> dict:
    """
    리드 리서치 수행 후 CRM 상태를 'researched'로 업데이트.

    Args:
        lead_id: CRM 리드 ID
        days: 최근 N일
        max_per_category: 카테고리당 최대 기사 수

    Returns:
        custom_research dict (또는 에러 dict)
    """
    from pipeline_store import LeadCRM

    crm = LeadCRM()
    lead = crm.get_lead(lead_id)

    if not lead:
        return {"error": f"리드를 찾을 수 없음: {lead_id}"}

    research = research_lead(lead, days, max_per_category)

    # CRM 업데이트
    crm.update_lead(lead_id, {
        "custom_research": research,
        "status": "researched",
    })

    # history에 리서치 기록 추가
    crm.update_status(lead_id, "researched",
                      note=f"리서치 완료: {research['total_articles']}건 수집")

    return research


def format_research_for_prompt(research: dict) -> str:
    """
    리서치 결과를 Claude 프롬프트에 넣을 수 있는 텍스트로 포맷.

    Returns:
        포맷된 텍스트 (뉴스 제목 + 요약 목록)
    """
    lines = []

    sections = [
        ("산업 트렌드", research.get("industry_context", [])),
        ("기업 뉴스", research.get("company_context", [])),
        ("경쟁사 동향", research.get("competitor_context", [])),
        ("규제 변화", research.get("regulation_context", [])),
    ]

    for section_name, articles in sections:
        if not articles:
            continue
        lines.append(f"\n[{section_name}]")
        for i, art in enumerate(articles[:3], 1):
            title = art.get("title", "제목 없음")
            desc = art.get("description", "")
            source = art.get("source", "")
            full_text = art.get("full_text", "")

            lines.append(f"  {i}. {title}")
            if source:
                lines.append(f"     출처: {source}")
            if desc:
                lines.append(f"     요약: {desc[:200]}")
            elif full_text:
                lines.append(f"     본문 발췌: {full_text[:200]}")

    if not lines:
        return "(수집된 뉴스 없음)"

    return "\n".join(lines)
