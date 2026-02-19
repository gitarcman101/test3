# DETA Newsletter Automation 🚀

자동화된 뉴스레터 수집, 생성, 발송 시스템

## 📁 프로젝트 구조

```
deta_newsletter_automation/
├── src/
│   ├── collectors/          # 콘텐츠 수집
│   │   └── rss_collector.py
│   ├── processors/          # AI 처리
│   │   └── claude_summarizer.py
│   ├── publishers/          # 발송
│   │   └── stibee_publisher.py
│   └── utils/              # 유틸리티
│       ├── config_loader.py
│       └── logger.py
├── config/
│   ├── config.yaml         # 메인 설정
│   └── .env.example        # 환경변수 템플릿
├── templates/
│   └── newsletter_template.html
├── logs/                   # 자동 생성됨
├── data/                   # 임시 데이터
├── main.py                 # 메인 실행 파일
└── requirements.txt
```

## 🚀 빠른 시작

### 1. 환경 설정

```powershell
# 가상환경 생성
python -m venv venv
.\venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

### 2. API 키 설정

`config/.env.example`을 복사하여 `config/.env` 생성:

```powershell
cp config\.env.example config\.env
```

`.env` 파일에 실제 API 키 입력:
- `ANTHROPIC_API_KEY`: Claude API 키
- `STIBEE_API_KEY`: Stibee API 키
- `NOTION_API_KEY`: Notion API 키 (선택)
- `SLACK_BOT_TOKEN`: Slack 토큰 (선택)

### 3. 설정 커스터마이징

`config/config.yaml`에서:
- RSS 피드 추가/수정
- 키워드 필터 설정
- AI 프롬프트 조정
- 발송 스케줄 설정

### 4. 실행

```powershell
python main.py
```

## 📊 자동화 플로우

```
RSS 피드 수집 
    ↓
Claude AI 요약
    ↓
Notion 큐레이션 (수동)
    ↓
뉴스레터 생성
    ↓
Slack 승인
    ↓
Stibee 발송
```

## 🔧 주요 기능

### ✅ 완료된 기능
- [x] RSS 피드 수집
- [x] Claude AI 요약
- [x] Stibee 발송 연동
- [x] 로깅 시스템
- [x] 설정 관리

### 🚧 진행 예정
- [ ] Notion/Airtable 연동
- [ ] Slack 승인 워크플로우
- [ ] 성과 분석 대시보드
- [ ] 스케줄링 자동화
- [ ] 개인화 기능

## 📝 개발 로드맵

- **Day 1**: ✅ 프로젝트 구조 생성
- **Day 2**: RSS + Claude 통합
- **Day 3**: Notion 연동
- **Day 4**: 뉴스레터 생성 + Stibee
- **Day 5**: Slack 승인 + 통합
- **Day 6**: 분석 + 스케줄링
- **Day 7**: 테스트 + 문서화

## 🛠 기술 스택

- **언어**: Python 3.9+
- **AI**: Claude 3.5 Sonnet
- **이메일**: Stibee API
- **데이터**: Notion/Airtable
- **알림**: Slack
- **스케줄링**: schedule/crontab

## 📖 상세 문서

각 모듈의 사용법은 해당 파일의 docstring 참조

## 🐛 문제 해결

### API 키 오류
- `.env` 파일이 `config/` 폴더에 있는지 확인
- API 키가 올바른지 확인

### RSS 수집 실패
- 인터넷 연결 확인
- RSS URL이 유효한지 확인

### Claude API 오류
- API 키가 유효한지 확인
- 요청 제한을 초과하지 않았는지 확인

## 📧 문의

DETA AI Consulting Korea
- Website: https://deta.kr
- Email: contact@deta.kr

---

**만든이**: Claude Code + DETA Team  
**버전**: 1.0.0  
**최종 수정**: 2026-02-15
