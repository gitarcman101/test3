# PLAN_TRACK_A.md — 콜드메일 구현 명세

> **참조**: PLAN_MASTER.md (전체 아키텍처)
> **상태**: Track A는 기존 DETA-Newsletter 코드의 확장. 신규 코드 20%, 수정 80%.
> **구현 도구**: Claude Code (로컬 DETA-Newsletter repo에서 직접 수정)
> **변경**: Day 0/3/7 자동 시퀀스 삭제 → 1회 발송 + 수동 follow-up

---

## 1. 리드 데이터 스키마

### 현재 (DETA-Newsletter)
리드는 Excel 업로드 또는 수동 입력. 필드:
- 회사명, 담당자명, 이메일, 산업, (선택) 메모

### 확장 스키마

`pipeline_store.py`의 리드 JSON 구조를 아래와 같이 확장:

```json
{
  "lead_id": "lead_20260220_001",
  "company": "삼성엔지니어링",
  "industry": "chemicals",
  "contact_name": "김OO",
  "contact_email": "kim@samsungeng.com",
  "contact_title": "해외사업본부 과장",
  "trigger": "최근 사우디 화학플랜트 수주",
  "source": "KOTRA DB",
  "status": "new",
  "last_sent_at": null,
  "replied": false,
  "converted_to_subscriber": false,
  "custom_research": null,
  "created_at": "2026-02-20T09:00:00",
  "history": []
}
```

### status 값 정의

```
new → researched → sent → replied → meeting_set
                     ↓
                   no_response → archived
```

| status | 의미 | 다음 액션 |
|--------|------|-----------|
| `new` | 리드 입력됨, 아직 미발송 | 맞춤 리서치 → 메일 생성 |
| `researched` | 기업 리서치 완료 | 메일 생성 → 리뷰 |
| `sent` | 메일 발송됨 | 회신 확인 (수동 follow-up) |
| `replied` | 회신 수신 | 수동 follow-up |
| `meeting_set` | 미팅 확정 | 세일즈 프로세스로 이관 |
| `converted_subscriber` | 뉴스레터 구독 전환 | Track B로 이관 |
| `no_response` | 무응답 | 90일 후 재시도 큐 |
| `archived` | 더 이상 추적 안 함 | — |

---

## 2. 기업별 맞춤 리서치 모듈

### 신규 파일: `lead_researcher.py`

```python
"""
기업별 맞춤 리서치 모듈

기존 news_collector_1.py의 산업 키워드 검색에 더해,
리드 기업명을 기반으로 최근 뉴스/IR/수출 실적을 검색합니다.

Input: lead dict (company, industry, trigger)
Output: custom_research dict (insights, sources, relevance_score)
"""

# 핵심 로직 (pseudo)

def research_lead(lead: dict) -> dict:
    """
    Step 1: 산업 데이터 (기존 news_collector_1.py 재사용)
      - lead['industry'] 키워드로 최근 1주 뉴스 수집
    
    Step 2: 기업 타겟 검색 (신규)
      - Google News: "{company} {industry}" 최근 3개월
      - Google News: "{company} 수출 OR 해외진출 OR 수주" 최근 6개월
      - (선택) 관세청 수출입 데이터 API
    
    Step 3: Claude로 맞춤 인사이트 생성
      - 프롬프트: 산업 데이터 + 기업 뉴스 → 이 기업에 가장 관련성 높은 시장 인사이트 1가지
      - 150단어 이내로 생성
      - 구체적 수치/사례 포함 필수
    
    Step 4: 결과 저장
      - lead['custom_research']에 저장
      - lead['status'] = 'researched'
    """
    
    # 산업 데이터 (기존 코드 재사용)
    industry_news = collect_industry_news(lead['industry'])
    
    # 기업 타겟 검색 (신규)
    company_news = collect_company_news(
        company=lead['company'],
        industry=lead['industry'],
        trigger=lead.get('trigger', '')
    )
    
    # Claude 맞춤 인사이트
    insight = generate_custom_insight(
        industry_data=industry_news,
        company_data=company_news,
        lead=lead
    )
    
    return {
        'industry_context': industry_news[:3],  # 상위 3개 뉴스
        'company_context': company_news[:3],     # 상위 3개 뉴스
        'custom_insight': insight,               # Claude 생성 인사이트
        'researched_at': datetime.now().isoformat()
    }
```

