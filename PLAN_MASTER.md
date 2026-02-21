# DETA 이메일 파이프라인 마스터 플랜

> **목적**: 이 문서는 Claude Code에서 구현 시 참조하는 최상위 기획 문서입니다.
> **최종 수정**: 2026-02-20
> **Repo**: gitarcman101/DETA-Newsletter

---

## 1. 프로젝트 개요

DETA AI Consulting Korea의 이메일 기반 리드 발굴 및 육성 시스템.
두 개의 트랙을 하나의 코드베이스에서 운영합니다.

| 구분 | Track A: 콜드메일 | Track B: 뉴스레터 |
|------|-------------------|-------------------|
| 대상 | 새 리드 (DETA를 모르는 기업) | 기존 구독자 (이미 인지) |
| 목적 | 1:1 맞춤 가치 제공 → 미팅/문의 전환 | 업계 인텔리전스 정기 제공 → 신뢰 구축 |
| 분량 | 150단어 이하, 30초 내 소화 | 6-zone 1페이지, 60초 스캔 |
| 톤 | 1:1 대화 (도움을 주려는 전문가) | 업계 브리핑 (정보 제공자) |
| 발송 | Outlook Graph API (일 30-50건) 또는 스티비 자동이메일 | 스티비 일반이메일 (구독자 전체) |
| 주기 | 리드 확보 시점에 1회 발송 (follow-up은 수동) | 주 1회 (12산업 rotation) |
| 성공 지표 | 회신율, 미팅 전환율 | 오픈율, CTR, 구독 유지율 |

---

## 2. 현재 DETA-Newsletter Repo 현황 분석

### 이미 구축된 것 (그대로 활용)

```
streamlit_app.py           → 5-Step 파이프라인 대시보드
newsletter_pipeline.py     → 뉴스 수집 + Claude 인사이트 + HTML 생성 엔진
stibee_integration.py      → 스티비 API (구독자 관리 + 자동이메일 발송)
news_collector_1.py        → RSS + Google News + trafilatura 크롤러
pipeline_store.py          → 파이프라인 실행 기록 JSON
apollo_lead_extractor.py   → Apollo 리드 추출기
pages/1_review.py          → 리뷰 대시보드 (승인/반려/코멘트)
templates/newsletter_v2.html → Jinja2 이메일 템플릿 (Palantir 다크 테마)
config/config.yaml         → 파이프라인 설정
```

### 핵심 인식: DETA-Newsletter는 이미 콜드메일 MVP

현재 파이프라인은 "뉴스레터"라고 명명되었지만 실제로는:
- 리드 개별 입력 → 리드별 산업/기업 맞춤 인사이트 → 최대 10명 동시 처리 → 리뷰 후 발송
- 이 구조는 콜드메일(Track A)에 더 가까움
- 구독자 전체 대량 발송(Track B)은 현재 지원하지 않음

---

