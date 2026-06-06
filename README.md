# PPROPOSAL — AI 기반 제안요청서(RFP) 분석 · 제안서 자동생성 시스템

한국 공공기관 **제안요청서(RFP)** 문서(PDF / HWPX / DOCX)를 업로드하면 Claude가
**사업개요 · 요구사항 · 배점기준 · 제안목차**를 구조화 추출하고, Excel/Markdown/JSON으로
내보냅니다. 나아가 PPTX 템플릿을 기반으로 **제안서 초안**과 **영업 견적(WBS/조직도/M·M)**까지
자동 생성하는 단일 사용자용 Flask 웹앱입니다.

> 분석 엔진은 두 가지가 공존합니다.
> - **v2 (기본·정본)** — `services_v2/`. HWPX/DOCX 네이티브 파싱 + 5단계 멀티에이전트 파이프라인.
> - **v1 (폴백)** — `services/`. PDF 전용, 단일 LLM 호출 + 규칙 기반 요구사항 파서.
>
> `/api/parse`는 기본적으로 v2를 사용하며, `?engine=v1`로 명시하면 레거시 경로를 탑니다.
> HWPX/DOCX는 v1이 지원하지 않아 항상 v2로 처리됩니다.

---

## 주요 기능

- **다포맷 입력** — PDF(PyMuPDF + OCR 폴백), HWPX(OWPML), DOCX(OOXML) 네이티브 파싱
- **멀티에이전트 분석(v2)** — 분류 → 4개 전문가(개요·요구사항·배점·목차) 병렬 → 검증(+재시도) → 견적·양식학습
- **하이브리드 요구사항 추출** — 표는 규칙 기반(결정적) 파서, 서술형/누락분은 LLM으로 보완
- **내보내기** — v1 Excel(4시트), v2 Excel(7시트)·Markdown 보고서·JSON
- **제안서 생성** — PPTX 템플릿 업로드/분석 → 목차↔템플릿 매핑 → 섹션별 콘텐츠 생성 → PPTX 출력
- **영업 견적** — 기간/인력 휴리스틱 기반 WBS·조직도·M/M 산정(LLM 미사용)
- **드래그 앤 드롭 업로드** — KRDS(대한민국 정부 디자인 시스템) 기반 UI

---

## 프로젝트 구조

```
proposal_gen2/
├── app.py                      # Flask 진입점 + 전체 HTTP 라우팅
├── config.py                   # 환경별 설정 (FLASK_ENV로 선택)
├── requirements.txt            # 런타임 의존성
├── requirements-dev.txt        # 개발/테스트 의존성(+pytest)
├── .env.example                # 환경 변수 템플릿
├── Dockerfile / docker-compose.yml
├── pytest.ini
│
├── services/                   # v1 분석 + 제안서 생성 모듈
│   ├── pdf_extractor.py        # PDF 텍스트 추출 (v2도 재사용)
│   ├── excel_exporter.py       # Excel 생성 (v2도 재사용)
│   ├── rfp_analyzer.py         # v1 단일 LLM 분석 (폴백)
│   ├── rfp_requirement_parser.py
│   ├── template_manager.py     # PPTX 템플릿 분석/저장
│   ├── font_manager.py · toc_manager.py · toc_template_mapper.py
│   ├── content_generator.py    # 섹션별 제안서 콘텐츠 생성(Claude)
│   └── pptx_filler.py          # 템플릿에 콘텐츠 채워 PPTX 출력
│
├── services_v2/                # v2 멀티에이전트 파이프라인
│   ├── orchestrator.py         # 5단계 파이프라인 조율
│   ├── documents/              # ingest: pdf / hwpx / docx → RfpDocument
│   ├── agents/                 # classifier · overview · scoring · toc · validator
│   │   └── requirements/       #   coordinator · table_parser(규칙) · narrative_parser(LLM)
│   ├── results/                # rfp_analysis(dataclass) · exporters · fingerprints · storage
│   ├── estimation/             # 견적 휴리스틱
│   └── prompts/                # 에이전트 시스템 프롬프트(.md)
│
├── static/                     # KRDS CSS + Vanilla JS 모듈
├── templates/index.html        # SPA 메인 페이지
├── scripts/                    # smoke / seed / validate 등 유틸리티
├── tests/                      # pytest 스위트 (278 케이스)
│
├── data/                       # 런타임 데이터(analyses·templates_storage·logs) — .gitignore
├── docs/                       # 작업 로그 등 문서
└── sample/ · sample_outputs/   # 샘플 RFP / 산출물 — .gitignore
```

---

## 요구사항