### `news_collector_1.py` — 수정 불필요

기업명 기반 검색이 이미 구현되어 있음:
- `collect_for_company(company, industry, competitors, days, max_per_category)`
- `collect_competitor_news(competitors, industry, days, max_per_company)`

`lead_researcher.py`에서 이 함수들을 직접 호출하면 됨.

---

## 3. 콜드메일 프롬프트

### 단일 콜드메일: "가치 선제공"

**목적**: 아무것도 요구하지 않고 유용한 정보만 전달
**CTA**: "관심 있으시면 추가 자료 보내드릴까요?"
**톤**: 정중하지만 간결, 영업 느낌 최소화
**follow-up**: 수동으로 진행 (자동 시퀀스 없음)

**Claude 프롬프트** (`templates/prompts/cold_email.txt`):

```
당신은 DETA AI Consulting Korea의 시장 분석 전문가입니다.

아래 정보를 바탕으로 콜드메일 본문을 작성하세요.

[리드 정보]
- 회사: {company}
- 담당자: {contact_name} {contact_title}
- 산업: {industry}
- 트리거: {trigger}

[맞춤 리서치 결과]
{custom_research.custom_insight}

[작성 규칙]
1. 총 150단어 이내 (한국어 기준)
2. 첫 문장: {trigger}를 언급하며 연락 이유 설명 (1줄)
3. 본문: 해당 기업에 직접 관련된 시장 인사이트 1가지 (3-4문장)
   - 반드시 구체적 수치나 사례 포함
   - "귀사"라는 표현 사용
4. 마무리: "저희가 이 분야에서 정리한 추가 분석 자료가 있는데, 혹시 관심 있으시면 보내드려도 될까요?"
5. 절대 하지 말 것:
   - 미팅/통화 요청
   - DETA 서비스 직접 홍보
   - "무료" 강조
   - 장황한 자기소개

[출력 형식]
Subject: {company}의 {trigger_short} 관련 — {industry} 시장 동향 공유

{contact_name} {contact_title}님, 안녕하세요.

{본문}

김용현 드림
DETA AI Consulting Korea | IndustryARC
```

---

## 4. 콜드메일 템플릿

### 신규 파일: `templates/cold_email.html`

기존 Palantir 다크 테마 (newsletter_v2.html)는 콜드메일에 부적합.
콜드메일은 **플레인 텍스트에 가까운 미니멀 HTML**이어야 함.

```
디자인 원칙:
- 배경: 흰색 (#FFFFFF)
- 폰트: 시스템 기본 폰트 (웹폰트 로드 없음)
- 이미지: 없음 (스팸 필터 회피)
- 링크: 본문 내 최소 1개 (CTA만)
- 서명: 텍스트 기반 (이름 + 직책 + 연락처)
- HTML 구조: 최소한의 태그만 사용
- 반응형: 별도 처리 불필요 (단순 텍스트 구조)
```

**서명 블록 (공통)**:
```
김용현 드림
DETA AI Consulting Korea | IndustryARC

Mobile: +82 10-9153-1111
Email: yonghyun.kim@industryarc.com
Web: https://deta.kr
```

---

## 5. streamlit_app.py 수정 명세

### 현재 구조
```
5-Step 파이프라인:
Step 1: Lead Input
Step 2: News Collection
Step 3: AI Insight
Step 4: HTML Build
Step 5: Send
```

