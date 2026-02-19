# DETA Newsletter Pipeline

B2B 리드 기반 개인화 뉴스레터 자동 생성 및 발송 파이프라인

## 프로젝트 구조

```
deta_newsletter/
├── streamlit_app.py           # 메인 대시보드 (5-Step 파이프라인 UI)
├── newsletter_pipeline.py     # 뉴스 수집 + AI 인사이트 + HTML 생성 엔진
├── stibee_integration.py      # 스티비 API 연동 (구독자 관리 + 자동 이메일 발송)
├── news_collector_1.py        # RSS/Google News 크롤러 (trafilatura 기반)
├── pipeline_store.py          # 파이프라인 실행 기록 JSON 저장소
├── apollo_lead_extractor.py   # Apollo 리드 추출기
├── pages/
│   └── 1_review.py            # 리뷰 대시보드 (승인/반려/코멘트)
├── templates/
│   ├── newsletter_v2.html     # Jinja2 이메일 템플릿 (Palantir 다크 테마)
│   └── newsletter_template.html
├── config/
│   ├── .env.example           # 환경변수 템플릿
│   └── config.yaml            # 파이프라인 설정
├── .streamlit/
│   └── config.toml            # Streamlit 테마 설정
├── data/                      # 파이프라인 실행 기록 (자동 생성)
│   └── runs/
│       └── run_YYYYMMDD_HHMM/
├── output/                    # HTML 뉴스레터 출력 (자동 생성)
└── requirements.txt
```

## 파이프라인 프로세스

```
Step 1 — Lead Input          리드 입력 (Excel 업로드 / 수동 입력)
       ↓
Step 2 — News Collection     산업별 뉴스 수집 (RSS + Google News 크롤링)
       ↓
Step 3 — AI Insight          Claude AI 인사이트 생성 (리드별 개인화)
       ↓
Step 4 — HTML Build          뉴스레터 HTML 생성 + 리뷰/편집
       ↓
Step 5 — Send                스티비 자동 이메일 API 발송 + 수동 복사
```

- 최대 10명 리드 동시 처리
- 리드별 산업/기업 맞춤 인사이트 생성
- 리뷰 대시보드에서 승인된 리드만 발송
- 파이프라인 실행 기록 JSON 자동 저장

## 기술 스택

| 구분 | 기술 |
|------|------|
| **UI** | Streamlit (Palantir 다크 테마) |
| **AI** | Claude 3.5 Sonnet (Anthropic API) |
| **뉴스 수집** | RSS + Google News + trafilatura 본문 크롤링 |
| **이메일 발송** | 스티비 자동 이메일 API v1.0 |
| **구독자 관리** | 스티비 구독자 API v1/v2 |
| **템플릿** | Jinja2 HTML (이메일 클라이언트 호환) |
| **데이터 저장** | JSON 파일 기반 (pipeline_store.py) |
| **배포** | Streamlit Cloud / 로컬 |
| **언어** | Python 3.9+ |

## 빠른 시작

### 1. 환경 설정

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp config/.env.example config/.env
```

`config/.env`에 필수 키 입력:

| 키 | 설명 | 필수 |
|----|------|------|
| `ANTHROPIC_API_KEY` | Claude API 키 | O |
| `STIBEE_API_KEY` | 스티비 API 키 | O |
| `STIBEE_LIST_ID` | 스티비 주소록 ID | O |
| `STIBEE_AUTO_EMAIL_URL` | 스티비 자동 이메일 API URL | O |
| `REVIEW_PASSWORD` | 대시보드 접근 비밀번호 | O |
| `SENDER_EMAIL` | 스티비 발신자 이메일 | - |

### 3. 스티비 자동 이메일 설정

1. 스티비 로그인 > 자동 이메일 > 새로 만들기
2. 트리거: **API로 직접 요청** 선택
3. 이메일 제목: `$%subject_line%$`
4. 이메일 본문: `$%insight_html%$`
5. 저장 후 **실행** 상태로 전환
6. API URL 복사 > `config/.env`의 `STIBEE_AUTO_EMAIL_URL`에 설정

### 4. 실행

```bash
streamlit run streamlit_app.py
```

### Streamlit Cloud 배포

Streamlit Cloud에서는 `config/.env` 대신 **App Settings > Secrets**에 환경변수 설정:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
STIBEE_API_KEY = "..."
STIBEE_LIST_ID = "473532"
STIBEE_AUTO_EMAIL_URL = "https://stibee.com/api/v1.0/auto/..."
REVIEW_PASSWORD = "..."
```

## 주요 파일

| 파일 | 설명 |
|------|------|
| `streamlit_app.py` | 메인 UI — 5단계 파이프라인, 비밀번호 인증, 파이프라인 트래커 |
| `newsletter_pipeline.py` | 핵심 엔진 — 뉴스 수집, Claude 인사이트, HTML 빌드 |
| `stibee_integration.py` | 스티비 API — 구독자 등록, 자동 이메일 트리거, 통계 |
| `pipeline_store.py` | 실행 기록 — JSON 파일 기반 CRUD |
| `pages/1_review.py` | 리뷰 대시보드 — 리드별 승인/반려/코멘트 |
| `news_collector_1.py` | 뉴스 크롤러 — RSS 파서 + trafilatura 본문 추출 |
| `templates/newsletter_v2.html` | 이메일 템플릿 — Palantir 다크 테마, 반응형 |

---

**만든이**: detaman
**버전**: 2.0.0
