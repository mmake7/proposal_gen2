# PPROPOSAL — AI 기반 제안요청서(RFP) 분석 시스템

공공기관 제안요청서(RFP) PDF를 업로드하면 Claude AI가 자동으로 분석하여
**사업개요, 요구사항, 배점기준, 제안목차**를 구조화된 데이터로 추출합니다.

## 주요 기능

- **PDF 텍스트 추출** — PyMuPDF 기반 다중 페이지 추출, OCR 폴백 지원
- **AI 분석** — Claude API를 활용한 RFP 핵심 정보 자동 분류
- **Excel 내보내기** — 4개 시트(사업개요·요구사항·배점기준·제안목차)로 구성된 `.xlsx` 다운로드
- **드래그 앤 드롭 업로드** — KRDS(대한민국 정부 디자인 시스템) 기반 UI

## 프로젝트 구조

```
proposal_gen2/
├── app.py                      # Flask 앱 진입점 (라우트 정의)
├── config.py                   # 환경별 설정 (Dev / Prod)
├── requirements.txt            # Python 의존성
├── .env.example                # 환경 변수 템플릿
├── services/
│   ├── pdf_extractor.py        # PDF 텍스트 추출
│   ├── rfp_analyzer.py         # Claude AI 분석
│   └── excel_exporter.py       # Excel 파일 생성
├── static/
│   ├── css/                    # KRDS 스타일시트
│   └── js/                     # 프론트엔드 모듈 (upload, tabs, download 등)
├── templates/
│   └── index.html              # SPA 메인 페이지
└── tests/                      # pytest 테스트 스위트
```

## 설치 방법

### 사전 요구사항

- Python 3.9 이상
- [Anthropic API 키](https://console.anthropic.com/)

### 설치

```bash
# 저장소 클론
git clone <repository-url>
cd proposal_gen2

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY 값을 입력하세요
```

## 환경 변수 설정

`.env.example`을 `.env`로 복사한 뒤 아래 항목을 설정합니다.

| 변수명 | 필수 | 설명 | 기본값 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **필수** | Claude API 인증 키 | — |
| `SECRET_KEY` | 권장 | Flask 세션 시크릿 키 | `dev-secret-change-in-production` |
| `PORT` | 선택 | 서버 포트 | `5000` |

## 개발 서버 실행

```bash
python app.py
```

서버가 `http://localhost:5000` 에서 시작됩니다. 브라우저에서 접속하면 바로 사용할 수 있습니다.

### 프로덕션 배포

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API 엔드포인트

### `POST /api/parse` — RFP PDF 업로드 및 분석

PDF 파일을 업로드하면 AI가 분석하여 구조화된 JSON을 반환합니다.

**Request**

```
Content-Type: multipart/form-data
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `file` | File | PDF 파일 (최대 50MB) |

**Response `200 OK`**

```jsonc
{
  "overview": {
    "project_name": "사업명",
    "organization": "발주기관",
    "period": "2026.04 ~ 2026.12",
    "budget": "500",
    "budget_unit": "백만원",
    "contract_type": "제한경쟁입찰",
    "contract_method": "총액계약",
    "qualifications": "중소기업",
    "location": "서울특별시",
    "purpose": "사업 목적 설명"
  },
  "requirements": [
    {
      "category": "기능",
      "id": "FR-001",
      "name": "요구사항명",
      "desc": "상세 설명",
      "level": "필수"
    }
  ],
  "scoring": [
    {
      "category": "기술",
      "item": "평가항목명",
      "criteria": "평가기준 설명",
      "score": 20
    }
  ],
  "toc": [
    {
      "level": 1,
      "title": "장 제목",
      "children": [
        { "level": 2, "title": "절 제목", "children": [] }
      ]
    }
  ]
}
```

**에러 응답**

| 상태 코드 | 원인 |
|---|---|
| `400` | 파일 미첨부 또는 파일명 비어 있음 |
| `413` | 파일 크기 50MB 초과 |
| `415` | PDF가 아닌 파일 업로드 |
| `422` | PDF 텍스트 추출 실패 또는 AI 분석 실패 |

---

### `GET /api/download/excel` — 분석 결과 Excel 다운로드

가장 최근 분석 결과를 Excel 파일로 다운로드합니다. `/api/parse`를 먼저 호출해야 합니다.

**Response `200 OK`**

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="RFP분석_{사업명}_{timestamp}.xlsx"
```

Excel 파일은 4개 시트로 구성됩니다:

| 시트명 | 내용 |
|---|---|
| 사업개요 | 사업명, 발주기관, 기간, 예산 등 개요 정보 |
| 요구사항 | 기능/비기능 요구사항 목록 |
| 배점기준 | 평가 항목별 배점표 (합계 자동 계산) |
| 제안목차 | 제안서 목차 구조 (계층 들여쓰기) |

**에러 응답**

| 상태 코드 | 원인 |
|---|---|
| `404` | 분석 결과 없음 (PDF 업로드를 먼저 수행) |
| `500` | Excel 생성 실패 |

## 테스트

```bash
# 전체 테스트 실행
pytest

# 유닛 테스트만
pytest -m unit

# API 테스트만
pytest -m api

# 통합 테스트만
pytest -m integration
```

## 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Flask 3.1 |
| AI | Anthropic Claude API |
| PDF 처리 | PyMuPDF (fitz) |
| Excel 생성 | openpyxl |
| Frontend | Vanilla JS + KRDS |
| 테스트 | pytest |

## 라이선스

이 프로젝트는 내부 사용 목적으로 개발되었습니다.