### 변경 후 구조
```
탭 구조:
┌──────────┬──────────┬──────────┐
│ 콜드메일  │ 뉴스레터  │ CRM     │
│ (Track A) │ (Track B) │ (통합)   │
└──────────┴──────────┴──────────┘

[콜드메일 탭] — 기존 5-Step 유지
  Step 1: Lead Input (기존 유지)
    - 추가: trigger 필드, source 필드
  Step 2: Lead Research (신규)
    - 기업별 맞춤 리서치 실행
    - 결과 미리보기
  Step 3: Email Generate (기존 AI Insight 확장)
    - 콜드메일 모드로 실행
  Step 4: Review & Edit (기존 유지)
    - 승인 시 상태 업데이트
  Step 5: Send (기존 유지)
    - 발송 채널 선택 (스티비 / Outlook)
  + Lead Tracker: 리드 상태 현황 대시보드

[뉴스레터 탭] — PLAN_TRACK_B.md 참조

[CRM 탭] — 통합 현황
  - 리드 현황: status별 카운트
  - 구독자 현황: 총 수, 신규, 이탈
  - 전환 퍼널: 콜드메일 → 구독 → 문의 → 계약
```

---

## 6. Outlook Graph API 구현 명세 (선택적)

### 신규 파일: `outlook_sender.py`

**사전 조건**:
1. Azure Portal에서 앱 등록 (App Registration)
2. `Mail.Send` 권한 부여
3. Client ID, Client Secret, Tenant ID 획득
4. config/.env에 추가:
   ```
   MS_CLIENT_ID=xxxxxxxx
   MS_CLIENT_SECRET=xxxxxxxx
   MS_TENANT_ID=xxxxxxxx
   MS_SENDER_EMAIL=yonghyun.kim@industryarc.com
   ```

```python
"""
MS Graph API를 통한 Outlook 이메일 발송

사용처: Track A 콜드메일 (1:1 개인화 발송)
장점: 수신자에게 진짜 1:1 메일로 인식됨
제약: 일 30-50건 이내 권장

주요 기능:
1. send_email(to, subject, body) - 단건 발송
2. send_reply(thread_id, body) - 같은 스레드에 회신
3. check_replies(since_datetime) - 최근 회신 확인
"""

# 구현 시 참고사항:
# - msal 라이브러리 사용 (Microsoft Authentication Library)
# - 토큰 캐싱 필수 (매번 인증 X)
# - 발송 간 2-5초 랜덤 딜레이 (스팸 방지)
# - 발송 로그를 pipeline_store에 기록
# - 에러 시 재시도 1회 후 skip (무한 재시도 방지)
```

### 도메인 평판 보호 규칙

```
일일 한도: 30건 (초기), 점진적 증가하여 최대 50건
발송 간격: 2-5초 랜덤 딜레이
시간대: 평일 오전 9-11시 KST (수신 기업 시간대 고려)
바운스 관리: 2회 연속 바운스 → 자동 archive
옵트아웃: 모든 메일 하단에 수신거부 링크 포함
```

---

## 7. 구현 체크리스트

Claude Code에서 아래 순서대로 구현:

### Phase 1: 콜드메일 기본 구조 (2일)
- [ ] pipeline_store.py — 리드 CRM 스키마 확장 (간소화된 status)
- [ ] lead_researcher.py — 기업 리서치 모듈 (news_collector_1.py 재사용)
- [ ] templates/prompts/cold_email.txt — 콜드메일 프롬프트
- [ ] templates/cold_email.html — 미니멀 콜드메일 템플릿
- [ ] newsletter_pipeline.py — 콜드메일 모드 추가
- [ ] streamlit_app.py — 콜드메일 탭 추가 + 리드 트래커

### Phase 2: Outlook 연동 — 선택적
- [ ] outlook_sender.py — Graph API 발송 모듈
- [ ] streamlit_app.py — 발송 채널 선택 UI 추가
- [ ] config/.env — MS Graph 인증 정보 추가