## 3. 공유 인프라 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    공유 인프라 레이어                       │
│                                                         │
│  news_collector_1.py    → 산업별 뉴스 수집 (RSS/Google)   │
│  newsletter_pipeline.py → Claude AI 분석 엔진             │
│  pipeline_store.py      → 실행 기록                       │
│  config/config.yaml     → 12산업 정의, 키워드, 소스        │
│  pages/1_review.py      → 리뷰 대시보드                   │
│                                                         │
├────────────────────┬────────────────────────────────────┤
│                    │                                    │
│   Track A          │   Track B                          │
│   콜드메일          │   뉴스레터                          │
│                    │                                    │
│   PLAN_TRACK_A.md  │   PLAN_TRACK_B.md                  │
│   참조              │   참조                              │
│                    │                                    │
└────────────────────┴────────────────────────────────────┘
```

---

## 4. Track 간 연결 (브릿지)

### A → B: 콜드메일 반응자 → 뉴스레터 구독 전환
- 콜드메일 발송 후 수동 follow-up 시 뉴스레터 구독 제안
- 수락 시 스티비 구독자 자동 등록
- 리드 상태: `sent` → `converted_subscriber`

### B → A: 고관여 구독자 → 세일즈 아웃리치 트리거
- 뉴스레터 3회 연속 오픈 + CTA 클릭 1회 이상 → 고관여 플래그
- 고관여 구독자를 콜드메일 리드 DB에 추가 (단, 이미 맞춤 인사이트 포함)
- Slack 알림: "삼성엔지니어링 김OO — 화학 뉴스레터 3회 연속 오픈, CTA 2회 클릭"

---

## 5. 실행 우선순위

| 순서 | 작업 | 트랙 | 근거 |
|------|------|------|------|
| 1 | Track A 콜드메일 파이프라인 확장 | A | 기존 코드 80% 활용. 수정량 적고 즉시 리드 발굴 가능 |
| 2 | 콜드메일용 플레인 텍스트 템플릿 추가 | A | 현재 다크 테마 → 콜드메일에 부적합 |
| 3 | 발송 채널 구현 (스티비 or Outlook) | A | 스티비로 먼저 검증 → 회신율 보고 Outlook 전환 판단 |
| 4 | Track B 뉴스레터 브로드캐스트 모듈 | B | Track A에서 콘텐츠 생성 안정화 후 확장 |
| 5 | 통합 CRM + A↔B 브릿지 | 공유 | 두 트랙 모두 가동 후 연결 |

---

## 6. 발송 채널 전략

### 콜드메일 (Track A)

**Phase 1 — 스티비 자동이메일 유지 (현재)**
- 코드 변경 최소
- 오픈/클릭 트래킹 내장
- 단, 수신자가 "마케팅 메일"로 인식할 가능성

**Phase 2 — Outlook Graph API 추가 (선택적)**
- `yonghyun.kim@industryarc.com`에서 직접 발송
- 수신자에게 1:1 메일로 인식됨
- 회신이 Outlook 받은편지함에 직접 도착
- 주의: 일 30-50건 이내 유지, 도메인 평판 관리 필수
- SPF/DKIM/DMARC 설정 확인 필요

**Phase 3 — 병행 운영**
- 1차 콜드메일: Outlook (높은 도달률)
- 뉴스레터 전환 후: 스티비 (대량 관리)

### 뉴스레터 (Track B)

- 스티비 일반이메일 API (구독자 전체 대상 발송)
- 현재 DETA-Newsletter의 자동이메일 API와 별도 엔드포인트

---

## 7. 파일 구조 변경 계획

### 신규 파일

```
[Track A 관련]
outlook_sender.py          → MS Graph API Outlook 발송 모듈 (Phase 2, 선택)
templates/cold_email.html  → 콜드메일용 미니멀 템플릿 (플레인 텍스트 스타일)
templates/prompts/
  cold_email.txt           → Claude 프롬프트: 콜드메일 (가치 선제공, 1회 발송)

[Track B 관련]
newsletter_broadcast.py    → 12산업 rotation + 6-zone 콘텐츠 생성 + 스티비 일반이메일 발송
templates/newsletter_broadcast.html → 6-zone 뉴스레터 템플릿
config/industries.json     → 12산업 정의 (키워드, 소스, rotation 스케줄)

[공유]
subscriber_manager.py      → 콜드메일↔뉴스레터 구독자 전환 관리
lead_researcher.py         → 기업별 맞춤 리서치 모듈 (기업명 기반 뉴스/IR 검색)
```

### 수정 파일

```
streamlit_app.py           → 탭 추가 (콜드메일 | 뉴스레터 | CRM)
newsletter_pipeline.py     → Claude 프롬프트 콜드메일 모드 추가
pipeline_store.py          → 리드 상태/발송 이력 필드 추가
config/config.yaml         → 12산업 rotation 스케줄 추가
```

---

## 8. 기술 스택 (변경/추가분)

| 구분 | 현재 | 추가 |
|------|------|------|
| AI | Claude 3.5 Sonnet | 동일 (프롬프트만 분화) |
| 발송 (콜드메일) | 스티비 자동이메일 | + Outlook Graph API (선택) |
| 발송 (뉴스레터) | 스티비 자동이메일 | → 스티비 일반이메일 API |
| 리드 추출 | Apollo | 동일 |
| 리드 상태 관리 | 없음 | pipeline_store.py 확장 |
| 기업 리서치 | 산업 키워드 검색만 | + 기업명 타겟 검색 (이미 구현됨) |

---

## 9. KPI 목표

### Track A: 콜드메일

| 지표 | Month 1-3 | Month 4-12 |
|------|-----------|------------|
| 주간 발송 리드 수 | 20-30 | 50+ |
| 1차 메일 오픈율 | 40%+ | 50%+ |
| 회신율 | 5% | 10%+ |
| 미팅 전환 | 2건/월 | 5건+/월 |
| 뉴스레터 전환 | 10% | 20%+ |

### Track B: 뉴스레터

| 지표 | Month 1-3 | Month 4-12 |
|------|-----------|------------|
| 구독자 수 | 300 | 1,500+ |
| 오픈율 | 35%+ | 40%+ |
| CTA 클릭률 | 5% | 8% |
| 리드 생성/월 | 5 | 20+ |
| 유료 서비스 전환 | 1-2건/월 | 5건+/월 |