- **Python 3.9 ~ 3.12** (코드는 `from __future__ import annotations`로 3.9 호환, 프로덕션 컨테이너는 3.12)
- [Anthropic API 키](https://console.anthropic.com/)

## 설치

```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt           # 런타임만
pip install -r requirements-dev.txt       # 테스트까지 (pytest 포함)

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY 값을 입력하세요
```

## 환경 변수

`.env`로 설정합니다. (`.env` 로드 후 `.env.local`이 있으면 override 적용)

| 변수 | 필수 | 설명 | 기본값 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **필수** | Claude API 인증 키 | — |
| `ANTHROPIC_MODEL` | 선택 | 사용할 모델 ID | `claude-opus-4-8` |
| `FLASK_ENV` | 선택 | `development`(디버거 ON) / `production`(OFF) | `production` |
| `SECRET_KEY` | 권장 | Flask 세션 시크릿 | `dev-secret-...` |
| `PORT` | 선택 | 서버 포트 | `5000` |
| `HOST` | 선택 | `python app.py` 바인드 호스트 | `0.0.0.0` |
| `V2_AUTO_SAVE` | 선택 | v2 결과를 `data/analyses/`에 자동저장(웹 경로는 미적용) | `0` |

> LLM 호출은 최신 Opus(`claude-opus-4-8`)에 **adaptive thinking + effort=high**로 동작합니다.
> 비용을 줄이려면 `ANTHROPIC_MODEL`을 `claude-sonnet-4-6` 등으로 바꾸세요.

## 실행

### 개발 서버
```bash
python app.py            # 기본 http://localhost:5000
# 디버거/리로더가 필요하면:
FLASK_ENV=development python app.py
```

### 프로덕션 (Docker)
```bash
docker compose up --build
```
> ⚠️ 본 앱은 **단일 사용자 전제**로, 분석/세션 상태를 프로세스 전역 변수에 보관합니다.
> 따라서 gunicorn은 **워커 1 / 스레드 1**로 직렬화 실행합니다(Dockerfile에 설정됨).
> 멀티유저로 확장하려면 세션 키 기반 서버사이드 캐시로 상태를 재설계해야 합니다.

---

## 주요 API 엔드포인트

### 분석
| 메서드 · 경로 | 설명 |
|---|---|
| `POST /api/parse[?engine=v1\|v2]` | RFP 업로드 및 분석 (기본 v2, HWPX/DOCX는 항상 v2) |

**요청**: `multipart/form-data`, 필드 `file` (PDF/HWPX/DOCX, 최대 50MB)
**응답 `200`** (요약):
```jsonc
{
  "overview":  { "project_name": "...", "organization": "...", "budget": "500", "budget_unit": "백만원", ... },
  "requirements": [ { "category": "기능", "id": "FR-001", "name": "...", "desc": "...", "level": "필수" } ],
  "scoring":      [ { "category": "기술", "item": "...", "criteria": "...", "score": 20 } ],
  "toc":          [ { "level": 1, "title": "...", "children": [ ... ] } ]
}
```
**에러**: `400`(파일 없음) · `413`(50MB 초과) · `415`(미지원 확장자) · `422`(추출/분석 실패)

### 내보내기
| 메서드 · 경로 | 설명 |
|---|---|
| `GET /api/download/excel` | v1 결과 → Excel 4시트 |
| `GET /api/v2/export/excel` | v2 결과 → Excel 7시트(+검증/WBS/조직도/M·M/에이전트로그) |
| `GET /api/v2/export/markdown` | v2 결과 → Markdown 보고서 |
| `GET /api/v2/export/json` | v2 결과 → 전체 JSON |

### 제안서 생성 파이프라인
| 메서드 · 경로 | 설명 |
|---|---|
| `POST /api/templates/upload` · `GET/DELETE /api/templates[/<id>]` | PPTX 템플릿 업로드/조회/삭제 |
| `GET/PUT /api/toc/current`, `POST /api/toc/current/apply-template`, `.../finalize` | 세션 목차 편집·확정 |
| `POST /api/proposal/map` | 목차 ↔ 템플릿 슬라이드 자동 매핑 |
| `POST /api/proposal/generate` → `GET /api/proposal/content` | 섹션별 콘텐츠 생성/조회 |
| `POST /api/proposal/export` | 최종 PPTX 다운로드 |
| `GET/POST/PUT/DELETE /api/fonts/presets`, `GET/PUT /api/fonts/settings` | 폰트 프리셋/적용 설정 |

---

## 테스트

```bash
pytest                 # 전체
pytest -m unit         # 단위
pytest -m integration  # 통합
pytest -m api          # API 엔드포인트
```
> 테스트는 Anthropic API를 mock 처리하므로 키 없이/과금 없이 실행됩니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Flask 3.1 |
| AI | Anthropic Claude API (`claude-opus-4-8`, adaptive thinking) |
| 문서 처리 | PyMuPDF · pdfplumber(PDF), stdlib zipfile/ElementTree(HWPX/DOCX) |
| Excel / PPTX | openpyxl · python-pptx |
| Frontend | Vanilla JS + KRDS |
| 테스트 | pytest |

## 알려진 제약 / 로드맵

- **단일 사용자 전용** — 세션 상태가 프로세스 전역(멀티워커 비권장). 멀티유저는 재설계 필요.
- **v1은 폴백** — `?engine=v1`. v1 분석기/요구사항 파서는 v2와 일부 중복(향후 정리 후보).
- **자동저장 경로** — `V2_AUTO_SAVE`는 CLI/스크립트 경로에서만 동작(웹 라우트는 우회).

## 라이선스

내부 사용 목적으로 개발되었습니다.
