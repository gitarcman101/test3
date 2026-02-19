# B2B 콜드메일 뉴스레터 파이프라인

## 전체 워크플로우

```
[1. 담당자 추출]       [2. 이슈 수집]       [3. 인사이트 생성]     [4. 스티비 발송]
Apollo.io API   →   뉴스 수집         →   Claude API /      →  스티비 자동이메일
직급/부서/지역        산업별 트렌드          템플릿 기반             개인화 발송
회사 규모 필터        기업별 뉴스           개인화된 콘텐츠          오픈율/클릭율
이메일 검증          Google News RSS      맞춤형 시사점            수신거부 관리
품질 스코어링                            CTA 자동 생성            주소록 자동 동기화
```

---

## 파일 구조

```
├── apollo_lead_extractor.py   # 1단계: Apollo 담당자 추출
├── newsletter_pipeline.py     # 2-3단계: 뉴스 수집 + 인사이트 생성
├── stibee_integration.py      # 4단계: 스티비 연동 (구독자 관리 + 발송)
├── .env.example               # 환경변수 템플릿
├── .env                       # 실제 환경변수 (직접 생성)
└── output/
    ├── apollo_leads_*.xlsx    # 담당자 리스트
    └── newsletters/
        ├── *.html             # 개인별 뉴스레터 HTML
        └── stibee_log_*.json  # 발송 로그
```

---

## 빠른 시작

### 1. 설치

```bash
pip install requests openpyxl
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열고 API 키들을 입력
```

### 3. 스티비 사전 설정

#### 3-1. API 키 발급
워크스페이스 설정 → API 키 → 새로 만들기

#### 3-2. 주소록 준비
1. 콜드메일용 주소록 생성
2. **사용자 정의 필드 추가** (주소록 설정에서):

| 태그 | 이름 | 용도 |
|------|------|------|
| `name` | 이름 | 수신자 이름 |
| `company` | 회사명 | 회사명 |
| `title` | 직함 | 직함 |
| `industry` | 산업 | 산업 분류 |
| `seniority` | 직급 | C-Level, VP 등 |
| `linkedin` | LinkedIn | LinkedIn URL |
| `phone` | 전화번호 | 전화번호 |

3. 주소록 ID 확인 (URL에서: `stibee.com/lists/123456` → `123456`)

#### 3-3. 자동 이메일 설정 (개인화 발송용)
1. 자동 이메일 새로 만들기
2. 주소록: 위에서 만든 주소록 선택
3. 트리거: **"API로 직접 요청"** 선택
4. 이메일 제목: `$%subject_line%$` 또는 고정 제목
5. 이메일 본문 작성 (치환 변수 사용):

```
$%greeting%$

💡 핵심 인사이트
$%industry_insight%$

🎯 $%company%$에 대한 시사점
$%company_relevance%$

✅ Key Takeaway: $%key_takeaway%$

$%cta%$
```

> 또는 `$%insight_html%$` 하나로 전체 HTML을 삽입할 수도 있습니다.

6. 자동 이메일 **"실행"** 상태로 전환
7. API URL 복사 → `.env`의 `STIBEE_AUTO_EMAIL_URL`에 설정

### 4. 실행

```bash
# 1단계: 담당자 추출
python apollo_lead_extractor.py

# 2단계: 뉴스레터 생성 + 스티비 발송
python stibee_integration.py
```

---

## 발송 방식 비교

### 방식 A: 자동 이메일 API (추천)

```python
run_stibee_pipeline(
    leads_file="output/apollo_leads_xxx.xlsx",
    mode="auto",
    send_emails=True,
)
```

- 1건씩 개인화된 콘텐츠
- 사용자 정의 필드 치환 ($%name%$, $%insight%$ 등)
- 스티비 통계 (오픈율, 클릭율) 자동 추적
- 수신거부 자동 처리
- 1초당 3회 제한 (대량 발송 시 시간 소요)

### 방식 B: 이메일 API (일괄 발송)

```python
send_bulk_via_email_api(
    list_id="123456",
    subject="[산업 인사이트] 이번 주 트렌드",
    html_content=html,
    sender_email="your@email.com",
)
```

- 주소록 전체 한 번에 발송
- 빠른 발송
- 개인화 제한 (기본 치환만 가능)
- 프로 요금제 이상 필요

---

## 스티비 요금제별 사용 가능 기능

| 기능 | 스탠다드 | 프로 | 엔터프라이즈 |
|------|---------|------|-------------|
| 구독자 추가/관리 API | O | O | O |
| 이메일 생성/발송 API | X | O | O |
| 주소록 관리 API | X | X | O |
| 자동 이메일 API 트리거 | O | O | O |

> **스탠다드 요금제에서도 자동 이메일 API 트리거는 사용 가능합니다.**
> 구독자 추가 + 자동 이메일 트리거 조합으로 개인화 발송이 가능합니다.

---

## 비용 구조

| 서비스 | 무료 범위 | 유료 |
|--------|----------|------|
| Apollo.io | 월 50 크레딧 | $49/월~ |
| Google News RSS | 무제한 | 무료 |
| NewsAPI (선택) | 하루 100건 | $449/월~ |
| Claude API (선택) | 종량제 | ~$3/백만토큰 |
| **스티비** | **월 500건 발송** | **월 16,500원~** |

**최소 비용 구성**: Apollo 무료 + Google News RSS + 템플릿 인사이트 + 스티비 스탠다드

---

## 커스터마이징

### 산업별 키워드 수정
`newsletter_pipeline.py`의 `INDUSTRY_KEYWORDS` 딕셔너리를 수정

### 이메일 템플릿 수정
- **방식 A (자동 이메일)**: 스티비 웹 에디터에서 직접 수정
- **방식 B (이메일 API)**: `NewsletterBuilder.build_html()` 수정

### 발송 스케줄링 (크론탭)

```bash
# 매주 월요일 오전 9시 실행
0 9 * * 1 cd /path/to/project && python stibee_integration.py
```
